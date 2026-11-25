"""Guided SDLC workflow: stage status, prerequisite gates and downstream invalidation.

Stage order (each stage needs the previous one APPROVED):

    1 Project Features -> 2 Requirements -> 3 SRS -> 4 Architecture -> 5 UML Diagrams

UML Diagrams are the domain model, the class diagram and the sequence diagrams. Approval is
"effective" only when the stored artifact status is APPROVED *and* its prerequisite stage is
effectively approved, so approvals that predate these gates (or whose upstream stage was later
reopened) are never silently treated as valid.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.artifacts.models import (
    Artifact,
    ArtifactChangeType,
    ArtifactStatus,
    ArtifactType,
    ArtifactVersion,
)
from app.domains.features.models import Feature, FeatureStatus
from app.domains.workspace.models import Project

T = ArtifactType


@dataclass(frozen=True)
class StageDef:
    key: str
    number: int
    name: str
    path: str  # frontend route segment
    types: tuple[ArtifactType, ...]
    prereq: str | None


STAGES: list[StageDef] = [
    StageDef("FEATURES", 1, "Project Features", "features", (), None),
    StageDef("REQUIREMENTS", 2, "Requirements", "requirements", (T.REQUIREMENTS,), "FEATURES"),
    StageDef("SRS", 3, "SRS", "srs", (T.SRS,), "REQUIREMENTS"),
    StageDef("ARCHITECTURE", 4, "Architecture", "architecture", (T.ARCHITECTURE,), "SRS"),
    StageDef("UML", 5, "UML Diagrams", "uml",
             (T.DOMAIN_MODEL, T.UML_CLASS, T.UML_SEQUENCE), "ARCHITECTURE"),
]
BY_KEY = {s.key: s for s in STAGES}
STAGE_OF_TYPE = {t: s.key for s in STAGES for t in s.types}

# Artifacts that become stale when the key artifact changes (transitive).
DOWNSTREAM: dict[ArtifactType, list[ArtifactType]] = {
    T.REQUIREMENTS: [T.SRS, T.ARCHITECTURE, T.DOMAIN_MODEL, T.UML_CLASS, T.UML_SEQUENCE],
    T.SRS: [T.ARCHITECTURE, T.DOMAIN_MODEL, T.UML_CLASS, T.UML_SEQUENCE],
    T.ARCHITECTURE: [T.DOMAIN_MODEL, T.UML_CLASS, T.UML_SEQUENCE],
    T.DOMAIN_MODEL: [T.UML_CLASS, T.UML_SEQUENCE],
}

REQUIRED_STAGE_MESSAGES = {
    "FEATURES": "Feature approval required",
    "REQUIREMENTS": "Requirements approval required",
    "SRS": "SRS approval required",
    "ARCHITECTURE": "Architecture approval required",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Facts
    # ------------------------------------------------------------------
    def _project(self, project_id: uuid.UUID) -> Project:
        p = self.db.query(Project).filter_by(id=project_id).first()
        if p is None:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return p

    def feature_counts(self, project_id: uuid.UUID) -> dict[str, int]:
        counts = {"total": 0, "approved": 0, "pending": 0, "rejected": 0}
        for (status,) in self.db.query(Feature.status).filter(Feature.project_id == project_id):
            counts["total"] += 1
            if status == FeatureStatus.APPROVED:
                counts["approved"] += 1
            elif status == FeatureStatus.REJECTED:
                counts["rejected"] += 1
            else:  # GENERATED or PENDING_REVIEW
                counts["pending"] += 1
        return counts

    def _artifacts(self, project_id: uuid.UUID) -> dict[ArtifactType, Artifact]:
        rows = self.db.query(Artifact).filter(Artifact.project_id == project_id).all()
        return {a.type: a for a in rows}

    @staticmethod
    def features_gate(counts: dict[str, int]) -> tuple[bool, str | None]:
        if counts["total"] == 0:
            return False, ("No features have been extracted yet. Extract features and review "
                           "them first.")
        if counts["pending"] > 0:
            n = counts["pending"]
            return False, (f"{n} feature{'s are' if n != 1 else ' is'} still pending review. "
                           "Approve or reject every extracted feature first.")
        if counts["approved"] == 0:
            return False, ("No feature is approved. At least one feature must be approved "
                           "before requirements can be generated.")
        return True, None

    # ------------------------------------------------------------------
    # Status computation
    # ------------------------------------------------------------------
    def _compute(self, project_id: uuid.UUID) -> tuple[dict[str, dict[str, Any]], dict]:
        counts = self.feature_counts(project_id)
        arts = self._artifacts(project_id)
        gate_ok, gate_reason = self.features_gate(counts)
        info: dict[str, dict[str, Any]] = {}

        for stage in STAGES:
            prereq_ok = True
            if stage.prereq is not None:
                prereq_ok = info[stage.prereq]["completed"]
            present = [arts[t] for t in stage.types if t in arts]
            stored_approved = [a for a in present if a.status == ArtifactStatus.APPROVED]
            if stage.key == "FEATURES":
                if counts["total"] == 0:
                    status = "NOT_STARTED"
                elif counts["pending"] > 0:
                    status = "PENDING_REVIEW"
                elif gate_ok:
                    status = "APPROVED"
                else:
                    status = "IN_PROGRESS"
                prereq_ok = True
            elif not prereq_ok:
                had_approval = any(a.status in (ArtifactStatus.APPROVED,
                                                ArtifactStatus.REQUIRES_REVIEW) for a in present)
                status = "REQUIRES_REVIEW" if had_approval else "BLOCKED"
            elif len(stored_approved) == len(stage.types):
                status = "APPROVED"
            elif any(a.status == ArtifactStatus.REQUIRES_REVIEW for a in present):
                status = "REQUIRES_REVIEW"
            elif any(a.status == ArtifactStatus.PENDING_REVIEW for a in present):
                status = "PENDING_REVIEW"
            elif present:
                status = "IN_PROGRESS"
            else:
                status = "NOT_STARTED"
            info[stage.key] = {"status": status, "prereq_ok": prereq_ok,
                               "completed": status == "APPROVED", "artifacts": present}
        return info, {"counts": counts, "gate_ok": gate_ok, "gate_reason": gate_reason,
                      "arts": arts}

    def effective_approved(self, project_id: uuid.UUID, type_: ArtifactType) -> bool:
        info, _ = self._compute(project_id)
        stage = BY_KEY[STAGE_OF_TYPE[type_]]
        a = next((x for x in info[stage.key]["artifacts"] if x.type == type_), None)
        return bool(a and a.status == ArtifactStatus.APPROVED and info[stage.key]["prereq_ok"])

    def get_workflow(self, project_id: uuid.UUID) -> dict[str, Any]:
        self._project(project_id)
        info, extra = self._compute(project_id)
        stages: list[dict[str, Any]] = []
        current = None
        for stage in STAGES:
            i = info[stage.key]
            prereq = BY_KEY[stage.prereq] if stage.prereq else None
            blocked = prereq is not None and not i["prereq_ok"]
            if current is None and not i["completed"]:
                current = stage.key
            entry: dict[str, Any] = {
                "key": stage.key, "number": stage.number, "name": stage.name,
                "path": stage.path, "status": i["status"],
                "approval_status": ("APPROVED" if i["completed"] else
                                    "REQUIRES_REVIEW" if i["status"] == "REQUIRES_REVIEW"
                                    else "NOT_APPROVED"),
                "completed": i["completed"], "accessible": not blocked, "blocked": blocked,
                "required_stage": prereq.key if prereq else None,
                "required_stage_name": prereq.name if prereq else None,
                "blocked_reason": None, "suggested_action": None,
                "artifacts": [{"id": str(a.id), "type": a.type.value, "status": a.status.value,
                               "version": a.current_version} for a in i["artifacts"]],
                "missing_artifact_types": [t.value for t in stage.types
                                           if t not in {a.type for a in i["artifacts"]}],
                "can_proceed": i["completed"], "proceed_blocked_reason": None,
            }
            if blocked and prereq is not None:
                entry.update(self._blocked_text(stage, prereq, info, extra))
            if not i["completed"]:
                entry["proceed_blocked_reason"] = self._proceed_reason(stage, i, entry)
            if stage.key == "FEATURES":
                entry["counts"] = extra["counts"]
                entry["gate_reason"] = extra["gate_reason"]
            stages.append(entry)
        return {"project_id": str(project_id), "current_stage": current or STAGES[-1].key,
                "complete": all(s["completed"] for s in stages), "stages": stages}

    @staticmethod
    def _proceed_reason(stage: StageDef, i: dict, entry: dict) -> str:
        st = i["status"]
        if st == "BLOCKED":
            return entry["blocked_reason"] or "A previous stage is not approved."
        if st == "NOT_STARTED":
            return f"{stage.name} has not been generated yet."
        if st == "PENDING_REVIEW":
            return f"{stage.name} must be reviewed and approved."
        if st == "REQUIRES_REVIEW":
            return (f"{stage.name} must be re-validated and approved because an earlier "
                    "stage changed.")
        return f"{stage.name} is not fully approved yet."

    def _blocked_text(self, stage: StageDef, prereq: StageDef, info: dict,
                      extra: dict) -> dict[str, str]:
        pstatus = info[prereq.key]["status"]
        if prereq.key == "FEATURES":
            reason = extra["gate_reason"] or "Features must be reviewed first."
            action = "Go back to Features, review the extracted features and approve them."
        elif pstatus == "REQUIRES_REVIEW":
            reason = (f"{prereq.name} changed after it was approved and needs review before "
                      f"{stage.name} can proceed.")
            action = f"Re-validate and approve {prereq.name} again."
        elif pstatus == "NOT_STARTED":
            reason = f"{prereq.name} has not been generated yet. Complete it before {stage.name}."
            action = f"Generate and approve {prereq.name}."
        else:
            reason = f"{prereq.name} must be approved before {stage.name} can proceed."
            action = f"Review and approve {prereq.name}."
        return {"blocked_reason": reason, "suggested_action": action}

    # ------------------------------------------------------------------
    # Gates (enforced by the artifact endpoints)
    # ------------------------------------------------------------------
    def blocked_detail(self, project_id: uuid.UUID, type_: ArtifactType,
                       info: dict, extra: dict) -> dict[str, Any] | None:
        stage = BY_KEY[STAGE_OF_TYPE[type_]]
        if stage.prereq is None:
            return None
        prereq = BY_KEY[stage.prereq]
        if info[stage.prereq]["completed"]:
            return None
        text = self._blocked_text(stage, prereq, info, extra)
        return {
            "blocked": True,
            "message": REQUIRED_STAGE_MESSAGES.get(prereq.key, "Approval required"),
            "reason": text["blocked_reason"],
            "stage": stage.key,
            "required_stage": prereq.key,
            "required_stage_name": prereq.name,
            "current_stage_status": info[prereq.key]["status"],
            "stage_status": info[stage.key]["status"],
            "suggested_action": text["suggested_action"],
        }

    def assert_can_modify(self, project_id: uuid.UUID, type_: ArtifactType,
                          *, needs_domain_model: bool = False) -> None:
        """Raise 409 with a structured body when a prerequisite is not approved."""
        self._project(project_id)
        info, extra = self._compute(project_id)
        detail = self.blocked_detail(project_id, type_, info, extra)
        if detail is None and needs_domain_model:
            dm = extra["arts"].get(T.DOMAIN_MODEL)
            if dm is None or dm.status != ArtifactStatus.APPROVED:
                state = dm.status.value if dm else "NOT_STARTED"
                detail = {
                    "blocked": True,
                    "message": "Domain model approval required",
                    "reason": "The domain model must be approved before class and sequence "
                              "diagrams are generated, because they are derived from it.",
                    "stage": "UML", "required_stage": "UML",
                    "required_stage_name": "UML Diagrams",
                    "required_artifact": T.DOMAIN_MODEL.value,
                    "current_stage_status": state, "stage_status": info["UML"]["status"],
                    "suggested_action": "Generate and approve the Domain Model first.",
                }
        if detail is not None:
            raise HTTPException(status_code=409, detail=detail)

    # ------------------------------------------------------------------
    # Invalidation (stored status changes, with history)
    # ------------------------------------------------------------------
    def invalidate_downstream(self, project_id: uuid.UUID, changed: ArtifactType,
                              note: str) -> list[Artifact]:
        """Approved artifacts derived from `changed` need review again. Caller commits."""
        arts = self._artifacts(project_id)
        flagged: list[Artifact] = []
        for t in DOWNSTREAM.get(changed, []):
            a = arts.get(t)
            if a is not None and a.status == ArtifactStatus.APPROVED:
                a.status = ArtifactStatus.REQUIRES_REVIEW
                a.current_version += 1
                self.db.add(ArtifactVersion(
                    id=uuid.uuid4(), artifact_id=a.id, version_number=a.current_version,
                    content_snapshot=a.content, status_snapshot=a.status,
                    validation_snapshot=a.validation_result,
                    change_type=ArtifactChangeType.STATUS_CHANGE, change_note=note,
                    created_at=_now()))
                flagged.append(a)
        return flagged

    def on_features_changed(self, project_id: uuid.UUID) -> None:
        """A feature was approved, rejected, edited or restored: requirements need review."""
        req = self._artifacts(project_id).get(T.REQUIREMENTS)
        if req is not None and req.status == ArtifactStatus.APPROVED:
            req.status = ArtifactStatus.REQUIRES_REVIEW
            req.current_version += 1
            self.db.add(ArtifactVersion(
                id=uuid.uuid4(), artifact_id=req.id, version_number=req.current_version,
                content_snapshot=req.content, status_snapshot=req.status,
                validation_snapshot=req.validation_result,
                change_type=ArtifactChangeType.STATUS_CHANGE,
                change_note="Project features changed after the requirements were approved.",
                created_at=_now()))
            self.invalidate_downstream(
                project_id, T.REQUIREMENTS,
                "Upstream REQUIREMENTS need review (project features changed).")
        self.db.commit()
