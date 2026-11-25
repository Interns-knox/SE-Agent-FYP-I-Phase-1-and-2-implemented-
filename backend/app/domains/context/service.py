import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.context.schemas import ContextResponse, FeatureSummary
from app.domains.features.models import ChangeType, Feature, FeatureStatus, FeatureVersion
from app.domains.features.schemas import FeatureResponse
from app.domains.workspace.models import Project
from app.domains.workspace.schemas import ProjectResponse


class ContextService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_context(self, project_id: uuid.UUID) -> ContextResponse:
        """Assemble the context snapshot for a project."""
        project = self.db.query(Project).filter_by(id=project_id).first()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        features = (
            self.db.query(Feature)
            .filter(Feature.project_id == project_id)
            .order_by(Feature.created_at.asc())
            .all()
        )

        approved_features = [
            FeatureResponse.model_validate(f)
            for f in features
            if f.status == FeatureStatus.APPROVED
        ]
        all_features_summary = [FeatureSummary.model_validate(f) for f in features]

        latest_version = (
            self.db.query(FeatureVersion)
            .join(Feature, FeatureVersion.feature_id == Feature.id)
            .filter(
                Feature.project_id == project_id,
                FeatureVersion.change_type == ChangeType.CREATED,
            )
            .order_by(FeatureVersion.created_at.desc())
            .first()
        )
        last_extraction_at = latest_version.created_at if latest_version else None

        return ContextResponse(
            project=ProjectResponse.model_validate(project),
            approved_features=approved_features,
            all_features_summary=all_features_summary,
            last_extraction_at=last_extraction_at,
        )
