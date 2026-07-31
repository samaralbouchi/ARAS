from fastapi import APIRouter

from backend.app.schemas.request import AssessmentRequest
from backend.app.services.assessment_service import AssessmentService

router = APIRouter()

service = AssessmentService()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/assess")
async def assess(request: AssessmentRequest):
    result = await service.assess(str(request.url))

    return result