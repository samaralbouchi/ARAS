"""Security Agent.

This module is one of the parallel analysis ("judgment") layers of
ARAF. It evaluates how safely an autonomous AI agent could interact
with a website: whether traffic is encrypted and protected in
transit (HTTPS, HSTS), whether an authentication mechanism is
declared for sensitive operations, whether the site protects itself
against abusive automated traffic (rate limiting), and whether basic
defensive HTTP response headers are present.

This agent MUST NOT:
    - perform HTTP requests
    - parse HTML
    - discover APIs
    - crawl websites
    - use BeautifulSoup, HttpClient, or any extraction tool

It only reads an already-collected `WebsiteEvidence` snapshot and
turns it into a scored `SecurityResult`. Evidence collection belongs
to the Evidence Collector, a separate, earlier layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from models.evidence import WebsiteEvidence
from models.security import SecurityResult

_CRITERIA_COUNT = 6
_CRITERION_WEIGHT = 100.0 / _CRITERIA_COUNT

# Response headers considered when checking for defensive HTTP headers.
# At least this many distinct headers must be present to pass.
_MIN_DEFENSIVE_HEADERS = 2
_DEFENSIVE_HEADERS = (
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "permissions-policy",
)

# Header names that indicate an authentication mechanism is in place.
_AUTH_HEADERS = ("www-authenticate", "x-api-key", "authorization")

# Header names that indicate the site enforces rate limiting.
_RATE_LIMIT_HEADERS = (
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "ratelimit-limit",
    "retry-after",
)

# Header names that leak implementation detail to would-be attackers
# (and to agents that might otherwise infer trust from vagueness).
_INFO_DISCLOSURE_HEADERS = ("server", "x-powered-by")


@dataclass(frozen=True)
class _CriterionOutcome:
    """The result of evaluating a single security criterion.

    Attributes:
        passed: Whether the criterion was satisfied.
        details: Evidence to merge into `SecurityResult.details`.
        issue: Message to record if the criterion failed.
        recommendation: Fix to record if the criterion failed.
    """

    passed: bool
    details: dict[str, object]
    issue: str
    recommendation: str


class SecurityAgent:
    """Evaluates a website's security posture for AI agents.

    This class holds no evidence-collection logic. It is a pure
    judgment step: it reads a `WebsiteEvidence` snapshot and scores it
    against a fixed set of equally-weighted security criteria.
    """

    def evaluate(self, evidence: WebsiteEvidence) -> SecurityResult:
        """Evaluate security posture from already-collected evidence.

        Args:
            evidence: The `WebsiteEvidence` snapshot to evaluate.

        Returns:
            A `SecurityResult` with a score in [0, 100], a pass/fail
            breakdown, supporting details, and recommendations for
            every failed criterion.
        """
        result = SecurityResult()

        criteria: list[tuple[str, Callable[[WebsiteEvidence], _CriterionOutcome]]] = [
            ("https_enforced", self._evaluate_https_enforced),
            ("hsts_enabled", self._evaluate_hsts_enabled),
            ("defensive_headers", self._evaluate_defensive_headers),
            ("authentication_declared", self._evaluate_authentication_declared),
            ("rate_limiting_declared", self._evaluate_rate_limiting_declared),
            ("minimal_info_disclosure", self._evaluate_minimal_info_disclosure),
        ]

        for name, evaluator in criteria:
            self._apply(name, evaluator(evidence), result)

        result.score = self._compute_score(result.checks)
        return result

    # ------------------------------------------------------------------
    # Result assembly
    # ------------------------------------------------------------------

    @staticmethod
    def _apply(name: str, outcome: _CriterionOutcome, result: SecurityResult) -> None:
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

    @staticmethod
    def _lower_headers(evidence: WebsiteEvidence) -> dict[str, str]:
        """Return response headers with lower-cased keys for case-insensitive lookup.

        Args:
            evidence: The evidence snapshot to read headers from.

        Returns:
            A copy of `evidence.headers` keyed by lower-cased header name.
        """
        return {str(key).lower(): value for key, value in evidence.headers.items()}

    # ------------------------------------------------------------------
    # 1. HTTPS enforced
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_https_enforced(evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that the site is served over HTTPS.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        passed = evidence.url.lower().startswith("https://")

        return _CriterionOutcome(
            passed=passed,
            details={"url_scheme": "https" if passed else "http"},
            issue="Site is not served over HTTPS",
            recommendation=(
                "Serve the site exclusively over HTTPS and redirect all "
                "HTTP traffic so agent-to-site communication is encrypted."
            ),
        )

    # ------------------------------------------------------------------
    # 2. HSTS
    # ------------------------------------------------------------------

    def _evaluate_hsts_enabled(self, evidence: WebsiteEvidence) -> _CriterionOutcome:
        """Check that the HTTP Strict-Transport-Security header is present.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        headers = self._lower_headers(evidence)
        passed = "strict-transport-security" in headers

        return _CriterionOutcome(
            passed=passed,
            details={"hsts_header": headers.get("strict-transport-security")},
            issue="No Strict-Transport-Security (HSTS) header found",
            recommendation=(
                "Send a Strict-Transport-Security header so clients and "
                "agents always connect over HTTPS, even on the first request."
            ),
        )

    # ------------------------------------------------------------------
    # 3. Defensive HTTP headers
    # ------------------------------------------------------------------

    def _evaluate_defensive_headers(
        self, evidence: WebsiteEvidence
    ) -> _CriterionOutcome:
        """Check that a reasonable set of defensive HTTP headers is present.

        Considers Content-Security-Policy, X-Content-Type-Options,
        X-Frame-Options, Referrer-Policy, and Permissions-Policy.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        headers = self._lower_headers(evidence)
        present = sorted(name for name in _DEFENSIVE_HEADERS if name in headers)
        passed = len(present) >= _MIN_DEFENSIVE_HEADERS

        return _CriterionOutcome(
            passed=passed,
            details={"defensive_headers_present": present},
            issue="Too few defensive HTTP headers present",
            recommendation=(
                "Add defensive headers such as Content-Security-Policy, "
                "X-Content-Type-Options, X-Frame-Options, and Referrer-Policy."
            ),
        )

    # ------------------------------------------------------------------
    # 4. Authentication mechanism declared
    # ------------------------------------------------------------------

    def _evaluate_authentication_declared(
        self, evidence: WebsiteEvidence
    ) -> _CriterionOutcome:
        """Check that an authentication mechanism (OAuth, JWT, API key) is declared.

        Looks for headers that signal an authentication scheme is in
        place, such as `WWW-Authenticate`, `X-Api-Key`, or
        `Authorization`.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        headers = self._lower_headers(evidence)
        present = sorted(name for name in _AUTH_HEADERS if name in headers)
        passed = bool(present)

        return _CriterionOutcome(
            passed=passed,
            details={"auth_headers_present": present},
            issue="No authentication mechanism (OAuth, JWT, API key) declared",
            recommendation=(
                "Declare an authentication scheme (e.g. OAuth 2.0, JWT "
                "Bearer tokens, or an API key via `WWW-Authenticate`) so "
                "agents know how to authenticate for protected actions."
            ),
        )

    # ------------------------------------------------------------------
    # 5. Rate limiting declared
    # ------------------------------------------------------------------

    def _evaluate_rate_limiting_declared(
        self, evidence: WebsiteEvidence
    ) -> _CriterionOutcome:
        """Check that rate-limiting headers are present.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        headers = self._lower_headers(evidence)
        present = sorted(name for name in _RATE_LIMIT_HEADERS if name in headers)
        passed = bool(present)

        return _CriterionOutcome(
            passed=passed,
            details={"rate_limit_headers_present": present},
            issue="No rate-limiting headers found",
            recommendation=(
                "Expose rate-limit headers (e.g. X-RateLimit-Limit, "
                "X-RateLimit-Remaining, Retry-After) so agents can throttle "
                "themselves instead of being abruptly blocked."
            ),
        )

    # ------------------------------------------------------------------
    # 6. Minimal information disclosure
    # ------------------------------------------------------------------

    def _evaluate_minimal_info_disclosure(
        self, evidence: WebsiteEvidence
    ) -> _CriterionOutcome:
        """Check that the server does not over-share implementation details.

        Headers like `Server` or `X-Powered-By` reveal software and
        versions that make targeted exploitation easier.

        Args:
            evidence: The evidence snapshot to evaluate.

        Returns:
            The outcome of this criterion.
        """
        headers = self._lower_headers(evidence)
        leaking = sorted(name for name in _INFO_DISCLOSURE_HEADERS if name in headers)
        passed = not leaking

        return _CriterionOutcome(
            passed=passed,
            details={"info_disclosure_headers_present": leaking},
            issue="Server discloses implementation details via response headers",
            recommendation=(
                "Remove or obfuscate headers like Server and X-Powered-By "
                "to avoid revealing software and versions to attackers."
            ),
        )
