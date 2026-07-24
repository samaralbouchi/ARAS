"""Discoverability Agent.

This module is the first analysis ("judgment") layer of ARAS. It
evaluates how easily an AI agent can discover and understand the
public entry points of a website: standard discovery files
(`robots.txt`, `sitemap.xml`, `llms.txt`), page metadata, Open Graph
tags, machine-readable API surfaces, and internal navigation.

This agent MUST NOT:
    - perform HTTP requests
    - parse HTML
    - discover APIs
    - crawl websites
    - use BeautifulSoup, HttpClient, or any extraction tool

It only reads an already-collected `WebsiteEvidence` snapshot and
turns it into a scored `DiscoverabilityResult`. Evidence collection
belongs to the Evidence Collector, a separate, earlier layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from models.discoverability import DiscoverabilityResult
from models.evidence import WebsiteEvidence

_CRITERIA_COUNT = 7
_CRITERION_WEIGHT = 100.0 / _CRITERIA_COUNT


@dataclass(frozen=True)
class _CriterionOutcome:
    """The result of evaluating a single discoverability criterion.

    Attributes:
        passed: Whether the criterion was satisfied.
        details: Evidence to merge into `DiscoverabilityResult.details`.
        issue: Message to record if the criterion failed.
        recommendation: Fix to record if the criterion failed.
    """

    passed: bool
    details: dict[str, object]
    issue: str
    recommendation: str


class DiscoverabilityAgent:
    """Evaluates a website's discoverability for AI agents.

    This class holds no evidence-collection logic. It is a pure
    judgment step: it reads a `WebsiteEvidence` snapshot and scores it
    against a fixed set of equally-weighted discoverability criteria.
    """

    def evaluate(self, evidence: WebsiteEvidence) -> DiscoverabilityResult:
        """Evaluate discoverability from already-collected evidence.

        Args:
            evidence: The `WebsiteEvidence` snapshot to evaluate.

        Returns:
            A `DiscoverabilityResult` with a score in [0, 100], a
            pass/fail breakdown, supporting details, and
            recommendations for every failed criterion.
        """
        result = DiscoverabilityResult()

        criteria: list[tuple[str, Callable[[WebsiteEvidence], _CriterionOutcome]]] = [
            ("robots_txt", self._evaluate_robots_txt),
            ("sitemap", self._evaluate_sitemap),
            ("llms_txt", self._evaluate_llms_txt),
            ("metadata", self._evaluate_metadata),
            ("open_graph", self._evaluate_open_graph),
            ("api_discoverability", self._evaluate_api_discoverability),
            ("internal_links", self._evaluate_internal_links),
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
        name: str, outcome: _CriterionOutcome, result: DiscoverabilityResult
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
    # 1. robots.txt
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_robots_txt(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that `robots.txt` was discovered.

        `WebsiteEvidence.robots_txt` is only ever populated by the
        Evidence Collector when the `/robots.txt` request succeeded
        with a 200 status code, so its mere presence already implies
        that condition.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        found = bool(evidence.robots_txt)
        return _CriterionOutcome(
            passed=found,
            details={"robots_found": found},
            issue="No robots.txt found",
            recommendation="Add a robots.txt file at the site root.",
        )

    # ------------------------------------------------------------------
    # 2. sitemap.xml
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_sitemap(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that `sitemap.xml` was discovered.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        found = bool(evidence.sitemap_xml)
        return _CriterionOutcome(
            passed=found,
            details={"sitemap_found": found},
            issue="No sitemap.xml found",
            recommendation="Publish a sitemap.xml listing the site's discoverable pages.",
        )

    # ------------------------------------------------------------------
    # 3. llms.txt
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_llms_txt(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that `llms.txt` was discovered.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        found = bool(evidence.llms_txt)
        return _CriterionOutcome(
            passed=found,
            details={"llms_found": found},
            issue="No llms.txt found",
            recommendation="Add an llms.txt file to guide AI agents to key site content.",
        )

    # ------------------------------------------------------------------
    # 4. Metadata quality
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_metadata(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that the homepage declares title, description, and canonical.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        has_title = bool(evidence.title)
        has_description = bool(evidence.meta_tags.get("description"))
        has_canonical = bool(evidence.canonical)
        passed = has_title and has_description and has_canonical

        details = {
            "title": evidence.title,
            "has_description": has_description,
            "canonical": evidence.canonical,
        }

        missing = [
            label
            for label, present in (
                ("title", has_title),
                ("meta description", has_description),
                ("canonical URL", has_canonical),
            )
            if not present
        ]
        issue = f"Missing metadata: {', '.join(missing)}" if missing else ""
        recommendation = (
            f"Add the missing metadata: {', '.join(missing)}."
            if missing
            else ""
        )

        return _CriterionOutcome(
            passed=passed,
            details=details,
            issue=issue,
            recommendation=recommendation,
        )

    # ------------------------------------------------------------------
    # 5. Open Graph
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_open_graph(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that at least one Open Graph tag is present.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        found = bool(evidence.open_graph)
        return _CriterionOutcome(
            passed=found,
            details={"open_graph_tags": list(evidence.open_graph.keys())},
            issue="No Open Graph metadata found",
            recommendation="Add Open Graph metadata (og:title, og:description, og:image, ...).",
        )

    # ------------------------------------------------------------------
    # 6. API discoverability
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_api_discoverability(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that at least one machine-readable API surface was found.

        Considers OpenAPI specs, Swagger UI, GraphQL endpoints, raw
        REST endpoints, and general API documentation, as recorded in
        `evidence.api_analysis`.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        api_analysis = evidence.api_analysis
        openapi_urls = api_analysis.get("openapi_urls") or []
        swagger_urls = api_analysis.get("swagger_urls") or []
        graphql_endpoints = api_analysis.get("graphql_endpoints") or []
        api_endpoints = api_analysis.get("api_endpoints") or []
        api_documentation_urls = api_analysis.get("api_documentation_urls") or []

        found = bool(
            openapi_urls
            or swagger_urls
            or graphql_endpoints
            or api_endpoints
            or api_documentation_urls
        )

        return _CriterionOutcome(
            passed=found,
            details={
                "openapi_urls": openapi_urls,
                "swagger_urls": swagger_urls,
                "graphql": graphql_endpoints,
                "api_endpoints": api_endpoints,
                "api_documentation_urls": api_documentation_urls,
            },
            issue="No API documentation found",
            recommendation="Publish OpenAPI or Swagger documentation for any exposed API.",
        )

    # ------------------------------------------------------------------
    # 7. Internal navigation
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_internal_links(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that the homepage links to other pages on the same site.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        found = bool(evidence.internal_links)
        return _CriterionOutcome(
            passed=found,
            details={"internal_links_count": len(evidence.internal_links)},
            issue="No internal navigation links found",
            recommendation="Add internal links so agents can navigate beyond the homepage.",
        )
