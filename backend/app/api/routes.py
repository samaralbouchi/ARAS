from fastapi import APIRouter, HTTPException

from backend.app.schemas.autofix import AutoFixDecideRequest, AutoFixRunRequest
from backend.app.schemas.request import AssessmentRequest
from backend.app.services.assessment_service import AssessmentService
from backend.app.services.autofix_service import AutoFixService

router = APIRouter()

service = AssessmentService()
# Reuses `service` so recommendations come from the same
# AssessmentService instance (and its cached collaborators) as /assess.
autofix_service = AutoFixService(assessment_service=service)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/assess")
async def assess(request: AssessmentRequest):
    result = await service.assess(str(request.url))


    return result


@router.post("/autofix/run")
async def autofix_run(request: AutoFixRunRequest):
    """Start an AutoFix pipeline run: mode selection -> AutoFix -> human validation."""
    result = await autofix_service.start_run(
        str(request.url),
        repo_path=request.repo_path,
        repo_url=request.repo_url,
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=422, detail=result["message"])

    return result


@router.get("/autofix/{run_id}")
async def autofix_get(run_id: str):
    """Fetch the current state (fixes + validation queue) of a run."""
    try:
        return autofix_service.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/autofix/{run_id}/decide")
async def autofix_decide(run_id: str, request: AutoFixDecideRequest):
    """Record a human decision (approve/reject) for one fix in a run."""
    try:
        return autofix_service.decide(
            run_id,
            fix_index=request.fix_index,
            approved=request.approved,
            reviewer=request.reviewer,
            note=request.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (IndexError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/autofix/{run_id}/retry-rejected")
async def autofix_retry_rejected(run_id: str):
    """Send every REJECTED fix in a run back through the AutoFix agent."""
    try:
        return autofix_service.retry_rejected(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))