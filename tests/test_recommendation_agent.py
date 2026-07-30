"""Unit tests for the Recommendation Agent."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.recommendation_agent import RecommendationAgent
from models.comprehension import ComprehensionResult
from models.discoverability import DiscoverabilityResult
from models.interaction import InteractionResult
from models.security import SecurityResult


class FakeRetriever:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def get_context_for_topics(self, topics: list[str], k_per_topic: int = 2) -> str:
        if self.fail:
            raise RuntimeError("retrieval failed")
        return "(source: fake)\nThis is a fake RAG excerpt for: " + ", ".join(topics)


def _make_result(result_cls, score: float, issues: list[str] | None = None, recommendations: list[str] | None = None):
    return result_cls(
        score=score,
        checks={},
        details={},
        issues=issues or [],
        recommendations=recommendations or [],
    )


def test_evaluate_orders_recommendations_by_priority() -> None:
    agent = RecommendationAgent(retriever=FakeRetriever())

    discoverability = _make_result(DiscoverabilityResult, 80.0, ["missing sitemap"], ["Add sitemap.xml"])
    comprehension = _make_result(ComprehensionResult, 55.0, ["missing JSON-LD"], ["Publish JSON-LD structured data"])
    interaction = _make_result(InteractionResult, 30.0, ["no OpenAPI spec"], ["Expose an OpenAPI specification"])
    security = _make_result(SecurityResult, 100.0)

    result = agent.evaluate(discoverability, comprehension, interaction, security)

    assert result.total_issues == 3
    assert [rec.priority for rec in result.recommendations] == ["critical", "high", "medium"]
    assert result.recommendations[0].issue == "no OpenAPI spec"


def test_evaluate_includes_score_and_rag_excerpt_in_recommendation_text() -> None:
    agent = RecommendationAgent(retriever=FakeRetriever())

    discoverability = _make_result(DiscoverabilityResult, 20.0, ["missing llms.txt"], ["Add a llms.txt file with site metadata"])
    comprehension = _make_result(ComprehensionResult, 100.0)
    interaction = _make_result(InteractionResult, 100.0)
    security = _make_result(SecurityResult, 100.0)

    result = agent.evaluate(discoverability, comprehension, interaction, security)
    assert result.total_issues == 1

    recommendation = result.recommendations[0]
    assert "Add a llms.txt file with site metadata" in recommendation.recommendation
    assert "category score 20.0" in recommendation.recommendation
    assert "RAG excerpt:" in recommendation.recommendation
    assert recommendation.rag_context.startswith("(source: fake)")


def test_evaluate_degrades_gracefully_when_rag_retrieval_fails() -> None:
    agent = RecommendationAgent(retriever=FakeRetriever(fail=True))

    discoverability = _make_result(DiscoverabilityResult, 20.0, ["missing sitemap"], ["Add sitemap.xml"])
    comprehension = _make_result(ComprehensionResult, 100.0)
    interaction = _make_result(InteractionResult, 100.0)
    security = _make_result(SecurityResult, 100.0)

    result = agent.evaluate(discoverability, comprehension, interaction, security)
    assert result.total_issues == 1

    recommendation = result.recommendations[0]
    assert recommendation.rag_context == ""
    assert "RAG excerpt:" not in recommendation.recommendation


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
