import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.ai.extraction import FeatureExtractionService
from app.domains.ai.provider import get_llm_provider
from app.domains.features.schemas import FeatureListResponse
from app.domains.features.service import FeatureService
from app.domains.workspace.models import ProjectStage
from app.domains.workspace.schemas import (
    ProjectCreate,
    ProjectListItemResponse,
    ProjectResponse,
)
from app.domains.workspace.service import ProjectService

router = APIRouter(prefix="/projects", tags=["workspace"])

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
def health_check() -> dict[str, str]:
    """Return service health status."""
    return {"status": "ok"}


@router.post("", status_code=201, response_model=ProjectResponse)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Create a new project."""
    service = ProjectService(db)
    return service.create_project(data)


@router.get("", response_model=list[ProjectListItemResponse])
def list_projects(
    db: Session = Depends(get_db),
) -> list[ProjectListItemResponse]:
    """List all projects with feature count summaries."""
    service = ProjectService(db)
    return service.list_projects()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Get a single project by ID."""
    service = ProjectService(db)
    return service.get_project(project_id)


@router.post("/{project_id}/extract", response_model=FeatureListResponse)
def extract_features(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FeatureListResponse:
    """Extract features from the project description using the configured LLM provider."""
    # 1. Verify project exists (auto-raises 404 if missing)
    project_service = ProjectService(db)
    project = project_service.get_project(project_id)

    # 2. Get the LLM provider
    provider = get_llm_provider()

    # 3. Run AI extraction (may raise 422/503/504)
    extraction_service = FeatureExtractionService(provider)
    result = extraction_service.extract(project.description)

    # 4. Persist extracted features
    feature_service = FeatureService(db)
    features = feature_service.create_features_from_extraction(project_id, result.features)

    # 5. Advance project stage
    project_service.update_stage(project_id, ProjectStage.EXTRACTION_DONE)

    # 6. Return feature list
    return FeatureListResponse(features=features)
