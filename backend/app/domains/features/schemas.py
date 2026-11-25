import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.domains.features.models import ChangeType, FeatureStatus


class FeatureResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str
    status: FeatureStatus
    current_version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FeatureListResponse(BaseModel):
    features: list[FeatureResponse]


class FeaturePatch(BaseModel):
    description: str = Field(..., min_length=1)


class FeatureVersionResponse(BaseModel):
    id: uuid.UUID
    feature_id: uuid.UUID
    version_number: int
    name_snapshot: str
    description_snapshot: str
    change_type: ChangeType
    created_at: datetime

    model_config = {"from_attributes": True}


class VersionListResponse(BaseModel):
    versions: list[FeatureVersionResponse]
