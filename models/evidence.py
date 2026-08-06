"""
Data contract for the Evidence Collector Agent.

This module defines the single output type produced by the Evidence
Collector: a flat, JSON-serializable snapshot of raw artifacts gathered
from a website.

No scoring, grading, or interpretation logic belongs here.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class CollectionError:

    step: str
    message: str



@dataclass
class WebsiteEvidence:
    """
    Raw evidence collected from a website.

    This object contains only observed facts.
    Analysis and scoring are performed by agents.
    """


    # -------------------------
    # Website identity
    # -------------------------

    url: str


    html: Optional[str] = None

    headers: dict[str, Any] = field(
        default_factory=dict
    )


    # -------------------------
    # Discovery artifacts
    # -------------------------

    robots_txt: Optional[str] = None

    sitemap_xml: Optional[str] = None

    llms_txt: Optional[str] = None



    # -------------------------
    # Metadata
    # -------------------------

    title: Optional[str] = None

    meta_description: Optional[str] = None

    meta_tags: dict[str, str] = field(
        default_factory=dict
    )

    canonical: Optional[str] = None

    robots_meta: dict[str, Any] = field(
        default_factory=dict
    )


    # -------------------------
    # Social semantics
    # -------------------------

    open_graph: dict[str, str] = field(
        default_factory=dict
    )

    twitter_cards: dict[str, str] = field(
        default_factory=dict
    )


    # -------------------------
    # Structured semantics
    # -------------------------

    structured_data: dict[str, list[Any]] = field(
        default_factory=dict
    )

    schema_org_types: list[str] = field(
        default_factory=list
    )

    json_ld_entities: list[dict[str, Any]] = field(
        default_factory=list
    )


    # -------------------------
    # Accessibility
    # -------------------------

    aria_attributes: dict[str, int] = field(
        default_factory=dict
    )

    labels_count: int = 0

    forms_count: int = 0



    # -------------------------
    # Links/resources
    # -------------------------

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


    favicon: Optional[str] = None



    # -------------------------
    # HTML structure
    # -------------------------

    semantic_tags: dict[str, int] = field(
        default_factory=dict
    )

    headings: dict[str, int] = field(
        default_factory=dict
    )


    # -------------------------
    # Images/content
    # -------------------------

    images_total: int = 0

    images_with_alt: int = 0

    text_length: int = 0

    html_length: int = 0



    # -------------------------
    # API / frontend evidence
    # -------------------------

    api_candidates: dict[str, int] = field(
        default_factory=dict
    )

    api_analysis: dict[str, Any] = field(
        default_factory=dict
    )

    frontend_analysis: dict[str, Any] = field(
        default_factory=dict
    )


    # -------------------------
    # HTTP information
    # -------------------------

    status_code: Optional[int] = None

    response_time: Optional[float] = None



    # -------------------------
    # Protection
    # -------------------------

    blocked: bool = False

    blocked_reason: Optional[str] = None

    blocked_provider: Optional[str] = None



    # -------------------------
    # Metadata
    # -------------------------

    collected_at: str = field(
        default_factory=lambda:
        datetime.now(
            timezone.utc
        ).isoformat()
    )


    errors: list[CollectionError] = field(
        default_factory=list
    )



    def add_error(
        self,
        step: str,
        message: str
    ) -> None:

        self.errors.append(
            CollectionError(
                step=step,
                message=message
            )
        )


    @property
    def json_ld_items(self):

        return self.structured_data.get(
            "json-ld",
            []
        )


    @property
    def microdata_items(self):

        return self.structured_data.get(
            "microdata",
            []
        )


    @property
    def rdfa_items(self):

        return self.structured_data.get(
            "rdfa",
            []
        )


    def to_dict(self) -> dict[str, Any]:

        return asdict(self)



    def to_json(
        self,
        indent: int = 2
    ) -> str:

        import json

        return json.dumps(
            self.to_dict(),
            indent=indent,
            default=str
        )