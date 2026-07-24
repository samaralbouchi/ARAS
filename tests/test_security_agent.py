"""Unit tests for :class:`SecurityAgent`.

Covers a fully secure website (HTTPS, HSTS, defensive headers,
declared auth, rate limiting, minimal disclosure), each individual
criterion failing in isolation, and a website with no security
signals at all. The agent consumes only a `WebsiteEvidence` instance
built by hand here — no network access, HTML parsing, or other
evidence-collection tool is exercised by these tests.

It also includes an end-to-end scenario against a real website that
chains the existing `EvidenceCollectorAgent` into the
`SecurityAgent`. That scenario only orchestrates existing
components — it adds no new logic to either agent.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file directly (e.g. from an IDE "Run" button) by
# ensuring the project root is importable, not just the `tests/` folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.evidence_collector import EvidenceCollectorAgent
from agents.security_agent import SecurityAgent
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
        headers={
            "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "WWW-Authenticate": 'Bearer realm="api"',
            "X-RateLimit-Limit": "1000",
            "X-RateLimit-Remaining": "999",
        },
    )


def test_perfect_website_scores_100() -> None:
    """Every criterion passes: the score should be exactly 100."""
    agent = SecurityAgent()

    result = agent.evaluate(_perfect_evidence())
    _print_result("perfect website", result)

    assert result.score == 100.0
    assert all(result.checks.values())
    assert result.issues == []
    assert result.recommendations == []


def test_no_https() -> None:
    """Site served over plain HTTP: only that criterion fails."""
    agent = SecurityAgent()
    evidence = _perfect_evidence()
    evidence.url = "http://www.example.com"

    result = agent.evaluate(evidence)
    _print_result("no https", result)

    assert result.checks["https_enforced"] is False
    assert "not served over HTTPS" in result.issues[0]
    assert result.score == round(5 / 6 * 100, 2)


def test_no_hsts() -> None:
    """No Strict-Transport-Security header: only that criterion fails."""
    agent = SecurityAgent()
    evidence = _perfect_evidence()
    del evidence.headers["Strict-Transport-Security"]

    result = agent.evaluate(evidence)
    _print_result("no hsts", result)

    assert result.checks["hsts_enabled"] is False
    assert "No Strict-Transport-Security" in result.issues[0]
    assert result.score == round(5 / 6 * 100, 2)


def test_insufficient_defensive_headers() -> None:
    """Fewer than 2 defensive headers present: only that criterion fails."""
    agent = SecurityAgent()
    evidence = _perfect_evidence()
    for header in (
        "Content-Security-Policy",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
    ):
        evidence.headers.pop(header, None)

    result = agent.evaluate(evidence)
    _print_result("insufficient defensive headers", result)

    assert result.checks["defensive_headers"] is False
    assert "Too few defensive HTTP headers" in result.issues[0]
    assert result.score == round(5 / 6 * 100, 2)


def test_no_authentication_declared() -> None:
    """No auth-related header present: only that criterion fails."""
    agent = SecurityAgent()
    evidence = _perfect_evidence()
    del evidence.headers["WWW-Authenticate"]

    result = agent.evaluate(evidence)
    _print_result("no authentication declared", result)

    assert result.checks["authentication_declared"] is False
    assert "No authentication mechanism" in result.issues[0]
    assert result.score == round(5 / 6 * 100, 2)


def test_no_rate_limiting() -> None:
    """No rate-limit headers present: only that criterion fails."""
    agent = SecurityAgent()
    evidence = _perfect_evidence()
    del evidence.headers["X-RateLimit-Limit"]
    del evidence.headers["X-RateLimit-Remaining"]

    result = agent.evaluate(evidence)
    _print_result("no rate limiting", result)

    assert result.checks["rate_limiting_declared"] is False
    assert "No rate-limiting headers" in result.issues[0]
    assert result.score == round(5 / 6 * 100, 2)


def test_information_disclosure() -> None:
    """Server header leaks implementation details: only that criterion fails."""
    agent = SecurityAgent()
    evidence = _perfect_evidence()
    evidence.headers["Server"] = "nginx/1.18.0 (Ubuntu)"

    result = agent.evaluate(evidence)
    _print_result("information disclosure", result)

    assert result.checks["minimal_info_disclosure"] is False
    assert "discloses implementation details" in result.issues[0]
    assert result.score == round(5 / 6 * 100, 2)


def test_everything_missing_scores_near_zero() -> None:
    """A bare, empty evidence record should score at (or near) zero.

    Minimal information disclosure trivially passes when no headers
    are present at all, so a fully empty evidence record scores 1/6
    rather than 0.
    """
    agent = SecurityAgent()
    evidence = WebsiteEvidence(url="http://www.example.com")

    result = agent.evaluate(evidence)
    _print_result("everything missing", result)

    assert result.checks["https_enforced"] is False
    assert result.checks["hsts_enabled"] is False
    assert result.checks["defensive_headers"] is False
    assert result.checks["authentication_declared"] is False
    assert result.checks["rate_limiting_declared"] is False
    assert result.checks["minimal_info_disclosure"] is True
    assert result.score == round(1 / 6 * 100, 2)


# ---------------------------------------------------------------------------
# End-to-end scenario: real website -> Evidence Collector -> Security Agent.
# Adds no new logic to either agent; it only orchestrates the two existing
# components.
# ---------------------------------------------------------------------------


def test_real_site_security() -> None:
    """End-to-end: collect real evidence, then evaluate security posture.

    Requires network access.
    """
    evidence = EvidenceCollectorAgent().collect(TARGET_URL)
    result = SecurityAgent().evaluate(evidence)
    _print_result(f"real site: {TARGET_URL}", result)

    assert 0.0 <= result.score <= 100.0
    assert len(result.checks) == 6


if __name__ == "__main__":
    test_perfect_website_scores_100()
    test_no_https()
    test_no_hsts()
    test_insufficient_defensive_headers()
    test_no_authentication_declared()
    test_no_rate_limiting()
    test_information_disclosure()
    test_everything_missing_scores_near_zero()
    test_real_site_security()
    print("All tests passed.")
