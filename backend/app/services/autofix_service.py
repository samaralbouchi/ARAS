"""AutoFix Service.

Bridges the HTTP layer to the AutoFix extension pipeline
(`AutoFixOrchestratorAgent`). It reuses `AssessmentService` to get the
`RecommendationResult` for a URL — the same recommendations the
`/assess` endpoint would show — then runs mode selection, AutoFix, and
human validation on top of it.

Runs are kept in an in-memory dict, keyed by a `run_id`, so `decide()`
and `retry_rejected()` can be called from later, separate HTTP
requests against a previous run. This is intentionally process-local
and non-persistent (no DB yet): restarting the backend loses
in-progress runs. That's an acceptable trade-off for now; swapping in
real persistence later only touches this class.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from agents.autofix_orchestrator_agent import AutoFixOrchestratorAgent
from backend.app.services.assessment_service import AssessmentService
from models.autofix_pipeline import AutoFixPipelineResult
from models.recommendation import RecommendationResult

_Run = tuple[RecommendationResult, AutoFixPipelineResult]


class AutoFixService:
    """Owns the AutoFix pipeline orchestrator and its in-memory run store."""

    def __init__(
        self,
        assessment_service: Optional[AssessmentService] = None,
        orchestrator: Optional[AutoFixOrchestratorAgent] = None,
    ) -> None:
        """Initialize the service, optionally overriding its collaborators.

        Args:
            assessment_service: Used to obtain the `RecommendationResult`
                for a URL. Defaults to a real `AssessmentService`.
            orchestrator: Used to run the AutoFix pipeline. Defaults to
                a real `AutoFixOrchestratorAgent`.
        """
        self._assessment_service = assessment_service or AssessmentService()
        self._orchestrator = orchestrator or AutoFixOrchestratorAgent()
        self._runs: dict[str, _Run] = {}

    async def start_run(
        self,
        url: str,
        repo_path: Optional[str] = None,
        repo_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """Compute recommendations for `url`, then run the AutoFix pipeline.

        Args:
            url: The website URL to assess and propose fixes for.
            repo_path: Local git working directory, forwarded to
                `ModeSelectorAgent`.
            repo_url: Remote git URL to clone, forwarded to
                `ModeSelectorAgent`.

        Returns:
            On success, a dict with a new `run_id` plus the
            `AutoFixPipelineResult` fields (`mode_selection`,
            `autofix_result`, `validation_result`,
            `ready_for_simulation`). On failure (unreachable URL), a
            dict with `status: "error"` and a `message`, mirroring
            `AssessmentService.assess()`'s error shape.
        """
        try:
            recommendation_result = (
                await self._assessment_service.get_recommendation_result(url)
            )
        except ValueError as exc:
            return {"status": "error", "message": str(exc), "url": url}

        pipeline_result = self._orchestrator.execute(
            recommendation_result,
            repo_path=repo_path,
            repo_url=repo_url,
        )

        run_id = str(uuid.uuid4())
        self._runs[run_id] = (recommendation_result, pipeline_result)

        return {"run_id": run_id, "url": url, **pipeline_result.to_dict()}

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Fetch the current state of a run.

        Args:
            run_id: Identifier returned by `start_run`.

        Returns:
            A dict with `run_id` plus the current
            `AutoFixPipelineResult` fields.

        Raises:
            KeyError: If `run_id` is unknown.
        """
        _, pipeline_result = self._get_run(run_id)
        return {"run_id": run_id, **pipeline_result.to_dict()}

    def decide(
        self,
        run_id: str,
        fix_index: int,
        approved: bool,
        reviewer: str,
        note: str = "",
    ) -> dict[str, Any]:
        """Record a human decision for one fix in a run.

        Args:
            run_id: Identifier returned by `start_run`.
            fix_index: Index into the run's
                `validation_result.validations`.
            approved: `True` to approve the fix, `False` to reject it.
            reviewer: Identifier of the human making the decision.
                Required and non-empty.
            note: Optional free-text reviewer comment.

        Returns:
            A dict with `run_id` plus the updated
            `AutoFixPipelineResult` fields.

        Raises:
            KeyError: If `run_id` is unknown.
            IndexError: If `fix_index` is out of range.
            ValueError: If `reviewer` is empty.
        """
        recommendation_result, pipeline_result = self._get_run(run_id)

        updated = self._orchestrator.decide(
            pipeline_result,
            fix_index=fix_index,
            approved=approved,
            reviewer=reviewer,
            note=note,
        )
        self._runs[run_id] = (recommendation_result, updated)

        return {"run_id": run_id, **updated.to_dict()}

    def retry_rejected(self, run_id: str) -> dict[str, Any]:
        """Send every REJECTED fix in a run back through the AutoFix agent.

        Args:
            run_id: Identifier returned by `start_run`.

        Returns:
            A dict with `run_id` plus the updated
            `AutoFixPipelineResult` fields. If nothing was `REJECTED`,
            the run is returned unchanged.

        Raises:
            KeyError: If `run_id` is unknown.
        """
        recommendation_result, pipeline_result = self._get_run(run_id)

        retried = self._orchestrator.retry_rejected(
            pipeline_result, recommendation_result
        )
        self._runs[run_id] = (recommendation_result, retried)

        return {"run_id": run_id, **retried.to_dict()}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_run(self, run_id: str) -> _Run:
        if run_id not in self._runs:
            raise KeyError(f"run_id '{run_id}' introuvable.")
        return self._runs[run_id]