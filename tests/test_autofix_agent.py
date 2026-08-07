"""Unit tests for :class:`AutoFixAgent`.

Covers: rule-based fixes for `robots.txt` (missing and blocked
agents) in both black-box mode (instruction only) and git-repo mode
(real diff computed from files on disk), and LLM-generated fixes for
every other issue via an injected fake generator so no real Ollama
server is required. Also covers aggregate counts on `AutoFixResult`
and defensive fallback when the generator raises.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.autofix_agent import AutoFixAgent
from models.mode import ModeSelection, OperatingMode
from models.recommendation import Recommendation, RecommendationResult


def _mode(
    mode: OperatingMode = OperatingMode.BLACK_BOX,
    can_apply_fixes: bool = False,
    repo_path: str | None = None,
) -> ModeSelection:
    return ModeSelection(
        mode=mode,
        can_apply_fixes=can_apply_fixes,
        repo_path=repo_path,
        reason="test",
        source="local" if repo_path else "none",
    )


def _recommendation(
    issue: str,
    category: str = "discoverability",
    recommendation: str = "Fix it.",
    how_to_apply: str = "",
    rag_context: str = "",
) -> Recommendation:
    return Recommendation(
        category=category,
        issue=issue,
        recommendation=recommendation,
        how_to_apply=how_to_apply,
        rag_context=rag_context,
    )


class _FakeGenerator:
    """Deterministic stand-in for `FixGenerator`, no LLM call."""

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self._responses = responses

    def generate_all(
        self, recommendations: list[Recommendation]
    ) -> list[dict[str, Any]]:
        if self._responses is not None:
            return self._responses
        return [
            {"issue": rec.issue, "instruction": f"Do X for: {rec.issue}"}
            for rec in recommendations
        ]


class _RaisingGenerator:
    def generate_all(self, recommendations: list[Recommendation]):
        raise RuntimeError("boom")


class AutoFixAgentRuleBasedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = AutoFixAgent(generator=_FakeGenerator())

    def test_robots_missing_black_box_gives_instruction_no_diff(self) -> None:
        rec_result = RecommendationResult(
            recommendations=[_recommendation("No robots.txt found")],
            total_issues=1,
        )

        result = self.agent.propose_fixes(rec_result, _mode())

        self.assertEqual(result.total_fixes, 1)
        self.assertEqual(result.rule_based_count, 1)
        self.assertEqual(result.llm_generated_count, 0)

        fix = result.fixes[0]
        self.assertEqual(fix.fix_type, "rule_based")
        self.assertEqual(fix.confidence, 0.9)
        self.assertEqual(fix.diff, "")
        self.assertIn("robots.txt", fix.instruction)
        self.assertTrue(fix.requires_human_validation)
        self.assertEqual(fix.mode, OperatingMode.BLACK_BOX.value)

    def test_robots_missing_git_repo_mode_produces_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rec_result = RecommendationResult(
                recommendations=[_recommendation("No robots.txt found")],
                total_issues=1,
            )
            mode = _mode(OperatingMode.GIT_REPO, can_apply_fixes=True, repo_path=tmp)

            result = self.agent.propose_fixes(rec_result, mode)

            fix = result.fixes[0]
            self.assertEqual(fix.fix_type, "rule_based")
            self.assertNotEqual(fix.diff, "")
            self.assertIn("GPTBot", fix.diff)

    def test_robots_blocked_black_box_gives_instruction_no_diff(self) -> None:
        rec_result = RecommendationResult(
            recommendations=[
                _recommendation(
                    "robots.txt disallows known AI agents: gptbot, claudebot"
                )
            ],
            total_issues=1,
        )

        result = self.agent.propose_fixes(rec_result, _mode())

        fix = result.fixes[0]
        self.assertEqual(fix.fix_type, "rule_based")
        self.assertEqual(fix.diff, "")
        self.assertIn("gptbot", fix.instruction)
        self.assertIn("claudebot", fix.instruction)

    def test_robots_blocked_git_repo_mode_rewrites_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            robots_path = Path(tmp) / "robots.txt"
            robots_path.write_text(
                "User-agent: gptbot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
            )

            rec_result = RecommendationResult(
                recommendations=[
                    _recommendation(
                        "robots.txt disallows known AI agents: gptbot"
                    )
                ],
                total_issues=1,
            )
            mode = _mode(OperatingMode.GIT_REPO, can_apply_fixes=True, repo_path=tmp)

            result = self.agent.propose_fixes(rec_result, mode)

            fix = result.fixes[0]
            self.assertEqual(fix.fix_type, "rule_based")
            self.assertNotEqual(fix.diff, "")
            self.assertIn("+Allow: /", fix.diff)
            self.assertIn("-Disallow: /", fix.diff)

    def test_robots_blocked_git_repo_mode_no_file_found_falls_back_to_instruction(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rec_result = RecommendationResult(
                recommendations=[
                    _recommendation(
                        "robots.txt disallows known AI agents: gptbot"
                    )
                ],
                total_issues=1,
            )
            mode = _mode(OperatingMode.GIT_REPO, can_apply_fixes=True, repo_path=tmp)

            result = self.agent.propose_fixes(rec_result, mode)

            fix = result.fixes[0]
            self.assertEqual(fix.diff, "")
            self.assertIn("gptbot", fix.instruction)


class AutoFixAgentLlmFixTests(unittest.TestCase):
    def test_non_robots_issue_uses_llm_generator(self) -> None:
        agent = AutoFixAgent(generator=_FakeGenerator())
        rec_result = RecommendationResult(
            recommendations=[
                _recommendation(
                    "No schema.org markup found",
                    category="comprehension",
                    rag_context="some context",
                )
            ],
            total_issues=1,
        )

        result = agent.propose_fixes(rec_result, _mode())

        self.assertEqual(result.rule_based_count, 0)
        self.assertEqual(result.llm_generated_count, 1)

        fix = result.fixes[0]
        self.assertEqual(fix.fix_type, "llm_generated")
        self.assertEqual(fix.confidence, 0.7)  # has rag_context
        self.assertIn("No schema.org markup found", fix.instruction)

    def test_llm_fix_without_rag_context_has_lower_confidence(self) -> None:
        agent = AutoFixAgent(generator=_FakeGenerator())
        rec_result = RecommendationResult(
            recommendations=[
                _recommendation("No schema.org markup found", rag_context="")
            ],
            total_issues=1,
        )

        result = agent.propose_fixes(rec_result, _mode())

        self.assertEqual(result.fixes[0].confidence, 0.5)

    def test_llm_instruction_list_is_joined_into_text(self) -> None:
        agent = AutoFixAgent(
            generator=_FakeGenerator(
                responses=[{"issue": "x", "instruction": ["step 1", "step 2"]}]
            )
        )
        rec_result = RecommendationResult(
            recommendations=[_recommendation("Some other issue")],
            total_issues=1,
        )

        result = agent.propose_fixes(rec_result, _mode())

        self.assertEqual(result.fixes[0].instruction, "step 1\nstep 2")

    def test_generator_failure_falls_back_to_recommendation_text(self) -> None:
        agent = AutoFixAgent(generator=_RaisingGenerator())
        rec_result = RecommendationResult(
            recommendations=[
                _recommendation(
                    "Some other issue",
                    recommendation="Do the recommended thing.",
                    how_to_apply="",
                )
            ],
            total_issues=1,
        )

        result = agent.propose_fixes(rec_result, _mode())

        fix = result.fixes[0]
        self.assertEqual(fix.fix_type, "llm_generated")
        self.assertEqual(fix.instruction, "Do the recommended thing.")


class AutoFixAgentAggregateTests(unittest.TestCase):
    def test_mixed_issues_produce_correct_counts_and_order(self) -> None:
        agent = AutoFixAgent(generator=_FakeGenerator())
        rec_result = RecommendationResult(
            recommendations=[
                _recommendation("No robots.txt found"),
                _recommendation("No schema.org markup found", category="comprehension"),
                _recommendation(
                    "robots.txt disallows known AI agents: gptbot"
                ),
            ],
            total_issues=3,
        )

        result = agent.propose_fixes(rec_result, _mode())

        self.assertEqual(result.total_fixes, 3)
        self.assertEqual(result.rule_based_count, 2)
        self.assertEqual(result.llm_generated_count, 1)
        # Order must match the input recommendations, not the
        # rule-based/LLM processing order.
        self.assertEqual(
            [fix.issue for fix in result.fixes],
            [
                "No robots.txt found",
                "No schema.org markup found",
                "robots.txt disallows known AI agents: gptbot",
            ],
        )

    def test_empty_recommendations_gives_empty_result(self) -> None:
        agent = AutoFixAgent(generator=_FakeGenerator())
        rec_result = RecommendationResult(recommendations=[], total_issues=0)

        result = agent.propose_fixes(rec_result, _mode())

        self.assertEqual(result.total_fixes, 0)
        self.assertEqual(result.fixes, [])


if __name__ == "__main__":
    unittest.main()