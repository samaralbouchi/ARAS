"""Unit tests for :class:`DiscoverabilityAgent`.

Covers a perfectly discoverable website, each individual criterion
failing in isolation, and a website with nothing discoverable at all.
The agent consumes only a `WebsiteEvidence` instance built by hand
here — no network access, HTML parsing, or other evidence-collection
tool is exercised by these tests.

It also includes an end-to-end scenario against a real website
(`https://www.mytek.tn`) that chains the existing
`EvidenceCollectorAgent` into the `DiscoverabilityAgent` and renders
the outcome as a PDF report. That scenario only orchestrates existing
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

from agents.discoverability_agent import DiscoverabilityAgent
from agents.evidence_collector import EvidenceCollectorAgent
from models.discoverability import DiscoverabilityResult
from models.evidence import WebsiteEvidence

URL = "https://www.example.com"


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
        robots_txt="User-agent: *\nSitemap: https://www.example.com/sitemap.xml",
        sitemap_xml="<urlset></urlset>",
        llms_txt="# Example\n\n> A sample site.",
        title="Example Site",
        meta_tags={"description": "A sample site for testing."},
        canonical="https://www.example.com/",
        open_graph={"og:title": "Example Site", "og:description": "A sample site."},
        internal_links=["https://www.example.com/about", "https://www.example.com/contact"],
        api_analysis={
            "openapi_urls": ["https://www.example.com/openapi.json"],
            "swagger_urls": [],
            "redoc_urls": [],
            "api_documentation_urls": [],
            "api_endpoints": [],
            "graphql_endpoints": [],
        },
    )


def test_perfect_website_scores_100() -> None:
    """Every criterion passes: the score should be exactly 100."""
    agent = DiscoverabilityAgent()

    result = agent.evaluate(_perfect_evidence())
    _print_result("perfect website", result)

    assert result.score == 100.0
    assert all(result.checks.values())
    assert result.issues == []
    assert result.recommendations == []
    assert result.details["title"] == "Example Site"
    assert result.details["canonical"] == "https://www.example.com/"


def test_missing_robots_txt() -> None:
    """robots.txt absent: only that criterion fails."""
    agent = DiscoverabilityAgent()
    evidence = _perfect_evidence()
    evidence.robots_txt = None

    result = agent.evaluate(evidence)
    _print_result("missing robots.txt", result)

    assert result.checks["robots_txt"] is False
    assert "No robots.txt found" in result.issues
    assert result.score == round(6 / 7 * 100, 2)


def test_missing_sitemap() -> None:
    """sitemap.xml absent: only that criterion fails."""
    agent = DiscoverabilityAgent()
    evidence = _perfect_evidence()
    evidence.sitemap_xml = None

    result = agent.evaluate(evidence)
    _print_result("missing sitemap.xml", result)

    assert result.checks["sitemap"] is False
    assert "No sitemap.xml found" in result.issues
    assert result.score == round(6 / 7 * 100, 2)


def test_missing_llms_txt() -> None:
    """llms.txt absent: only that criterion fails."""
    agent = DiscoverabilityAgent()
    evidence = _perfect_evidence()
    evidence.llms_txt = None

    result = agent.evaluate(evidence)
    _print_result("missing llms.txt", result)

    assert result.checks["llms_txt"] is False
    assert "No llms.txt found" in result.issues
    assert result.score == round(6 / 7 * 100, 2)


def test_no_metadata() -> None:
    """Title, description, and canonical all absent: metadata fails."""
    agent = DiscoverabilityAgent()
    evidence = _perfect_evidence()
    evidence.title = None
    evidence.meta_tags = {}
    evidence.canonical = None

    result = agent.evaluate(evidence)
    _print_result("no metadata", result)

    assert result.checks["metadata"] is False
    assert any("Missing metadata" in issue for issue in result.issues)
    assert result.score == round(6 / 7 * 100, 2)


def test_no_open_graph() -> None:
    """No Open Graph tags: only that criterion fails."""
    agent = DiscoverabilityAgent()
    evidence = _perfect_evidence()
    evidence.open_graph = {}

    result = agent.evaluate(evidence)
    _print_result("no Open Graph", result)

    assert result.checks["open_graph"] is False
    assert "No Open Graph metadata found" in result.issues
    assert result.score == round(6 / 7 * 100, 2)


def test_no_api_discoverability() -> None:
    """No machine-readable API surface: only that criterion fails."""
    agent = DiscoverabilityAgent()
    evidence = _perfect_evidence()
    evidence.api_analysis = {
        "openapi_urls": [],
        "swagger_urls": [],
        "redoc_urls": [],
        "api_documentation_urls": [],
        "api_endpoints": [],
        "graphql_endpoints": [],
    }

    result = agent.evaluate(evidence)
    _print_result("no API discoverability", result)

    assert result.checks["api_discoverability"] is False
    assert "No API documentation found" in result.issues
    assert result.score == round(6 / 7 * 100, 2)


def test_no_internal_links() -> None:
    """No internal navigation links: only that criterion fails."""
    agent = DiscoverabilityAgent()
    evidence = _perfect_evidence()
    evidence.internal_links = []

    result = agent.evaluate(evidence)
    _print_result("no internal links", result)

    assert result.checks["internal_links"] is False
    assert "No internal navigation links found" in result.issues
    assert result.score == round(6 / 7 * 100, 2)


def test_everything_missing_scores_near_zero() -> None:
    """A bare, empty evidence record should score at (or near) zero."""
    agent = DiscoverabilityAgent()
    evidence = WebsiteEvidence(url=URL)

    result = agent.evaluate(evidence)
    _print_result("everything missing", result)

    assert result.score == 0.0
    assert all(passed is False for passed in result.checks.values())
    assert len(result.issues) == 7
    assert len(result.recommendations) == 7


# ---------------------------------------------------------------------------
# End-to-end scenario: real website -> Evidence Collector -> Discoverability
# Agent -> PDF report.
#
# This section adds no logic to either agent; it only orchestrates the two
# existing components and renders their output. `reportlab` is used to build
# the PDF since no PDF library was already part of the project.
# ---------------------------------------------------------------------------

TARGET_URL = "https://www.mytek.tn"
REPORT_PATH = Path(__file__).resolve().parent.parent / "discoverability_report_mytek.pdf"

# Maps each `DiscoverabilityResult.checks` key to its human-readable label
# and the `details` key(s) that best summarize it, used when rendering the
# criteria table in the PDF report.
_CRITERIA_LABELS: dict[str, str] = {
    "robots_txt": "robots.txt",
    "sitemap": "sitemap.xml",
    "llms_txt": "llms.txt",
    "metadata": "Metadata",
    "open_graph": "Open Graph",
    "api_discoverability": "API discoverability",
    "internal_links": "Internal links",
}


def _criterion_detail_summary(name: str, details: dict[str, Any]) -> str:
    """Summarize the supporting evidence for a single criterion.

    Args:
        name: The criterion's key in `DiscoverabilityResult.checks`.
        details: The full `DiscoverabilityResult.details` mapping.

    Returns:
        A short, human-readable description of the evidence backing
        this criterion's pass/fail outcome.
    """
    if name == "robots_txt":
        return f"found={details.get('robots_found')}"
    if name == "sitemap":
        return f"found={details.get('sitemap_found')}"
    if name == "llms_txt":
        return f"found={details.get('llms_found')}"
    if name == "metadata":
        return (
            f"title={bool(details.get('title'))}, "
            f"description={details.get('has_description')}, "
            f"canonical={bool(details.get('canonical'))}"
        )
    if name == "open_graph":
        return f"tags={len(details.get('open_graph_tags') or [])}"
    if name == "api_discoverability":
        total = (
            len(details.get("openapi_urls") or [])
            + len(details.get("swagger_urls") or [])
            + len(details.get("graphql") or [])
            + len(details.get("api_endpoints") or [])
            + len(details.get("api_documentation_urls") or [])
        )
        return f"surfaces found={total}"
    if name == "internal_links":
        return f"count={details.get('internal_links_count')}"
    return ""


def _generate_pdf_report(
    url: str, result: DiscoverabilityResult, output_path: Path
) -> None:
    """Render a `DiscoverabilityResult` as a PDF report.

    Args:
        url: The website URL that was assessed.
        result: The evaluation produced by `DiscoverabilityAgent.evaluate`.
        output_path: Filesystem path the PDF should be written to.
    """
    styles = getSampleStyleSheet()
    heading_style = ParagraphStyle(
        "SectionHeading", parent=styles["Heading2"], spaceBefore=12, spaceAfter=6
    )

    passed_count = sum(1 for outcome in result.checks.values() if outcome)
    failed_count = len(result.checks) - passed_count

    story: list[Any] = [
        Paragraph("ARAS Discoverability Assessment Report", styles["Title"]),
        Spacer(1, 0.5 * cm),
        Paragraph(f"<b>Website URL:</b> {url}", styles["Normal"]),
        Paragraph(
            f"<b>Analysis date:</b> {datetime.now(timezone.utc).isoformat()}",
            styles["Normal"],
        ),
        Paragraph("<b>Agent used:</b> Discoverability Agent", styles["Normal"]),
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

    # Section 3: Evidence details
    story.append(Paragraph("3. Evidence Details", heading_style))
    details = result.details
    api_details = (
        f"OpenAPI={details.get('openapi_urls') or []}, "
        f"Swagger={details.get('swagger_urls') or []}, "
        f"GraphQL={details.get('graphql') or []}, "
        f"API endpoints={details.get('api_endpoints') or []}"
    )
    evidence_lines = [
        f"robots.txt present: {details.get('robots_found')}",
        f"sitemap.xml present: {details.get('sitemap_found')}",
        f"llms.txt present: {details.get('llms_found')}",
        f"Title: {details.get('title')}",
        f"Canonical URL: {details.get('canonical')}",
        f"Open Graph tags: {details.get('open_graph_tags') or []}",
        f"API detected: {api_details}",
    ]
    story.append(
        ListFlowable(
            [ListItem(Paragraph(line, styles["Normal"])) for line in evidence_lines],
            bulletType="bullet",
        )
    )

    # Section 4: Issues
    story.append(Paragraph("4. Issues", heading_style))
    if result.issues:
        story.append(
            ListFlowable(
                [ListItem(Paragraph(issue, styles["Normal"])) for issue in result.issues],
                bulletType="bullet",
            )
        )
    else:
        story.append(Paragraph("No issues found.", styles["Normal"]))

    # Section 5: Recommendations
    story.append(Paragraph("5. Recommendations", heading_style))
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


def _print_console_summary(url: str, result: DiscoverabilityResult, report_path: Path) -> None:
    """Print the human-facing summary of a real-site assessment run.

    Args:
        url: The website URL that was assessed.
        result: The evaluation produced by `DiscoverabilityAgent.evaluate`.
        report_path: Filesystem path the PDF report was written to.
    """
    # Windows consoles often default to a legacy code page (cp1252) that
    # cannot encode ✓/✗; fall back to ASCII markers rather than crash.
    try:
        "✓".encode(sys.stdout.encoding or "utf-8")
        pass_mark, fail_mark = "✓", "✗"
    except UnicodeEncodeError:
        pass_mark, fail_mark = "[PASS]", "[FAIL]"

    print("=" * 30)
    print("ARAS Discoverability Report")
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


def test_mytek_real_site_discoverability_report() -> None:
    """End-to-end: collect real evidence, evaluate it, render a PDF report.

    Chains the existing `EvidenceCollectorAgent` into the existing
    `DiscoverabilityAgent` against a live website, then renders the
    resulting `DiscoverabilityResult` as a PDF. Requires network access.
    """
    evidence = EvidenceCollectorAgent().collect(TARGET_URL)
    result = DiscoverabilityAgent().evaluate(evidence)
    _print_result(f"real site: {TARGET_URL}", result)

    _generate_pdf_report(TARGET_URL, result, REPORT_PATH)
    _print_console_summary(TARGET_URL, result, REPORT_PATH)

    assert REPORT_PATH.exists()
    assert 0.0 <= result.score <= 100.0
    assert len(result.checks) == 7


if __name__ == "__main__":
    test_perfect_website_scores_100()
    test_missing_robots_txt()
    test_missing_sitemap()
    test_missing_llms_txt()
    test_no_metadata()
    test_no_open_graph()
    test_no_api_discoverability()
    test_no_internal_links()
    test_everything_missing_scores_near_zero()
    test_mytek_real_site_discoverability_report()
    print("All tests passed.")
