import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.features.models import FeatureStatus
from app.domains.features.schemas import (
    FeatureListResponse,
    FeaturePatch,
    FeatureResponse,
    VersionListResponse,
)
from app.domains.features.service import FeatureService

# No prefix — routes span /projects/... and /features/...
router = APIRouter(tags=["features"])


@router.get("/projects/{project_id}/features", response_model=FeatureListResponse)
def list_features(
    project_id: uuid.UUID,
    status: FeatureStatus | None = None,
    db: Session = Depends(get_db),
) -> FeatureListResponse:
    """List features for a project, optionally filtered by status."""
    service = FeatureService(db)
    features = service.list_features(project_id, status)
    return FeatureListResponse(features=features)


@router.patch("/features/{feature_id}", response_model=FeatureResponse)
def edit_feature(
    feature_id: uuid.UUID,
    data: FeaturePatch,
    db: Session = Depends(get_db),
) -> FeatureResponse:
    """Edit a feature's description."""
    service = FeatureService(db)
    return service.edit_feature(feature_id, data)


@router.post("/features/{feature_id}/approve", response_model=FeatureResponse)
def approve_feature(
    feature_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FeatureResponse:
    """Approve a feature."""
    service = FeatureService(db)
    return service.approve_feature(feature_id)


@router.post("/features/{feature_id}/reject", response_model=FeatureResponse)
def reject_feature(
    feature_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FeatureResponse:
    """Reject a feature."""
    service = FeatureService(db)
    return service.reject_feature(feature_id)


@router.post("/features/{feature_id}/restore", response_model=FeatureResponse)
def restore_feature(
    feature_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FeatureResponse:
    """Restore a rejected feature to PENDING_REVIEW."""
    service = FeatureService(db)
    return service.restore_feature(feature_id)


@router.get("/features/{feature_id}/versions", response_model=VersionListResponse)
def get_versions(
    feature_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> VersionListResponse:
    """Get the version history of a feature."""
    service = FeatureService(db)
    versions = service.get_versions(feature_id)
    return VersionListResponse(versions=versions)
