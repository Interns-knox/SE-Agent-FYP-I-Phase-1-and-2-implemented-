import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.workflow.schemas import WorkflowResponse
from app.domains.workflow.service import WorkflowService

router = APIRouter(tags=["workflow"])


@router.get("/projects/{project_id}/workflow", response_model=WorkflowResponse)
def get_workflow(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """Stage-by-stage SDLC progress, approval state and prerequisite gates."""
    return WorkflowService(db).get_workflow(project_id)
