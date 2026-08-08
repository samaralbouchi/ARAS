"""AutoFix Service.

Bridges the HTTP layer to the AutoFix extension pipeline
(`AutoFixOrchestratorAgent`) and, once a run is fully reviewed, to the
`SimulationAgent`. It reuses `AssessmentService` to get the
`AssessmentResult` + `RecommendationResult` for a URL — the same
assessment the `/assess` endpoint would show — then runs mode
selection, AutoFix, and human validation on top of it.

Runs are kept in an in-memory dict, keyed by a `run_id`, so `decide()`,
`retry_rejected()`, and `simulate()` can be called from later, separate
HTTP requests against a previous run. This is intentionally
process-local and non-persistent (no DB yet): restarting the backend
loses in-progress runs. That's an acceptable trade-off for now;
swapping in real persistence later only touches this class.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from agents.autofix_orchestrator_agent import AutoFixOrchestratorAgent
from agents.simulation_agent import SimulationAgent
from backend.app.services.assessment_service import AssessmentService
from models.assessment import AssessmentResult
from models.autofix_pipeline import AutoFixPipelineResult
from models.evidence import WebsiteEvidence
from models.recommendation import RecommendationResult
from models.simulation import SimulationResult

_NOT_READY_FOR_SIMULATION_MESSAGE = (
    "Le run n'est pas prêt pour la simulation : il reste des fixes en "
    "attente de revue, ou aucun fix n'a encore été approuvé."
)


@dataclass
class _Run:
    """Everything the service needs to remember about one run.

    `simulation_result` starts at `None` and is filled in by
    `simulate()`. It is deliberately reset to `None` by `decide()` and
    `retry_rejected()`: either call can change which fixes are
    `APPROVED`, which makes any previous simulation stale.
    """

    recommendation_result: RecommendationResult
    assessment_result: AssessmentResult
    pipeline_result: AutoFixPipelineResult
    simulation_result: Optional[SimulationResult] = None


class AutoFixService:
    """Owns the AutoFix pipeline orchestrator, the Simulation agent, and the in-memory run store."""

    def __init__(
        self,
        assessment_service: Optional[AssessmentService] = None,
        orchestrator: Optional[AutoFixOrchestratorAgent] = None,
        simulation_agent: Optional[SimulationAgent] = None,
    ) -> None:
        """Initialize the service, optionally overriding its collaborators.

        Args:
            assessment_service: Used to obtain the `AssessmentResult`
                and `RecommendationResult` for a URL. Defaults to a
                real `AssessmentService`.
            orchestrator: Used to run the AutoFix pipeline. Defaults to
                a real `AutoFixOrchestratorAgent`.
            simulation_agent: Used to compute before/after scores for
                approved fixes. Defaults to a real `SimulationAgent`.
        """
        self._assessment_service = assessment_service or AssessmentService()
        self._orchestrator = orchestrator or AutoFixOrchestratorAgent()
        self._simulation_agent = simulation_agent or SimulationAgent()
        self._runs: dict[str, _Run] = {}

    async def start_run(
        self,
        url: str,
        repo_path: Optional[str] = None,
        repo_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """Compute an assessment for `url`, then run the AutoFix pipeline.

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
            assessment_result, recommendation_result = (
                await self._assessment_service.get_assessment_and_recommendations(url)
            )
        except ValueError as exc:
            return {"status": "error", "message": str(exc), "url": url}

        pipeline_result = self._orchestrator.execute(
            recommendation_result,
            repo_path=repo_path,
            repo_url=repo_url,
        )

        run_id = str(uuid.uuid4())
        self._runs[run_id] = _Run(
            recommendation_result=recommendation_result,
            assessment_result=assessment_result,
            pipeline_result=pipeline_result,
        )

        return {"run_id": run_id, "url": url, **pipeline_result.to_dict()}

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Fetch the current state of a run.

        Args:
            run_id: Identifier returned by `start_run`.

        Returns:
            A dict with `run_id` plus the current
            `AutoFixPipelineResult` fields, and `simulation_result`
            too if `simulate()` has already been called for this run.

        Raises:
            KeyError: If `run_id` is unknown.
        """
        run = self._get_run(run_id)
        result = {"run_id": run_id, **run.pipeline_result.to_dict()}
        if run.simulation_result is not None:
            result["simulation_result"] = run.simulation_result.to_dict()
        return result

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
        run = self._get_run(run_id)

        updated = self._orchestrator.decide(
            run.pipeline_result,
            fix_index=fix_index,
            approved=approved,
            reviewer=reviewer,
            note=note,
        )
        run.pipeline_result = updated
        run.simulation_result = None  # stale: approval set just changed

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
        run = self._get_run(run_id)

        retried = self._orchestrator.retry_rejected(
            run.pipeline_result, run.recommendation_result
        )
        run.pipeline_result = retried
        run.simulation_result = None  # stale: fixes/approval set just changed

        return {"run_id": run_id, **retried.to_dict()}

    def simulate(self, run_id: str) -> dict[str, Any]:
        """Compute real before/after scores for a run's approved fixes.

        This is the "Human validation agent -> Simulation agent" step
        from the architecture diagram. It requires every fix to have
        been reviewed already (no `PENDING` entries) and at least one
        `APPROVED` fix — the same condition
        `AutoFixPipelineResult.ready_for_simulation` checks.

        Args:
            run_id: Identifier returned by `start_run`.

        Returns:
            A dict with `run_id`, the `AutoFixPipelineResult` fields,
            and a `simulation_result` field (the `SimulationResult`,
            as a dict).

        Raises:
            KeyError: If `run_id` is unknown.
            ValueError: If the run is not yet `ready_for_simulation`.
        """
        run = self._get_run(run_id)

        if not run.pipeline_result.ready_for_simulation:
            raise ValueError(_NOT_READY_FOR_SIMULATION_MESSAGE)

        evidence = self._evidence_from_assessment(run.assessment_result)
        simulation_result = self._simulation_agent.simulate(
            evidence=evidence,
            assessment_result=run.assessment_result,
            pipeline_result=run.pipeline_result,
        )
        run.simulation_result = simulation_result

        return {
            "run_id": run_id,
            **run.pipeline_result.to_dict(),
            "simulation_result": simulation_result.to_dict(),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_run(self, run_id: str) -> _Run:
        if run_id not in self._runs:
            raise KeyError(f"run_id '{run_id}' introuvable.")
        return self._runs[run_id]

    @staticmethod
    def _evidence_from_assessment(assessment_result: AssessmentResult) -> WebsiteEvidence:
        """Rebuild a `WebsiteEvidence` from `AssessmentResult.evidence`.

        `AssessmentResult.evidence` is the flat dict produced by
        `WebsiteEvidence.to_dict()` when the original assessment ran.
        Rebuilding a `WebsiteEvidence` from it lets `SimulationAgent`
        patch and re-score without a second HTTP fetch of `url`.

        Caveat: `errors` comes back as a list of plain dicts rather
        than `CollectionError` instances (`asdict` flattens nested
        dataclasses). This is harmless today since no analysis agent
        reads `WebsiteEvidence.errors` for scoring.

        Args:
            assessment_result: The original assessment.

        Returns:
            A `WebsiteEvidence` equivalent to the one the assessment
            was computed from.
        """
        return WebsiteEvidence(**assessment_result.evidence)