"""Report Generator Agent.

This module is the final agent in the ARAF pipeline. It compiles the
`AssessmentResult` (from the Orchestrator) and the `RecommendationResult`
(from the Recommendation Agent) into a single `AgenticReadinessReport`,
ready to render as Markdown, JSON, or hand off to another format
(PDF/HTML) downstream.

This agent MUST NOT:
    - perform any scoring
    - generate or reprioritize recommendations

It only assembles and renders what upstream agents already produced.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path
from typing import Optional, Union

from models.report import (
    AgenticReadinessReport,
    AssessmentResult,
    Priority,
    RecommendationResult,
    Severity,
    utcnow,
)

# Ordering used only to sort issues/recommendations for human-readable output.
# This is display ordering, not scoring/prioritization logic.
_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}

_PRIORITY_ORDER = {
    Priority.P0: 0,
    Priority.P1: 1,
    Priority.P2: 2,
}


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

class BaseRenderer(ABC):
    """Interface every renderer must implement.

    Text-based renderers (Markdown, JSON, ...) return `str`.
    Binary renderers (PDF, ...) return `bytes`.
    """

    @abstractmethod
    def render(self, report: AgenticReadinessReport) -> Union[str, bytes]:
        raise NotImplementedError


class JSONRenderer(BaseRenderer):
    """Renders the report as pretty-printed JSON."""

    def __init__(self, indent: int = 2):
        self.indent = indent

    def render(self, report: AgenticReadinessReport) -> str:
        return json.dumps(report.to_dict(), indent=self.indent, ensure_ascii=False)


class MarkdownRenderer(BaseRenderer):
    """Renders the report as a human-readable Markdown document."""

    def render(self, report: AgenticReadinessReport) -> str:
        lines: list[str] = []

        lines.append(f"# Agentic Readiness Report — {report.url}")
        lines.append("")
        lines.append(f"_Generated: {report.generated_at.isoformat()}_")
        lines.append("")
        lines.append(f"## Overall Agentic Readiness Score: {report.overall_score:.1f} / 100")
        lines.append("")

        lines.append("## Report Summary")
        lines.append("")
        lines.append(f"- **Total issues detected:** {len(report.issues)}")
        lines.append(f"- **Total recommendations:** {len(report.recommendations)}")
        if report.rag_sources_used:
            lines.append(f"- **Knowledge base sources referenced:** {len(report.rag_sources_used)}")
        lines.append("")

        lines.append("## Category Scores")
        lines.append("")
        lines.append("| Category | Score | Max |")
        lines.append("|---|---|---|")
        for cs in report.category_scores:
            lines.append(f"| {cs.category.value.capitalize()} | {cs.score:.1f} | {cs.max_score:.1f} |")
        lines.append("")

        lines.append("## Detected Issues")
        lines.append("")
        if report.issues:
            sorted_issues = sorted(report.issues, key=lambda i: _SEVERITY_ORDER.get(i.severity, 99))
            for issue in sorted_issues:
                lines.append(f"### [{issue.severity.value.upper()}] {issue.title}")
                lines.append(f"- **Category:** {issue.category.value}")
                lines.append(f"- **Description:** {issue.description}")
                if issue.evidence_ref:
                    lines.append(f"- **Evidence:** `{issue.evidence_ref}`")
                lines.append("")
        else:
            lines.append("No issues detected.")
            lines.append("")

        lines.append("## Prioritized Recommendations")
        lines.append("")
        if report.recommendations:
            sorted_recs = sorted(report.recommendations, key=lambda r: _PRIORITY_ORDER.get(r.priority, 99))
            for rec in sorted_recs:
                lines.append(f"### [{rec.priority.value}] {rec.title}")
                lines.append(f"- **Category:** {rec.category.value}")
                lines.append(f"- **Description:** {rec.description}")
                if rec.effort or rec.impact:
                    lines.append(f"- **Effort:** {rec.effort or 'n/a'} · **Impact:** {rec.impact or 'n/a'}")
                if rec.related_issue_ids:
                    lines.append(f"- **Related issues:** {', '.join(rec.related_issue_ids)}")
                if rec.knowledge_sources:
                    lines.append(f"- **Sources:** {', '.join(rec.knowledge_sources)}")
                if getattr(rec, 'rag_context', None):
                    lines.append(f"- **RAG evidence:** {rec.rag_context}")
                lines.append("")
        else:
            lines.append("No recommendations.")
            lines.append("")

        if report.artifacts_collected:
            lines.append("## Artifacts Collected")
            lines.append("")
            for artifact in report.artifacts_collected:
                lines.append(f"- {artifact}")
            lines.append("")

        if report.rag_sources_used:
            lines.append("## Knowledge Base Sources Used")
            lines.append("")
            for src in report.rag_sources_used:
                lines.append(f"- {src}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"


class PDFRenderer(BaseRenderer):
    """Renders the report as a PDF document using reportlab.

    Requires: pip install reportlab --break-system-packages
    """

    def render(self, report: AgenticReadinessReport) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
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

        styles = getSampleStyleSheet()
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            title="Agentic Readiness Report",
        )
        story: list = []

        # --- Header -----------------------------------------------------
        story.append(Paragraph("Agentic Readiness Report", styles["Title"]))
        story.append(Paragraph(report.url, styles["Heading3"]))
        story.append(Paragraph(f"Generated: {report.generated_at.isoformat()}", styles["Normal"]))
        story.append(Spacer(1, 14))
        story.append(
            Paragraph(f"Overall Agentic Readiness Score: {report.overall_score:.1f} / 100", styles["Heading2"])
        )
        story.append(Spacer(1, 12))
        story.append(Paragraph("Report Summary", styles["Heading3"]))
        story.append(Paragraph(f"Total issues detected: {len(report.issues)}", styles["Normal"]))
        story.append(Paragraph(f"Total recommendations: {len(report.recommendations)}", styles["Normal"]))
        story.append(Paragraph(f"Knowledge sources referenced: {len(report.rag_sources_used)}", styles["Normal"]))
        story.append(Spacer(1, 18))
        story.append(Spacer(1, 12))

        # --- Category scores table ---------------------------------------
        story.append(Paragraph("Category Scores", styles["Heading2"]))
        data = [["Category", "Score", "Max"]]
        for cs in report.category_scores:
            data.append([cs.category.value.capitalize(), f"{cs.score:.1f}", f"{cs.max_score:.1f}"])
        table = Table(data, colWidths=[8 * cm, 4 * cm, 4 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b2b2b")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 18))

        # --- Issues --------------------------------------------------------
        story.append(Paragraph("Detected Issues", styles["Heading2"]))
        if report.issues:
            sorted_issues = sorted(report.issues, key=lambda i: _SEVERITY_ORDER.get(i.severity, 99))
            for issue in sorted_issues:
                story.append(Paragraph(f"[{issue.severity.value.upper()}] {issue.title}", styles["Heading4"]))
                story.append(Paragraph(f"Category: {issue.category.value}", styles["Normal"]))
                story.append(Paragraph(issue.description, styles["Normal"]))
                if issue.evidence_ref:
                    story.append(Paragraph(f"Evidence: {issue.evidence_ref}", styles["Normal"]))
                story.append(Spacer(1, 8))
        else:
            story.append(Paragraph("No issues detected.", styles["Normal"]))
        story.append(Spacer(1, 18))

        # --- Recommendations -------------------------------------------------
        story.append(Paragraph("Prioritized Recommendations", styles["Heading2"]))
        if report.recommendations:
            sorted_recs = sorted(report.recommendations, key=lambda r: _PRIORITY_ORDER.get(r.priority, 99))
            for rec in sorted_recs:
                story.append(Paragraph(f"[{rec.priority.value}] {rec.title}", styles["Heading4"]))
                story.append(Paragraph(f"Category: {rec.category.value}", styles["Normal"]))
                story.append(Paragraph(rec.description, styles["Normal"]))
                meta_bits = []
                if rec.effort or rec.impact:
                    meta_bits.append(f"Effort: {rec.effort or 'n/a'} · Impact: {rec.impact or 'n/a'}")
                if rec.knowledge_sources:
                    meta_bits.append(f"Sources: {', '.join(rec.knowledge_sources)}")
                if meta_bits:
                    story.append(Paragraph(" | ".join(meta_bits), styles["Normal"]))
                if getattr(rec, 'rag_context', None):
                    context_text = rec.rag_context.replace("\n", "<br/>")
                    story.append(Paragraph(f"RAG evidence: {context_text}", styles["Normal"]))
                story.append(Spacer(1, 8))
        else:
            story.append(Paragraph("No recommendations.", styles["Normal"]))
        story.append(Spacer(1, 18))

        # --- Artifacts & RAG sources -----------------------------------------
        if report.artifacts_collected:
            story.append(Paragraph("Artifacts Collected", styles["Heading2"]))
            items = [ListItem(Paragraph(a, styles["Normal"])) for a in report.artifacts_collected]
            story.append(ListFlowable(items, bulletType="bullet"))
            story.append(Spacer(1, 18))

        if report.rag_sources_used:
            story.append(Paragraph("Knowledge Base Sources Used", styles["Heading2"]))
            items = [ListItem(Paragraph(s, styles["Normal"])) for s in report.rag_sources_used]
            story.append(ListFlowable(items, bulletType="bullet"))

        doc.build(story)
        return buffer.getvalue()


RENDERERS: dict[str, BaseRenderer] = {
    "markdown": MarkdownRenderer(),
    "json": JSONRenderer(),
    "pdf": PDFRenderer(),
}


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ReportGeneratorAgent:
    """Assembles upstream results into a final report and renders it.

    Usage
    -----
    >>> agent = ReportGeneratorAgent()
    >>> report = agent.generate(assessment_result, recommendation_result)
    >>> markdown = agent.render(report, fmt="markdown")
    >>> agent.save(report, "report.md", fmt="markdown")
    """

    def __init__(self, renderers: Optional[dict[str, BaseRenderer]] = None):
        # Allow dependency injection of custom/additional renderers
        # (e.g. an HTML or PDF renderer) without touching this class.
        self._renderers = dict(RENDERERS)
        if renderers:
            self._renderers.update(renderers)

    # ------------------------------------------------------------------
    # Assembly (no scoring, no recommendation logic — pure composition)
    # ------------------------------------------------------------------
    def generate(
        self,
        assessment: AssessmentResult,
        recommendations: RecommendationResult,
        extra_metadata: Optional[dict] = None,
    ) -> AgenticReadinessReport:
        """Combine the two upstream results into one immutable report."""

        if not assessment.url:
            raise ValueError("AssessmentResult.url is required")

        return AgenticReadinessReport(
            url=assessment.url,
            generated_at=utcnow(),
            overall_score=assessment.overall_score,
            category_scores=list(assessment.category_scores),
            issues=list(assessment.issues),
            recommendations=list(recommendations.recommendations),
            rag_sources_used=list(recommendations.rag_sources_used),
            artifacts_collected=list(assessment.artifacts_collected),
            metadata=extra_metadata or {},
        )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def render(self, report: AgenticReadinessReport, fmt: str = "markdown") -> Union[str, bytes]:
        """Render an assembled report in the given format.

        Returns `str` for text formats (markdown, json) and `bytes` for
        binary formats (pdf).
        """

        try:
            renderer = self._renderers[fmt]
        except KeyError as exc:
            available = ", ".join(sorted(self._renderers))
            raise ValueError(f"Unknown format '{fmt}'. Available formats: {available}") from exc
        return renderer.render(report)

    def save(self, report: AgenticReadinessReport, path: str | Path, fmt: str = "markdown") -> Path:
        """Render and write the report to disk. Returns the written path.

        Handles both text renderers (str) and binary renderers like PDF (bytes).
        """

        content = self.render(report, fmt=fmt)
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            out_path.write_bytes(content)
        else:
            out_path.write_text(content, encoding="utf-8")
        return out_path

    # ------------------------------------------------------------------
    # Convenience: assemble + render in one call
    # ------------------------------------------------------------------
    def run(
        self,
        assessment: AssessmentResult,
        recommendations: RecommendationResult,
        fmt: str = "markdown",
        extra_metadata: Optional[dict] = None,
    ) -> str:
        report = self.generate(assessment, recommendations, extra_metadata=extra_metadata)
        return self.render(report, fmt=fmt)