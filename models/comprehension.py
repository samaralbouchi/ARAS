"""Data contract for the Comprehension Agent.

This module defines the single output type produced by the
Comprehension Agent: a scored, JSON-serializable judgment of how
easily an AI agent can parse and understand the *content* of a
website's homepage — its semantic HTML structure, heading hierarchy,
structured data, declared language, image accessibility, and
text-to-markup efficiency. No evidence collection (HTTP requests, HTML
parsing, crawling) belongs here — this is a data container only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ComprehensionResult:
    """Scored assessment of a website's comprehensibility for AI agents.

    This dataclass is the sole output of :class:`ComprehensionAgent`.
    It is derived entirely from an already-collected `WebsiteEvidence`
    instance — no new evidence is gathered while producing it.

    Attributes:
        score: Overall comprehension score in the range [0, 100].
        checks: Pass/fail outcome of each individual criterion, keyed
            by criterion name (e.g. `"semantic_html"`, `"headings"`).
        details: Supporting evidence for each criterion (raw values
            such as the semantic tags found or the text-to-HTML ratio)
            useful for reporting and debugging.
        recommendations: Technical recommendations, one per failed
            criterion, describing how to fix it.
        issues: Human-readable descriptions of every failed criterion.
    """

    score: float = 0.0
    checks: dict[str, bool] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert this result into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize this result to a JSON string.

        Args:
            indent: Number of spaces to indent nested JSON structures.

        Returns:
            A JSON string representation of the result.
        """
        import json

        return json.dumps(self.to_dict(), indent=indent, default=str)
