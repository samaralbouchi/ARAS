"""Data models used by the Recommendation Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Recommendation:
    category: str
    issue: str
    recommendation: str
    how_to_apply: str = ""
    sources: List[str] = field(default_factory=list)
    priority: str = "medium"
    rag_context: str = ""
    rag_sources: List[dict] = field(default_factory=list)


@dataclass(frozen=True)
class RecommendationResult:
    recommendations: List[Recommendation]
    total_issues: int
    rag_sources_used: List[dict] = field(default_factory=list)
