
"""
HTML parsing layer for the Evidence Collector.

This module converts raw HTML into structured evidence.
It performs no scoring and no recommendation logic.
"""

from __future__ import annotations

import json
from typing import Optional, Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from models.html import HtmlParseResult


_IGNORED_LINK_SCHEMES = (
    "javascript:",
    "mailto:",
    "tel:",
)


_SEMANTIC_TAGS = (
    "header",
    "nav",
    "main",
    "article",
    "section",
    "aside",
    "footer",
)


_HEADING_TAGS = (
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
)


class HtmlParser:

    def __init__(
        self,
        html: str,
        base_url: Optional[str] = None
    ) -> None:

        self._html = html
        self._base_url = base_url
        self._soup = BeautifulSoup(
            html or "",
            "html.parser"
        )


    def parse(self) -> HtmlParseResult:

        internal_links, external_links = self._extract_links()

        images_total, images_with_alt = (
            self._extract_image_alt_coverage()
        )

        return HtmlParseResult(

            # Metadata
            title=self._extract_title(),

            meta_description=self._extract_meta_description(),

            language=self._extract_language(),

            meta_tags=self._extract_meta_tags(),

            canonical=self._extract_canonical(),

            robots_meta=self._extract_robots_meta(),


            # Social metadata
            open_graph=self._extract_open_graph(),

            twitter_cards=self._extract_twitter_cards(),


            # Structured data
            structured_data=self._extract_structured_data(),

            schema_org_types=self._extract_schema_types(),

            json_ld_entities=self._extract_json_ld_entities(),


            # Accessibility
            aria_attributes=self._extract_aria_attributes(),

            labels_count=self._extract_labels_count(),

            forms_count=len(
                self._soup.find_all("form")
            ),


            # Resources
            favicon=self._extract_favicon(),

            internal_links=internal_links,

            external_links=external_links,

            javascript_files=self._extract_javascript_files(),

            css_files=self._extract_css_files(),


            # Structure
            semantic_tags=self._extract_semantic_tags(),

            headings=self._extract_headings(),


            # Images
            images_total=images_total,

            images_with_alt=images_with_alt,


            # Content
            text_length=self._extract_text_length(),

            html_length=len(
                self._html or ""
            )
        )


    # ============================================================
    # METADATA
    # ============================================================


    def _extract_title(self):

        tag = self._soup.title

        if not tag:
            return None

        return tag.get_text(strip=True) or None



    def _extract_meta_description(self):

        tag = self._soup.find(
            "meta",
            attrs={
                "name": "description"
            }
        )

        if not isinstance(tag, Tag):
            return None

        content = tag.get("content")

        return (
            content.strip()
            if isinstance(content, str)
            else None
        )



    def _extract_meta_tags(self):

        result = {}

        for tag in self._soup.find_all("meta"):

            name = tag.get("name")
            content = tag.get("content")

            if (
                isinstance(name, str)
                and isinstance(content, str)
            ):
                result[name.lower()] = content

        return result



    def _extract_language(self):

        html = self._soup.find("html")

        if isinstance(html, Tag):

            lang = html.get("lang")

            if isinstance(lang, str):
                return lang.strip()

        return None



    def _extract_canonical(self):

        tag = self._soup.find(
            "link",
            rel="canonical"
        )

        if not isinstance(tag, Tag):
            return None

        href = tag.get("href")

        if isinstance(href, str):

            return self._resolve_url(
                href
            )

        return None



    def _extract_robots_meta(self):

        result = {}

        tag = self._soup.find(
            "meta",
            attrs={
                "name": "robots"
            }
        )

        if not isinstance(tag, Tag):
            return result


        content = tag.get("content")

        if not isinstance(content, str):
            return result


        for item in content.split(","):

            item = item.strip()

            if ":" in item:

                key, value = item.split(
                    ":",
                    1
                )

                result[key] = value

            else:

                result[item] = True


        return result



    # ============================================================
    # SOCIAL
    # ============================================================


    def _extract_open_graph(self):

        result = {}

        for tag in self._soup.find_all("meta"):

            prop = tag.get("property")
            content = tag.get("content")

            if (
                isinstance(prop, str)
                and prop.startswith("og:")
                and isinstance(content, str)
            ):

                result[prop] = content


        return result



    def _extract_twitter_cards(self):

        result = {}

        for tag in self._soup.find_all("meta"):

            name = tag.get("name")
            content = tag.get("content")


            if (
                isinstance(name, str)
                and name.startswith("twitter:")
                and isinstance(content, str)
            ):

                result[name] = content


        return result



    # ============================================================
    # STRUCTURED DATA
    # ============================================================


    def _extract_structured_data(self):

        result = {
            "json-ld": []
        }


        for script in self._soup.find_all(
            "script",
            type="application/ld+json"
        ):

            try:

                data = json.loads(
                    script.string
                )

                result["json-ld"].append(
                    data
                )

            except Exception:

                continue


        return result



    def _extract_json_ld_entities(self):

        entities = []


        for item in self._extract_structured_data().get(
            "json-ld",
            []
        ):

            if isinstance(item, dict):

                entities.append(item)


        return entities



    def _extract_schema_types(self):

        types = []


        for entity in self._extract_json_ld_entities():

            value = entity.get("@type")


            if isinstance(value, str):

                types.append(value)


            elif isinstance(value, list):

                types.extend(value)


        return list(set(types))



    # ============================================================
    # ACCESSIBILITY
    # ============================================================


    def _extract_aria_attributes(self):

        result = {}


        for tag in self._soup.find_all(True):

            for attr in tag.attrs:

                if attr.startswith("aria-"):

                    result[attr] = (
                        result.get(attr, 0)
                        + 1
                    )


        return result



    def _extract_labels_count(self):

        return len(
            self._soup.find_all("label")
        )



    # ============================================================
    # EXISTING METHODS
    # ============================================================


    def _extract_semantic_tags(self):

        return {
            tag: len(
                self._soup.find_all(tag)
            )
            for tag in _SEMANTIC_TAGS
            if self._soup.find_all(tag)
        }



    def _extract_headings(self):

        return {
            tag: len(
                self._soup.find_all(tag)
            )
            for tag in _HEADING_TAGS
            if self._soup.find_all(tag)
        }



    def _extract_image_alt_coverage(self):

        images = self._soup.find_all("img")

        with_alt = 0

        for img in images:

            alt = img.get("alt")

            if isinstance(alt, str) and alt.strip():

                with_alt += 1


        return len(images), with_alt



    def _extract_text_length(self):

        text = self._soup.get_text(
            " ",
            strip=True
        )

        return len(text)



    def _extract_favicon(self):

        tag = self._soup.find(
            "link",
            rel=lambda x:
            x and "icon" in x
        )

        if isinstance(tag, Tag):

            href = tag.get("href")

            if isinstance(href, str):
                return self._resolve_url(href)


        return None



    def _extract_links(self):

        internal = []
        external = []

        host = (
            urlparse(self._base_url).netloc
            if self._base_url
            else ""
        )


        for a in self._soup.find_all("a"):

            href = a.get("href")


            if not isinstance(href, str):
                continue


            if href.startswith(
                _IGNORED_LINK_SCHEMES
            ):
                continue


            url = self._resolve_url(href)

            if urlparse(url).netloc == host:

                internal.append(url)

            else:

                external.append(url)


        return list(set(internal)), list(set(external))



    def _extract_javascript_files(self):

        return [
            self._resolve_url(
                s["src"]
            )
            for s in self._soup.find_all(
                "script",
                src=True
            )
        ]



    def _extract_css_files(self):

        return [
            self._resolve_url(
                l["href"]
            )
            for l in self._soup.find_all(
                "link",
                rel="stylesheet",
                href=True
            )
        ]



    def _resolve_url(self, url):

        if self._base_url:

            return urljoin(
                self._base_url,
                url
            )

        return url