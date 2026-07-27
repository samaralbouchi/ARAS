"""Data contract for the Orchestrator Agent.

This module defines the single output type produced by the
Orchestrator Agent: a complete, JSON-serializable Agentic Readiness
Assessment for a single website — the raw evidence collected, the four
parallel analysis results (Discoverability, Comprehension, Interaction,
Security), and an overall aggregate score. No new scoring logic or
recommendation generation belongs here; this is a data container that
simply assembles what the Evidence Collector and the four analysis
agents already produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


@dataclass
class AssessmentResult:
    """Complete Agentic Readiness Assessment for a single website.

    This dataclass is the sole output of :class:`OrchestratorAgent`. It
    never performs its own evidence collection or scoring — every
    field is copied from the `WebsiteEvidence` snapshot and the four
    `*Result` objects produced by the analysis agents it coordinates.

    Attributes:
        url: The website URL that was assessed.
        evidence: Full `WebsiteEvidence` snapshot, as a plain dict.
        discoverability: `DiscoverabilityResult`, as a plain dict.
        comprehension: `ComprehensionResult`, as a plain dict.
        interaction: `InteractionResult`, as a plain dict.
        security: `SecurityResult`, as a plain dict.
        overall_score: Unweighted average of the four analysis scores,
            in [0, 100].
        collection_errors: Non-fatal evidence-collection failures,
            copied from `evidence.errors`, surfaced here for
            convenience so callers don't need to dig into `evidence`.
        assessed_at: UTC timestamp when the assessment was assembled.
    """

    url: str
    evidence: dict[str, Any] = field(default_factory=dict)
    discoverability: dict[str, Any] = field(default_factory=dict)
    comprehension: dict[str, Any] = field(default_factory=dict)
    interaction: dict[str, Any] = field(default_factory=dict)
    security: dict[str, Any] = field(default_factory=dict)
    overall_score: float = 0.0
    collection_errors: list[dict[str, Any]] = field(default_factory=list)
    assessed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert this assessment into a plain JSON-serializable dict.

        Returns:
            A nested dict representation suitable for `json.dumps`.
        """
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize this assessment to a JSON string.

        Args:
            indent: Number of spaces to indent nested JSON structures.

        Returns:
            A JSON string representation of the assessment.
        """
        import json

        return json.dumps(self.to_dict(), indent=indent, default=str)