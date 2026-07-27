"""Data contract for the Evidence Collector Agent.

This module defines the single output type produced by the Evidence
Collector: a flat, JSON-serializable snapshot of raw artifacts gathered
from a website. No scoring, grading, or interpretation logic belongs
here — this is a data container only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class CollectionError:
    """Represents a single non-fatal failure encountered while collecting evidence.

    Attributes:
        step: Name of the collection step that failed (e.g. "sitemap_xml").
        message: Human-readable description of the failure.
    """

    step: str
    message: str


@dataclass
class WebsiteEvidence:
    """Raw evidence collected from a single website.

    This dataclass is the sole output of the Evidence Collector Agent.
    It never contains derived scores, judgments, or recommendations —
    only facts observed during collection. Any field that could not be
    collected is left at its default (None, empty dict/list) rather
    than causing the whole collection to fail.

    Attributes:
        url: The original URL requested for evidence collection.
        html: Raw homepage HTML source, if fetched successfully.
        headers: HTTP response headers from the homepage request.
        robots_txt: Raw contents of /robots.txt, if present.
        sitemap_xml: Raw contents of /sitemap.xml, if present.
        llms_txt: Raw contents of /llms.txt, if present.
        title: The homepage <title> text.
        meta_tags: Mapping of meta tag name/property to content.
        canonical: The resolved canonical URL, if declared.
        open_graph: Mapping of OpenGraph property to content.
        robots_meta: Parsed content of <meta name="robots">.
        structured_data: Structured data grouped by format
            (e.g. {"json-ld": [...], "microdata": [...], "rdfa": [...]}).
        internal_links: Absolute URLs linking to the same domain.
        external_links: Absolute URLs linking to other domains.
        api_candidates: Candidate API/spec endpoints discovered, with
            their observed status codes.
        api_analysis: Full `ApiDiscoveryResult` snapshot (OpenAPI,
            Swagger, ReDoc, documentation, REST/GraphQL endpoints, and
            MCP evidence) as a plain dict.
        frontend_analysis: Full `FrontendAnalysisResult` snapshot
            (API references discovered via static analysis of frontend
            JavaScript) as a plain dict.
        javascript_files: Absolute URLs of <script src="..."> resources.
        css_files: Absolute URLs of <link rel="stylesheet"> resources.
        language: Value of the <html lang="..."> attribute.
        favicon: Absolute URL of the resolved favicon.
        semantic_tags: Count of each HTML5 semantic element found on
            the homepage (e.g. {"main": 1, "nav": 1}).
        headings: Count of each heading level found on the homepage
            (e.g. {"h1": 1, "h2": 4}).
        images_total: Total number of <img> elements on the homepage.
        images_with_alt: Number of <img> elements carrying a non-empty
            alt attribute.
        text_length: Length, in characters, of the homepage's visible
            text content.
        html_length: Length, in characters, of the raw homepage HTML.
        status_code: HTTP status code of the homepage request.
        response_time: Homepage request duration, in seconds.
        blocked: Whether the homepage response looked like a known
            bot/WAF block or challenge page rather than genuine site
            content (see `tools.bot_block_detector.BotBlockDetector`).
        blocked_reason: Short, human-readable explanation of the block
            verdict, if `blocked` is True.
        blocked_provider: Best-guess identity of the blocking system,
            one of `"akamai"`, `"cloudflare"`, `"generic"`, or `None`
            if `blocked` is False.
        collected_at: UTC timestamp when collection was performed.
        errors: List of non-fatal errors encountered during collection.
    """

    url: str
    html: Optional[str] = None
    headers: dict[str, Any] = field(default_factory=dict)
    robots_txt: Optional[str] = None
    sitemap_xml: Optional[str] = None
    llms_txt: Optional[str] = None
    title: Optional[str] = None
    meta_tags: dict[str, str] = field(default_factory=dict)
    canonical: Optional[str] = None
    open_graph: dict[str, str] = field(default_factory=dict)
    robots_meta: dict[str, Any] = field(default_factory=dict)
    structured_data: dict[str, list[Any]] = field(default_factory=dict)
    internal_links: list[str] = field(default_factory=list)
    external_links: list[str] = field(default_factory=list)
    api_candidates: dict[str, int] = field(default_factory=dict)
    api_analysis: dict[str, Any] = field(default_factory=dict)
    frontend_analysis: dict[str, Any] = field(default_factory=dict)
    javascript_files: list[str] = field(default_factory=list)
    css_files: list[str] = field(default_factory=list)
    language: Optional[str] = None
    favicon: Optional[str] = None
    semantic_tags: dict[str, int] = field(default_factory=dict)
    headings: dict[str, int] = field(default_factory=dict)
    images_total: int = 0
    images_with_alt: int = 0
    text_length: int = 0
    html_length: int = 0
    status_code: Optional[int] = None
    response_time: Optional[float] = None
    blocked: bool = False
    blocked_reason: Optional[str] = None
    blocked_provider: Optional[str] = None
    collected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    errors: list[CollectionError] = field(default_factory=list)

    def add_error(self, step: str, message: str) -> None:
        """Record a non-fatal collection failure for a given step.

        Args:
            step: Name of the collection step that failed.
            message: Human-readable description of the failure.
        """
        self.errors.append(CollectionError(step=step, message=message))

    def to_dict(self) -> dict[str, Any]:
        """Convert this evidence record into a plain JSON-serializable dict.

        Returns:
            A nested dict representation suitable for `json.dumps`.
        """
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize this evidence record to a JSON string.

        Args:
            indent: Number of spaces to indent nested JSON structures.

        Returns:
            A JSON string representation of the evidence record.
        """
        import json

        return json.dumps(self.to_dict(), indent=indent, default=str)