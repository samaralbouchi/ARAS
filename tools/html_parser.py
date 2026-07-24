"""HTML parsing layer for the Evidence Collector.

This module is responsible ONLY for parsing a raw HTML string into
structured information. It performs no HTTP requests, downloads no
external resources, performs no scoring, and makes no assumptions
about Agentic Readiness — those concerns live elsewhere (the HTTP
client and the agent/scoring layers).

The parser consumes only an HTML string and, optionally, the base URL
it was fetched from (used solely to resolve relative links).
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from models.html import HtmlParseResult

_IGNORED_LINK_SCHEMES = ("javascript:", "mailto:", "tel:")

_SEMANTIC_TAGS = (
    "header",
    "nav",
    "main",
    "article",
    "section",
    "aside",
    "footer",
)

_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")


class HtmlParser:
    """Extracts structural information from a raw HTML document.

    This class holds no network access and no knowledge of scoring or
    recommendations. It is a pure, reusable transformation from raw
    HTML text to a :class:`HtmlParseResult`.
    """

    def __init__(self, html: str, base_url: Optional[str] = None) -> None:
        """Initialize the parser with raw HTML and an optional base URL.

        Args:
            html: The raw HTML document to parse.
            base_url: The URL the HTML was fetched from, used to resolve
                relative links and to classify links as internal or
                external. If omitted, relative links are left unresolved
                and all links are treated as external.
        """
        self._html = html
        self._base_url = base_url
        self._soup = BeautifulSoup(html or "", "html.parser")

    def parse(self) -> HtmlParseResult:
        """Parse the HTML document into a structured result.

        Returns:
            A `HtmlParseResult` describing the document. Missing or
            malformed elements never raise; they are simply omitted.
        """
        internal_links, external_links = self._extract_links()
        images_total, images_with_alt = self._extract_image_alt_coverage()

        return HtmlParseResult(
            title=self._extract_title(),
            language=self._extract_language(),
            meta_tags=self._extract_meta_tags(),
            canonical=self._extract_canonical(),
            open_graph=self._extract_open_graph(),
            robots_meta=self._extract_robots_meta(),
            favicon=self._extract_favicon(),
            internal_links=internal_links,
            external_links=external_links,
            javascript_files=self._extract_javascript_files(),
            css_files=self._extract_css_files(),
            semantic_tags=self._extract_semantic_tags(),
            headings=self._extract_headings(),
            images_total=images_total,
            images_with_alt=images_with_alt,
            text_length=self._extract_text_length(),
            html_length=len(self._html or ""),
        )

    # ------------------------------------------------------------------
    # Individual extractors
    # ------------------------------------------------------------------

    def _extract_title(self) -> Optional[str]:
        """Extract the document's <title> text.

        Returns:
            The stripped title text, or None if absent.
        """
        tag = self._soup.title
        if tag is None or tag.string is None:
            return None
        text = tag.string.strip()
        return text or None

    def _extract_language(self) -> Optional[str]:
        """Extract the `lang` attribute from the <html> tag.

        Returns:
            The language code, or None if absent.
        """
        html_tag = self._soup.find("html")
        if not isinstance(html_tag, Tag):
            return None
        lang = html_tag.get("lang")
        if not isinstance(lang, str) or not lang.strip():
            return None
        return lang.strip()

    def _extract_meta_tags(self) -> dict[str, str]:
        """Extract every `<meta name="...">` tag into a name/content mapping.

        Returns:
            A dict mapping meta tag name to its content. Tags without a
            `name` or `content` attribute are skipped.
        """
        meta_tags: dict[str, str] = {}
        for tag in self._soup.find_all("meta"):
            if not isinstance(tag, Tag):
                continue
            name = tag.get("name")
            content = tag.get("content")
            if isinstance(name, str) and name.strip() and isinstance(content, str):
                meta_tags[name.strip().lower()] = content
        return meta_tags

    def _extract_open_graph(self) -> dict[str, str]:
        """Extract every `<meta property="og:*">` tag into a mapping.

        Returns:
            A dict mapping the full `og:*` property name to its content.
        """
        open_graph: dict[str, str] = {}
        for tag in self._soup.find_all("meta"):
            if not isinstance(tag, Tag):
                continue
            prop = tag.get("property")
            content = tag.get("content")
            if (
                isinstance(prop, str)
                and prop.strip().lower().startswith("og:")
                and isinstance(content, str)
            ):
                open_graph[prop.strip().lower()] = content
        return open_graph

    def _extract_robots_meta(self) -> dict[str, object]:
        """Extract and parse `<meta name="robots">` into individual directives.

        Comma-separated directives such as "noindex, nofollow" become
        boolean flags; directives with a value such as "max-snippet:-1"
        keep their value as a string.

        Returns:
            A dict of directive name to True or its associated value.
            Empty if no robots meta tag is present.
        """
        robots_meta: dict[str, object] = {}
        for tag in self._soup.find_all("meta", attrs={"name": "robots"}):
            if not isinstance(tag, Tag):
                continue
            content = tag.get("content")
            if not isinstance(content, str):
                continue
            for directive in content.split(","):
                directive = directive.strip()
                if not directive:
                    continue
                if ":" in directive:
                    key, _, value = directive.partition(":")
                    robots_meta[key.strip().lower()] = value.strip()
                else:
                    robots_meta[directive.lower()] = True
        return robots_meta

    def _extract_canonical(self) -> Optional[str]:
        """Extract the resolved canonical URL, if declared.

        Returns:
            The absolute canonical URL, or None if absent.
        """
        tag = self._soup.find("link", attrs={"rel": "canonical"})
        if not isinstance(tag, Tag):
            return None
        href = tag.get("href")
        if not isinstance(href, str) or not href.strip():
            return None
        return self._resolve_url(href.strip())

    def _extract_favicon(self) -> Optional[str]:
        """Extract the resolved favicon URL, if declared.

        Supports both `rel="icon"` and `rel="shortcut icon"`.

        Returns:
            The absolute favicon URL, or None if absent.
        """
        for tag in self._soup.find_all("link"):
            if not isinstance(tag, Tag):
                continue
            rel_values = tag.get("rel")
            rel = " ".join(rel_values).lower() if isinstance(rel_values, list) else str(rel_values or "").lower()
            if rel in ("icon", "shortcut icon"):
                href = tag.get("href")
                if isinstance(href, str) and href.strip():
                    return self._resolve_url(href.strip())
        return None

    def _extract_css_files(self) -> list[str]:
        """Extract absolute URLs of `<link rel="stylesheet">` resources.

        Returns:
            A deduplicated list of absolute stylesheet URLs.
        """
        css_files: list[str] = []
        seen: set[str] = set()
        for tag in self._soup.find_all("link"):
            if not isinstance(tag, Tag):
                continue
            rel_values = tag.get("rel")
            rel = " ".join(rel_values).lower() if isinstance(rel_values, list) else str(rel_values or "").lower()
            if rel != "stylesheet":
                continue
            href = tag.get("href")
            if not isinstance(href, str) or not href.strip():
                continue
            resolved = self._resolve_url(href.strip())
            if resolved not in seen:
                seen.add(resolved)
                css_files.append(resolved)
        return css_files

    def _extract_javascript_files(self) -> list[str]:
        """Extract absolute URLs of `<script src="...">` resources.

        Returns:
            A deduplicated list of absolute JavaScript file URLs.
        """
        js_files: list[str] = []
        seen: set[str] = set()
        for tag in self._soup.find_all("script"):
            if not isinstance(tag, Tag):
                continue
            src = tag.get("src")
            if not isinstance(src, str) or not src.strip():
                continue
            resolved = self._resolve_url(src.strip())
            if resolved not in seen:
                seen.add(resolved)
                js_files.append(resolved)
        return js_files

    def _extract_semantic_tags(self) -> dict[str, int]:
        """Count occurrences of each HTML5 semantic element.

        Considers `<header>`, `<nav>`, `<main>`, `<article>`,
        `<section>`, `<aside>`, and `<footer>`.

        Returns:
            A dict mapping tag name to occurrence count. Tags that do
            not appear at all are omitted rather than recorded as 0.
        """
        counts: dict[str, int] = {}
        for tag_name in _SEMANTIC_TAGS:
            found = self._soup.find_all(tag_name)
            if found:
                counts[tag_name] = len(found)
        return counts

    def _extract_headings(self) -> dict[str, int]:
        """Count occurrences of each heading level (`<h1>`-`<h6>`).

        Returns:
            A dict mapping heading tag name to occurrence count.
            Levels that do not appear at all are omitted rather than
            recorded as 0.
        """
        counts: dict[str, int] = {}
        for tag_name in _HEADING_TAGS:
            found = self._soup.find_all(tag_name)
            if found:
                counts[tag_name] = len(found)
        return counts

    def _extract_image_alt_coverage(self) -> tuple[int, int]:
        """Count total `<img>` elements and how many carry a non-empty `alt`.

        Returns:
            A tuple of `(images_total, images_with_alt)`.
        """
        images = self._soup.find_all("img")
        images_total = len(images)
        images_with_alt = 0
        for tag in images:
            if not isinstance(tag, Tag):
                continue
            alt = tag.get("alt")
            if isinstance(alt, str) and alt.strip():
                images_with_alt += 1
        return images_total, images_with_alt

    def _extract_text_length(self) -> int:
        """Measure the length of the page's visible text content.

        Script and style contents are excluded since they are not
        visible text, even though they live inside the document body.
        Does not mutate the shared `soup` tree, so it is safe to call
        regardless of extraction order.

        Returns:
            The character count of the extracted, whitespace-collapsed
            text content.
        """
        _EXCLUDED_PARENTS = ("script", "style")
        fragments = [
            str(node).strip()
            for node in self._soup.find_all(string=True)
            if node.parent is not None
            and node.parent.name not in _EXCLUDED_PARENTS
            and str(node).strip()
        ]
        return len(" ".join(fragments))

    def _extract_links(self) -> tuple[list[str], list[str]]:
        """Extract and classify every `<a href="...">` link on the page.

        Ignores empty links, `javascript:`, `mailto:`, `tel:` links, and
        bare in-page fragments (`#...`).

        Returns:
            A tuple of `(internal_links, external_links)`, each a
            deduplicated list of absolute URLs.
        """
        internal_links: list[str] = []
        external_links: list[str] = []
        seen: set[str] = set()

        base_host = urlparse(self._base_url).netloc.lower() if self._base_url else ""

        for tag in self._soup.find_all("a"):
            if not isinstance(tag, Tag):
                continue
            href = tag.get("href")
            if not isinstance(href, str):
                continue
            href = href.strip()
            if self._should_ignore_link(href):
                continue

            resolved = self._resolve_url(href)
            if resolved in seen:
                continue
            seen.add(resolved)

            link_host = urlparse(resolved).netloc.lower()
            if base_host and link_host == base_host:
                internal_links.append(resolved)
            else:
                external_links.append(resolved)

        return internal_links, external_links

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _should_ignore_link(href: str) -> bool:
        """Determine whether a raw href value should be skipped.

        Args:
            href: The raw, stripped `href` attribute value.

        Returns:
            True if the link is empty, a fragment-only link, or uses an
            ignored scheme (`javascript:`, `mailto:`, `tel:`).
        """
        if not href or href.startswith("#"):
            return True
        return href.lower().startswith(_IGNORED_LINK_SCHEMES)

    def _resolve_url(self, url: str) -> str:
        """Resolve a possibly relative URL against the base URL.

        Args:
            url: The raw URL found in the document.

        Returns:
            The absolute URL if a base URL was provided, otherwise the
            original URL unchanged.
        """
        if self._base_url:
            return urljoin(self._base_url, url)
        return url
