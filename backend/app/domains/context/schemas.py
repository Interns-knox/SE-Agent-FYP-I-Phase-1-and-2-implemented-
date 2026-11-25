import uuid
from datetime import datetime

from pydantic import BaseModel

from app.domains.features.models import FeatureStatus
from app.domains.features.schemas import FeatureResponse
from app.domains.workspace.schemas import ProjectResponse


class FeatureSummary(BaseModel):
    id: uuid.UUID
    name: str
    status: FeatureStatus
    current_version: int

    model_config = {"from_attributes": True}


class ContextResponse(BaseModel):
    project: ProjectResponse
    approved_features: list[FeatureResponse]
    all_features_summary: list[FeatureSummary]
    last_extraction_at: datetime | None
