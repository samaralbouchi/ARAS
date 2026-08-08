"""Unit tests for :class:`AutoFixService`.

Covers: a full `start_run` -> `decide` -> `retry_rejected` -> `get_run`
cycle against a fake `AssessmentService` (no real HTTP/Ollama calls)
and a fake `AutoFixOrchestratorAgent`-shaped collaborator, plus the
error paths (unreachable URL, unknown run_id, invalid decide input).
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.app.services.autofix_service import AutoFixService
from models.autofix_pipeline import AutoFixPipelineResult
from models.fix import AutoFixResult, ProposedFix
from models.mode import ModeSelection, OperatingMode
from models.recommendation import Recommendation, RecommendationResult
from models.validation import FixValidation, ValidationResult, ValidationStatus


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _recommendation_result() -> RecommendationResult:
    return RecommendationResult(
        recommendations=[
            Recommendation(
                category="discoverability",
                issue="No robots.txt found",
                recommendation="Add one.",
            ),
        ],
        total_issues=1,
    )


class _FakeAssessmentService:
    """Stands in for AssessmentService: no HTTP, no Ollama."""

    def __init__(self, unreachable: bool = False) -> None:
        self._unreachable = unreachable

    async def get_recommendation_result(self, url: str) -> RecommendationResult:
        if self._unreachable:
            raise ValueError("Site inexistant ou inaccessible")
        return _recommendation_result()


class _FakeOrchestrator:
    """Deterministic stand-in for AutoFixOrchestratorAgent."""

    def execute(
        self,
        recommendation_result: RecommendationResult,
        repo_path: Optional[str] = None,
        repo_url: Optional[str] = None,
    ) -> AutoFixPipelineResult:
        fix = ProposedFix(
            issue=recommendation_result.recommendations[0].issue,
            category=recommendation_result.recommendations[0].category,
            fix_type="rule_based",
            mode="black_box",
            confidence=0.9,
            instruction="Do the thing.",
        )
        autofix_result = AutoFixResult(
            fixes=[fix], total_fixes=1, rule_based_count=1, mode="black_box"
        )
        validation = FixValidation(fix=fix, status=ValidationStatus.PENDING)
        validation_result = ValidationResult(
            validations=[validation],
            mode="black_box",
            pending_count=1,
        )
        return AutoFixPipelineResult(
            mode_selection=ModeSelection(
                mode=OperatingMode.BLACK_BOX,
                can_apply_fixes=False,
                reason="test",
                source="none",
            ),
            autofix_result=autofix_result,
            validation_result=validation_result,
        )

    def decide(
        self,
        pipeline_result: AutoFixPipelineResult,
        fix_index: int,
        approved: bool,
        reviewer: str,
        note: str = "",
    ) -> AutoFixPipelineResult:
        if not reviewer or not reviewer.strip():
            raise ValueError("reviewer requis")
        if not (0 <= fix_index < len(pipeline_result.validation_result.validations)):
            raise IndexError("fix_index hors limites")

        from dataclasses import replace

        validations = list(pipeline_result.validation_result.validations)
        validations[fix_index] = replace(
            validations[fix_index],
            status=ValidationStatus.APPROVED
            if approved
            else ValidationStatus.REJECTED,
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
        return AutoFixPipelineResult(
            mode_selection=pipeline_result.mode_selection,
            autofix_result=pipeline_result.autofix_result,
            validation_result=ValidationResult(
                validations=validations,
                mode=pipeline_result.validation_result.mode,
                approved_count=approved_count,
                rejected_count=rejected_count,
                pending_count=pending_count,
            ),
        )

    def retry_rejected(
        self,
        pipeline_result: AutoFixPipelineResult,
        recommendation_result: RecommendationResult,
    ) -> AutoFixPipelineResult:
        # Minimal stand-in: just re-run execute() on the same input,
        # good enough to prove the service wires the call through.
        return self.execute(recommendation_result)


class AutoFixServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AutoFixService(
            assessment_service=_FakeAssessmentService(),
            orchestrator=_FakeOrchestrator(),
        )

    def test_start_run_returns_run_id_and_pipeline_fields(self) -> None:
        result = _run(self.service.start_run("https://example.com"))

        self.assertIn("run_id", result)
        self.assertEqual(result["url"], "https://example.com")
        self.assertEqual(result["autofix_result"]["total_fixes"], 1)
        self.assertEqual(result["validation_result"]["pending_count"], 1)
        self.assertFalse(result["ready_for_simulation"])

    def test_start_run_returns_error_for_unreachable_url(self) -> None:
        service = AutoFixService(
            assessment_service=_FakeAssessmentService(unreachable=True),
            orchestrator=_FakeOrchestrator(),
        )

        result = _run(service.start_run("https://dead.example"))

        self.assertEqual(result["status"], "error")
        self.assertIn("inaccessible", result["message"])

    def test_get_run_unknown_id_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            self.service.get_run("does-not-exist")

    def test_decide_then_get_run_reflects_the_update(self) -> None:
        started = _run(self.service.start_run("https://example.com"))
        run_id = started["run_id"]

        decided = self.service.decide(
            run_id, fix_index=0, approved=True, reviewer="sam"
        )

        self.assertEqual(decided["validation_result"]["approved_count"], 1)
        self.assertTrue(decided["ready_for_simulation"])

        fetched = self.service.get_run(run_id)
        self.assertEqual(
            fetched["validation_result"]["approved_count"], 1
        )

    def test_decide_without_reviewer_raises_value_error(self) -> None:
        started = _run(self.service.start_run("https://example.com"))

        with self.assertRaises(ValueError):
            self.service.decide(
                started["run_id"], fix_index=0, approved=True, reviewer=""
            )

    def test_retry_rejected_unknown_run_id_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            self.service.retry_rejected("does-not-exist")


if __name__ == "__main__":
    unittest.main()