"""Recommendation Agent.

This module is the fifth step of the ARAF judgment pipeline, sitting
between the four parallel analysis agents (Discoverability,
Comprehension, Interaction, Security) and the Report Generator.

Its job:
    1. Flatten the four analysis results.
    2. Retrieve supporting knowledge using RAG.
    3. Generate improved recommendations and implementation steps.
    4. Prioritize recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol

from models.comprehension import ComprehensionResult
from models.discoverability import DiscoverabilityResult
from models.interaction import InteractionResult
from models.recommendation import Recommendation, RecommendationResult
from models.security import SecurityResult
from rag.generator import RecommendationGenerator


_CRITICAL_THRESHOLD = 40.0
_HIGH_THRESHOLD = 70.0

_PRIORITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2
}

_DEFAULT_K_PER_TOPIC = 2


class _SupportsTopicRetrieval(Protocol):

    def get_context_for_topics(
        self,
        topics: list[str],
        k_per_topic: int = 2
    ) -> tuple[str, list[dict]]:
        ...


@dataclass(frozen=True)
class _RawEntry:

    category: str
    issue: str
    recommendation: str
    category_score: float



class RecommendationAgent:

    def __init__(
        self,
        retriever: Optional[_SupportsTopicRetrieval] = None,
        k_per_topic: int = _DEFAULT_K_PER_TOPIC,
    ) -> None:

        self._retriever = retriever
        self._k_per_topic = k_per_topic

        # LLM generator using RAG context
        self._generator = RecommendationGenerator()



    def evaluate(
        self,
        discoverability: DiscoverabilityResult,
        comprehension: ComprehensionResult,
        interaction: InteractionResult,
        security: SecurityResult,
    ) -> RecommendationResult:


        raw_entries = self._flatten(
            discoverability,
            comprehension,
            interaction,
            security
        )


        recommendation_inputs = []


        # Retrieve RAG context for every issue
        for entry in raw_entries:

            rag_context, rag_sources = self._fetch_rag_context(
                entry.issue
            )


            recommendation_inputs.append(
                {
                    "issue": entry.issue,
                    "base_recommendation": entry.recommendation,
                    "rag_context": rag_context,
                    "rag_sources": rag_sources,
                    "entry": entry
                }
            )


        # Generate all recommendations using the LLM
        generated_results = self._generator.generate_all(
            recommendation_inputs
        )
        

        recommendations = []

        for item, generated in zip(
            recommendation_inputs,
            generated_results
        ):

            entry = item["entry"]

            recommendation = generated.get(
                "recommendation",
                entry.recommendation
            )

            how_to_apply = generated.get(
                "how_to_apply",
                ""
            )

            # Si le LLM renvoie une liste, on la convertit en texte
            if isinstance(how_to_apply, list):
                how_to_apply = "\n".join(how_to_apply)

            recommendations.append(
                Recommendation(
                    category=entry.category,

                    issue=entry.issue,

                    recommendation=recommendation,

                    how_to_apply=how_to_apply,

                    sources=[
                        s["source"]
                        for s in item["rag_sources"]
                        if "source" in s
                    ],

                    priority=self._compute_priority(
                        entry.category_score
                    ),

                    rag_context=item["rag_context"],

                    rag_sources=item["rag_sources"],
                )
            )



        recommendations.sort(
            key=lambda rec: _PRIORITY_RANK[rec.priority]
        )



        seen_sources = set()
        rag_sources_used = []


        for rec in recommendations:

            for source in rec.rag_sources:

                key = (
                    source["source"],
                    source["source_type"]
                )


                if key not in seen_sources:

                    seen_sources.add(key)

                    rag_sources_used.append(source)


        



        return RecommendationResult(

            recommendations=recommendations,

            total_issues=len(recommendations),

            rag_sources_used=rag_sources_used
        )

        



    # -----------------------------------------------------
    # Flatten analysis results
    # -----------------------------------------------------

    @staticmethod
    def _flatten(
        discoverability,
        comprehension,
        interaction,
        security,
    ) -> list[_RawEntry]:


        categories = [

            ("discoverability", discoverability),

            ("comprehension", comprehension),

            ("interaction", interaction),

            ("security", security),
        ]


        entries = []


        for name, result in categories:


            for issue, recommendation in zip(
                result.issues,
                result.recommendations
            ):


                entries.append(

                    _RawEntry(

                        category=name,

                        issue=issue,

                        recommendation=recommendation,

                        category_score=result.score
                    )
                )


        return entries



    # -----------------------------------------------------
    # RAG retrieval
    # -----------------------------------------------------

    def _fetch_rag_context(
        self,
        issue: str
    ) -> tuple[str, list[dict]]:


        if self._retriever is None:

            return "", []


        try:

            return self._retriever.get_context_for_topics(

                [issue],

                k_per_topic=self._k_per_topic
            )


        except Exception:

            return "", []



    # -----------------------------------------------------
    # Priority
    # -----------------------------------------------------

    @staticmethod
    def _compute_priority(
        category_score: float
    ) -> str:


        if category_score < _CRITICAL_THRESHOLD:

            return "critical"


        if category_score < _HIGH_THRESHOLD:

            return "high"


        return "medium"