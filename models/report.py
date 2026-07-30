"""Data models for the Report Generator Agent.

These dataclasses describe the *shape* of the data the Report Generator
consumes (produced upstream by the Orchestrator / Analysis Agents /
Recommendation Agent) and the shape of what it produces (the final
`AgenticReadinessReport`).

If your Orchestrator and Recommendation Agent already define
`AssessmentResult` / `RecommendationResult` classes elsewhere, you can
either import those instead of these, or adapt field names via a small
mapping layer.

Nothing in this file performs scoring or recommendation logic — it is pure
data structure, consistent with the Report Generator's "assemble only" role.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    """Severity level of a detected issue."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Priority(str, Enum):
    """Priority level of a recommendation."""

    P0 = "P0"  # must fix
    P1 = "P1"  # should fix
    P2 = "P2"  # nice to have


class AnalysisCategory(str, Enum):
    """Matches the four Parallel Analysis Agents in the ARAF diagram."""

    DISCOVERABILITY = "discoverability"
    COMPREHENSION = "comprehension"
    INTERACTION = "interaction"
    SECURITY = "security"


# ---------------------------------------------------------------------------
# Upstream inputs (produced BEFORE the Report Generator runs)
# ---------------------------------------------------------------------------

@dataclass
class CategoryScore:
    """Score produced by one of the four Parallel Analysis Agents."""

    category: AnalysisCategory
    score: float  # e.g. 0-100
    max_score: float = 100.0
    findings: List[str] = field(default_factory=list)
    raw_metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectedIssue:
    """A concrete problem found during analysis, tied to evidence."""

    id: str
    category: AnalysisCategory
    severity: Severity
    title: str
    description: str
    evidence_ref: Optional[str] = None  # pointer into Shared Evidence Repository


@dataclass
class AssessmentResult:
    """Aggregate output of the Orchestrator after all analysis agents finish.

    This is the first of the two inputs the Report Generator Agent consumes.
    """

    url: str
    assessed_at: datetime
    overall_score: float
    category_scores: List[CategoryScore]
    issues: List[DetectedIssue] = field(default_factory=list)
    artifacts_collected: List[str] = field(default_factory=list)  # e.g. ["robots.txt", "llms.txt", ...]


@dataclass
class Recommendation:
    """A single prioritized, actionable recommendation."""

    id: str
    category: AnalysisCategory
    priority: Priority
    title: str
    description: str
    related_issue_ids: List[str] = field(default_factory=list)
    effort: Optional[str] = None  # e.g. "low" / "medium" / "high"
    impact: Optional[str] = None  # e.g. "low" / "medium" / "high"
    knowledge_sources: List[str] = field(default_factory=list)  # RAG sources used
    rag_context: str = ""


@dataclass
class RecommendationResult:
    """Output of the Recommendation Agent.

    This is the second of the two inputs the Report Generator Agent consumes.
    """

    recommendations: List[Recommendation]
    rag_sources_used: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Final output
# ---------------------------------------------------------------------------

@dataclass
class AgenticReadinessReport:
    """Final assembled report — the Report Generator Agent's sole output."""

    url: str
    generated_at: datetime
    overall_score: float
    category_scores: List[CategoryScore]
    issues: List[DetectedIssue]
    recommendations: List[Recommendation]
    rag_sources_used: List[str] = field(default_factory=list)
    artifacts_collected: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Plain-dict representation, safe for json.dumps."""

        def _cat_score(cs: CategoryScore) -> Dict[str, Any]:
            return {
                "category": cs.category.value,
                "score": cs.score,
                "max_score": cs.max_score,
                "findings": cs.findings,
                "raw_metrics": cs.raw_metrics,
            }

        def _issue(i: DetectedIssue) -> Dict[str, Any]:
            return {
                "id": i.id,
                "category": i.category.value,
                "severity": i.severity.value,
                "title": i.title,
                "description": i.description,
                "evidence_ref": i.evidence_ref,
            }

        def _rec(r: Recommendation) -> Dict[str, Any]:
            return {
                "id": r.id,
                "category": r.category.value,
                "priority": r.priority.value,
                "title": r.title,
                "description": r.description,
                "related_issue_ids": r.related_issue_ids,
                "effort": r.effort,
                "impact": r.impact,
                "knowledge_sources": r.knowledge_sources,
                "rag_context": r.rag_context,
            }

        return {
            "url": self.url,
            "generated_at": self.generated_at.isoformat(),
            "overall_score": self.overall_score,
            "category_scores": [_cat_score(c) for c in self.category_scores],
            "issues": [_issue(i) for i in self.issues],
            "recommendations": [_rec(r) for r in self.recommendations],
            "rag_sources_used": self.rag_sources_used,
            "artifacts_collected": self.artifacts_collected,
            "metadata": self.metadata,
        }


def utcnow() -> datetime:
    """Small helper kept here so agent code has no other stdlib coupling."""
    return datetime.now(timezone.utc)