"""Unit tests for :class:`SimulationAgent`.

Covers: unified-diff application (the in-memory counterpart to
`AutoFixAgent._build_diff`), cumulative per-category simulation with
injected fake category agents, the `BLACK_BOX` skip path, the
"no applicable fix" skip path, unknown-category handling, overall
score aggregation, and the `run()` standard input contract.
"""

from __future__ import annotations

import difflib
import sys
import unittest
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.simulation_agent import SimulationAgent
from models.assessment import AssessmentResult
from models.autofix_pipeline import AutoFixPipelineResult
from models.evidence import WebsiteEvidence
from models.fix import AutoFixResult, ProposedFix
from models.mode import ModeSelection, OperatingMode
from models.validation import FixValidation, ValidationResult, ValidationStatus


# ----------------------------------------------------------------------
# Fixtures / builders
# ----------------------------------------------------------------------


def _diff(before: str, after: str, path_label: str = "robots.txt") -> str:
    """Build a diff exactly the way `AutoFixAgent._build_diff` does."""
    diff_lines = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=f"a/{path_label}",
        tofile=f"b/{path_label}",
        lineterm="",
    )
    return "\n".join(diff_lines)


def _fix(
    issue: str,
    category: str = "discoverability",
    diff: str = "",
    mode: str = "git_repo",
    confidence: float = 0.9,
) -> ProposedFix:
    return ProposedFix(
        issue=issue,
        category=category,
        fix_type="rule_based",
        mode=mode,
        confidence=confidence,
        diff=diff,
        instruction=f"Instruction for {issue}",
    )


def _evidence(robots_txt: Optional[str] = None) -> WebsiteEvidence:
    return WebsiteEvidence(url="https://example.com", robots_txt=robots_txt)


def _assessment_result(
    discoverability: float = 50.0,
    comprehension: float = 60.0,
    interaction: float = 70.0,
    security: float = 80.0,
) -> AssessmentResult:
    scores = {
        "discoverability": discoverability,
        "comprehension": comprehension,
        "interaction": interaction,
        "security": security,
    }
    return AssessmentResult(
        url="https://example.com",
        discoverability={"score": discoverability},
        comprehension={"score": comprehension},
        interaction={"score": interaction},
        security={"score": security},
        overall_score=round(sum(scores.values()) / 4, 2),
    )


def _mode_selection(
    mode: OperatingMode = OperatingMode.GIT_REPO,
    can_apply_fixes: bool = True,
    repo_path: Optional[str] = "/tmp/fake-repo",
) -> ModeSelection:
    return ModeSelection(
        mode=mode,
        can_apply_fixes=can_apply_fixes,
        repo_path=repo_path,
        reason="test",
        source="local" if mode == OperatingMode.GIT_REPO else "none",
    )


def _validation_result(approved_fixes: list[ProposedFix], mode: str = "git_repo") -> ValidationResult:
    validations = [
        FixValidation(fix=fix, status=ValidationStatus.APPROVED, reviewer="human")
        for fix in approved_fixes
    ]
    return ValidationResult(
        validations=validations,
        mode=mode,
        approved_count=len(validations),
        rejected_count=0,
        pending_count=0,
    )


def _pipeline_result(
    mode_selection: ModeSelection, approved_fixes: list[ProposedFix]
) -> AutoFixPipelineResult:
    autofix_result = AutoFixResult(
        fixes=approved_fixes,
        total_fixes=len(approved_fixes),
        rule_based_count=len(approved_fixes),
        mode=mode_selection.mode.value,
    )
    return AutoFixPipelineResult(
        mode_selection=mode_selection,
        autofix_result=autofix_result,
        validation_result=_validation_result(approved_fixes, mode_selection.mode.value),
    )


class _FakeCategoryResult:
    def __init__(self, score: float) -> None:
        self.score = score


class _FakeCategoryAgent:
    """Returns a fixed score and records every evidence it was called with."""

    def __init__(self, score: float) -> None:
        self._score = score
        self.calls: list[WebsiteEvidence] = []

    def evaluate(self, evidence: WebsiteEvidence) -> _FakeCategoryResult:
        self.calls.append(evidence)
        return _FakeCategoryResult(self._score)


def _agent(
    discoverability_score: float = 90.0,
    comprehension_score: float = 60.0,
    interaction_score: float = 70.0,
    security_score: float = 80.0,
) -> tuple[SimulationAgent, dict[str, _FakeCategoryAgent]]:
    fakes = {
        "discoverability": _FakeCategoryAgent(discoverability_score),
        "comprehension": _FakeCategoryAgent(comprehension_score),
        "interaction": _FakeCategoryAgent(interaction_score),
        "security": _FakeCategoryAgent(security_score),
    }
    agent = SimulationAgent(
        discoverability_agent=fakes["discoverability"],
        comprehension_agent=fakes["comprehension"],
        interaction_agent=fakes["interaction"],
        security_agent=fakes["security"],
    )
    return agent, fakes


# ----------------------------------------------------------------------
# Unified diff application
# ----------------------------------------------------------------------


class ApplyUnifiedDiffTests(unittest.TestCase):
    def test_apply_diff_creates_missing_file(self) -> None:
        after = "User-agent: *\nAllow: /"
        diff = _diff("", after)

        patched = SimulationAgent._apply_unified_diff("", diff)

        self.assertEqual(patched, "User-agent: *\nAllow: /\n")

    def test_apply_diff_unblocks_bot(self) -> None:
        before = "User-agent: gptbot\nDisallow: /\n"
        after = "User-agent: gptbot\nAllow: /"
        diff = _diff(before, after)

        patched = SimulationAgent._apply_unified_diff(before, diff)

        self.assertEqual(patched, "User-agent: gptbot\nAllow: /\n")

    def test_apply_diff_preserves_untouched_context(self) -> None:
        before = "User-agent: *\nDisallow: /admin\nUser-agent: gptbot\nDisallow: /\n"
        after = "User-agent: *\nDisallow: /admin\nUser-agent: gptbot\nAllow: /"
        diff = _diff(before, after)

        patched = SimulationAgent._apply_unified_diff(before, diff)

        self.assertEqual(
            patched,
            "User-agent: *\nDisallow: /admin\nUser-agent: gptbot\nAllow: /\n",
        )

    def test_malformed_hunk_header_raises(self) -> None:
        with self.assertRaises(ValueError):
            SimulationAgent._apply_unified_diff("a", "@@ not a real header @@\n+b")

    def test_parse_diff_target_extracts_basename(self) -> None:
        diff = _diff("", "content")
        self.assertEqual(SimulationAgent._parse_diff_target(diff), "robots.txt")

    def test_parse_diff_target_none_for_empty_diff(self) -> None:
        self.assertIsNone(SimulationAgent._parse_diff_target(""))


# ----------------------------------------------------------------------
# Per-category simulation
# ----------------------------------------------------------------------


class SimulateTests(unittest.TestCase):
    def test_git_repo_mode_rescoes_category_with_single_fix(self) -> None:
        agent, fakes = _agent(discoverability_score=95.0)
        diff = _diff("", "User-agent: *\nAllow: /")
        fix = _fix("robots.txt missing", category="discoverability", diff=diff)

        result = agent.simulate(
            evidence=_evidence(robots_txt=None),
            assessment_result=_assessment_result(discoverability=50.0),
            pipeline_result=_pipeline_result(_mode_selection(), [fix]),
        )

        self.assertEqual(len(result.category_simulations), 1)
        sim = result.category_simulations[0]
        self.assertEqual(sim.category, "discoverability")
        self.assertFalse(sim.skipped)
        self.assertEqual(sim.score_before, 50.0)
        self.assertEqual(sim.score_after, 95.0)
        self.assertEqual(sim.delta, 45.0)
        self.assertEqual(sim.fixes_applied, [fix])
        # The category agent must have been called with a *patched*
        # copy, not the original evidence object.
        called_with = fakes["discoverability"].calls[0]
        self.assertEqual(called_with.robots_txt, "User-agent: *\nAllow: /\n")

    def test_original_evidence_is_never_mutated(self) -> None:
        agent, _ = _agent()
        diff = _diff("", "User-agent: *\nAllow: /")
        fix = _fix("robots.txt missing", diff=diff)
        original_evidence = _evidence(robots_txt=None)

        agent.simulate(
            evidence=original_evidence,
            assessment_result=_assessment_result(),
            pipeline_result=_pipeline_result(_mode_selection(), [fix]),
        )

        self.assertIsNone(original_evidence.robots_txt)

    def test_cumulative_simulation_applies_all_fixes_in_category_once(self) -> None:
        agent, fakes = _agent(discoverability_score=99.0)
        before = "User-agent: gptbot\nDisallow: /\nUser-agent: claudebot\nDisallow: /\n"
        after1 = "User-agent: gptbot\nAllow: /\nUser-agent: claudebot\nDisallow: /"
        diff1 = _diff(before, after1)
        after2 = "User-agent: gptbot\nAllow: /\nUser-agent: claudebot\nAllow: /"
        diff2 = _diff(after1, after2)

        fix1 = _fix("robots.txt blocks gptbot", diff=diff1)
        fix2 = _fix("robots.txt blocks claudebot", diff=diff2)

        result = agent.simulate(
            evidence=_evidence(robots_txt=before),
            assessment_result=_assessment_result(discoverability=40.0),
            pipeline_result=_pipeline_result(_mode_selection(), [fix1, fix2]),
        )

        self.assertEqual(len(result.category_simulations), 1)
        sim = result.category_simulations[0]
        self.assertEqual(len(sim.fixes_applied), 2)
        # Category agent called exactly once for both fixes combined.
        self.assertEqual(len(fakes["discoverability"].calls), 1)

    def test_black_box_mode_skips_with_reason(self) -> None:
        agent, fakes = _agent()
        fix = _fix("robots.txt missing", mode="black_box")

        result = agent.simulate(
            evidence=_evidence(),
            assessment_result=_assessment_result(discoverability=50.0),
            pipeline_result=_pipeline_result(
                _mode_selection(mode=OperatingMode.BLACK_BOX, can_apply_fixes=False, repo_path=None),
                [fix],
            ),
        )

        sim = result.category_simulations[0]
        self.assertTrue(sim.skipped)
        self.assertIsNone(sim.score_after)
        self.assertIsNone(sim.delta)
        self.assertIn("black_box", sim.skip_reason)
        self.assertEqual(fakes["discoverability"].calls, [])

    def test_empty_diff_skips_category_with_no_applicable_fix(self) -> None:
        agent, fakes = _agent()
        fix = _fix("robots.txt missing", diff="")

        result = agent.simulate(
            evidence=_evidence(),
            assessment_result=_assessment_result(),
            pipeline_result=_pipeline_result(_mode_selection(), [fix]),
        )

        sim = result.category_simulations[0]
        self.assertTrue(sim.skipped)
        self.assertEqual(sim.fixes_applied, [])
        self.assertEqual(fakes["discoverability"].calls, [])

    def test_unsupported_target_file_skips_category(self) -> None:
        agent, fakes = _agent()
        diff = _diff("", "console.log('x')", path_label="app.js")
        fix = _fix("some js issue", diff=diff)

        result = agent.simulate(
            evidence=_evidence(),
            assessment_result=_assessment_result(),
            pipeline_result=_pipeline_result(_mode_selection(), [fix]),
        )

        sim = result.category_simulations[0]
        self.assertTrue(sim.skipped)
        self.assertEqual(fakes["discoverability"].calls, [])

    def test_unknown_category_is_skipped(self) -> None:
        agent, _ = _agent()
        diff = _diff("", "x")
        fix = _fix("weird issue", category="performance", diff=diff)

        result = agent.simulate(
            evidence=_evidence(),
            assessment_result=_assessment_result(),
            pipeline_result=_pipeline_result(_mode_selection(), [fix]),
        )

        sim = result.category_simulations[0]
        self.assertTrue(sim.skipped)
        self.assertIn("performance", sim.skip_reason)

    def test_no_approved_fixes_yields_no_category_simulations(self) -> None:
        agent, _ = _agent()

        result = agent.simulate(
            evidence=_evidence(),
            assessment_result=_assessment_result(),
            pipeline_result=_pipeline_result(_mode_selection(), []),
        )

        self.assertEqual(result.category_simulations, [])
        self.assertEqual(result.overall_score_after, result.overall_score_before)
        self.assertEqual(result.overall_delta, 0.0)


# ----------------------------------------------------------------------
# Overall score aggregation
# ----------------------------------------------------------------------


class OverallScoreTests(unittest.TestCase):
    def test_overall_score_mixes_simulated_and_unchanged_categories(self) -> None:
        agent, _ = _agent(discoverability_score=100.0)
        diff = _diff("", "User-agent: *\nAllow: /")
        fix = _fix("robots.txt missing", category="discoverability", diff=diff)

        result = agent.simulate(
            evidence=_evidence(),
            assessment_result=_assessment_result(
                discoverability=50.0, comprehension=60.0, interaction=70.0, security=80.0
            ),
            pipeline_result=_pipeline_result(_mode_selection(), [fix]),
        )

        # (100 + 60 + 70 + 80) / 4 = 77.5 — only discoverability moved.
        self.assertEqual(result.overall_score_after, 77.5)
        self.assertEqual(result.overall_score_before, 65.0)

    def test_skipped_category_keeps_its_original_score_in_overall(self) -> None:
        agent, _ = _agent()
        fix = _fix("robots.txt missing", category="discoverability", diff="")

        result = agent.simulate(
            evidence=_evidence(),
            assessment_result=_assessment_result(
                discoverability=50.0, comprehension=60.0, interaction=70.0, security=80.0
            ),
            pipeline_result=_pipeline_result(_mode_selection(), [fix]),
        )

        self.assertEqual(result.overall_score_after, result.overall_score_before)


# ----------------------------------------------------------------------
# Standard input contract
# ----------------------------------------------------------------------


class RunContractTests(unittest.TestCase):
    def test_run_delegates_to_simulate(self) -> None:
        agent, _ = _agent(discoverability_score=95.0)
        diff = _diff("", "User-agent: *\nAllow: /")
        fix = _fix("robots.txt missing", diff=diff)
        evidence = _evidence()
        assessment_result = _assessment_result(discoverability=50.0)
        pipeline_result = _pipeline_result(_mode_selection(), [fix])

        result = agent.run(
            {
                "evidence": evidence,
                "assessment_result": assessment_result,
                "pipeline_result": pipeline_result,
            }
        )

        self.assertEqual(len(result.category_simulations), 1)
        self.assertEqual(result.category_simulations[0].score_after, 95.0)


if __name__ == "__main__":
    unittest.main()