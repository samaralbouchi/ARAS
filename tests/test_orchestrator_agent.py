"""Unit tests for :class:`OrchestratorAgent`.

Covers, using a fake evidence collector (no real network access): a
full pipeline run with real analysis agents, correct wiring of fake
analysis agents, overall-score aggregation, propagation of collection
errors, and the `run()` standard input contract. This verifies that
the orchestrator coordinates correctly; it performs no scoring logic
of its own (that is covered by each analysis agent's own test suite).

It also includes an end-to-end scenario against a real website that
chains the whole pipeline: `EvidenceCollectorAgent` ->
`DiscoverabilityAgent` / `ComprehensionAgent` / `InteractionAgent` /
`SecurityAgent`, all coordinated by `OrchestratorAgent` itself. That
scenario adds no new logic to the orchestrator or to any analysis
agent — it only exercises the real, default-wired pipeline end to end.
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
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from agents.orchestrator_agent import OrchestratorAgent
from models.assessment import AssessmentResult
from models.evidence import CollectionError, WebsiteEvidence

URL = "https://www.example.com"
TARGET_URL = "https://www.bpifrance.fr"
REPORT_PATH = (
    Path(__file__).resolve().parent.parent / "agentic_readiness_report_bpifrance.pdf"
)

SAMPLE_HTML = """
<html lang="en">
<head>
    <title>Example</title>
    <meta name="description" content="An example site.">
    <link rel="canonical" href="https://www.example.com/">
    <meta property="og:title" content="Example">
</head>
<body>
    <header><nav>Home</nav></header>
    <main>
        <h1>Example</h1>
        <h2>About</h2>
        <p>Some visible text content that is long enough to pass the ratio check easily without much markup around it at all.</p>
        <a href="/about">About</a>
    </main>
    <footer>Footer</footer>
</body>
</html>
"""


class FakeEvidenceCollector:
    """Stand-in for `EvidenceCollectorAgent` that returns a canned evidence snapshot."""

    def __init__(self, evidence: WebsiteEvidence) -> None:
        self._evidence = evidence

    def collect(self, url: str) -> WebsiteEvidence:
        assert url == URL
        return self._evidence


class FakeAnalysisAgent:
    """Stand-in for any of the four analysis agents, returning a canned score."""

    def __init__(self, score: float) -> None:
        self._score = score
        self.received_evidence = None

    def evaluate(self, evidence: WebsiteEvidence):
        self.received_evidence = evidence

        class _Result:
            def __init__(self, score: float) -> None:
                self.score = score

            def to_dict(self):
                return {"score": self.score}

        return _Result(self._score)


def _rich_evidence(errors=None) -> WebsiteEvidence:
    return WebsiteEvidence(
        url=URL,
        html=SAMPLE_HTML,
        status_code=200,
        title="Example",
        language="en",
        meta_tags={"description": "An example site."},
        canonical="https://www.example.com/",
        open_graph={"og:title": "Example"},
        semantic_tags={"header": 1, "nav": 1, "main": 1, "footer": 1},
        headings={"h1": 1, "h2": 1},
        internal_links=["https://www.example.com/about"],
        robots_txt="User-agent: *",
        sitemap_xml="<urlset></urlset>",
        llms_txt="# Example",
        images_total=0,
        images_with_alt=0,
        text_length=200,
        html_length=500,
        errors=errors or [],
    )


def test_full_pipeline_with_real_analysis_agents() -> None:
    """A rich evidence snapshot flows through all four real analysis agents."""
    evidence = _rich_evidence()
    agent = OrchestratorAgent(evidence_collector=FakeEvidenceCollector(evidence))

    result = agent.assess(URL)

    assert result.url == URL
    assert result.evidence["title"] == "Example"
    assert 0.0 <= result.discoverability["score"] <= 100.0
    assert 0.0 <= result.comprehension["score"] <= 100.0
    assert 0.0 <= result.interaction["score"] <= 100.0
    assert 0.0 <= result.security["score"] <= 100.0
    assert result.collection_errors == []
    print("overall_score:", result.overall_score)
    print("discoverability:", result.discoverability["score"])
    print("comprehension:", result.comprehension["score"])
    print("interaction:", result.interaction["score"])
    print("security:", result.security["score"])


def test_analysis_agents_receive_the_collected_evidence() -> None:
    """Every injected analysis agent is called with the same evidence object."""
    evidence = _rich_evidence()
    discoverability = FakeAnalysisAgent(score=100.0)
    comprehension = FakeAnalysisAgent(score=80.0)
    interaction = FakeAnalysisAgent(score=60.0)
    security = FakeAnalysisAgent(score=40.0)

    agent = OrchestratorAgent(
        evidence_collector=FakeEvidenceCollector(evidence),
        discoverability_agent=discoverability,
        comprehension_agent=comprehension,
        interaction_agent=interaction,
        security_agent=security,
    )

    result = agent.assess(URL)

    assert discoverability.received_evidence is evidence
    assert comprehension.received_evidence is evidence
    assert interaction.received_evidence is evidence
    assert security.received_evidence is evidence
    assert result.discoverability == {"score": 100.0}
    assert result.security == {"score": 40.0}


def test_overall_score_is_the_average_of_the_four_scores() -> None:
    """`overall_score` is the unweighted mean of the four analysis scores."""
    evidence = _rich_evidence()
    agent = OrchestratorAgent(
        evidence_collector=FakeEvidenceCollector(evidence),
        discoverability_agent=FakeAnalysisAgent(score=100.0),
        comprehension_agent=FakeAnalysisAgent(score=80.0),
        interaction_agent=FakeAnalysisAgent(score=60.0),
        security_agent=FakeAnalysisAgent(score=40.0),
    )

    result = agent.assess(URL)

    assert result.overall_score == 70.0


def test_collection_errors_are_propagated() -> None:
    """Non-fatal collection errors surface on `AssessmentResult.collection_errors`."""
    evidence = _rich_evidence(
        errors=[CollectionError(step="resource_discovery", message="timed out")]
    )
    agent = OrchestratorAgent(evidence_collector=FakeEvidenceCollector(evidence))

    result = agent.assess(URL)

    assert result.collection_errors == [
        {"step": "resource_discovery", "message": "timed out"}
    ]


def test_bot_block_verdict_is_propagated() -> None:
    """`evidence.blocked` (+ reason/provider) surfaces on `AssessmentResult`."""
    evidence = _rich_evidence()
    evidence.blocked = True
    evidence.blocked_reason = "Cloudflare block/challenge page detected (header:cf-ray)"
    evidence.blocked_provider = "cloudflare"
    agent = OrchestratorAgent(evidence_collector=FakeEvidenceCollector(evidence))

    result = agent.assess(URL)

    assert result.blocked is True
    assert result.blocked_provider == "cloudflare"
    assert result.blocked_reason == (
        "Cloudflare block/challenge page detected (header:cf-ray)"
    )


def test_not_blocked_by_default() -> None:
    """A normal, unblocked evidence snapshot yields `blocked=False` with no reason/provider."""
    evidence = _rich_evidence()
    agent = OrchestratorAgent(evidence_collector=FakeEvidenceCollector(evidence))

    result = agent.assess(URL)

    assert result.blocked is False
    assert result.blocked_reason is None
    assert result.blocked_provider is None


def test_run_accepts_standard_input_contract() -> None:
    """`run({"url": ...})` delegates to `assess` with that URL."""
    evidence = _rich_evidence()
    agent = OrchestratorAgent(evidence_collector=FakeEvidenceCollector(evidence))

    result = agent.run({"url": URL})

    assert result.url == URL


# ---------------------------------------------------------------------------
# End-to-end scenario: real website -> Evidence Collector -> all four
# analysis agents -> Orchestrator -> PDF report.
#
# This section adds no logic to any agent; it only orchestrates the existing
# components and renders their combined output as the final "Agentic
# Readiness Report" from the architecture diagram. `reportlab` is used to
# build the PDF since no PDF library was already part of the project.
# ---------------------------------------------------------------------------

# Per-agent criterion -> human-readable label, used when rendering each
# agent's criteria table in the PDF report. Keys must match this module's
# `AssessmentResult.<agent>["checks"]` dict for that agent.
_AGENT_CRITERIA_LABELS: dict[str, dict[str, str]] = {
    "discoverability": {
        "robots_txt": "robots.txt",
        "sitemap": "sitemap.xml",
        "llms_txt": "llms.txt",
        "metadata": "Metadata",
        "open_graph": "Open Graph",
        "api_discoverability": "API discoverability",
        "internal_links": "Internal links",
    },
    "comprehension": {
        "semantic_html": "Semantic HTML",
        "heading_structure": "Heading structure",
        "structured_data": "Structured data",
        "language_declared": "Language declared",
        "image_alt_text": "Image alt text",
        "token_efficiency": "Token efficiency",
    },
    "interaction": {
        "mcp_endpoint": "MCP endpoint",
        "mcp_tools_and_resources": "MCP tools/resources",
        "openapi_spec": "OpenAPI specification",
        "swagger_documentation": "Swagger/ReDoc docs",
        "agent_actionability": "Agent actionability",
    },
    "security": {
        "https_enforced": "HTTPS enforced",
        "hsts_enabled": "HSTS enabled",
        "defensive_headers": "Defensive HTTP headers",
        "authentication_declared": "Authentication declared",
        "rate_limiting_declared": "Rate limiting declared",
        "minimal_info_disclosure": "Minimal info disclosure",
    },
}

# Display name for each agent section, in the order they should appear.
_AGENT_DISPLAY_NAMES: dict[str, str] = {
    "discoverability": "Discoverability Agent",
    "comprehension": "Comprehension Agent",
    "interaction": "Interaction Agent",
    "security": "Security Agent",
}


def _criterion_detail_summary(agent_key: str, name: str, details: dict[str, Any]) -> str:
    """Summarize the supporting evidence for a single criterion of one agent.

    Args:
        agent_key: One of `"discoverability"`, `"comprehension"`,
            `"interaction"`, `"security"`.
        name: The criterion's key in that agent's `checks` dict.
        details: That agent's full `details` mapping.

    Returns:
        A short, human-readable description of the evidence backing
        this criterion's pass/fail outcome.
    """
    if agent_key == "discoverability":
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
    if agent_key == "comprehension":
        if name == "semantic_html":
            return f"tags used={details.get('semantic_tags_used') or []}"
        if name == "heading_structure":
            return f"h1_count={details.get('h1_count')}"
        if name == "structured_data":
            return (
                f"json-ld={details.get('json_ld_count')}, "
                f"microdata={details.get('microdata_count')}, "
                f"rdfa={details.get('rdfa_count')}"
            )
        if name == "language_declared":
            return f"language={details.get('language')}"
        if name == "image_alt_text":
            return f"coverage={details.get('alt_coverage')}"
        if name == "token_efficiency":
            return f"text/html ratio={details.get('text_to_html_ratio')}"
    if agent_key == "interaction":
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
    if agent_key == "security":
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


def _agent_section(
    story: list[Any],
    styles: Any,
    heading_style: ParagraphStyle,
    section_number: int,
    agent_key: str,
    agent_result: dict[str, Any],
) -> None:
    """Append one agent's full section (score, criteria, issues, recommendations).

    Args:
        story: The in-progress reportlab flowable list to append to.
        styles: The reportlab stylesheet returned by `getSampleStyleSheet()`.
        heading_style: The shared section-heading paragraph style.
        section_number: The section number to print in the heading.
        agent_key: One of `"discoverability"`, `"comprehension"`,
            `"interaction"`, `"security"`.
        agent_result: That agent's result, as a plain dict (`score`,
            `checks`, `details`, `issues`, `recommendations`).
    """
    name = _AGENT_DISPLAY_NAMES[agent_key]
    labels = _AGENT_CRITERIA_LABELS[agent_key]
    checks = agent_result.get("checks", {})
    details = agent_result.get("details", {})
    issues = agent_result.get("issues", [])
    recommendations = agent_result.get("recommendations", [])

    story.append(Paragraph(f"{section_number}. {name}", heading_style))
    story.append(Paragraph(f"<b>Score:</b> {agent_result.get('score')}/100", styles["Normal"]))

    table_data = [["Criterion", "Status", "Details"]]
    for key, label in labels.items():
        status = "PASS" if checks.get(key) else "FAIL"
        table_data.append([label, status, _criterion_detail_summary(agent_key, key, details)])

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

    if issues:
        story.append(Paragraph("Issues", ParagraphStyle("Sub", parent=styles["Heading3"], spaceBefore=8)))
        story.append(
            ListFlowable(
                [ListItem(Paragraph(issue, styles["Normal"])) for issue in issues],
                bulletType="bullet",
            )
        )
    if recommendations:
        story.append(
            Paragraph("Recommendations", ParagraphStyle("Sub2", parent=styles["Heading3"], spaceBefore=8))
        )
        story.append(
            ListFlowable(
                [
                    ListItem(Paragraph(recommendation, styles["Normal"]))
                    for recommendation in recommendations
                ],
                bulletType="bullet",
            )
        )


def _generate_pdf_report(url: str, result: AssessmentResult, output_path: Path) -> None:
    """Render a full `AssessmentResult` as the final Agentic Readiness Report PDF.

    Args:
        url: The website URL that was assessed.
        result: The assessment produced by `OrchestratorAgent.assess`.
        output_path: Filesystem path the PDF should be written to.
    """
    styles = getSampleStyleSheet()
    heading_style = ParagraphStyle(
        "SectionHeading", parent=styles["Heading2"], spaceBefore=12, spaceAfter=6
    )

    story: list[Any] = [
        Paragraph("Agentic Readiness Assessment Report", styles["Title"]),
        Spacer(1, 0.5 * cm),
        Paragraph(f"<b>Website URL:</b> {url}", styles["Normal"]),
        Paragraph(f"<b>Assessed at:</b> {result.assessed_at}", styles["Normal"]),
        Paragraph("<b>Coordinated by:</b> Orchestrator Agent", styles["Normal"]),
    ]

    # Section 0: Overall score summary
    story.append(Paragraph("Overall Agentic Readiness Score", heading_style))
    story.append(
        Paragraph(f"<b>Overall score:</b> {result.overall_score}/100", styles["Normal"])
    )
    summary_table = Table(
        [
            ["Discoverability", "Comprehension", "Interaction", "Security"],
            [
                f"{result.discoverability.get('score')}/100",
                f"{result.comprehension.get('score')}/100",
                f"{result.interaction.get('score')}/100",
                f"{result.security.get('score')}/100",
            ],
        ],
        colWidths=[4 * cm] * 4,
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E3440")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    story.append(Spacer(1, 0.3 * cm))
    story.append(summary_table)

    if result.blocked:
        story.append(Spacer(1, 0.3 * cm))
        story.append(
            Paragraph(
                f"<b><font color='#B00020'>⚠ Bot/WAF block detected "
                f"({result.blocked_provider}):</font></b> {result.blocked_reason} "
                f"— scores above likely reflect a block/challenge page, not the "
                f"site's real content.",
                styles["Normal"],
            )
        )

    if result.collection_errors:
        story.append(Paragraph("Collection Errors", heading_style))
        story.append(
            ListFlowable(
                [
                    ListItem(
                        Paragraph(f"{err['step']}: {err['message']}", styles["Normal"])
                    )
                    for err in result.collection_errors
                ],
                bulletType="bullet",
            )
        )

    # One detailed section per analysis agent.
    story.append(PageBreak())
    _agent_section(story, styles, heading_style, 1, "discoverability", result.discoverability)
    story.append(PageBreak())
    _agent_section(story, styles, heading_style, 2, "comprehension", result.comprehension)
    story.append(PageBreak())
    _agent_section(story, styles, heading_style, 3, "interaction", result.interaction)
    story.append(PageBreak())
    _agent_section(story, styles, heading_style, 4, "security", result.security)

    SimpleDocTemplate(str(output_path), pagesize=A4).build(story)


def _print_console_summary(url: str, result: AssessmentResult, report_path: Path) -> None:
    """Print the human-facing summary of a real-site assessment run.

    Args:
        url: The website URL that was assessed.
        result: The assessment produced by `OrchestratorAgent.assess`.
        report_path: Filesystem path the PDF report was written to.
    """
    print("=" * 30)
    print("Agentic Readiness Report")
    print(f"Website: {url}")
    print()
    print(f"Overall score: {result.overall_score}/100")
    print(f"  Discoverability: {result.discoverability['score']}/100")
    print(f"  Comprehension:   {result.comprehension['score']}/100")
    print(f"  Interaction:     {result.interaction['score']}/100")
    print(f"  Security:        {result.security['score']}/100")
    if result.blocked:
        print()
        print(f"⚠ Bot/WAF block detected ({result.blocked_provider}): {result.blocked_reason}")
    print()
    print("PDF generated:")
    print(report_path)
    print("=" * 30)


def _print_assessment(label: str, result) -> None:
    print(f"--- {label} ---")
    print(f"url:              {result.url}")
    print(f"overall_score:    {result.overall_score}")
    print(f"discoverability:  {result.discoverability['score']}")
    print(f"comprehension:    {result.comprehension['score']}")
    print(f"interaction:      {result.interaction['score']}")
    print(f"security:         {result.security['score']}")
    print(f"collection_errors:{result.collection_errors}")
    print(f"blocked:          {result.blocked} (provider={result.blocked_provider})")
    print()


def test_real_site_assessment() -> None:
    """End-to-end: run the full, real pipeline against a live website and render a PDF.

    Requires network access.
    """
    agent = OrchestratorAgent()  # every collaborator is the real, default one

    result = agent.assess(TARGET_URL)
    _print_assessment(f"real site: {TARGET_URL}", result)

    _generate_pdf_report(TARGET_URL, result, REPORT_PATH)
    _print_console_summary(TARGET_URL, result, REPORT_PATH)

    assert REPORT_PATH.exists()
    assert result.url == TARGET_URL
    assert 0.0 <= result.overall_score <= 100.0
    assert 0.0 <= result.discoverability["score"] <= 100.0
    assert 0.0 <= result.comprehension["score"] <= 100.0
    assert 0.0 <= result.interaction["score"] <= 100.0
    assert 0.0 <= result.security["score"] <= 100.0


if __name__ == "__main__":
    test_full_pipeline_with_real_analysis_agents()
    test_analysis_agents_receive_the_collected_evidence()
    test_overall_score_is_the_average_of_the_four_scores()
    test_collection_errors_are_propagated()
    test_bot_block_verdict_is_propagated()
    test_not_blocked_by_default()
    test_run_accepts_standard_input_contract()
    test_real_site_assessment()
    print("All tests passed.")