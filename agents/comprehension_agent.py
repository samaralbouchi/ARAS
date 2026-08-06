"""Comprehension Agent.

This module is one of the parallel analysis ("judgment") layers of
ARAS. It evaluates how easily an AI agent can parse and understand
the *content* of a website's homepage: its semantic HTML structure,
heading hierarchy, structured data, metadata completeness,
accessibility semantics, and text-to-markup efficiency.

This agent MUST NOT:
    - perform HTTP requests
    - parse HTML
    - discover APIs
    - crawl websites
    - use BeautifulSoup, HttpClient, or any extraction tool

It only reads an already-collected `WebsiteEvidence` snapshot and
turns it into a scored `ComprehensionResult`. Evidence collection
belongs to the Evidence Collector, a separate, earlier layer.

Design notes (v2):
    - Open Graph and internal-navigation checks were removed from
      this agent: they are already scored by `DiscoverabilityAgent`
      and duplicating them here rewarded sites twice for the same
      signal without adding new information.
    - `language_declared` was folded into `metadata_completeness`
      rather than scored twice.
    - The former `json_ld_semantic_understanding` and
      `schema_org_entity_description` checks (bare JSON-LD presence
      vs. presence of a recognized `@type`) were merged into a single
      `schema_org_typed_entities` check, since a JSON-LD block with no
      `@type` is not meaningfully more useful to an agent than no
      JSON-LD at all.
    - The former `content_representation_formats` check was an exact
      duplicate of `structured_data_availability` (same boolean
      logic, different label) and was removed outright.
    - `semantic_html` and `heading_structure` were added: the
      evidence for both (`semantic_tags`, `headings`) was already
      collected but never scored, leaving real structural signals
      unused.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from models.comprehension import ComprehensionResult
from models.evidence import WebsiteEvidence

_CRITERIA_COUNT = 7
_CRITERION_WEIGHT = 100.0 / _CRITERIA_COUNT

# A homepage must use at least this many distinct semantic landmark
# tags to be considered structurally comprehensible.
_MIN_SEMANTIC_TAGS = 3

# Minimum text-to-HTML ratio for content to be considered efficient
# (i.e. not mostly markup/boilerplate).
_MIN_CONTENT_EFFICIENCY_RATIO = 0.10


@dataclass(frozen=True)
class _CriterionOutcome:
    """The result of evaluating a single comprehension criterion.

    Attributes:
        passed: Whether the criterion was satisfied.
        details: Evidence to merge into `ComprehensionResult.details`.
        issue: Message to record if the criterion failed.
        recommendation: Fix to record if the criterion failed.
    """

    passed: bool
    details: dict[str, object]
    issue: str
    recommendation: str


class ComprehensionAgent:
    """Evaluates a website's comprehensibility for AI agents.

    This class holds no evidence-collection logic. It is a pure
    judgment step: it reads a `WebsiteEvidence` snapshot and scores it
    against a fixed set of equally-weighted comprehension criteria.
    """

    def evaluate(self, evidence: WebsiteEvidence) -> ComprehensionResult:
        """Evaluate comprehensibility from already-collected evidence.

        Args:
            evidence: The `WebsiteEvidence` snapshot to evaluate.

        Returns:
            A `ComprehensionResult` with a score in [0, 100], a
            pass/fail breakdown, supporting details, and
            recommendations for every failed criterion.
        """
        result = ComprehensionResult()

        criteria: list[tuple[str, Callable[[WebsiteEvidence], _CriterionOutcome]]] = [
            ("semantic_html", self._evaluate_semantic_html),
            ("heading_structure", self._evaluate_heading_structure),
            ("structured_data_availability", self._evaluate_structured_data_availability),
            ("schema_org_typed_entities", self._evaluate_schema_org_typed_entities),
            ("metadata_completeness", self._evaluate_metadata_completeness),
            ("accessibility_semantics", self._evaluate_accessibility_semantics),
            ("content_efficiency", self._evaluate_content_efficiency),
        ]

        for name, evaluator in criteria:
            self._apply(name, evaluator(evidence), result)

        result.score = self._compute_score(result.checks)
        return result

    # Kept for compatibility with callers written against the
    # earlier `analyze()` name (e.g. `OrchestratorAgent`).
    def analyze(self, evidence: WebsiteEvidence) -> ComprehensionResult:
        return self.evaluate(evidence)

    # ------------------------------------------------------------------
    # Result assembly
    # ------------------------------------------------------------------

    @staticmethod
    def _apply(name: str, outcome: _CriterionOutcome, result: ComprehensionResult) -> None:
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
    # 1. Semantic HTML structure
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_semantic_html(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that the homepage uses a reasonable set of semantic landmark tags.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        tags_used = sorted(evidence.semantic_tags.keys())
        passed = len(tags_used) >= _MIN_SEMANTIC_TAGS

        return _CriterionOutcome(
            passed=passed,
            details={"semantic_tags_used": tags_used},
            issue="Insufficient semantic HTML structure",
            recommendation=(
                "Use semantic landmark elements such as <header>, <nav>, "
                "<main>, and <footer> so agents can parse page structure."
            ),
        )

    # ------------------------------------------------------------------
    # 2. Heading structure
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_heading_structure(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that the homepage declares exactly one <h1>.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        h1_count = evidence.headings.get("h1", 0)
        passed = h1_count == 1

        return _CriterionOutcome(
            passed=passed,
            details={"h1_count": h1_count, "headings": dict(evidence.headings)},
            issue="Missing or improper heading hierarchy (expected exactly one <h1>)",
            recommendation=(
                "Use exactly one <h1> per page, followed by a consistent "
                "h2/h3 hierarchy, so agents can infer document structure."
            ),
        )

    # ------------------------------------------------------------------
    # 3. Structured data availability
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_structured_data_availability(
        evidence: WebsiteEvidence,
    ) -> _CriterionOutcome:
        """Check that some form of structured data (JSON-LD, Microdata, RDFa) is present.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        json_ld_found = len(evidence.json_ld_items) > 0
        microdata_found = len(evidence.microdata_items) > 0
        rdfa_found = len(evidence.rdfa_items) > 0
        passed = json_ld_found or microdata_found or rdfa_found

        return _CriterionOutcome(
            passed=passed,
            details={
                "json_ld_found": json_ld_found,
                "microdata_found": microdata_found,
                "rdfa_found": rdfa_found,
            },
            issue="No structured data found",
            recommendation="Add JSON-LD structured data using Schema.org vocabulary.",
        )

    # ------------------------------------------------------------------
    # 4. Schema.org typed entities
    # ------------------------------------------------------------------

    def _evaluate_schema_org_typed_entities(
        self, evidence: WebsiteEvidence
    ) -> _CriterionOutcome:
        """Check that structured data declares at least one recognized Schema.org type.

        A structured-data block with no `@type` (e.g. malformed or
        incomplete JSON-LD) is not meaningfully more useful to an
        agent than having no structured data at all, so this is
        scored separately from mere presence.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        schema_types = self._extract_schema_types(evidence)
        passed = len(schema_types) > 0

        return _CriterionOutcome(
            passed=passed,
            details={"schema_types": schema_types},
            issue="No Schema.org entities detected",
            recommendation=(
                "Define semantic entities such as Organization, Product, "
                "Article, or FAQ using the schema.org @type property."
            ),
        )

    # ------------------------------------------------------------------
    # 5. Metadata completeness
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_metadata_completeness(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that the homepage declares title, description, and language.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        has_title = bool(evidence.title)
        has_description = bool(evidence.meta_tags.get("description"))
        has_language = bool(evidence.language)
        passed = has_title and has_description and has_language

        missing = [
            label
            for label, present in (
                ("title", has_title),
                ("meta description", has_description),
                ("language", has_language),
            )
            if not present
        ]

        return _CriterionOutcome(
            passed=passed,
            details={
                "title": has_title,
                "description": has_description,
                "language": evidence.language,
            },
            issue=(
                f"Missing metadata information: {', '.join(missing)}"
                if missing
                else ""
            ),
            recommendation=(
                "Add title, meta description, and a lang attribute on the "
                "<html> element."
                if missing
                else ""
            ),
        )

    # ------------------------------------------------------------------
    # 6. Accessibility semantics
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_accessibility_semantics(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that the homepage uses ARIA attributes or form labels.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        passed = bool(evidence.aria_attributes) or evidence.labels_count > 0

        return _CriterionOutcome(
            passed=passed,
            details={
                "aria": evidence.aria_attributes,
                "labels": evidence.labels_count,
                "forms": evidence.forms_count,
            },
            issue="Accessibility semantic information is limited",
            recommendation="Add ARIA attributes and semantic <label> elements.",
        )

    # ------------------------------------------------------------------
    # 7. Content efficiency
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_content_efficiency(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that visible text makes up a reasonable share of the raw HTML.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        ratio = (
            evidence.text_length / evidence.html_length
            if evidence.html_length
            else 0.0
        )
        passed = ratio >= _MIN_CONTENT_EFFICIENCY_RATIO

        return _CriterionOutcome(
            passed=passed,
            details={"text_to_html_ratio": round(ratio, 3)},
            issue="Low text-to-markup ratio: the HTML contains little meaningful text",
            recommendation=(
                "Reduce unnecessary markup and boilerplate so a larger "
                "share of the page is meaningful, extractable text."
            ),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_schema_types(evidence: WebsiteEvidence) -> list[str]:
        """Extract every distinct Schema.org `@type` declared in JSON-LD.

        Args:
            evidence: The evidence snapshot to read JSON-LD items from.

        Returns:
            A de-duplicated list of `@type` values found across all
            JSON-LD entities.
        """
        types: list[str] = []
        for item in evidence.json_ld_items:
            if not isinstance(item, dict) or "@type" not in item:
                continue
            value = item["@type"]
            if isinstance(value, list):
                types.extend(value)
            else:
                types.append(value)
        return list(dict.fromkeys(types))