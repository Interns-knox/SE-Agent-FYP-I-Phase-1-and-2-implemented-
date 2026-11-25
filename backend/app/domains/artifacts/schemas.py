import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domains.artifacts.models import ArtifactChangeType, ArtifactStatus, ArtifactType


class ArtifactResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    type: ArtifactType
    title: str
    content: dict[str, Any]
    status: ArtifactStatus
    current_version: int
    source_refs: dict[str, Any]
    validation_result: dict[str, Any] | None
    ai_critique: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ArtifactListResponse(BaseModel):
    artifacts: list[ArtifactResponse]


class GenerateRequest(BaseModel):
    type: ArtifactType
    feedback: str | None = Field(default=None, max_length=4000)


class RegenerateRequest(BaseModel):
    feedback: str | None = Field(default=None, max_length=4000)


class ArtifactEdit(BaseModel):
    # Content shape is deliberately not enforced here: the deterministic
    # validator reports structural problems so users can see and fix them.
    content: dict[str, Any]
    title: str | None = Field(default=None, min_length=1, max_length=255)
    change_note: str | None = Field(default=None, max_length=2000)


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class ArtifactVersionResponse(BaseModel):
    id: uuid.UUID
    artifact_id: uuid.UUID
    version_number: int
    content_snapshot: dict[str, Any]
    status_snapshot: ArtifactStatus
    validation_snapshot: dict[str, Any] | None
    change_type: ArtifactChangeType
    change_note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactVersionListResponse(BaseModel):
    versions: list[ArtifactVersionResponse]


class ArtifactDecisionResponse(BaseModel):
    id: uuid.UUID
    artifact_id: uuid.UUID
    artifact_version: int
    decision: str
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactDecisionListResponse(BaseModel):
    decisions: list[ArtifactDecisionResponse]


class TraceLinkResponse(BaseModel):
    id: uuid.UUID
    owner_artifact_id: uuid.UUID
    owner_type: ArtifactType
    owner_status: ArtifactStatus
    source_kind: str
    source_ref: str
    target_kind: str
    target_ref: str
    relation: str


class DependencyResponse(BaseModel):
    links: list[TraceLinkResponse]


class ConsistencyResponse(BaseModel):
    validation: dict[str, Any]
    coverage: dict[str, list[str]]


class ArtifactDiffResponse(BaseModel):
    artifact_id: uuid.UUID
    from_version: int
    to_version: int
    identical: bool
    additions: int
    deletions: int
    diff: str


class RenderRequest(BaseModel):
    source: str = Field(..., max_length=200_000)


class RenderResponse(BaseModel):
    ok: bool
    svg: str | None = None
    error: str | None = None
    line: int | None = None
    renderer_available: bool
    cached: bool = False
