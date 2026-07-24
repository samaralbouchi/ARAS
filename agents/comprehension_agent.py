"""Comprehension Agent.

This module is one of the parallel analysis ("judgment") layers of
ARAS. It evaluates how easily an AI agent can parse and understand the
*content* of a website's homepage: semantic HTML structure, heading
hierarchy, structured data, declared language, image accessibility,
and text-to-markup (token) efficiency.

This agent MUST NOT:
    - perform HTTP requests
    - parse HTML
    - discover APIs
    - crawl websites
    - use BeautifulSoup, HttpClient, or any extraction tool

It only reads an already-collected `WebsiteEvidence` snapshot and
turns it into a scored `ComprehensionResult`. Evidence collection
belongs to the Evidence Collector, a separate, earlier layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from models.comprehension import ComprehensionResult
from models.evidence import WebsiteEvidence

_CRITERIA_COUNT = 6
_CRITERION_WEIGHT = 100.0 / _CRITERIA_COUNT

# Minimum fraction of <img> elements that must carry alt text.
_MIN_IMAGE_ALT_COVERAGE = 0.8

# Minimum visible-text-to-raw-HTML ratio. Below this, a page is
# considered markup-heavy relative to its actual content, which raises
# the token cost of consuming it for an LLM-based agent.
_MIN_TEXT_TO_HTML_RATIO = 0.15

# Minimum number of distinct HTML5 semantic elements considered
# "meaningful" semantic structure.
_MIN_SEMANTIC_TAGS = 3


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
    """Evaluates how easily an AI agent can understand a website's content.

    This class holds no evidence-collection logic. It is a pure
    judgment step: it reads a `WebsiteEvidence` snapshot and scores it
    against a fixed set of equally-weighted comprehension criteria.
    """

    def evaluate(self, evidence: WebsiteEvidence) -> ComprehensionResult:
        """Evaluate comprehension from already-collected evidence.

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
            ("structured_data", self._evaluate_structured_data),
            ("language_declared", self._evaluate_language_declared),
            ("image_alt_text", self._evaluate_image_alt_text),
            ("token_efficiency", self._evaluate_token_efficiency),
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
        name: str, outcome: _CriterionOutcome, result: ComprehensionResult
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
    # 1. Semantic HTML
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_semantic_html(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that the homepage uses a meaningful set of semantic HTML5 tags.

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
            issue="Insufficient semantic HTML structure (mostly generic <div>s)",
            recommendation=(
                "Use semantic HTML5 elements (header, nav, main, article, "
                "section, footer) instead of generic <div>s so agents can "
                "identify page regions without guessing."
            ),
        )

    # ------------------------------------------------------------------
    # 2. Heading hierarchy
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_heading_structure(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check for exactly one <h1> plus at least one supporting subheading.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        headings = evidence.headings
        h1_count = headings.get("h1", 0)
        has_single_h1 = h1_count == 1
        has_subheadings = any(headings.get(f"h{level}", 0) > 0 for level in range(2, 7))
        passed = has_single_h1 and has_subheadings

        return _CriterionOutcome(
            passed=passed,
            details={"headings": dict(headings), "h1_count": h1_count},
            issue="Missing or improper heading hierarchy",
            recommendation=(
                "Use exactly one <h1> per page and structure the remaining "
                "content with <h2>-<h6> subheadings."
            ),
        )

    # ------------------------------------------------------------------
    # 3. Structured data
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_structured_data(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that some structured data (JSON-LD, Microdata, or RDFa) exists.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        structured_data = evidence.structured_data
        json_ld = structured_data.get("json-ld") or []
        microdata = structured_data.get("microdata") or []
        rdfa = structured_data.get("rdfa") or []
        total = len(json_ld) + len(microdata) + len(rdfa)
        passed = total > 0

        return _CriterionOutcome(
            passed=passed,
            details={
                "json_ld_count": len(json_ld),
                "microdata_count": len(microdata),
                "rdfa_count": len(rdfa),
            },
            issue="No structured data (JSON-LD, Microdata, or RDFa) found",
            recommendation=(
                "Add JSON-LD structured data (schema.org) to describe page "
                "content in a machine-readable way."
            ),
        )

    # ------------------------------------------------------------------
    # 4. Declared language
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_language_declared(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that the homepage declares a language via <html lang="...">.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        passed = bool(evidence.language)
        return _CriterionOutcome(
            passed=passed,
            details={"language": evidence.language},
            issue="No language declared on the <html> tag",
            recommendation='Add a lang attribute to the <html> tag (e.g. lang="en").',
        )

    # ------------------------------------------------------------------
    # 5. Image alt-text coverage
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_image_alt_text(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that most images carry descriptive alt text.

        A page with no images at all trivially passes this criterion.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        total = evidence.images_total
        with_alt = evidence.images_with_alt
        coverage = (with_alt / total) if total else 1.0
        passed = total == 0 or coverage >= _MIN_IMAGE_ALT_COVERAGE

        return _CriterionOutcome(
            passed=passed,
            details={
                "images_total": total,
                "images_with_alt": with_alt,
                "alt_coverage": round(coverage, 2),
            },
            issue="Many images are missing alt text",
            recommendation=(
                "Add descriptive alt text to images so agents can understand "
                "visual content without rendering it."
            ),
        )

    # ------------------------------------------------------------------
    # 6. Token efficiency (text-to-HTML ratio)
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_token_efficiency(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that visible text makes up a reasonable share of the raw HTML.

        A low ratio indicates a page heavy with markup, inline styles,
        or boilerplate relative to its actual content, which increases
        the token cost of consuming it for an LLM-based agent.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        html_length = evidence.html_length
        text_length = evidence.text_length
        ratio = (text_length / html_length) if html_length else 0.0
        passed = html_length > 0 and ratio >= _MIN_TEXT_TO_HTML_RATIO

        return _CriterionOutcome(
            passed=passed,
            details={
                "text_length": text_length,
                "html_length": html_length,
                "text_to_html_ratio": round(ratio, 3),
            },
            issue=(
                "Low text-to-markup ratio: the page is heavy with markup "
                "relative to its actual content, increasing token cost for agents"
            ),
            recommendation=(
                "Reduce unnecessary wrapper elements and inline styles to "
                "improve the text-to-markup ratio for LLM consumption."
            ),
        )
