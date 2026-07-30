"""Data models used by the Recommendation Agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Recommendation:
    category: str
    issue: str
    recommendation: str
    priority: str
    rag_context: str = ""


@dataclass(frozen=True)
class RecommendationResult:
    recommendations: List[Recommendation]
    total_issues: int
