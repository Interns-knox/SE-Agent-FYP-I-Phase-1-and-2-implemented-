import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.ai.provider import LLMProvider, get_llm_provider
from app.domains.artifacts import uml_render
from app.domains.artifacts.models import ArtifactStatus, ArtifactType
from app.domains.artifacts.schemas import (
    ArtifactDecisionListResponse,
    ArtifactDiffResponse,
    ArtifactEdit,
    ArtifactListResponse,
    ArtifactResponse,
    ArtifactVersionListResponse,
    ArtifactVersionResponse,
    ConsistencyResponse,
    DependencyResponse,
    GenerateRequest,
    RegenerateRequest,
    RejectRequest,
    RenderRequest,
    RenderResponse,
    TraceLinkResponse,
)
from app.domains.artifacts.service import ArtifactService

router = APIRouter(tags=["artifacts"])


def get_provider() -> LLMProvider:
    """Dependency so tests can substitute the provider; production uses the configured one."""
    return get_llm_provider()


@router.post("/projects/{project_id}/artifacts/generate", status_code=201,
             response_model=ArtifactResponse)
def generate_artifact(
    project_id: uuid.UUID,
    data: GenerateRequest,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_provider),
):
    return ArtifactService(db).generate(project_id, data.type, provider, data.feedback)


@router.get("/projects/{project_id}/artifacts", response_model=ArtifactListResponse)
def list_artifacts(
    project_id: uuid.UUID,
    type: ArtifactType | None = None,
    status: ArtifactStatus | None = None,
    db: Session = Depends(get_db),
):
    items = ArtifactService(db).list_artifacts(project_id, type, status)
    return ArtifactListResponse(artifacts=items)


@router.get("/projects/{project_id}/dependencies", response_model=DependencyResponse)
def get_dependencies(project_id: uuid.UUID, db: Session = Depends(get_db)):
    rows = ArtifactService(db).dependencies(project_id)
    return DependencyResponse(
        links=[
            TraceLinkResponse(
                id=lk.id,
                owner_artifact_id=lk.owner_artifact_id,
                owner_type=art.type,
                owner_status=art.status,
                source_kind=lk.source_kind,
                source_ref=lk.source_ref,
                target_kind=lk.target_kind,
                target_ref=lk.target_ref,
                relation=lk.relation,
            )
            for lk, art in rows
        ]
    )


@router.get("/projects/{project_id}/consistency", response_model=ConsistencyResponse)
def get_consistency(project_id: uuid.UUID, db: Session = Depends(get_db)):
    validation, coverage = ArtifactService(db).consistency(project_id)
    return ConsistencyResponse(validation=validation, coverage=coverage)


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
def get_artifact(artifact_id: uuid.UUID, db: Session = Depends(get_db)):
    return ArtifactService(db).get(artifact_id)


@router.put("/artifacts/{artifact_id}", response_model=ArtifactResponse)
def edit_artifact(artifact_id: uuid.UUID, data: ArtifactEdit, db: Session = Depends(get_db)):
    return ArtifactService(db).edit(artifact_id, data.content, data.title, data.change_note)


@router.post("/artifacts/{artifact_id}/regenerate", response_model=ArtifactResponse)
def regenerate_artifact(
    artifact_id: uuid.UUID,
    data: RegenerateRequest | None = None,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_provider),
):
    return ArtifactService(db).regenerate(
        artifact_id, provider, data.feedback if data else None
    )


@router.post("/artifacts/{artifact_id}/validate", response_model=ArtifactResponse)
def validate_artifact(artifact_id: uuid.UUID, db: Session = Depends(get_db)):
    return ArtifactService(db).validate(artifact_id)


@router.post("/artifacts/{artifact_id}/approve", response_model=ArtifactResponse)
def approve_artifact(artifact_id: uuid.UUID, db: Session = Depends(get_db)):
    return ArtifactService(db).approve(artifact_id)


@router.post("/artifacts/{artifact_id}/reject", response_model=ArtifactResponse)
def reject_artifact(
    artifact_id: uuid.UUID,
    data: RejectRequest | None = None,
    db: Session = Depends(get_db),
):
    return ArtifactService(db).reject(artifact_id, data.reason if data else None)


@router.post("/artifacts/{artifact_id}/critique", response_model=ArtifactResponse)
def critique_artifact(
    artifact_id: uuid.UUID,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_provider),
):
    return ArtifactService(db).critique(artifact_id, provider)


@router.get("/artifacts/{artifact_id}/versions", response_model=ArtifactVersionListResponse)
def list_versions(artifact_id: uuid.UUID, db: Session = Depends(get_db)):
    return ArtifactVersionListResponse(versions=ArtifactService(db).versions(artifact_id))


@router.get("/artifacts/{artifact_id}/versions/{version_number}",
            response_model=ArtifactVersionResponse)
def get_version(artifact_id: uuid.UUID, version_number: int, db: Session = Depends(get_db)):
    return ArtifactService(db).get_version(artifact_id, version_number)


@router.get("/artifacts/{artifact_id}/decisions", response_model=ArtifactDecisionListResponse)
def list_decisions(artifact_id: uuid.UUID, db: Session = Depends(get_db)):
    return ArtifactDecisionListResponse(decisions=ArtifactService(db).decisions(artifact_id))


@router.get("/artifacts/{artifact_id}/diff", response_model=ArtifactDiffResponse)
def diff_versions(artifact_id: uuid.UUID, from_version: int | None = Query(None, ge=1),
                  to_version: int | None = Query(None, ge=1), db: Session = Depends(get_db)):
    """Unified diff between two stored versions of an artifact (default: previous -> current)."""
    return ArtifactDiffResponse(**ArtifactService(db).diff(artifact_id, from_version, to_version))


@router.post("/projects/{project_id}/artifacts/requirements/normalize-ids")
def normalize_requirement_ids(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """Migrate legacy requirement ids (e.g. REQ-001) to FR-/NFR- ids, keeping history."""
    return ArtifactService(db).normalize_requirement_ids(project_id)


@router.get("/uml/renderer")
def renderer_status():
    """Whether the local PlantUML renderer is installed."""
    return uml_render.renderer_status()


@router.post("/uml/render", response_model=RenderResponse)
def render_plantuml(data: RenderRequest):
    """Validate and render PlantUML source to SVG locally. Failures return ok=false with the
    error and line; the caller keeps the source."""
    return uml_render.render_svg(data.source)
