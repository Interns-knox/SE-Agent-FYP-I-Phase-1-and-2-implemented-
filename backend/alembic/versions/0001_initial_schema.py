"""Initial schema: projects, features, feature_versions, user_decisions

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Create enum types before the tables that reference them
    # ------------------------------------------------------------------
    projectstatus = sa.Enum(
        "ACTIVE",
        "ARCHIVED",
        name="projectstatus",
    )
    projectstage = sa.Enum(
        "CREATED",
        "EXTRACTION_DONE",
        name="projectstage",
    )
    featurestatus = sa.Enum(
        "GENERATED",
        "PENDING_REVIEW",
        "APPROVED",
        "REJECTED",
        name="featurestatus",
    )
    changetype = sa.Enum(
        "CREATED",
        "EDITED",
        "STATUS_CHANGE",
        name="changetype",
    )

    projectstatus.create(op.get_bind(), checkfirst=True)
    projectstage.create(op.get_bind(), checkfirst=True)
    featurestatus.create(op.get_bind(), checkfirst=True)
    changetype.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # 1. projects
    # ------------------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "ARCHIVED", name="projectstatus", create_type=False),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "stage",
            sa.Enum("CREATED", "EXTRACTION_DONE", name="projectstage", create_type=False),
            nullable=False,
            server_default="CREATED",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # 2. features
    # ------------------------------------------------------------------
    op.create_table(
        "features",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "GENERATED",
                "PENDING_REVIEW",
                "APPROVED",
                "REJECTED",
                name="featurestatus",
                create_type=False,
            ),
            nullable=False,
            server_default="PENDING_REVIEW",
        ),
        sa.Column(
            "current_version",
            sa.Integer,
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_features_project_id",
        "features",
        ["project_id"],
    )

    # ------------------------------------------------------------------
    # 3. feature_versions
    # ------------------------------------------------------------------
    op.create_table(
        "feature_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "feature_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("features.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("name_snapshot", sa.Text, nullable=False),
        sa.Column("description_snapshot", sa.Text, nullable=False),
        sa.Column(
            "change_type",
            sa.Enum(
                "CREATED",
                "EDITED",
                "STATUS_CHANGE",
                name="changetype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_feature_versions_feature_id",
        "feature_versions",
        ["feature_id"],
    )

    # ------------------------------------------------------------------
    # 4. user_decisions
    # ------------------------------------------------------------------
    op.create_table(
        "user_decisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "feature_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("features.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_user_decisions_feature_id",
        "user_decisions",
        ["feature_id"],
    )
    op.create_index(
        "ix_user_decisions_project_id",
        "user_decisions",
        ["project_id"],
    )


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_index("ix_user_decisions_project_id", table_name="user_decisions")
    op.drop_index("ix_user_decisions_feature_id", table_name="user_decisions")
    op.drop_table("user_decisions")

    op.drop_index("ix_feature_versions_feature_id", table_name="feature_versions")
    op.drop_table("feature_versions")

    op.drop_index("ix_features_project_id", table_name="features")
    op.drop_table("features")

    op.drop_table("projects")

    # Drop enum types after all tables are gone
    sa.Enum(name="changetype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="featurestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="projectstage").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="projectstatus").drop(op.get_bind(), checkfirst=True)
