"""Platform persistence for engineering artifacts: artifacts, artifact_versions,
artifact_decisions and trace_links.

These tables store the platform's own records (requirements, SRS, architecture, domain model,
UML diagrams, their versions, validation results, approval decisions and traceability links).
They are NOT a schema for any generated application.

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None

TYPES = ("REQUIREMENTS", "SRS", "ARCHITECTURE", "DOMAIN_MODEL", "UML_CLASS", "UML_SEQUENCE")
STATUSES = ("PENDING_REVIEW", "APPROVED", "REJECTED", "REQUIRES_REVIEW")
CHANGES = ("GENERATED", "REGENERATED", "EDITED", "STATUS_CHANGE")


def _enum(values, name):
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for values, name in ((TYPES, "artifacttype"), (STATUSES, "artifactstatus"),
                         (CHANGES, "artifactchangetype")):
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    uuid_t = postgresql.UUID(as_uuid=True)
    ts = sa.DateTime(timezone=True)

    op.create_table(
        "artifacts",
        sa.Column("id", uuid_t, primary_key=True, nullable=False),
        sa.Column("project_id", uuid_t, sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("type", _enum(TYPES, "artifacttype"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", postgresql.JSONB, nullable=False),
        sa.Column("status", _enum(STATUSES, "artifactstatus"), nullable=False,
                  server_default="PENDING_REVIEW"),
        sa.Column("current_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("source_refs", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("validation_result", postgresql.JSONB, nullable=True),
        sa.Column("ai_critique", postgresql.JSONB, nullable=True),
        sa.Column("created_at", ts, nullable=False),
        sa.Column("updated_at", ts, nullable=False),
        sa.UniqueConstraint("project_id", "type", name="uq_artifacts_project_type"),
    )
    op.create_index("ix_artifacts_project_id", "artifacts", ["project_id"])

    op.create_table(
        "artifact_versions",
        sa.Column("id", uuid_t, primary_key=True, nullable=False),
        sa.Column("artifact_id", uuid_t, sa.ForeignKey("artifacts.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("content_snapshot", postgresql.JSONB, nullable=False),
        sa.Column("status_snapshot", _enum(STATUSES, "artifactstatus"), nullable=False),
        sa.Column("validation_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("change_type", _enum(CHANGES, "artifactchangetype"), nullable=False),
        sa.Column("change_note", sa.Text, nullable=True),
        sa.Column("created_at", ts, nullable=False),
    )
    op.create_index("ix_artifact_versions_artifact_id", "artifact_versions", ["artifact_id"])

    op.create_table(
        "artifact_decisions",
        sa.Column("id", uuid_t, primary_key=True, nullable=False),
        sa.Column("artifact_id", uuid_t, sa.ForeignKey("artifacts.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("project_id", uuid_t, sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("artifact_version", sa.Integer, nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("created_at", ts, nullable=False),
    )
    op.create_index("ix_artifact_decisions_artifact_id", "artifact_decisions", ["artifact_id"])
    op.create_index("ix_artifact_decisions_project_id", "artifact_decisions", ["project_id"])

    op.create_table(
        "trace_links",
        sa.Column("id", uuid_t, primary_key=True, nullable=False),
        sa.Column("project_id", uuid_t, sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("owner_artifact_id", uuid_t, sa.ForeignKey("artifacts.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("source_kind", sa.String(30), nullable=False),
        sa.Column("source_ref", sa.String(255), nullable=False),
        sa.Column("target_kind", sa.String(30), nullable=False),
        sa.Column("target_ref", sa.String(255), nullable=False),
        sa.Column("relation", sa.String(30), nullable=False),
        sa.Column("created_at", ts, nullable=False),
    )
    op.create_index("ix_trace_links_project_id", "trace_links", ["project_id"])
    op.create_index("ix_trace_links_owner_artifact_id", "trace_links", ["owner_artifact_id"])


def downgrade() -> None:
    op.drop_index("ix_trace_links_owner_artifact_id", table_name="trace_links")
    op.drop_index("ix_trace_links_project_id", table_name="trace_links")
    op.drop_table("trace_links")
    op.drop_index("ix_artifact_decisions_project_id", table_name="artifact_decisions")
    op.drop_index("ix_artifact_decisions_artifact_id", table_name="artifact_decisions")
    op.drop_table("artifact_decisions")
    op.drop_index("ix_artifact_versions_artifact_id", table_name="artifact_versions")
    op.drop_table("artifact_versions")
    op.drop_index("ix_artifacts_project_id", table_name="artifacts")
    op.drop_table("artifacts")
    for name in ("artifactchangetype", "artifactstatus", "artifacttype"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
