from typing import Optional

from pydantic import BaseModel, HttpUrl


class AutoFixRunRequest(BaseModel):
    """Body of POST /autofix/run.

    Mirrors `AssessmentRequest` (a URL is always required) plus the
    two optional repo hints `ModeSelectorAgent` accepts.
    """

    url: HttpUrl
    repo_path: Optional[str] = None
    repo_url: Optional[str] = None


class AutoFixDecideRequest(BaseModel):
    """Body of POST /autofix/{run_id}/decide.

    `fix_index` refers to the position in the run's
    `validation_result.validations` list, as returned by
    POST /autofix/run or GET /autofix/{run_id}.
    """

    fix_index: int
    approved: bool
    reviewer: str
    note: str = ""