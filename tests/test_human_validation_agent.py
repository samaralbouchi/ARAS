"""Unit tests for :class:`HumanValidationAgent`.

Covers the "Sécurité toujours validée" policy (security fixes are
never auto-approved, even at max confidence, and can only become
APPROVED via an explicit human `decide()` call), the optional
auto-approve threshold for non-security fixes, the reject-then-loop
path, and basic input validation on `decide()`.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.human_validation_agent import HumanValidationAgent
from models.fix import AutoFixResult, ProposedFix
from models.validation import ValidationStatus


def _make_fix(
    issue: str = "Missing meta description",
    category: str = "comprehension",
    confidence: float = 0.9,
    fix_type: str = "rule_based",
) -> ProposedFix:
    return ProposedFix(
        issue=issue,
        category=category,
        fix_type=fix_type,
        mode="black_box",
        confidence=confidence,
        instruction="Ajouter une balise meta description.",
    )


class HumanValidationAgentTests(unittest.TestCase):
    def test_security_fix_stays_pending_even_at_max_confidence(self) -> None:
        agent = HumanValidationAgent(auto_approve_threshold=0.5)
        autofix_result = AutoFixResult(
            fixes=[_make_fix(category="security", confidence=1.0)],
            total_fixes=1,
            mode="git_repo",
        )

        result = agent.review(autofix_result)

        self.assertEqual(result.validations[0].status, ValidationStatus.PENDING)
        self.assertEqual(result.pending_count, 1)
        self.assertEqual(result.approved_count, 0)

    def test_no_threshold_means_everything_pending(self) -> None:
        agent = HumanValidationAgent()  # no auto-approve threshold
        autofix_result = AutoFixResult(
            fixes=[_make_fix(category="discoverability", confidence=0.95)],
            total_fixes=1,
            mode="black_box",
        )

        result = agent.review(autofix_result)

        self.assertEqual(result.validations[0].status, ValidationStatus.PENDING)

    def test_non_security_fix_auto_approved_above_threshold(self) -> None:
        agent = HumanValidationAgent(auto_approve_threshold=0.8)
        autofix_result = AutoFixResult(
            fixes=[_make_fix(category="discoverability", confidence=0.9)],
            total_fixes=1,
            mode="git_repo",
        )

        result = agent.review(autofix_result)
        validation = result.validations[0]

        self.assertEqual(validation.status, ValidationStatus.APPROVED)
        self.assertTrue(validation.auto_approved)
        self.assertEqual(validation.reviewer, "system")
        self.assertEqual(result.approved_count, 1)

    def test_non_security_fix_below_threshold_stays_pending(self) -> None:
        agent = HumanValidationAgent(auto_approve_threshold=0.8)
        autofix_result = AutoFixResult(
            fixes=[_make_fix(category="comprehension", confidence=0.6)],
            total_fixes=1,
            mode="git_repo",
        )

        result = agent.review(autofix_result)

        self.assertEqual(result.validations[0].status, ValidationStatus.PENDING)

    def test_human_can_approve_a_pending_fix(self) -> None:
        agent = HumanValidationAgent()
        autofix_result = AutoFixResult(fixes=[_make_fix()], total_fixes=1, mode="black_box")
        result = agent.review(autofix_result)

        updated = agent.decide(result, fix_index=0, approved=True, reviewer="samar")

        self.assertEqual(updated.validations[0].status, ValidationStatus.APPROVED)
        self.assertEqual(updated.validations[0].reviewer, "samar")
        self.assertFalse(updated.validations[0].auto_approved)
        self.assertEqual(updated.approved_count, 1)
        self.assertEqual(updated.pending_count, 0)

    def test_human_can_approve_a_security_fix_explicitly(self) -> None:
        agent = HumanValidationAgent()
        autofix_result = AutoFixResult(
            fixes=[_make_fix(category="security", confidence=0.95)],
            total_fixes=1,
            mode="git_repo",
        )
        result = agent.review(autofix_result)

        updated = agent.decide(result, fix_index=0, approved=True, reviewer="samar")

        self.assertEqual(updated.validations[0].status, ValidationStatus.APPROVED)
        self.assertEqual(updated.validations[0].reviewer, "samar")

    def test_rejected_fix_is_exposed_for_the_autofix_loop(self) -> None:
        agent = HumanValidationAgent()
        fix = _make_fix(issue="Weak CSP header")
        autofix_result = AutoFixResult(fixes=[fix], total_fixes=1, mode="git_repo")
        result = agent.review(autofix_result)

        updated = agent.decide(
            result, fix_index=0, approved=False, reviewer="samar", note="Trop risqué."
        )

        self.assertEqual(updated.rejected_count, 1)
        self.assertEqual(len(updated.rejected_fixes), 1)
        self.assertIs(updated.rejected_fixes[0], fix)
        self.assertEqual(updated.validations[0].note, "Trop risqué.")

    def test_approved_and_rejected_fixes_properties(self) -> None:
        agent = HumanValidationAgent()
        fix_a = _make_fix(issue="A")
        fix_b = _make_fix(issue="B")
        autofix_result = AutoFixResult(fixes=[fix_a, fix_b], total_fixes=2, mode="black_box")
        result = agent.review(autofix_result)

        result = agent.decide(result, fix_index=0, approved=True, reviewer="samar")
        result = agent.decide(result, fix_index=1, approved=False, reviewer="samar")

        self.assertEqual(result.approved_fixes, [fix_a])
        self.assertEqual(result.rejected_fixes, [fix_b])
        self.assertTrue(result.is_fully_reviewed)

    def test_decide_requires_non_empty_reviewer(self) -> None:
        agent = HumanValidationAgent()
        autofix_result = AutoFixResult(fixes=[_make_fix()], total_fixes=1, mode="black_box")
        result = agent.review(autofix_result)

        with self.assertRaises(ValueError):
            agent.decide(result, fix_index=0, approved=True, reviewer="")

        with self.assertRaises(ValueError):
            agent.decide(result, fix_index=0, approved=True, reviewer="   ")

    def test_decide_rejects_out_of_range_index(self) -> None:
        agent = HumanValidationAgent()
        autofix_result = AutoFixResult(fixes=[_make_fix()], total_fixes=1, mode="black_box")
        result = agent.review(autofix_result)

        with self.assertRaises(IndexError):
            agent.decide(result, fix_index=5, approved=True, reviewer="samar")

    def test_invalid_threshold_raises(self) -> None:
        with self.assertRaises(ValueError):
            HumanValidationAgent(auto_approve_threshold=1.5)

    def test_decide_does_not_mutate_input_result(self) -> None:
        agent = HumanValidationAgent()
        autofix_result = AutoFixResult(fixes=[_make_fix()], total_fixes=1, mode="black_box")
        original = agent.review(autofix_result)

        agent.decide(original, fix_index=0, approved=True, reviewer="samar")

        # original is untouched (immutable / functional update pattern)
        self.assertEqual(original.validations[0].status, ValidationStatus.PENDING)


if __name__ == "__main__":
    unittest.main()