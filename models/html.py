
"""
Data contract for the HTML Parser.

This module defines the single output type produced by the HTML
Parser: a flat, JSON-serializable snapshot of structural and semantic
information extracted from a raw HTML document.

No scoring, grading, or interpretation logic belongs here.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class HtmlParseResult:
    """
    Structured information extracted from a single HTML document.

    This object contains only observed HTML facts.
    No readiness score or recommendation logic is allowed here.
    """

    # -----------------------------
    # Basic document metadata
    # -----------------------------

    title: Optional[str] = None

    meta_description: Optional[str] = None

    language: Optional[str] = None

    meta_tags: dict[str, str] = field(default_factory=dict)

    canonical: Optional[str] = None

    robots_meta: dict[str, Any] = field(default_factory=dict)


    # -----------------------------
    # Social semantic metadata
    # -----------------------------

    open_graph: dict[str, str] = field(default_factory=dict)

    twitter_cards: dict[str, str] = field(default_factory=dict)


    # -----------------------------
    # Structured semantic data
    # -----------------------------

    structured_data: dict[str, list[Any]] = field(
        default_factory=dict
    )

    schema_org_types: list[str] = field(
        default_factory=list
    )

    json_ld_entities: list[dict[str, Any]] = field(
        default_factory=list
    )


    # -----------------------------
    # Accessibility semantics
    # -----------------------------

    aria_attributes: dict[str, int] = field(
        default_factory=dict
    )

    labels_count: int = 0

    forms_count: int = 0


    # -----------------------------
    # Resources
    # -----------------------------

    favicon: Optional[str] = None

    internal_links: list[str] = field(
        default_factory=list
    )

    external_links: list[str] = field(
        default_factory=list
    )

    javascript_files: list[str] = field(
        default_factory=list
    )

    css_files: list[str] = field(
        default_factory=list
    )


    # -----------------------------
    # HTML semantic structure
    # -----------------------------

    semantic_tags: dict[str, int] = field(
        default_factory=dict
    )

    headings: dict[str, int] = field(
        default_factory=dict
    )


    # -----------------------------
    # Content accessibility
    # -----------------------------

    images_total: int = 0

    images_with_alt: int = 0


    # -----------------------------
    # Content size indicators
    # -----------------------------

    text_length: int = 0

    html_length: int = 0


    def to_dict(self) -> dict[str, Any]:
        """
        Convert this parse result into a JSON serializable dictionary.
        """
        return asdict(self)