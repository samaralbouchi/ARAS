"""Unit tests for :class:`ComprehensionAgent`.

Covers a perfectly comprehensible website, each individual criterion
failing in isolation, and a website with nothing comprehensible at
all. The agent consumes only a `WebsiteEvidence` instance built by
hand here — no network access, HTML parsing, or other
evidence-collection tool is exercised by these tests.

It also includes an end-to-end scenario against a real website that
chains the existing `EvidenceCollectorAgent` into the
`ComprehensionAgent`. That scenario only orchestrates existing
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

from agents.comprehension_agent import ComprehensionAgent
from agents.evidence_collector import EvidenceCollectorAgent
from models.comprehension import ComprehensionResult
from models.evidence import WebsiteEvidence

URL = "https://www.example.com"
TARGET_URL = "https://www.bpifrance.fr/"
REPORT_PATH = Path(__file__).resolve().parent.parent / "comprehension_report_bpifrance.pdf"


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
        language="en",
        semantic_tags={"header": 1, "nav": 1, "main": 1, "footer": 1},
        headings={"h1": 1, "h2": 4, "h3": 2},
        structured_data={
            "json-ld": [{"@type": "Organization"}],
            "microdata": [],
            "rdfa": [],
        },
        images_total=10,
        images_with_alt=9,
        text_length=3000,
        html_length=10000,
    )


def test_perfect_website_scores_100() -> None:
    """Every criterion passes: the score should be exactly 100."""
    agent = ComprehensionAgent()

    result = agent.evaluate(_perfect_evidence())
    _print_result("perfect website", result)

    assert result.score == 100.0
    assert all(result.checks.values())
    assert result.issues == []
    assert result.recommendations == []
    assert result.details["language"] == "en"


def test_insufficient_semantic_html() -> None:
    """Fewer than 3 semantic tags used: only that criterion fails."""
    agent = ComprehensionAgent()
    evidence = _perfect_evidence()
    evidence.semantic_tags = {"nav": 1}

    result = agent.evaluate(evidence)
    _print_result("insufficient semantic HTML", result)

    assert result.checks["semantic_html"] is False
    assert "Insufficient semantic HTML structure" in result.issues[0]
    assert result.score == round(5 / 6 * 100, 2)


def test_missing_h1() -> None:
    """No <h1> at all: heading structure fails."""
    agent = ComprehensionAgent()
    evidence = _perfect_evidence()
    evidence.headings = {"h2": 4, "h3": 2}

    result = agent.evaluate(evidence)
    _print_result("missing h1", result)

    assert result.checks["heading_structure"] is False
    assert "Missing or improper heading hierarchy" in result.issues
    assert result.score == round(5 / 6 * 100, 2)


def test_duplicate_h1() -> None:
    """More than one <h1>: heading structure fails."""
    agent = ComprehensionAgent()
    evidence = _perfect_evidence()
    evidence.headings = {"h1": 2, "h2": 4}

    result = agent.evaluate(evidence)
    _print_result("duplicate h1", result)

    assert result.checks["heading_structure"] is False
    assert result.score == round(5 / 6 * 100, 2)


def test_no_structured_data() -> None:
    """No JSON-LD, Microdata, or RDFa: only that criterion fails."""
    agent = ComprehensionAgent()
    evidence = _perfect_evidence()
    evidence.structured_data = {"json-ld": [], "microdata": [], "rdfa": []}

    result = agent.evaluate(evidence)
    _print_result("no structured data", result)

    assert result.checks["structured_data"] is False
    assert "No structured data" in result.issues[0]
    assert result.score == round(5 / 6 * 100, 2)


def test_no_language_declared() -> None:
    """No <html lang="..."> attribute: only that criterion fails."""
    agent = ComprehensionAgent()
    evidence = _perfect_evidence()
    evidence.language = None

    result = agent.evaluate(evidence)
    _print_result("no language declared", result)

    assert result.checks["language_declared"] is False
    assert "No language declared" in result.issues[0]
    assert result.score == round(5 / 6 * 100, 2)


def test_poor_image_alt_coverage() -> None:
    """Most images missing alt text: only that criterion fails."""
    agent = ComprehensionAgent()
    evidence = _perfect_evidence()
    evidence.images_total = 10
    evidence.images_with_alt = 2

    result = agent.evaluate(evidence)
    _print_result("poor image alt coverage", result)

    assert result.checks["image_alt_text"] is False
    assert "missing alt text" in result.issues[0]
    assert result.score == round(5 / 6 * 100, 2)


def test_no_images_trivially_passes_alt_text() -> None:
    """A page with zero images should not be penalized for alt-text coverage."""
    agent = ComprehensionAgent()
    evidence = _perfect_evidence()
    evidence.images_total = 0
    evidence.images_with_alt = 0

    result = agent.evaluate(evidence)
    _print_result("no images at all", result)

    assert result.checks["image_alt_text"] is True
    assert result.score == 100.0


def test_low_token_efficiency() -> None:
    """Text makes up a tiny share of the raw HTML: token efficiency fails."""
    agent = ComprehensionAgent()
    evidence = _perfect_evidence()
    evidence.text_length = 300
    evidence.html_length = 10000

    result = agent.evaluate(evidence)
    _print_result("low token efficiency", result)

    assert result.checks["token_efficiency"] is False
    assert "Low text-to-markup ratio" in result.issues[0]
    assert result.score == round(5 / 6 * 100, 2)


def test_everything_missing_scores_near_zero() -> None:
    """A bare, empty evidence record should score at (or near) zero.

    Image alt-text coverage trivially passes with zero images, so a
    fully empty evidence record scores 1/6 rather than 0.
    """
    agent = ComprehensionAgent()
    evidence = WebsiteEvidence(url=URL)

    result = agent.evaluate(evidence)
    _print_result("everything missing", result)

    assert result.checks["semantic_html"] is False
    assert result.checks["heading_structure"] is False
    assert result.checks["structured_data"] is False
    assert result.checks["language_declared"] is False
    assert result.checks["image_alt_text"] is True
    assert result.checks["token_efficiency"] is False
    assert result.score == round(1 / 6 * 100, 2)


# ---------------------------------------------------------------------------
# End-to-end scenario: real website -> Evidence Collector -> Comprehension
# Agent -> PDF report.
#
# This section adds no logic to either agent; it only orchestrates the two
# existing components and renders their output. `reportlab` is used to build
# the PDF since no PDF library was already part of the project.
# ---------------------------------------------------------------------------

# Maps each `ComprehensionResult.checks` key to its human-readable label,
# used when rendering the criteria table in the PDF report.
_CRITERIA_LABELS: dict[str, str] = {
    "semantic_html": "Semantic HTML",
    "heading_structure": "Heading structure",
    "structured_data": "Structured data",
    "language_declared": "Language declared",
    "image_alt_text": "Image alt text",
    "token_efficiency": "Token efficiency",
}


def _criterion_detail_summary(name: str, details: dict[str, Any]) -> str:
    """Summarize the supporting evidence for a single criterion.

    Args:
        name: The criterion's key in `ComprehensionResult.checks`.
        details: The full `ComprehensionResult.details` mapping.

    Returns:
        A short, human-readable description of the evidence backing
        this criterion's pass/fail outcome.
    """
    if name == "semantic_html":
        return f"tags used={details.get('semantic_tags_used') or []}"
    if name == "heading_structure":
        return f"h1_count={details.get('h1_count')}, headings={details.get('headings')}"
    if name == "structured_data":
        return (
            f"json-ld={details.get('json_ld_count')}, "
            f"microdata={details.get('microdata_count')}, "
            f"rdfa={details.get('rdfa_count')}"
        )
    if name == "language_declared":
        return f"language={details.get('language')}"
    if name == "image_alt_text":
        return (
            f"total={details.get('images_total')}, "
            f"with_alt={details.get('images_with_alt')}, "
            f"coverage={details.get('alt_coverage')}"
        )
    if name == "token_efficiency":
        return f"text/html ratio={details.get('text_to_html_ratio')}"
    return ""


def _generate_pdf_report(
    url: str, result: ComprehensionResult, output_path: Path
) -> None:
    """Render a `ComprehensionResult` as a PDF report.

    Args:
        url: The website URL that was assessed.
        result: The evaluation produced by `ComprehensionAgent.evaluate`.
        output_path: Filesystem path the PDF should be written to.
    """
    styles = getSampleStyleSheet()
    heading_style = ParagraphStyle(
        "SectionHeading", parent=styles["Heading2"], spaceBefore=12, spaceAfter=6
    )

    passed_count = sum(1 for outcome in result.checks.values() if outcome)
    failed_count = len(result.checks) - passed_count

    story: list[Any] = [
        Paragraph("ARAS Comprehension Assessment Report", styles["Title"]),
        Spacer(1, 0.5 * cm),
        Paragraph(f"<b>Website URL:</b> {url}", styles["Normal"]),
        Paragraph(
            f"<b>Analysis date:</b> {datetime.now(timezone.utc).isoformat()}",
            styles["Normal"],
        ),
        Paragraph("<b>Agent used:</b> Comprehension Agent", styles["Normal"]),
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


def _print_console_summary(url: str, result: ComprehensionResult, report_path: Path) -> None:
    """Print the human-facing summary of a real-site assessment run.

    Args:
        url: The website URL that was assessed.
        result: The evaluation produced by `ComprehensionAgent.evaluate`.
        report_path: Filesystem path the PDF report was written to.
    """
    try:
        "✓".encode(sys.stdout.encoding or "utf-8")
        pass_mark, fail_mark = "✓", "✗"
    except UnicodeEncodeError:
        pass_mark, fail_mark = "[PASS]", "[FAIL]"

    print("=" * 30)
    print("ARAS Comprehension Report")
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


def test_real_site_comprehension() -> None:
    """End-to-end: collect real evidence, evaluate it, render a PDF report.

    Chains the existing `EvidenceCollectorAgent` into the existing
    `ComprehensionAgent` against a live website, then renders the
    resulting `ComprehensionResult` as a PDF. Requires network access.
    """
    evidence = EvidenceCollectorAgent().collect(TARGET_URL)
    result = ComprehensionAgent().evaluate(evidence)
    _print_result(f"real site: {TARGET_URL}", result)

    _generate_pdf_report(TARGET_URL, result, REPORT_PATH)
    _print_console_summary(TARGET_URL, result, REPORT_PATH)

    assert REPORT_PATH.exists()
    assert 0.0 <= result.score <= 100.0
    assert len(result.checks) == 6


if __name__ == "__main__":
    test_perfect_website_scores_100()
    test_insufficient_semantic_html()
    test_missing_h1()
    test_duplicate_h1()
    test_no_structured_data()
    test_no_language_declared()
    test_poor_image_alt_coverage()
    test_no_images_trivially_passes_alt_text()
    test_low_token_efficiency()
    test_everything_missing_scores_near_zero()
    test_real_site_comprehension()
    print("All tests passed.")