"""Unit tests for :class:`InteractionAgent`.

Covers a fully actionable website (MCP + OpenAPI + Swagger + callable
endpoints), each individual criterion failing in isolation, and a
website with no machine-readable interface at all. The agent consumes
only a `WebsiteEvidence` instance built by hand here — no network
access, HTML parsing, or other evidence-collection tool is exercised
by these tests.

It also includes an end-to-end scenario against a real website that
chains the existing `EvidenceCollectorAgent` into the
`InteractionAgent`. That scenario only orchestrates existing
components — it adds no new logic to either agent.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file directly (e.g. from an IDE "Run" button) by
# ensuring the project root is importable, not just the `tests/` folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.evidence_collector import EvidenceCollectorAgent
from agents.interaction_agent import InteractionAgent
from models.evidence import WebsiteEvidence

URL = "https://www.example.com"
TARGET_URL = "https://www.mytek.tn"


def _print_result(label: str, result) -> None:
    print(f"--- {label} ---")
    print(f"score:           {result.score}")
    print(f"checks:          {result.checks}")
    print(f"details:         {result.details}")
    print(f"issues:          {result.issues}")
    print(f"recommendations: {result.recommendations}")
    print()


def _perfect_evidence() -> WebsiteEvidence:
    """Build a `WebsiteEvidence` that should pass every criterion."""
    return WebsiteEvidence(
        url=URL,
        status_code=200,
        api_analysis={
            "openapi_urls": ["https://www.example.com/openapi.json"],
            "swagger_urls": ["https://www.example.com/docs/swagger"],
            "redoc_urls": [],
            "api_documentation_urls": ["https://www.example.com/docs"],
            "api_endpoints": ["https://www.example.com/api/v1/bookings"],
            "graphql_endpoints": [],
            "mcp_endpoints": ["https://www.example.com/mcp"],
            "mcp_resources": ["catalog"],
            "mcp_tools": ["book_appointment", "create_order"],
        },
    )


def test_perfect_website_scores_100() -> None:
    """Every criterion passes: the score should be exactly 100."""
    agent = InteractionAgent()

    result = agent.evaluate(_perfect_evidence())
    _print_result("perfect website", result)

    assert result.score == 100.0
    assert all(result.checks.values())
    assert result.issues == []
    assert result.recommendations == []


def test_no_mcp_endpoint() -> None:
    """No MCP endpoint discovered: only that criterion fails."""
    agent = InteractionAgent()
    evidence = _perfect_evidence()
    evidence.api_analysis["mcp_endpoints"] = []

    result = agent.evaluate(evidence)
    _print_result("no mcp endpoint", result)

    assert result.checks["mcp_endpoint"] is False
    assert "No MCP" in result.issues[0]
    assert result.score == round(4 / 5 * 100, 2)


def test_mcp_endpoint_without_tools_or_resources() -> None:
    """MCP endpoint found but exposes nothing callable: only that criterion fails."""
    agent = InteractionAgent()
    evidence = _perfect_evidence()
    evidence.api_analysis["mcp_tools"] = []
    evidence.api_analysis["mcp_resources"] = []

    result = agent.evaluate(evidence)
    _print_result("mcp endpoint without tools/resources", result)

    assert result.checks["mcp_tools_and_resources"] is False
    assert "no callable tools or resources" in result.issues[0]
    assert result.score == round(4 / 5 * 100, 2)


def test_no_openapi_spec() -> None:
    """No OpenAPI specification found: only that criterion fails."""
    agent = InteractionAgent()
    evidence = _perfect_evidence()
    evidence.api_analysis["openapi_urls"] = []

    result = agent.evaluate(evidence)
    _print_result("no openapi spec", result)

    assert result.checks["openapi_spec"] is False
    assert "No OpenAPI specification" in result.issues[0]
    assert result.score == round(4 / 5 * 100, 2)


def test_no_swagger_or_redoc() -> None:
    """No Swagger UI or ReDoc documentation found: only that criterion fails."""
    agent = InteractionAgent()
    evidence = _perfect_evidence()
    evidence.api_analysis["swagger_urls"] = []
    evidence.api_analysis["redoc_urls"] = []

    result = agent.evaluate(evidence)
    _print_result("no swagger or redoc", result)

    assert result.checks["swagger_documentation"] is False
    assert "No Swagger UI or ReDoc" in result.issues[0]
    assert result.score == round(4 / 5 * 100, 2)


def test_no_callable_interface() -> None:
    """Docs exist but nothing is actually callable: only that criterion fails."""
    agent = InteractionAgent()
    evidence = _perfect_evidence()
    evidence.api_analysis["api_endpoints"] = []
    evidence.api_analysis["graphql_endpoints"] = []
    evidence.api_analysis["mcp_endpoints"] = []
    # mcp_tools/resources become moot once there is no MCP endpoint, so
    # this scenario intentionally also fails the two MCP criteria above
    # it — we only assert on the criterion under test here.

    result = agent.evaluate(evidence)
    _print_result("no callable interface", result)

    assert result.checks["agent_actionability"] is False
    assert "cannot take action" in result.issues[-1]


def test_everything_missing_scores_zero() -> None:
    """A bare, empty evidence record should score 0: nothing is actionable."""
    agent = InteractionAgent()
    evidence = WebsiteEvidence(url=URL)

    result = agent.evaluate(evidence)
    _print_result("everything missing", result)

    assert result.score == 0.0
    assert not any(result.checks.values())


# ---------------------------------------------------------------------------
# End-to-end scenario: real website -> Evidence Collector -> Interaction
# Agent. Adds no new logic to either agent; it only orchestrates the two
# existing components.
# ---------------------------------------------------------------------------


def test_real_site_interaction() -> None:
    """End-to-end: collect real evidence, then evaluate interaction/actionability.

    Requires network access.
    """
    evidence = EvidenceCollectorAgent().collect(TARGET_URL)
    result = InteractionAgent().evaluate(evidence)
    _print_result(f"real site: {TARGET_URL}", result)

    assert 0.0 <= result.score <= 100.0
    assert len(result.checks) == 5


if __name__ == "__main__":
    test_perfect_website_scores_100()
    test_no_mcp_endpoint()
    test_mcp_endpoint_without_tools_or_resources()
    test_no_openapi_spec()
    test_no_swagger_or_redoc()
    test_no_callable_interface()
    test_everything_missing_scores_zero()
    test_real_site_interaction()
    print("All tests passed.")
