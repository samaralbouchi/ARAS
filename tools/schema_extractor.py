"""Structured data extraction layer for the Evidence Collector.

This module is responsible ONLY for extracting structured data
(JSON-LD, Microdata, RDFa) from a raw HTML string. It performs no HTTP
requests, no crawling, no quality analysis, no scoring, and makes no
assumptions about Agentic Readiness — those concerns live elsewhere.

The extractor consumes only an HTML string.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from bs4 import BeautifulSoup
from bs4.element import Tag

from models.schema import StructuredDataResult

_URL_ATTR_TAGS = {
    "a": "href",
    "area": "href",
    "link": "href",
    "img": "src",
    "audio": "src",
    "embed": "src",
    "iframe": "src",
    "source": "src",
    "track": "src",
    "video": "src",
    "object": "data",
}


class SchemaExtractor:
    """Extracts structured data (JSON-LD, Microdata, RDFa) from raw HTML.

    This class holds no network access and no knowledge of scoring or
    recommendations. It is a pure, reusable transformation from raw
    HTML text to a :class:`StructuredDataResult`.
    """

    def __init__(self, html: str) -> None:
        """Initialize the extractor with a raw HTML document.

        Args:
            html: The raw HTML document to extract structured data from.
        """
        self._html = html
        self._soup = BeautifulSoup(html or "", "html.parser")

    def extract(self) -> StructuredDataResult:
        """Extract all supported structured data formats from the document.

        Returns:
            A `StructuredDataResult` describing every JSON-LD, Microdata,
            and RDFa object found. Missing or malformed data never
            raises; it is simply omitted.
        """
        return StructuredDataResult(
            json_ld=self._extract_json_ld(),
            microdata=self._extract_microdata(),
            rdfa=self._extract_rdfa(),
        )

    # ------------------------------------------------------------------
    # JSON-LD
    # ------------------------------------------------------------------

    def _extract_json_ld(self) -> list[dict[str, Any]]:
        """Extract objects from `<script type="application/ld+json">` tags.

        Both single JSON objects and JSON arrays of objects are
        supported; arrays are flattened into individual dictionaries.
        Invalid JSON is silently skipped.

        Returns:
            A list of extracted JSON-LD objects.
        """
        objects: list[dict[str, Any]] = []
        for tag in self._soup.find_all("script", attrs={"type": "application/ld+json"}):
            if not isinstance(tag, Tag):
                continue
            raw_text = tag.get_text(strip=True)
            if not raw_text:
                continue
            try:
                parsed = json.loads(raw_text)
            except (json.JSONDecodeError, ValueError):
                continue
            objects.extend(self._flatten_json_ld(parsed))
        return objects

    @staticmethod
    def _flatten_json_ld(parsed: Any) -> list[dict[str, Any]]:
        """Flatten a parsed JSON-LD payload into a list of dict objects.

        Args:
            parsed: The result of `json.loads` on a JSON-LD script body.

        Returns:
            A list of dict objects; non-dict entries are ignored.
        """
        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        return []

    # ------------------------------------------------------------------
    # Microdata
    # ------------------------------------------------------------------

    def _extract_microdata(self) -> list[dict[str, Any]]:
        """Extract top-level items defined via microdata attributes.

        Detects `itemscope`/`itemtype`/`itemprop` attributes. Items
        nested inside another item's scope are represented as the value
        of the parent item's property rather than as separate top-level
        entries.

        Returns:
            A list of extracted microdata items.
        """
        items: list[dict[str, Any]] = []
        for tag in self._soup.find_all(attrs={"itemscope": True}):
            if not isinstance(tag, Tag) or self._has_ancestor_with_attr(tag, "itemscope"):
                continue
            items.append(self._parse_microdata_item(tag))
        return items

    def _parse_microdata_item(self, scope_tag: Tag) -> dict[str, Any]:
        """Parse a single microdata item rooted at an `itemscope` element.

        Args:
            scope_tag: The element carrying the `itemscope` attribute.

        Returns:
            A dict with a `type` key (if `itemtype` is present) and a
            `properties` key mapping property names to their values.
        """
        item: dict[str, Any] = {}
        itemtype = scope_tag.get("itemtype")
        if isinstance(itemtype, str) and itemtype.strip():
            item["type"] = itemtype.strip()

        properties: dict[str, Any] = {}
        for prop_tag in self._scoped_descendants(scope_tag, "itemprop", "itemscope"):
            value: Any
            if prop_tag.has_attr("itemscope"):
                value = self._parse_microdata_item(prop_tag)
            else:
                value = self._extract_microdata_value(prop_tag)
            for prop_name in str(prop_tag.get("itemprop", "")).split():
                self._add_property(properties, prop_name, value)

        item["properties"] = properties
        return item

    @staticmethod
    def _extract_microdata_value(tag: Tag) -> str:
        """Extract the plain-text or attribute value of a microdata property.

        Args:
            tag: The element carrying the `itemprop` attribute.

        Returns:
            The value as defined by the microdata specification: the
            `content` attribute for `<meta>`, a URL attribute for
            link/media elements, the `datetime` attribute for `<time>`,
            or the element's text content otherwise.
        """
        name = tag.name.lower()
        if name == "meta":
            return str(tag.get("content", ""))
        if name == "time" and tag.has_attr("datetime"):
            return str(tag.get("datetime", ""))
        if name in _URL_ATTR_TAGS:
            return str(tag.get(_URL_ATTR_TAGS[name], ""))
        return tag.get_text(strip=True)

    # ------------------------------------------------------------------
    # RDFa
    # ------------------------------------------------------------------

    def _extract_rdfa(self) -> list[dict[str, Any]]:
        """Extract top-level items defined via RDFa attributes.

        Detects `vocab`/`typeof`/`property` attributes. Items nested
        inside another item's scope are represented as the value of the
        parent item's property rather than as separate top-level entries.

        Returns:
            A list of extracted RDFa items.
        """
        items: list[dict[str, Any]] = []
        for tag in self._soup.find_all(attrs={"typeof": True}):
            if not isinstance(tag, Tag) or self._has_ancestor_with_attr(tag, "typeof"):
                continue
            items.append(self._parse_rdfa_item(tag))
        return items

    def _parse_rdfa_item(self, scope_tag: Tag) -> dict[str, Any]:
        """Parse a single RDFa item rooted at a `typeof` element.

        Args:
            scope_tag: The element carrying the `typeof` attribute.

        Returns:
            A dict with a `type` key and a `properties` key mapping
            property names to their values.
        """
        item: dict[str, Any] = {}
        typeof = scope_tag.get("typeof")
        if isinstance(typeof, str) and typeof.strip():
            item["type"] = typeof.strip()

        properties: dict[str, Any] = {}
        for prop_tag in self._scoped_descendants(scope_tag, "property", "typeof"):
            value: Any
            if prop_tag.has_attr("typeof"):
                value = self._parse_rdfa_item(prop_tag)
            else:
                value = self._extract_rdfa_value(prop_tag)
            for prop_name in str(prop_tag.get("property", "")).split():
                self._add_property(properties, prop_name, value)

        item["properties"] = properties
        return item

    @staticmethod
    def _extract_rdfa_value(tag: Tag) -> str:
        """Extract the value of an RDFa property element.

        Args:
            tag: The element carrying the `property` attribute.

        Returns:
            The `content` attribute if present, otherwise a URL
            attribute for link/media elements, otherwise the element's
            text content.
        """
        content = tag.get("content")
        if isinstance(content, str):
            return content
        name = tag.name.lower()
        if name in _URL_ATTR_TAGS:
            return str(tag.get(_URL_ATTR_TAGS[name], ""))
        return tag.get_text(strip=True)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_ancestor_with_attr(tag: Tag, attr: str) -> bool:
        """Determine whether any ancestor of `tag` carries the given attribute.

        Args:
            tag: The element to check ancestors of.
            attr: The HTML attribute name to look for.

        Returns:
            True if an ancestor element carries `attr`.
        """
        for parent in tag.parents:
            if isinstance(parent, Tag) and parent.has_attr(attr):
                return True
        return False

    @classmethod
    def _scoped_descendants(
        cls, scope_tag: Tag, prop_attr: str, scope_attr: str
    ) -> list[Tag]:
        """Find descendants carrying `prop_attr` that belong to this scope.

        A descendant belongs to `scope_tag`'s scope if the nearest
        ancestor carrying `scope_attr` (searching upward, `scope_tag`
        itself included) is `scope_tag` itself — descendants owned by a
        nested scope element are excluded so they can be attached as
        that nested item's own properties instead.

        Args:
            scope_tag: The element defining the current item's scope.
            prop_attr: The attribute name identifying a property element
                (e.g. `itemprop` or `property`).
            scope_attr: The attribute name identifying a nested scope
                boundary (e.g. `itemscope` or `typeof`).

        Returns:
            A list of property elements belonging directly to this scope.
        """
        results: list[Tag] = []
        for candidate in scope_tag.find_all(attrs={prop_attr: True}):
            if not isinstance(candidate, Tag):
                continue
            owner = cls._nearest_scope_owner(candidate, scope_tag, scope_attr)
            if owner is scope_tag:
                results.append(candidate)
        return results

    @staticmethod
    def _nearest_scope_owner(
        tag: Tag, root: Tag, scope_attr: str
    ) -> Optional[Tag]:
        """Find the nearest ancestor (or self) that owns `tag`'s scope.

        Args:
            tag: The element to find the owning scope for.
            root: The root scope element to stop the search at.
            scope_attr: The attribute name identifying a scope boundary.

        Returns:
            `root` if no closer scope boundary exists between `tag` and
            `root`; otherwise the closer scope-owning ancestor.
        """
        for parent in tag.parents:
            if parent is root:
                return root
            if isinstance(parent, Tag) and parent.has_attr(scope_attr):
                return parent
        return None

    @staticmethod
    def _add_property(properties: dict[str, Any], name: str, value: Any) -> None:
        """Add a property value, collapsing repeats into a list.

        Args:
            properties: The properties dict being built.
            name: The property name.
            value: The value to associate with `name`.
        """
        if not name:
            return
        if name not in properties:
            properties[name] = value
            return
        existing = properties[name]
        if isinstance(existing, list):
            existing.append(value)
        else:
            properties[name] = [existing, value]
