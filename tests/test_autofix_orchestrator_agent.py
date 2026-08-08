"""Unit tests for :class:`AutoFixOrchestratorAgent`.

Covers: the happy-path chain (mode selection -> AutoFix -> human
validation) via injected fake collaborators, the `run()` standard
input contract, the `decide()` pass-through, and the "Rejeté" retry
loop — including that approved/pending fixes are left untouched by a
retry and that a retry with nothing rejected is a no-op.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.autofix_orchestrator_agent import AutoFixOrchestratorAgent
from models.fix import AutoFixResult, ProposedFix
from models.mode import ModeSelection, OperatingMode
from models.recommendation import Recommendation, RecommendationResult
from models.validation import FixValidation, ValidationResult, ValidationStatus


def _recommendation(issue: str, category: str = "discoverability") -> Recommendation:
    return Recommendation(
        category=category,
        issue=issue,
        recommendation=f"Fix: {issue}",
    )


def _fix(
    issue: str,
    category: str = "discoverability",
    confidence: float = 0.9,
    fix_type: str = "rule_based",
) -> ProposedFix:
    return ProposedFix(
        issue=issue,
        category=category,
        fix_type=fix_type,
        mode="black_box",
        confidence=confidence,
        instruction=f"Instruction for {issue}",
    )


class _FakeModeSelector:
    def __init__(self, selection: ModeSelection) -> None:
        self.selection = selection
        self.calls: list[tuple[Optional[str], Optional[str]]] = []

    def select(
        self, repo_path: Optional[str] = None, repo_url: Optional[str] = None
    ) -> ModeSelection:
        self.calls.append((repo_path, repo_url))
        return self.selection


class _FakeAutoFix:
    """Returns one rule_based fix per recommendation it's given.

    Each call is recorded so tests can assert exactly which
    recommendations were (re)sent to the AutoFix agent.
    """

    def __init__(self) -> None:
        self.calls: list[RecommendationResult] = []

    def propose_fixes(
        self,
        recommendation_result: RecommendationResult,
        mode_selection: ModeSelection,
    ) -> AutoFixResult:
        self.calls.append(recommendation_result)
        fixes = [
            _fix(rec.issue, rec.category)
            for rec in recommendation_result.recommendations
        ]
        return AutoFixResult(
            fixes=fixes,
            total_fixes=len(fixes),
            rule_based_count=len(fixes),
            llm_generated_count=0,
            mode=mode_selection.mode.value,
        )


class _FakeHumanValidation:
    """Every fix starts PENDING; `decide()` mirrors the real agent."""

    def review(self, autofix_result: AutoFixResult) -> ValidationResult:
        validations = [
            FixValidation(fix=fix, status=ValidationStatus.PENDING)
            for fix in autofix_result.fixes
        ]
        return ValidationResult(
            validations=validations,
            mode=autofix_result.mode,
            approved_count=0,
            rejected_count=0,
            pending_count=len(validations),
        )

    def decide(
        self,
        validation_result: ValidationResult,
        fix_index: int,
        approved: bool,
        reviewer: str,
        note: str = "",
    ) -> ValidationResult:
        if not reviewer or not reviewer.strip():
            raise ValueError("reviewer requis")

        from dataclasses import replace

        new_status = (
            ValidationStatus.APPROVED if approved else ValidationStatus.REJECTED
        )
        validations = list(validation_result.validations)
        validations[fix_index] = replace(
            validations[fix_index],
            status=new_status,
            reviewer=reviewer,
            note=note,
        )

        approved_count = sum(
            1 for v in validations if v.status == ValidationStatus.APPROVED
        )
        rejected_count = sum(
            1 for v in validations if v.status == ValidationStatus.REJECTED
        )
        pending_count = sum(
            1 for v in validations if v.status == ValidationStatus.PENDING
        )

        return ValidationResult(
            validations=validations,
            mode=validation_result.mode,
            approved_count=approved_count,
            rejected_count=rejected_count,
            pending_count=pending_count,
        )


def _black_box_selection() -> ModeSelection:
    return ModeSelection(
        mode=OperatingMode.BLACK_BOX,
        can_apply_fixes=False,
        reason="test",
        source="none",
    )


class AutoFixOrchestratorAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mode_selector = _FakeModeSelector(_black_box_selection())
        self.autofix = _FakeAutoFix()
        self.human_validation = _FakeHumanValidation()
        self.orchestrator = AutoFixOrchestratorAgent(
            mode_selector_agent=self.mode_selector,
            autofix_agent=self.autofix,
            human_validation_agent=self.human_validation,
        )
        self.recommendation_result = RecommendationResult(
            recommendations=[
                _recommendation("No robots.txt found", "discoverability"),
                _recommendation("Missing security headers", "security"),
            ],
            total_issues=2,
        )

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_execute_chains_mode_selection_autofix_and_validation(self) -> None:
        result = self.orchestrator.execute(self.recommendation_result)

        self.assertEqual(result.mode_selection.mode, OperatingMode.BLACK_BOX)
        self.assertEqual(result.autofix_result.total_fixes, 2)
        self.assertEqual(result.validation_result.pending_count, 2)
        self.assertEqual(self.mode_selector.calls, [(None, None)])
        self.assertEqual(len(self.autofix.calls), 1)
        self.assertFalse(result.ready_for_simulation)

    def test_execute_forwards_repo_path_and_repo_url(self) -> None:
        self.orchestrator.execute(
            self.recommendation_result,
            repo_path="/some/repo",
            repo_url="https://example.com/repo.git",
        )

        self.assertEqual(
            self.mode_selector.calls, [("/some/repo", "https://example.com/repo.git")]
        )

    def test_run_standard_input_contract(self) -> None:
        result = self.orchestrator.run(
            {"recommendation_result": self.recommendation_result}
        )

        self.assertEqual(result.autofix_result.total_fixes, 2)

    def test_ready_for_simulation_true_once_fully_reviewed_with_an_approval(
        self,
    ) -> None:
        result = self.orchestrator.execute(self.recommendation_result)

        result = self.orchestrator.decide(
            result, fix_index=0, approved=True, reviewer="sam"
        )
        result = self.orchestrator.decide(
            result, fix_index=1, approved=True, reviewer="sam"
        )

        self.assertTrue(result.ready_for_simulation)

    # ------------------------------------------------------------------
    # decide()
    # ------------------------------------------------------------------

    def test_decide_updates_validation_only(self) -> None:
        result = self.orchestrator.execute(self.recommendation_result)

        updated = self.orchestrator.decide(
            result, fix_index=0, approved=True, reviewer="sam", note="looks fine"
        )

        self.assertIs(updated.mode_selection, result.mode_selection)
        self.assertIs(updated.autofix_result, result.autofix_result)
        self.assertEqual(updated.validation_result.approved_count, 1)
        self.assertEqual(updated.validation_result.pending_count, 1)
        self.assertEqual(
            updated.validation_result.validations[0].reviewer, "sam"
        )

    # ------------------------------------------------------------------
    # retry_rejected() -- the "Rejeté" loop
    # ------------------------------------------------------------------

    def test_retry_rejected_resends_only_rejected_issues_to_autofix(self) -> None:
        result = self.orchestrator.execute(self.recommendation_result)
        result = self.orchestrator.decide(
            result, fix_index=0, approved=True, reviewer="sam"
        )
        result = self.orchestrator.decide(
            result, fix_index=1, approved=False, reviewer="sam", note="too risky"
        )

        retried = self.orchestrator.retry_rejected(
            result, self.recommendation_result
        )

        # Only the rejected issue was resent to the AutoFix agent.
        second_call = self.autofix.calls[-1]
        self.assertEqual(len(second_call.recommendations), 1)
        self.assertEqual(
            second_call.recommendations[0].issue, "Missing security headers"
        )

        # The approved fix is untouched.
        approved_validation = next(
            v
            for v in retried.validation_result.validations
            if v.fix.issue == "No robots.txt found"
        )
        self.assertEqual(approved_validation.status, ValidationStatus.APPROVED)
        self.assertEqual(approved_validation.reviewer, "sam")

        # The retried issue is back to PENDING (fresh proposal, not
        # auto-approved), not left as REJECTED.
        retried_validation = next(
            v
            for v in retried.validation_result.validations
            if v.fix.issue == "Missing security headers"
        )
        self.assertEqual(retried_validation.status, ValidationStatus.PENDING)

        self.assertEqual(retried.autofix_result.total_fixes, 2)
        self.assertEqual(retried.validation_result.approved_count, 1)
        self.assertEqual(retried.validation_result.pending_count, 1)
        self.assertEqual(retried.validation_result.rejected_count, 0)

    def test_retry_rejected_is_noop_when_nothing_rejected(self) -> None:
        result = self.orchestrator.execute(self.recommendation_result)
        result = self.orchestrator.decide(
            result, fix_index=0, approved=True, reviewer="sam"
        )

        retried = self.orchestrator.retry_rejected(
            result, self.recommendation_result
        )

        self.assertIs(retried, result)
        # No extra call to the AutoFix agent.
        self.assertEqual(len(self.autofix.calls), 1)


if __name__ == "__main__":
    unittest.main()