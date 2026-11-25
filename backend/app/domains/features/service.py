import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.ai.schemas import ExtractedFeature
from app.domains.features.models import (
    ChangeType,
    Feature,
    FeatureStatus,
    FeatureVersion,
    UserDecision,
)
from app.domains.features.schemas import FeaturePatch
from app.domains.workflow.service import WorkflowService
from app.domains.workspace.models import Project


class FeatureService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Creation (called from extraction flow)
    # ------------------------------------------------------------------

    def create_features_from_extraction(
        self,
        project_id: uuid.UUID,
        extracted: list[ExtractedFeature],
    ) -> list[Feature]:
        """Persist features + initial version records in a single transaction."""
        now = datetime.now(timezone.utc)
        features: list[Feature] = []

        for item in extracted:
            feature = Feature(
                id=uuid.uuid4(),
                project_id=project_id,
                name=item.name,
                description=item.description,
                status=FeatureStatus.PENDING_REVIEW,
                current_version=1,
                created_at=now,
                updated_at=now,
            )
            self.db.add(feature)
            self.db.flush()  # populate feature.id before creating version

            version = FeatureVersion(
                id=uuid.uuid4(),
                feature_id=feature.id,
                version_number=1,
                name_snapshot=feature.name,
                description_snapshot=feature.description,
                change_type=ChangeType.CREATED,
                created_at=now,
            )
            self.db.add(version)
            features.append(feature)

        self.db.commit()
        for feature in features:
            self.db.refresh(feature)

        return features

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_features(
        self,
        project_id: uuid.UUID,
        status: FeatureStatus | None = None,
    ) -> list[Feature]:
        """Return features for a project, verifying the project exists."""
        project = self.db.query(Project).filter_by(id=project_id).first()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        query = self.db.query(Feature).filter(Feature.project_id == project_id)
        if status is not None:
            query = query.filter(Feature.status == status)

        return query.all()

    def get_feature(self, feature_id: uuid.UUID) -> Feature:
        """Return a single feature by id, raising 404 if not found."""
        feature = self.db.query(Feature).filter_by(id=feature_id).first()
        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")
        return feature

    # ------------------------------------------------------------------
    # Mutation — edit
    # ------------------------------------------------------------------

    def edit_feature(self, feature_id: uuid.UUID, data: FeaturePatch) -> Feature:
        """Update description, bump version, create EDITED version record."""
        feature = self.get_feature(feature_id)
        now = datetime.now(timezone.utc)

        feature.description = data.description
        feature.current_version += 1
        feature.updated_at = now

        version = self._create_version_record(feature, ChangeType.EDITED)
        version.description_snapshot = data.description  # snapshot the new description

        self.db.commit()
        self.db.refresh(feature)
        WorkflowService(self.db).on_features_changed(feature.project_id)
        return feature

    # ------------------------------------------------------------------
    # Mutation — status transitions
    # ------------------------------------------------------------------

    def approve_feature(self, feature_id: uuid.UUID) -> Feature:
        """Transition feature to APPROVED. Guard: must be PENDING_REVIEW or GENERATED."""
        feature = self.get_feature(feature_id)

        if feature.status not in (FeatureStatus.PENDING_REVIEW, FeatureStatus.GENERATED):
            raise HTTPException(
                status_code=422,
                detail="Feature cannot be approved from its current status",
            )

        now = datetime.now(timezone.utc)
        feature.status = FeatureStatus.APPROVED
        feature.current_version += 1
        feature.updated_at = now

        self._create_version_record(feature, ChangeType.STATUS_CHANGE)
        self._create_user_decision(feature, "APPROVED")

        self.db.commit()
        self.db.refresh(feature)
        WorkflowService(self.db).on_features_changed(feature.project_id)
        return feature

    def reject_feature(self, feature_id: uuid.UUID) -> Feature:
        """Transition feature to REJECTED. Guard: must be PENDING_REVIEW or GENERATED."""
        feature = self.get_feature(feature_id)

        if feature.status not in (FeatureStatus.PENDING_REVIEW, FeatureStatus.GENERATED):
            raise HTTPException(
                status_code=422,
                detail="Feature cannot be rejected from its current status",
            )

        now = datetime.now(timezone.utc)
        feature.status = FeatureStatus.REJECTED
        feature.current_version += 1
        feature.updated_at = now

        self._create_version_record(feature, ChangeType.STATUS_CHANGE)
        self._create_user_decision(feature, "REJECTED")

        self.db.commit()
        self.db.refresh(feature)
        WorkflowService(self.db).on_features_changed(feature.project_id)
        return feature

    def restore_feature(self, feature_id: uuid.UUID) -> Feature:
        """Restore a REJECTED feature back to PENDING_REVIEW."""
        feature = self.get_feature(feature_id)

        if feature.status != FeatureStatus.REJECTED:
            raise HTTPException(
                status_code=422,
                detail="Feature is not in a restorable state",
            )

        now = datetime.now(timezone.utc)
        feature.status = FeatureStatus.PENDING_REVIEW
        feature.current_version += 1
        feature.updated_at = now

        self._create_version_record(feature, ChangeType.STATUS_CHANGE)

        self.db.commit()
        self.db.refresh(feature)
        WorkflowService(self.db).on_features_changed(feature.project_id)
        return feature

    # ------------------------------------------------------------------
    # Versioning
    # ------------------------------------------------------------------

    def get_versions(self, feature_id: uuid.UUID) -> list[FeatureVersion]:
        """Return all version records for a feature, ordered ascending."""
        self.get_feature(feature_id)  # raises 404 if feature doesn't exist
        return (
            self.db.query(FeatureVersion)
            .filter(FeatureVersion.feature_id == feature_id)
            .order_by(FeatureVersion.version_number.asc())
            .all()
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_version_record(
        self, feature: Feature, change_type: ChangeType
    ) -> FeatureVersion:
        """Create and add a FeatureVersion to the session (caller commits)."""
        version = FeatureVersion(
            id=uuid.uuid4(),
            feature_id=feature.id,
            version_number=feature.current_version,
            name_snapshot=feature.name,
            description_snapshot=feature.description,
            change_type=change_type,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(version)
        return version

    def _create_user_decision(
        self, feature: Feature, decision: str
    ) -> UserDecision:
        """Create and add a UserDecision to the session (caller commits)."""
        user_decision = UserDecision(
            id=uuid.uuid4(),
            feature_id=feature.id,
            project_id=feature.project_id,
            decision=decision,
            reason=None,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(user_decision)
        return user_decision
