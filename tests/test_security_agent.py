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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow running this file directly (e.g. from an IDE "Run" button) by
# ensuring the project root is importable, not just the `tests/` folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from agents.evidence_collector import EvidenceCollectorAgent
from agents.security_agent import SecurityAgent
from models.evidence import WebsiteEvidence
from models.security import SecurityResult

URL = "https://www.example.com"
TARGET_URL = "https://www.bpifrance.fr/"
REPORT_PATH = Path(__file__).resolve().parent.parent / "security_report_bpifrance.pdf"


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
# End-to-end scenario: real website -> Evidence Collector -> Security Agent
# -> PDF report.
#
# This section adds no logic to either agent; it only orchestrates the two
# existing components and renders their output. `reportlab` is used to build
# the PDF since no PDF library was already part of the project.
# ---------------------------------------------------------------------------

# Maps each `SecurityResult.checks` key to its human-readable label, used
# when rendering the criteria table in the PDF report.
_CRITERIA_LABELS: dict[str, str] = {
    "https_enforced": "HTTPS enforced",
    "hsts_enabled": "HSTS enabled",
    "defensive_headers": "Defensive HTTP headers",
    "authentication_declared": "Authentication declared",
    "rate_limiting_declared": "Rate limiting declared",
    "minimal_info_disclosure": "Minimal info disclosure",
}


def _criterion_detail_summary(name: str, details: dict[str, Any]) -> str:
    """Summarize the supporting evidence for a single criterion.

    Args:
        name: The criterion's key in `SecurityResult.checks`.
        details: The full `SecurityResult.details` mapping.

    Returns:
        A short, human-readable description of the evidence backing
        this criterion's pass/fail outcome.
    """
    if name == "https_enforced":
        return f"scheme={details.get('url_scheme')}"
    if name == "hsts_enabled":
        return f"header={details.get('hsts_header')}"
    if name == "defensive_headers":
        return f"present={details.get('defensive_headers_present') or []}"
    if name == "authentication_declared":
        return f"present={details.get('auth_headers_present') or []}"
    if name == "rate_limiting_declared":
        return f"present={details.get('rate_limit_headers_present') or []}"
    if name == "minimal_info_disclosure":
        return f"leaking={details.get('info_disclosure_headers_present') or []}"
    return ""


def _generate_pdf_report(
    url: str, result: SecurityResult, output_path: Path
) -> None:
    """Render a `SecurityResult` as a PDF report.

    Args:
        url: The website URL that was assessed.
        result: The evaluation produced by `SecurityAgent.evaluate`.
        output_path: Filesystem path the PDF should be written to.
    """
    styles = getSampleStyleSheet()
    heading_style = ParagraphStyle(
        "SectionHeading", parent=styles["Heading2"], spaceBefore=12, spaceAfter=6
    )

    passed_count = sum(1 for outcome in result.checks.values() if outcome)
    failed_count = len(result.checks) - passed_count

    story: list[Any] = [
        Paragraph("ARAS Security Assessment Report", styles["Title"]),
        Spacer(1, 0.5 * cm),
        Paragraph(f"<b>Website URL:</b> {url}", styles["Normal"]),
        Paragraph(
            f"<b>Analysis date:</b> {datetime.now(timezone.utc).isoformat()}",
            styles["Normal"],
        ),
        Paragraph("<b>Agent used:</b> Security Agent", styles["Normal"]),
    ]

    # Section 1: Overall score
    story.append(Paragraph("1. Overall Score", heading_style))
    story.append(Paragraph(f"<b>Score:</b> {result.score}/100", styles["Normal"]))
    story.append(Paragraph(f"<b>Criteria passed:</b> {passed_count}", styles["Normal"]))
    story.append(Paragraph(f"<b>Criteria failed:</b> {failed_count}", styles["Normal"]))

    # Section 2: Criteria evaluation table
    story.append(Paragraph("2. Criteria Evaluation", heading_style))
    table_data = [["Criterion", "Status", "Details"]]
    for name, label in _CRITERIA_LABELS.items():
        status = "PASS" if result.checks.get(name) else "FAIL"
        table_data.append([label, status, _criterion_detail_summary(name, result.details)])

    criteria_table = Table(table_data, colWidths=[5 * cm, 2.5 * cm, 8.5 * cm])
    criteria_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E3440")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story.append(criteria_table)

    # Section 3: Issues
    story.append(Paragraph("3. Issues", heading_style))
    if result.issues:
        story.append(
            ListFlowable(
                [ListItem(Paragraph(issue, styles["Normal"])) for issue in result.issues],
                bulletType="bullet",
            )
        )
    else:
        story.append(Paragraph("No issues found.", styles["Normal"]))

    # Section 4: Recommendations
    story.append(Paragraph("4. Recommendations", heading_style))
    if result.recommendations:
        story.append(
            ListFlowable(
                [
                    ListItem(Paragraph(recommendation, styles["Normal"]))
                    for recommendation in result.recommendations
                ],
                bulletType="bullet",
            )
        )
    else:
        story.append(Paragraph("No recommendations.", styles["Normal"]))

    SimpleDocTemplate(str(output_path), pagesize=A4).build(story)


def _print_console_summary(url: str, result: SecurityResult, report_path: Path) -> None:
    """Print the human-facing summary of a real-site assessment run.

    Args:
        url: The website URL that was assessed.
        result: The evaluation produced by `SecurityAgent.evaluate`.
        report_path: Filesystem path the PDF report was written to.
    """
    try:
        "✓".encode(sys.stdout.encoding or "utf-8")
        pass_mark, fail_mark = "✓", "✗"
    except UnicodeEncodeError:
        pass_mark, fail_mark = "[PASS]", "[FAIL]"

    print("=" * 30)
    print("ARAS Security Report")
    print(f"Website: {url}")
    print()
    print(f"Score: {result.score}/100")
    print()
    print("Checks:")
    for name, label in _CRITERIA_LABELS.items():
        mark = pass_mark if result.checks.get(name) else fail_mark
        print(f"{mark} {label}")
    print()
    print("PDF generated:")
    print(report_path)
    print("=" * 30)


def test_real_site_security() -> None:
    """End-to-end: collect real evidence, evaluate it, render a PDF report.

    Chains the existing `EvidenceCollectorAgent` into the existing
    `SecurityAgent` against a live website, then renders the resulting
    `SecurityResult` as a PDF. Requires network access.
    """
    evidence = EvidenceCollectorAgent().collect(TARGET_URL)
    result = SecurityAgent().evaluate(evidence)
    _print_result(f"real site: {TARGET_URL}", result)

    _generate_pdf_report(TARGET_URL, result, REPORT_PATH)
    _print_console_summary(TARGET_URL, result, REPORT_PATH)

    assert REPORT_PATH.exists()
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