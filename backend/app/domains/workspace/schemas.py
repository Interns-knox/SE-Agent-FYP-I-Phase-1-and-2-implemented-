import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.domains.workspace.models import ProjectStage, ProjectStatus


class FeatureCountSummary(BaseModel):
    GENERATED: int = 0
    PENDING_REVIEW: int = 0
    APPROVED: int = 0
    REJECTED: int = 0


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    status: ProjectStatus
    stage: ProjectStage
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListItemResponse(ProjectResponse):
    feature_counts: FeatureCountSummary
