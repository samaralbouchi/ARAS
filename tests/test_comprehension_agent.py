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
from pathlib import Path

# Allow running this file directly (e.g. from an IDE "Run" button) by
# ensuring the project root is importable, not just the `tests/` folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.comprehension_agent import ComprehensionAgent
from agents.evidence_collector import EvidenceCollectorAgent
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
# Agent. Adds no new logic to either agent; it only orchestrates the two
# existing components.
# ---------------------------------------------------------------------------


def test_real_site_comprehension() -> None:
    """End-to-end: collect real evidence, then evaluate comprehension.

    Requires network access.
    """
    evidence = EvidenceCollectorAgent().collect(TARGET_URL)
    result = ComprehensionAgent().evaluate(evidence)
    _print_result(f"real site: {TARGET_URL}", result)

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
