"""Persistence models for Phase 2 engineering artifacts.

One generic ``artifacts`` table holds every artifact type (requirements, SRS,
architecture, domain model, UML diagrams). The type-specific payload lives in the
``content`` JSON column. Every content change creates an ``artifact_versions``
row, every human decision creates an ``artifact_decisions`` row, and the
dependency model is stored in ``trace_links``.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# JSONB on PostgreSQL, generic JSON elsewhere (unit tests run on SQLite).
JSONType = JSON().with_variant(JSONB(), "postgresql")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ArtifactType(str, Enum):
    REQUIREMENTS = "REQUIREMENTS"
    SRS = "SRS"
    ARCHITECTURE = "ARCHITECTURE"
    UML_CLASS = "UML_CLASS"
    UML_SEQUENCE = "UML_SEQUENCE"
    DOMAIN_MODEL = "DOMAIN_MODEL"


class ArtifactStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    # An upstream artifact changed after this one was approved. Not usable as an input
    # until a human re-validates and re-approves it.
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class ArtifactChangeType(str, Enum):
    GENERATED = "GENERATED"
    REGENERATED = "REGENERATED"
    EDITED = "EDITED"
    STATUS_CHANGE = "STATUS_CHANGE"


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("project_id", "type", name="uq_artifacts_project_type"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[ArtifactType] = mapped_column(
        SAEnum(ArtifactType, name="artifacttype"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[dict] = mapped_column(JSONType, nullable=False)
    status: Mapped[ArtifactStatus] = mapped_column(
        SAEnum(ArtifactStatus, name="artifactstatus"),
        default=ArtifactStatus.PENDING_REVIEW,
        nullable=False,
    )
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # {"feature_ids": [...], "artifacts": [{"artifact_id", "type", "version"}]}
    source_refs: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    # Deterministic validator output (see validation/result.py).
    validation_result: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    # Optional AI-generated critique. Advisory only, never used for approval.
    ai_critique: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_snapshot: Mapped[dict] = mapped_column(JSONType, nullable=False)
    status_snapshot: Mapped[ArtifactStatus] = mapped_column(
        SAEnum(ArtifactStatus, name="artifactstatus"), nullable=False
    )
    validation_snapshot: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    change_type: Mapped[ArtifactChangeType] = mapped_column(
        SAEnum(ArtifactChangeType, name="artifactchangetype"), nullable=False
    )
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class ArtifactDecision(Base):
    __tablename__ = "artifact_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    artifact_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class TraceLink(Base):
    """Directed dependency edge: ``source`` depends on / derives from ``target``.

    Each link is owned by the artifact whose content declares it, and is rebuilt
    whenever that artifact's content changes.
    """

    __tablename__ = "trace_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # kinds: FEATURE, REQUIREMENT, COMPONENT, DOMAIN_ENTITY, UML_DIAGRAM
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    relation: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
