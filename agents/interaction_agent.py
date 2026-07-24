"""Interaction Agent.

This module is one of the parallel analysis ("judgment") layers of
ARAF. It evaluates how *actionable* a website is for an autonomous AI
agent — not merely whether the agent can read and understand the
page (Comprehension), but whether it can actually carry out tasks on
it: calling MCP tools, invoking a documented REST/GraphQL API, or
following a machine-readable OpenAPI/Swagger contract.

This is the layer that distinguishes true agentic readiness (an agent
can book, fill a form, or purchase) from passive citability (an agent
can merely quote the page in an answer).

This agent MUST NOT:
    - perform HTTP requests
    - parse HTML
    - discover APIs
    - crawl websites
    - use BeautifulSoup, HttpClient, or any extraction tool

It only reads an already-collected `WebsiteEvidence` snapshot and
turns it into a scored `InteractionResult`. Evidence collection
belongs to the Evidence Collector, a separate, earlier layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from models.evidence import WebsiteEvidence
from models.interaction import InteractionResult

_CRITERIA_COUNT = 5
_CRITERION_WEIGHT = 100.0 / _CRITERIA_COUNT


@dataclass(frozen=True)
class _CriterionOutcome:
    """The result of evaluating a single interaction criterion.

    Attributes:
        passed: Whether the criterion was satisfied.
        details: Evidence to merge into `InteractionResult.details`.
        issue: Message to record if the criterion failed.
        recommendation: Fix to record if the criterion failed.
    """

    passed: bool
    details: dict[str, object]
    issue: str
    recommendation: str


class InteractionAgent:
    """Evaluates how actionable a website is for AI agents.

    This class holds no evidence-collection logic. It is a pure
    judgment step: it reads a `WebsiteEvidence` snapshot and scores it
    against a fixed set of equally-weighted interaction/actionability
    criteria.
    """

    def evaluate(self, evidence: WebsiteEvidence) -> InteractionResult:
        """Evaluate agent-actionability from already-collected evidence.

        Args:
            evidence: The `WebsiteEvidence` snapshot to evaluate.

        Returns:
            An `InteractionResult` with a score in [0, 100], a
            pass/fail breakdown, supporting details, and
            recommendations for every failed criterion.
        """
        result = InteractionResult()

        criteria: list[tuple[str, Callable[[WebsiteEvidence], _CriterionOutcome]]] = [
            ("mcp_endpoint", self._evaluate_mcp_endpoint),
            ("mcp_tools_and_resources", self._evaluate_mcp_tools_and_resources),
            ("openapi_spec", self._evaluate_openapi_spec),
            ("swagger_documentation", self._evaluate_swagger_documentation),
            ("agent_actionability", self._evaluate_agent_actionability),
        ]

        for name, evaluator in criteria:
            self._apply(name, evaluator(evidence), result)

        result.score = self._compute_score(result.checks)
        return result

    # ------------------------------------------------------------------
    # Result assembly
    # ------------------------------------------------------------------

    @staticmethod
    def _apply(
        name: str, outcome: _CriterionOutcome, result: InteractionResult
    ) -> None:
        """Merge a single criterion's outcome into the aggregate result.

        Args:
            name: The criterion's key in `result.checks`.
            outcome: The evaluated outcome for this criterion.
            result: The in-progress result to update.
        """
        result.checks[name] = outcome.passed
        result.details.update(outcome.details)
        if not outcome.passed:
            result.issues.append(outcome.issue)
            result.recommendations.append(outcome.recommendation)

    @staticmethod
    def _compute_score(checks: dict[str, bool]) -> float:
        """Compute the overall score from equally-weighted criteria.

        Args:
            checks: Pass/fail outcome of every evaluated criterion.

        Returns:
            The percentage of passed criteria, in [0, 100].
        """
        if not checks:
            return 0.0
        passed = sum(1 for outcome in checks.values() if outcome)
        return round(passed * _CRITERION_WEIGHT, 2)

    # ------------------------------------------------------------------
    # 1. MCP endpoint detection
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_mcp_endpoint(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that a Model Context Protocol (MCP) endpoint was found.

        An MCP endpoint is the strongest possible signal of agentic
        readiness: it means the site exposes a native, structured
        interface designed specifically for AI agents rather than
        browsers.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        mcp_endpoints = evidence.api_analysis.get("mcp_endpoints") or []
        passed = bool(mcp_endpoints)

        return _CriterionOutcome(
            passed=passed,
            details={"mcp_endpoints": mcp_endpoints},
            issue="No MCP (Model Context Protocol) endpoint detected",
            recommendation=(
                "Expose an MCP server so AI agents can discover and call "
                "your site's capabilities natively, instead of scraping HTML."
            ),
        )

    # ------------------------------------------------------------------
    # 2. MCP tools and resources
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_mcp_tools_and_resources(
        evidence: WebsiteEvidence,
    ) -> _CriterionOutcome:
        """Check that the MCP endpoint (if any) exposes callable tools or resources.

        A bare MCP endpoint with no declared tools or resources gives
        an agent nothing to actually invoke.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        mcp_tools = evidence.api_analysis.get("mcp_tools") or []
        mcp_resources = evidence.api_analysis.get("mcp_resources") or []
        passed = bool(mcp_tools or mcp_resources)

        return _CriterionOutcome(
            passed=passed,
            details={"mcp_tools": mcp_tools, "mcp_resources": mcp_resources},
            issue="MCP endpoint exposes no callable tools or resources",
            recommendation=(
                "Declare MCP tools (actions) and resources (data) so agents "
                "know what they can actually do on your site."
            ),
        )

    # ------------------------------------------------------------------
    # 3. OpenAPI specification
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_openapi_spec(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that a machine-readable OpenAPI specification was found.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        openapi_urls = evidence.api_analysis.get("openapi_urls") or []
        passed = bool(openapi_urls)

        return _CriterionOutcome(
            passed=passed,
            details={"openapi_urls": openapi_urls},
            issue="No OpenAPI specification found",
            recommendation=(
                "Publish an OpenAPI (openapi.json/yaml) specification "
                "describing your API's endpoints, parameters, and schemas."
            ),
        )

    # ------------------------------------------------------------------
    # 4. Swagger / ReDoc documentation
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_swagger_documentation(
        evidence: WebsiteEvidence,
    ) -> _CriterionOutcome:
        """Check that interactive Swagger or ReDoc API documentation was found.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        swagger_urls = evidence.api_analysis.get("swagger_urls") or []
        redoc_urls = evidence.api_analysis.get("redoc_urls") or []
        passed = bool(swagger_urls or redoc_urls)

        return _CriterionOutcome(
            passed=passed,
            details={"swagger_urls": swagger_urls, "redoc_urls": redoc_urls},
            issue="No Swagger UI or ReDoc documentation found",
            recommendation=(
                "Publish interactive Swagger UI or ReDoc documentation so "
                "agents (and developers) can explore available operations."
            ),
        )

    # ------------------------------------------------------------------
    # 5. Overall agent actionability
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_agent_actionability(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that at least one *callable* interface exists, not just docs.

        Documentation (OpenAPI, Swagger) tells an agent what it could
        do; this criterion checks whether there is something it can
        actually call — a live REST or GraphQL endpoint, or an MCP
        endpoint — which is the difference between a site being
        merely citable and a site being actionable (bookable,
        fillable, purchasable).

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        api_analysis = evidence.api_analysis
        api_endpoints = api_analysis.get("api_endpoints") or []
        graphql_endpoints = api_analysis.get("graphql_endpoints") or []
        mcp_endpoints = api_analysis.get("mcp_endpoints") or []
        passed = bool(api_endpoints or graphql_endpoints or mcp_endpoints)

        return _CriterionOutcome(
            passed=passed,
            details={
                "api_endpoints": api_endpoints,
                "graphql_endpoints": graphql_endpoints,
                "callable_mcp_endpoints": mcp_endpoints,
            },
            issue=(
                "No callable interface found: an agent can read this site "
                "but cannot take action on it (book, fill, purchase)"
            ),
            recommendation=(
                "Expose at least one callable interface (REST endpoint, "
                "GraphQL endpoint, or MCP tool) behind your documentation "
                "so agents can act, not just read."
            ),
        )
