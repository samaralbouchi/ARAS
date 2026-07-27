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
from agents.interaction_agent import InteractionAgent
from models.evidence import WebsiteEvidence
from models.interaction import InteractionResult

URL = "https://www.example.com"
TARGET_URL = "https://www.bpifrance.fr/"
REPORT_PATH = Path(__file__).resolve().parent.parent / "interaction_report_bpifrance.pdf"


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
# Agent -> PDF report.
#
# This section adds no logic to either agent; it only orchestrates the two
# existing components and renders their output. `reportlab` is used to build
# the PDF since no PDF library was already part of the project.
# ---------------------------------------------------------------------------

# Maps each `InteractionResult.checks` key to its human-readable label, used
# when rendering the criteria table in the PDF report.
_CRITERIA_LABELS: dict[str, str] = {
    "mcp_endpoint": "MCP endpoint",
    "mcp_tools_and_resources": "MCP tools/resources",
    "openapi_spec": "OpenAPI specification",
    "swagger_documentation": "Swagger/ReDoc docs",
    "agent_actionability": "Agent actionability",
}


def _criterion_detail_summary(name: str, details: dict[str, Any]) -> str:
    """Summarize the supporting evidence for a single criterion.

    Args:
        name: The criterion's key in `InteractionResult.checks`.
        details: The full `InteractionResult.details` mapping.

    Returns:
        A short, human-readable description of the evidence backing
        this criterion's pass/fail outcome.
    """
    if name == "mcp_endpoint":
        return f"endpoints={details.get('mcp_endpoints') or []}"
    if name == "mcp_tools_and_resources":
        return (
            f"tools={details.get('mcp_tools') or []}, "
            f"resources={details.get('mcp_resources') or []}"
        )
    if name == "openapi_spec":
        return f"urls={details.get('openapi_urls') or []}"
    if name == "swagger_documentation":
        return (
            f"swagger={details.get('swagger_urls') or []}, "
            f"redoc={details.get('redoc_urls') or []}"
        )
    if name == "agent_actionability":
        return (
            f"api={details.get('api_endpoints') or []}, "
            f"graphql={details.get('graphql_endpoints') or []}, "
            f"mcp={details.get('callable_mcp_endpoints') or []}"
        )
    return ""


def _generate_pdf_report(
    url: str, result: InteractionResult, output_path: Path
) -> None:
    """Render an `InteractionResult` as a PDF report.

    Args:
        url: The website URL that was assessed.
        result: The evaluation produced by `InteractionAgent.evaluate`.
        output_path: Filesystem path the PDF should be written to.
    """
    styles = getSampleStyleSheet()
    heading_style = ParagraphStyle(
        "SectionHeading", parent=styles["Heading2"], spaceBefore=12, spaceAfter=6
    )

    passed_count = sum(1 for outcome in result.checks.values() if outcome)
    failed_count = len(result.checks) - passed_count

    story: list[Any] = [
        Paragraph("ARAS Interaction Assessment Report", styles["Title"]),
        Spacer(1, 0.5 * cm),
        Paragraph(f"<b>Website URL:</b> {url}", styles["Normal"]),
        Paragraph(
            f"<b>Analysis date:</b> {datetime.now(timezone.utc).isoformat()}",
            styles["Normal"],
        ),
        Paragraph("<b>Agent used:</b> Interaction Agent", styles["Normal"]),
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


def _print_console_summary(url: str, result: InteractionResult, report_path: Path) -> None:
    """Print the human-facing summary of a real-site assessment run.

    Args:
        url: The website URL that was assessed.
        result: The evaluation produced by `InteractionAgent.evaluate`.
        report_path: Filesystem path the PDF report was written to.
    """
    try:
        "✓".encode(sys.stdout.encoding or "utf-8")
        pass_mark, fail_mark = "✓", "✗"
    except UnicodeEncodeError:
        pass_mark, fail_mark = "[PASS]", "[FAIL]"

    print("=" * 30)
    print("ARAS Interaction Report")
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


def test_real_site_interaction() -> None:
    """End-to-end: collect real evidence, evaluate it, render a PDF report.

    Chains the existing `EvidenceCollectorAgent` into the existing
    `InteractionAgent` against a live website, then renders the
    resulting `InteractionResult` as a PDF. Requires network access.
    """
    evidence = EvidenceCollectorAgent().collect(TARGET_URL)
    result = InteractionAgent().evaluate(evidence)
    _print_result(f"real site: {TARGET_URL}", result)

    _generate_pdf_report(TARGET_URL, result, REPORT_PATH)
    _print_console_summary(TARGET_URL, result, REPORT_PATH)

    assert REPORT_PATH.exists()
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