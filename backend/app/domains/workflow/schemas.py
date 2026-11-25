from typing import Any

from pydantic import BaseModel


class StageResponse(BaseModel):
    key: str
    number: int
    name: str
    path: str
    status: str
    approval_status: str
    completed: bool
    accessible: bool
    blocked: bool
    required_stage: str | None
    required_stage_name: str | None
    blocked_reason: str | None
    suggested_action: str | None
    artifacts: list[dict[str, Any]]
    missing_artifact_types: list[str]
    can_proceed: bool
    proceed_blocked_reason: str | None
    counts: dict[str, int] | None = None
    gate_reason: str | None = None


class WorkflowResponse(BaseModel):
    project_id: str
    current_stage: str
    complete: bool
    stages: list[StageResponse]
