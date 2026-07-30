"""Integration test: run the ARAF Report Generator Agent against a REAL
website (https://www.bpifrance.fr/) and export the result as a PDF.

This performs live network checks against the target site — robots.txt,
sitemap.xml, llms.txt, HTTPS/security headers, structured data, and
common API-discovery paths — then feeds the findings through
`ReportGeneratorAgent.generate()` / `.save()`, exactly like the
Orchestrator would with the real Parallel Analysis Agents.

The checks below (`check_discoverability`, `check_comprehension`, ...)
and `build_recommendations` are simplified stand-ins for the real
Discoverability/Comprehension/Interaction/Security Agents and the
Recommendation Agent, inlined here only so this test file is
self-contained and runnable on its own. The Report Generator Agent
itself still does none of that work — it only assembles + renders
what these stand-ins produce, per its contract.

Setup:
    pip install requests reportlab --break-system-packages

Run:
    pytest tests/test_report_generator_agent.py -v -s

Requires outbound internet access. If the target is unreachable, the
test is skipped (not failed), so CI without internet access still passes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import pytest
except ImportError:  # pragma: no cover
    pytest = None

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


class _SkipTest(Exception):
    """Raised when running this file directly (without pytest) and a skip condition is hit."""


def _skip(reason: str):
    if pytest is not None:
        pytest.skip(reason)
    raise _SkipTest(reason)

from agents.report_generator_agent import ReportGeneratorAgent
from models.report import (
    AnalysisCategory,
    AssessmentResult,
    CategoryScore,
    DetectedIssue,
    Priority,
    Recommendation,
    RecommendationResult,
    Severity,
    utcnow,
)

TARGET_URL = "https://www.bpifrance.fr/"
TIMEOUT = 10
GENERAL_REPORT_PDF = Path(__file__).resolve().parent.parent / "general_report_bpifrance.pdf"
USER_AGENT = "ARAF-Bot/1.0 (+https://example.com/araf)"


# ---------------------------------------------------------------------------
# Lightweight live checks (stand-ins for the 4 Parallel Analysis Agents)
# ---------------------------------------------------------------------------

def _safe_get(url: str):
    """GET a URL, swallowing network errors so a single dead endpoint
    doesn't crash the whole assessment."""
    try:
        return requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    except requests.RequestException:
        return None


def check_discoverability(base_url: str) -> tuple[CategoryScore, list[DetectedIssue]]:
    findings: list[str] = []
    issues: list[DetectedIssue] = []
    score = 0

    robots = _safe_get(urljoin(base_url, "/robots.txt"))
    if robots is not None and robots.status_code == 200:
        findings.append("robots.txt reachable")
        score += 30
    else:
        issues.append(
            DetectedIssue(
                id="DISC-001",
                category=AnalysisCategory.DISCOVERABILITY,
                severity=Severity.LOW,
                title="robots.txt not reachable",
                description="No robots.txt found at the site root (or it did not return HTTP 200).",
                evidence_ref="/robots.txt",
            )
        )

    sitemap = _safe_get(urljoin(base_url, "/sitemap.xml"))
    if sitemap is not None and sitemap.status_code == 200:
        findings.append("sitemap.xml reachable")
        score += 30
    else:
        issues.append(
            DetectedIssue(
                id="DISC-002",
                category=AnalysisCategory.DISCOVERABILITY,
                severity=Severity.MEDIUM,
                title="sitemap.xml not reachable",
                description="No sitemap.xml found at the site root (or it did not return HTTP 200).",
                evidence_ref="/sitemap.xml",
            )
        )

    llms = _safe_get(urljoin(base_url, "/llms.txt"))
    if llms is not None and llms.status_code == 200:
        findings.append("llms.txt reachable")
        score += 40
    else:
        issues.append(
            DetectedIssue(
                id="DISC-003",
                category=AnalysisCategory.DISCOVERABILITY,
                severity=Severity.MEDIUM,
                title="Missing llms.txt",
                description="No llms.txt file found, limiting how easily agentic crawlers can discover the site.",
                evidence_ref="/llms.txt",
            )
        )

    return CategoryScore(AnalysisCategory.DISCOVERABILITY, score=score, findings=findings), issues


def check_comprehension(homepage_html: str) -> tuple[CategoryScore, list[DetectedIssue]]:
    findings: list[str] = []
    issues: list[DetectedIssue] = []
    score = 0

    if re.search(r"<html[^>]*\blang=", homepage_html, re.IGNORECASE):
        findings.append("lang attribute present on <html>")
        score += 25
    else:
        issues.append(
            DetectedIssue(
                id="COMP-001",
                category=AnalysisCategory.COMPREHENSION,
                severity=Severity.LOW,
                title="Missing lang attribute",
                description="The <html> tag has no lang attribute, which helps agents identify content language.",
            )
        )

    if re.search(r"application/ld\+json", homepage_html, re.IGNORECASE):
        findings.append("JSON-LD structured data present")
        score += 40
    else:
        issues.append(
            DetectedIssue(
                id="COMP-002",
                category=AnalysisCategory.COMPREHENSION,
                severity=Severity.MEDIUM,
                title="No structured data detected",
                description="No JSON-LD (schema.org) block found on the homepage, reducing machine comprehension.",
            )
        )

    if re.search(r"<(main|article|nav)\b", homepage_html, re.IGNORECASE):
        findings.append("Semantic HTML5 landmarks present")
        score += 35
    else:
        issues.append(
            DetectedIssue(
                id="COMP-003",
                category=AnalysisCategory.COMPREHENSION,
                severity=Severity.LOW,
                title="Limited semantic HTML",
                description="No <main>/<article>/<nav> landmarks found on the homepage.",
            )
        )

    return CategoryScore(AnalysisCategory.COMPREHENSION, score=score, findings=findings), issues


def check_interaction(base_url: str) -> tuple[CategoryScore, list[DetectedIssue]]:
    findings: list[str] = []
    issues: list[DetectedIssue] = []
    score = 0

    candidate_paths = [
        "/openapi.json",
        "/swagger.json",
        "/.well-known/ai-plugin.json",
        "/.well-known/mcp.json",
    ]
    found_any = False
    for path in candidate_paths:
        resp = _safe_get(urljoin(base_url, path))
        if resp is not None and resp.status_code == 200:
            findings.append(f"{path} reachable")
            score += 25
            found_any = True

    if not found_any:
        issues.append(
            DetectedIssue(
                id="INT-001",
                category=AnalysisCategory.INTERACTION,
                severity=Severity.HIGH,
                title="No machine-readable API spec found",
                description=(
                    "No OpenAPI/Swagger definition or plugin manifest found at common "
                    "discovery paths, making programmatic interaction difficult for agents."
                ),
            )
        )

    return CategoryScore(AnalysisCategory.INTERACTION, score=score, findings=findings), issues


def check_security(base_url: str, homepage_resp) -> tuple[CategoryScore, list[DetectedIssue]]:
    findings: list[str] = []
    issues: list[DetectedIssue] = []
    score = 0

    if base_url.startswith("https://"):
        findings.append("HTTPS enforced")
        score += 40
    else:
        issues.append(
            DetectedIssue(
                id="SEC-001",
                category=AnalysisCategory.SECURITY,
                severity=Severity.CRITICAL,
                title="Site not served over HTTPS",
                description="The site does not enforce HTTPS for its primary URL.",
            )
        )

    headers = {k.lower() for k in (homepage_resp.headers if homepage_resp is not None else {})}

    if "strict-transport-security" in headers:
        findings.append("HSTS header present")
        score += 30
    else:
        issues.append(
            DetectedIssue(
                id="SEC-002",
                category=AnalysisCategory.SECURITY,
                severity=Severity.MEDIUM,
                title="Missing Strict-Transport-Security header",
                description="No HSTS header found on the homepage response.",
            )
        )

    if "content-security-policy" in headers:
        findings.append("CSP header present")
        score += 30
    else:
        issues.append(
            DetectedIssue(
                id="SEC-003",
                category=AnalysisCategory.SECURITY,
                severity=Severity.MEDIUM,
                title="Missing Content-Security-Policy header",
                description="No Content-Security-Policy header found on the homepage response.",
            )
        )

    return CategoryScore(AnalysisCategory.SECURITY, score=score, findings=findings), issues


def _estimate_effort(severity: Severity) -> str:
    return {
        Severity.CRITICAL: "high",
        Severity.HIGH: "medium",
        Severity.MEDIUM: "medium",
        Severity.LOW: "low",
        Severity.INFO: "low",
    }[severity]


def _estimate_impact(severity: Severity) -> str:
    return {
        Severity.CRITICAL: "high",
        Severity.HIGH: "high",
        Severity.MEDIUM: "medium",
        Severity.LOW: "medium",
        Severity.INFO: "low",
    }[severity]


def _knowledge_sources_for_issue(issue: DetectedIssue) -> list[str]:
    if issue.category == AnalysisCategory.SECURITY:
        return ["Security Practices", "Agentic Web Practices"]
    if issue.category == AnalysisCategory.INTERACTION:
        return ["OpenAPI Best Practices", "Agentic Web Practices"]
    if issue.category == AnalysisCategory.COMPREHENSION:
        return ["HTML Semantics", "Agentic Web Practices"]
    return ["Agentic Web Practices"]


def _rag_context_for_issue(issue: DetectedIssue) -> str:
    if issue.category == AnalysisCategory.SECURITY:
        return (
            "(source: Security Practices)\n"
            "Security headers and HTTPS enforcement are essential for agentic trust.\n"
            "Configure HSTS and CSP to protect both users and automated consumers."
        )
    if issue.category == AnalysisCategory.INTERACTION:
        return (
            "(source: OpenAPI Best Practices)\n"
            "Expose a machine-readable API specification so agents can discover supported actions.\n"
            "Use /openapi.json, /swagger.json, or /.well-known/ai-plugin.json."
        )
    if issue.category == AnalysisCategory.COMPREHENSION:
        return (
            "(source: HTML Semantics)\n"
            "Clear language declarations and structured data help machines understand page intent.\n"
            "Include lang attributes and JSON-LD schema wherever possible."
        )
    return (
        "(source: Agentic Web Practices)\n"
        "Discovery files such as robots.txt, sitemap.xml and llms.txt make the site easier to index and automate.\n"
        "Ensure they are present and accurate."
    )


def _describe_recommendation(issue: DetectedIssue) -> str:
    return (
        f"{issue.description} "
        "To improve agentic readiness, address this issue now and verify the fix with automated discovery tests."
    )


def build_recommendations(issues: list[DetectedIssue]) -> RecommendationResult:
    """Turn detected issues into recommendations via a simple 1:1 heuristic.

    (In the full ARAF pipeline this logic lives in the Recommendation Agent —
    inlined here only so this test file is self-contained.)
    """

    priority_by_severity = {
        Severity.CRITICAL: Priority.P0,
        Severity.HIGH: Priority.P0,
        Severity.MEDIUM: Priority.P1,
        Severity.LOW: Priority.P2,
        Severity.INFO: Priority.P2,
    }

    recommendations = [
        Recommendation(
            id=f"REC-{issue.id}",
            category=issue.category,
            priority=priority_by_severity.get(issue.severity, Priority.P1),
            title=f"Fix: {issue.title}",
            description=_describe_recommendation(issue),
            related_issue_ids=[issue.id],
            effort=_estimate_effort(issue.severity),
            impact=_estimate_impact(issue.severity),
            knowledge_sources=_knowledge_sources_for_issue(issue),
            rag_context=_rag_context_for_issue(issue),
        )
        for issue in issues
    ]
    return RecommendationResult(
        recommendations=recommendations,
        rag_sources_used=["Agentic Web Practices", "Security Practices", "OpenAPI Best Practices", "HTML Semantics"],
    )


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------

def test_generate_bpifrance_pdf_report():
    if requests is None:
        _skip("The 'requests' package is required for this live test (pip install requests).")

    homepage = _safe_get(TARGET_URL)
    if homepage is None:
        _skip(f"{TARGET_URL} is unreachable from this environment (no internet access?).")

    disc_score, disc_issues = check_discoverability(TARGET_URL)
    comp_score, comp_issues = check_comprehension(homepage.text)
    inter_score, inter_issues = check_interaction(TARGET_URL)
    sec_score, sec_issues = check_security(TARGET_URL, homepage)

    all_issues = disc_issues + comp_issues + inter_issues + sec_issues
    category_scores = [disc_score, comp_score, inter_score, sec_score]
    overall_score = sum(cs.score for cs in category_scores) / len(category_scores)

    assessment = AssessmentResult(
        url=TARGET_URL,
        assessed_at=utcnow(),
        overall_score=overall_score,
        category_scores=category_scores,
        issues=all_issues,
        artifacts_collected=["HTML homepage", "robots.txt", "sitemap.xml", "llms.txt"],
    )
    recommendations = build_recommendations(all_issues)

    agent = ReportGeneratorAgent()
    report = agent.generate(assessment, recommendations)

    GENERAL_REPORT_PDF.parent.mkdir(parents=True, exist_ok=True)
    written_path = agent.save(report, GENERAL_REPORT_PDF, fmt="pdf")

    assert written_path.exists()
    assert written_path.stat().st_size > 0

    print(f"\nOverall score for {TARGET_URL}: {overall_score:.1f}/100")
    print(f"PDF report written to: {written_path.resolve()}")


if __name__ == "__main__":
    # Allow `python tests/test_report_generator_agent.py` as a quick manual run
    # without needing pytest installed.
    try:
        test_generate_bpifrance_pdf_report()
        print("OK")
    except _SkipTest as exc:
        print(f"SKIPPED: {exc}")