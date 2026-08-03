"""Recommendation Agent.

This module is the fifth step of the ARAF judgment pipeline, sitting
between the four parallel analysis agents (Discoverability,
Comprehension, Interaction, Security) and the Report Generator. It
does not introduce any new pass/fail criterion: every recommendation
it emits already exists, verbatim, inside the `issues` /
`recommendations` pair of one of the four `*Result` objects it
consumes.

Its job is purely editorial:
    1. Flatten the four `*Result` objects into one list of
       `Recommendation` entries (one per failed criterion).
    2. Enrich each entry with supporting context pulled from the
       Knowledge Base (RAG), via an injected retriever.
    3. Prioritize the list so the most urgent fixes surface first.

This agent MUST NOT:
    - perform HTTP requests, HTML parsing, or API discovery
    - decide whether a criterion passed or failed (that belongs to the
      four analysis agents)
    - fail the whole assessment if the Knowledge Base is unavailable —
      RAG context is a nice-to-have; a recommendation without it is
      still actionable, so retrieval failures degrade gracefully to an
      empty `rag_context` instead of raising.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol

from models.comprehension import ComprehensionResult
from models.discoverability import DiscoverabilityResult
from models.interaction import InteractionResult
from models.recommendation import Recommendation, RecommendationResult
from models.security import SecurityResult

# Score thresholds used to translate a category's overall score into a
# priority bucket for every issue raised within that category: the
# weaker the category, the more urgent its fixes.
_CRITICAL_THRESHOLD = 40.0
_HIGH_THRESHOLD = 70.0

# Sort order used when two recommendations share the same priority
# bucket, so output is deterministic across runs.
_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2}

# Default number of Knowledge Base excerpts retrieved per issue.
_DEFAULT_K_PER_TOPIC = 2


class _SupportsTopicRetrieval(Protocol):
    """Structural interface required from an injected retriever.

    Matches `rag.retriever.KnowledgeBaseRetriever.get_context_for_topics`
    without requiring that concrete class (or its heavy embedding
    dependencies) at type-check time, so tests can inject a lightweight
    fake instead.
    """

    def get_context_for_topics(
        self, topics: list[str], k_per_topic: int = 2
    ) -> tuple[str, list[dict]]: ...


@dataclass(frozen=True)
class _RawEntry:
    """A single failed criterion, not yet prioritized or enriched.

    Attributes:
        category: Name of the originating analysis agent.
        issue: Human-readable description of the failed criterion.
        recommendation: The technical fix for this criterion.
        category_score: Overall score of the originating agent, used
            to derive this entry's priority.
    """

    category: str
    issue: str
    recommendation: str
    category_score: float


class RecommendationAgent:
    """Turns the four analysis results into one prioritized fix list.

    This class holds no scoring logic of its own. It is a pure
    aggregation and enrichment step: it reads the `issues` and
    `recommendations` already produced by the four analysis agents,
    attaches Knowledge Base context to each, and orders the result by
    urgency.

    The Knowledge Base retriever is injectable (and optional) so
    callers (tests, in particular) can substitute a fake or omit RAG
    context entirely without a real Chroma vector store on disk.
    """

    def __init__(
        self,
        retriever: Optional[_SupportsTopicRetrieval] = None,
        k_per_topic: int = _DEFAULT_K_PER_TOPIC,
    ) -> None:
        """Initialize the agent, optionally overriding its collaborators.

        Args:
            retriever: Collaborator used to fetch RAG context for each
                issue. Must expose
                `.get_context_for_topics(topics, k_per_topic) -> str`.
                Defaults to `None`, meaning every recommendation is
                emitted with an empty `rag_context` (no Knowledge Base
                augmentation) — a valid, fully-functional mode.
            k_per_topic: Number of Knowledge Base excerpts to retrieve
                per issue when a retriever is supplied.
        """
        self._retriever = retriever
        self._k_per_topic = k_per_topic

    def evaluate(
        self,
        discoverability: DiscoverabilityResult,
        comprehension: ComprehensionResult,
        interaction: InteractionResult,
        security: SecurityResult,
    ) -> RecommendationResult:
        """Produce a prioritized, RAG-enriched recommendation list.

        Args:
            discoverability: Output of the Discoverability Agent.
            comprehension: Output of the Comprehension Agent.
            interaction: Output of the Interaction Agent.
            security: Output of the Security Agent.

        Returns:
            A `RecommendationResult` with every failed criterion from
            the four inputs, sorted with the most urgent fixes first.
        """
        raw_entries = self._flatten(discoverability, comprehension, interaction, security)
        recommendations = [self._enrich(entry) for entry in raw_entries]
        recommendations.sort(key=lambda rec: _PRIORITY_RANK[rec.priority])

        seen_sources = set()
        rag_sources_used = []
        for rec in recommendations:
            for s in rec.rag_sources:
                key = (s["source"], s["source_type"])
                if key not in seen_sources:
                    seen_sources.add(key)
                    rag_sources_used.append(s)

        return RecommendationResult(
            recommendations=recommendations,
            total_issues=len(recommendations),
            rag_sources_used=rag_sources_used,
        )

    # ------------------------------------------------------------------
    # Flattening
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten(
        discoverability: DiscoverabilityResult,
        comprehension: ComprehensionResult,
        interaction: InteractionResult,
        security: SecurityResult,
    ) -> list[_RawEntry]:
        """Flatten the four analysis results into one list of raw entries.

        Each `*Result.issues[i]` is paired with `*Result.recommendations[i]`:
        both lists are appended to together, in lockstep, by the
        originating analysis agent for every failed criterion, so the
        two are always the same length and index-aligned.

        Args:
            discoverability: Output of the Discoverability Agent.
            comprehension: Output of the Comprehension Agent.
            interaction: Output of the Interaction Agent.
            security: Output of the Security Agent.

        Returns:
            One `_RawEntry` per failed criterion, across all four
            categories, in category order (Discoverability,
            Comprehension, Interaction, Security).
        """
        categories: list[tuple[str, Any]] = [
            ("discoverability", discoverability),
            ("comprehension", comprehension),
            ("interaction", interaction),
            ("security", security),
        ]

        entries: list[_RawEntry] = []
        for name, result in categories:
            for issue, recommendation in zip(result.issues, result.recommendations):
                entries.append(
                    _RawEntry(
                        category=name,
                        issue=issue,
                        recommendation=recommendation,
                        category_score=result.score,
                    )
                )
        return entries

    # ------------------------------------------------------------------
    # Enrichment
    # ------------------------------------------------------------------
    
    def _enrich(self, entry: _RawEntry) -> Recommendation:
        rag_context, rag_sources = self._fetch_rag_context(entry.issue)
        priority = self._compute_priority(entry.category_score)

        recommendation_text = self._format_recommendation_text(
            entry.recommendation,
            entry.category_score,
            priority,
            rag_context,
        )

        return Recommendation(
            category=entry.category,
            issue=entry.issue,
            recommendation=recommendation_text,
            priority=priority,
            rag_context=rag_context,
            rag_sources=rag_sources,
        )
    


    def _format_recommendation_text(
        self,
        recommendation: str,
        category_score: float,
        priority: str,
        rag_context: str,
    ) -> str:
        """Produce a more specific recommendation string.

        The RAG context is used to make the recommendation feel grounded
        in the supporting knowledge base, while the category score makes
        the urgency explicit.
        """
        if rag_context:
            snippet = self._extract_rag_snippet(rag_context)
            return (
                f"{recommendation} "
                f"(derived from category score {category_score:.1f}, priority {priority}; "
                f"RAG excerpt: {snippet})"
            )

        return (
            f"{recommendation} "
            f"(derived from category score {category_score:.1f}, priority {priority})"
        )

    def _extract_rag_snippet(self, rag_context: str) -> str:
        """Extract a concise, human-readable snippet from RAG context."""
        lines = [line.strip() for line in rag_context.splitlines() if line.strip()]
        if not lines:
            return "(no RAG excerpt available)"
        if len(lines) == 1:
            return lines[0]
        # Prefer the first non-source line if the first line looks like a source marker.
        if lines[0].startswith("(source:") and len(lines) > 1:
            return lines[1]
        return lines[0]

    @staticmethod
    def _compute_priority(category_score: float) -> str:
        """Derive an urgency bucket from a category's overall score.

        A lower category score means the underlying agent is failing
        most of its criteria, so every issue it raises is treated as
        more urgent.

        Args:
            category_score: Overall score ([0, 100]) of the
                originating analysis agent.

        Returns:
            One of `"critical"`, `"high"`, or `"medium"`.
        """
        if category_score < _CRITICAL_THRESHOLD:
            return "critical"
        if category_score < _HIGH_THRESHOLD:
            return "high"
        return "medium"

    def _fetch_rag_context(self, issue: str) -> tuple[str, list[dict]]:
        """Retrieve Knowledge Base context for a single issue.
        ...
        """
        if self._retriever is None:
            return "", []
        try:
            return self._retriever.get_context_for_topics(
                [issue], k_per_topic=self._k_per_topic
            )
        except Exception:
            return "", []