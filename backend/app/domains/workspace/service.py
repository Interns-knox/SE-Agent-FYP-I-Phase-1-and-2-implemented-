import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.features.models import Feature, FeatureStatus
from app.domains.workspace.models import Project, ProjectStage, ProjectStatus
from app.domains.workspace.schemas import (
    FeatureCountSummary,
    ProjectCreate,
    ProjectListItemResponse,
)


class ProjectService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_project(self, data: ProjectCreate) -> Project:
        """Create a new Project record and persist it to the database."""
        now = datetime.now(timezone.utc)
        project = Project(
            id=uuid.uuid4(),
            name=data.name,
            description=data.description,
            status=ProjectStatus.ACTIVE,
            stage=ProjectStage.CREATED,
            created_at=now,
            updated_at=now,
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def list_projects(self) -> list[ProjectListItemResponse]:
        """Return all projects with a feature count summary per FeatureStatus."""
        projects = self.db.query(Project).all()

        # Aggregate feature counts grouped by (project_id, status) in one query.
        counts = (
            self.db.query(
                Feature.project_id,
                Feature.status,
                func.count(Feature.id).label("cnt"),
            )
            .group_by(Feature.project_id, Feature.status)
            .all()
        )

        # Build a lookup: project_id -> {status -> count}
        counts_by_project: dict[uuid.UUID, dict[str, int]] = {}
        for row in counts:
            bucket = counts_by_project.setdefault(row.project_id, {})
            bucket[row.status.value] = row.cnt

        result: list[ProjectListItemResponse] = []
        for project in projects:
            status_counts = counts_by_project.get(project.id, {})
            feature_counts = FeatureCountSummary(
                GENERATED=status_counts.get(FeatureStatus.GENERATED.value, 0),
                PENDING_REVIEW=status_counts.get(FeatureStatus.PENDING_REVIEW.value, 0),
                APPROVED=status_counts.get(FeatureStatus.APPROVED.value, 0),
                REJECTED=status_counts.get(FeatureStatus.REJECTED.value, 0),
            )
            result.append(
                ProjectListItemResponse(
                    id=project.id,
                    name=project.name,
                    description=project.description,
                    status=project.status,
                    stage=project.stage,
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                    feature_counts=feature_counts,
                )
            )

        return result

    def get_project(self, project_id: uuid.UUID) -> Project:
        """Fetch a project by ID, raising HTTP 404 if not found."""
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if project is None:
            raise HTTPException(
                status_code=404,
                detail=f"Project {project_id} not found",
            )
        return project

    def update_stage(self, project_id: uuid.UUID, stage: ProjectStage) -> Project:
        """Update the stage of an existing project."""
        project = self.get_project(project_id)
        project.stage = stage
        project.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(project)
        return project
