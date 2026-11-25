import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.context.schemas import ContextResponse
from app.domains.context.service import ContextService

router = APIRouter(tags=["context"])


@router.get("/projects/{project_id}/context", response_model=ContextResponse)
def get_context(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ContextResponse:
    """Return the assembled context snapshot for a project."""
    service = ContextService(db)
    return service.get_context(project_id)
