from pydantic import BaseModel
from typing import Dict, Any


class AssessmentResponse(BaseModel):
    success: bool
    url: str

    overall_score: float

    discoverability_score: float
    comprehension_score: float
    interaction_score: float
    security_score: float

    recommendations: Dict[str, Any]

    report: Dict[str, Any]