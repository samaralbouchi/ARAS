from pydantic import BaseModel, HttpUrl


class AssessmentRequest(BaseModel):
    url: HttpUrl