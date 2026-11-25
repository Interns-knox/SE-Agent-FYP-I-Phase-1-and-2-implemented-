import copy
import difflib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.domains.ai.provider import LLMProvider
from app.domains.artifacts import domain_model as dm
from app.domains.artifacts import generation, requirement_ids
from app.domains.artifacts.models import (
    Artifact,
    ArtifactChangeType,
    ArtifactDecision,
    ArtifactStatus,
    ArtifactType,
    ArtifactVersion,
    TraceLink,
)
from app.domains.artifacts.traceability import rebuild_links
from app.domains.artifacts.validation.dispatch import validate_content
from app.domains.artifacts.validation.result import FAILED, Report, ValidationContext
from app.domains.features.models import Feature, FeatureStatus
from app.domains.workflow.service import WorkflowService
from app.domains.workspace.models import Project

T = ArtifactType

# Approved artifacts whose content is an input to a given type (fed to the model and recorded
# in source_refs). Stage-level approval gates live in app.domains.workflow.
UPSTREAM: dict[ArtifactType, list[ArtifactType]] = {
    T.REQUIREMENTS: [],
    T.SRS: [T.REQUIREMENTS],
    T.ARCHITECTURE: [T.REQUIREMENTS, T.SRS],
    T.DOMAIN_MODEL: [T.REQUIREMENTS, T.ARCHITECTURE],
    T.UML_CLASS: [T.REQUIREMENTS, T.ARCHITECTURE, T.DOMAIN_MODEL],
    T.UML_SEQUENCE: [T.REQUIREMENTS, T.ARCHITECTURE, T.DOMAIN_MODEL],
}
UPSTREAM_LABEL = {
    T.REQUIREMENTS: "requirements",
    T.SRS: "SRS narrative",
    T.ARCHITECTURE: "architecture",
    T.DOMAIN_MODEL: "domain model",
}
NEEDS_DOMAIN_MODEL = (T.UML_CLASS, T.UML_SEQUENCE)
EDITABLE_STATUSES = (ArtifactStatus.PENDING_REVIEW, ArtifactStatus.REQUIRES_REVIEW)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ArtifactService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def _project(self, project_id: uuid.UUID) -> Project:
        project = self.db.query(Project).filter_by(id=project_id).first()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return project

    def get(self, artifact_id: uuid.UUID) -> Artifact:
        artifact = self.db.query(Artifact).filter_by(id=artifact_id).first()
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")
        return artifact

    def list_artifacts(
        self,
        project_id: uuid.UUID,
        type_: ArtifactType | None = None,
        status: ArtifactStatus | None = None,
    ) -> list[Artifact]:
        self._project(project_id)
        q = self.db.query(Artifact).filter(Artifact.project_id == project_id)
        if type_ is not None:
            q = q.filter(Artifact.type == type_)
        if status is not None:
            q = q.filter(Artifact.status == status)
        return q.order_by(Artifact.created_at.asc()).all()

    def get_by_type(self, project_id: uuid.UUID, type_: ArtifactType) -> Artifact | None:
        return (
            self.db.query(Artifact)
            .filter(Artifact.project_id == project_id, Artifact.type == type_)
            .first()
        )

    def get_approved(self, project_id: uuid.UUID, type_: ArtifactType) -> Artifact | None:
        """Only effectively APPROVED artifacts may be used as downstream inputs: stored status
        APPROVED and every earlier workflow stage still approved."""
        a = self.get_by_type(project_id, type_)
        if a is None or a.status != ArtifactStatus.APPROVED:
            return None
        return a if WorkflowService(self.db).effective_approved(project_id, type_) else None

    def _gate(self, project_id: uuid.UUID, type_: ArtifactType) -> None:
        """Raise a structured 409 when a workflow prerequisite is not approved."""
        WorkflowService(self.db).assert_can_modify(
            project_id, type_, needs_domain_model=type_ in NEEDS_DOMAIN_MODEL)

    def _snapshots(self, artifact_id: uuid.UUID) -> list[Any]:
        return [c for c, _ in self._snapshots_with_trust(artifact_id)]

    def _snapshots_with_trust(self, artifact_id: uuid.UUID) -> list[tuple[Any, bool]]:
        """(content, passed_validation) for every stored version, oldest first."""
        rows = (self.db.query(ArtifactVersion.content_snapshot, ArtifactVersion.validation_snapshot)
                .filter_by(artifact_id=artifact_id)
                .order_by(ArtifactVersion.version_number.asc()).all())
        return [(c, not (isinstance(v, dict) and v.get("status") == FAILED)) for c, v in rows]

    def versions(self, artifact_id: uuid.UUID) -> list[ArtifactVersion]:
        self.get(artifact_id)
        return (
            self.db.query(ArtifactVersion)
            .filter_by(artifact_id=artifact_id)
            .order_by(ArtifactVersion.version_number.asc())
            .all()
        )

    def get_version(self, artifact_id: uuid.UUID, number: int) -> ArtifactVersion:
        self.get(artifact_id)
        v = (
            self.db.query(ArtifactVersion)
            .filter_by(artifact_id=artifact_id, version_number=number)
            .first()
        )
        if v is None:
            raise HTTPException(status_code=404, detail=f"Version {number} not found")
        return v

    def decisions(self, artifact_id: uuid.UUID) -> list[ArtifactDecision]:
        self.get(artifact_id)
        return (
            self.db.query(ArtifactDecision)
            .filter_by(artifact_id=artifact_id)
            .order_by(ArtifactDecision.created_at.asc())
            .all()
        )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def generate(
        self,
        project_id: uuid.UUID,
        type_: ArtifactType,
        provider: LLMProvider,
        feedback: str | None = None,
    ) -> Artifact:
        project = self._project(project_id)
        self._gate(project_id, type_)
        if self.get_by_type(project_id, type_) is not None:
            raise HTTPException(
                status_code=409,
                detail=f"A {type_.value} artifact already exists; regenerate it instead.",
            )
        content, refs = self._generate_content(project, type_, provider, feedback, None)
        now = _now()
        artifact = Artifact(
            id=uuid.uuid4(),
            project_id=project_id,
            type=type_,
            title=generation.TITLES[type_],
            content=content,
            status=ArtifactStatus.PENDING_REVIEW,
            current_version=1,
            source_refs=refs,
            created_at=now,
            updated_at=now,
        )
        self.db.add(artifact)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=409, detail=f"A {type_.value} artifact already exists."
            ) from exc
        self._validate_and_store(artifact)
        self._add_version(artifact, ArtifactChangeType.GENERATED, None)
        rebuild_links(self.db, artifact)
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    def regenerate(
        self, artifact_id: uuid.UUID, provider: LLMProvider, feedback: str | None = None
    ) -> Artifact:
        artifact = self.get(artifact_id)
        project = self._project(artifact.project_id)
        self._gate(project.id, artifact.type)
        content, refs = self._generate_content(
            project, artifact.type, provider, feedback, artifact.content, artifact
        )
        artifact.content = content
        artifact.source_refs = refs
        artifact.ai_critique = None
        artifact.status = ArtifactStatus.PENDING_REVIEW
        artifact.current_version += 1
        self.db.flush()
        self._validate_and_store(artifact)
        self._add_version(artifact, ArtifactChangeType.REGENERATED, feedback)
        rebuild_links(self.db, artifact)
        WorkflowService(self.db).invalidate_downstream(
            artifact.project_id, artifact.type,
            f"Upstream {artifact.type.value} was regenerated; review required.")
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    def _generate_content(
        self,
        project: Project,
        type_: ArtifactType,
        provider: LLMProvider,
        feedback: str | None,
        previous: dict | None,
        existing: Artifact | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        features = (
            self.db.query(Feature)
            .filter(Feature.project_id == project.id, Feature.status == FeatureStatus.APPROVED)
            .order_by(Feature.created_at.asc())
            .all()
        )
        if not features:
            raise HTTPException(
                status_code=422,
                detail="No approved features. Approve at least one feature first.",
            )
        upstream: dict[str, Any] = {}
        src_artifacts: list[dict[str, Any]] = []
        for up_type in UPSTREAM[type_]:
            up = self.get_approved(project.id, up_type)
            if up is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"An approved {up_type.value} artifact is required first.",
                )
            upstream[UPSTREAM_LABEL[up_type]] = self._upstream_view(up)
            src_artifacts.append(
                {"artifact_id": str(up.id), "type": up_type.value, "version": up.current_version}
            )
        feats = [
            {"id": str(f.id), "name": f.name, "description": f.description} for f in features
        ]
        try:
            prompt = generation.build_prompt(
                type_,
                {"name": project.name, "description": project.description},
                feats,
                upstream,
                feedback,
                previous,
            )
        except generation.PromptTooLarge as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        content = generation.call_llm_json(provider, prompt)
        if type_ == ArtifactType.REQUIREMENTS:
            snaps = self._snapshots(existing.id) if existing else []
            history = requirement_ids.historic_ids([*snaps, previous] if previous else snaps)
            content = requirement_ids.assign_ids(content, previous, history)
        elif type_ == ArtifactType.DOMAIN_MODEL:
            content = dm.normalize(content, previous)
        if type_ == ArtifactType.SRS:
            reqs = upstream["requirements"].get("requirements", [])
            sections = content.get("sections")
            content = {
                "sections": (sections if isinstance(sections, list) else [])
                + generation.render_requirement_sections(reqs),
                "requirement_ids": [r.get("id") for r in reqs if isinstance(r, dict)],
            }
        refs = {"feature_ids": [f["id"] for f in feats], "artifacts": src_artifacts}
        return content, refs

    @staticmethod
    def _upstream_view(a: Artifact) -> Any:
        """Content handed to the model: the SRS requirement sections duplicate the requirements,
        so only its narrative sections are included."""
        if a.type == T.SRS and isinstance(a.content, dict):
            secs = [x for x in a.content.get("sections", []) if isinstance(x, dict)
                    and x.get("id") not in ("functional_requirements",
                                            "non_functional_requirements")]
            return {"sections": secs}
        return a.content

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------
    def edit(
        self,
        artifact_id: uuid.UUID,
        content: dict[str, Any],
        title: str | None = None,
        change_note: str | None = None,
    ) -> Artifact:
        artifact = self.get(artifact_id)
        self._gate(artifact.project_id, artifact.type)
        old = artifact.content
        new = copy.deepcopy(content)
        retired: dict[str, str] = {}
        if artifact.type == T.DOMAIN_MODEL:
            new = dm.rerender_if_model_changed(new, old)
        elif artifact.type == T.REQUIREMENTS:
            hist = self._snapshots_with_trust(artifact.id)
            retired = requirement_ids.retired_ids([c for c, _ in hist], old,
                                                  [t for _, t in hist])
        artifact.content = new
        if title:
            artifact.title = title
        artifact.status = ArtifactStatus.PENDING_REVIEW  # any edit requires re-review
        artifact.current_version += 1
        artifact.ai_critique = None
        self.db.flush()
        self._validate_and_store(artifact, retired)
        self._add_version(artifact, ArtifactChangeType.EDITED, change_note)
        rebuild_links(self.db, artifact)
        WorkflowService(self.db).invalidate_downstream(
            artifact.project_id, artifact.type,
            f"Upstream {artifact.type.value} was edited; review required.")
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def build_context(self, project_id: uuid.UUID) -> ValidationContext:
        ctx = ValidationContext()
        for f in self.db.query(Feature).filter(Feature.project_id == project_id).all():
            ctx.feature_status[str(f.id)] = f.status.value
        for a in self.db.query(Artifact).filter(Artifact.project_id == project_id).all():
            if a.status == ArtifactStatus.REJECTED or not isinstance(a.content, dict):
                continue
            if a.type == T.REQUIREMENTS:
                ctx.requirements = {
                    r["id"]: r
                    for r in a.content.get("requirements", [])
                    if isinstance(r, dict) and isinstance(r.get("id"), str)
                }
            elif a.type == T.ARCHITECTURE:
                ctx.components = {
                    c["id"]: c
                    for c in a.content.get("components", [])
                    if isinstance(c, dict) and isinstance(c.get("id"), str)
                }
            elif a.type == T.DOMAIN_MODEL:
                ctx.domain_entities = {
                    e["id"]: e
                    for e in dm.model_of(a.content).get("entities", [])
                    if isinstance(e, dict) and isinstance(e.get("id"), str)
                }
        return ctx

    def _run_validation(self, artifact: Artifact,
                        retired: dict[str, str] | None = None) -> Report:
        ctx = self.build_context(artifact.project_id)
        ctx.retired_ids = retired or {}
        return validate_content(artifact.type, artifact.content, ctx)

    def _validate_and_store(self, artifact: Artifact,
                            retired: dict[str, str] | None = None) -> dict[str, Any]:
        result = self._run_validation(artifact, retired).to_dict(artifact.current_version)
        artifact.validation_result = result
        return result

    def validate(self, artifact_id: uuid.UUID) -> Artifact:
        artifact = self.get(artifact_id)
        self._validate_and_store(artifact)
        current = (
            self.db.query(ArtifactVersion)
            .filter_by(artifact_id=artifact.id, version_number=artifact.current_version)
            .first()
        )
        if current is not None:
            current.validation_snapshot = artifact.validation_result
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------
    def approve(self, artifact_id: uuid.UUID) -> Artifact:
        artifact = self.get(artifact_id)
        if artifact.status not in EDITABLE_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Artifact cannot be approved from status {artifact.status.value}.",
            )
        self._gate(artifact.project_id, artifact.type)
        result = self._validate_and_store(artifact)
        if result["status"] == FAILED:
            self.db.commit()  # keep the fresh validation result
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Artifact failed deterministic validation and cannot be approved.",
                    "validation": result,
                },
            )
        for src in artifact.source_refs.get("artifacts", []):
            up = self.db.query(Artifact).filter_by(id=uuid.UUID(src["artifact_id"])).first()
            if up is None or up.status != ArtifactStatus.APPROVED:
                self.db.rollback()
                raise HTTPException(
                    status_code=422,
                    detail=f"Source {src['type']} artifact is not approved; approve it first.",
                )
        artifact.status = ArtifactStatus.APPROVED
        artifact.current_version += 1
        self.db.flush()
        artifact.validation_result = {**artifact.validation_result,
                                      "content_version": artifact.current_version}
        self._add_version(artifact, ArtifactChangeType.STATUS_CHANGE, None)
        self._add_decision(artifact, "APPROVED", None)
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    def reject(self, artifact_id: uuid.UUID, reason: str | None = None) -> Artifact:
        artifact = self.get(artifact_id)
        if artifact.status == ArtifactStatus.REJECTED:
            raise HTTPException(status_code=422, detail="Artifact is already rejected.")
        artifact.status = ArtifactStatus.REJECTED
        artifact.current_version += 1
        self.db.flush()
        self._add_version(artifact, ArtifactChangeType.STATUS_CHANGE, reason)
        self._add_decision(artifact, "REJECTED", reason)
        WorkflowService(self.db).invalidate_downstream(
            artifact.project_id, artifact.type,
            f"Upstream {artifact.type.value} was rejected; review required.")
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    # ------------------------------------------------------------------
    # AI critique (advisory only)
    # ------------------------------------------------------------------
    def critique(self, artifact_id: uuid.UUID, provider: LLMProvider) -> Artifact:
        artifact = self.get(artifact_id)
        prompt = generation.build_critique_prompt(artifact.type, artifact.content)
        try:
            text = provider.generate(prompt)
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="AI service request timed out.") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="AI service is unavailable.") from exc
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
        artifact.ai_critique = {
            "source": "AI_GENERATED",
            "advisory": True,
            "model": settings.OLLAMA_MODEL,
            "text": text,
            "content_version": artifact.current_version,
            "generated_at": _now().isoformat(),
        }
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    # ------------------------------------------------------------------
    # Dependency model / consistency
    # ------------------------------------------------------------------
    def dependencies(self, project_id: uuid.UUID) -> list[tuple[TraceLink, Artifact]]:
        self._project(project_id)
        rows = (
            self.db.query(TraceLink, Artifact)
            .join(Artifact, TraceLink.owner_artifact_id == Artifact.id)
            .filter(TraceLink.project_id == project_id)
            .order_by(TraceLink.created_at.asc())
            .all()
        )
        return [(link, art) for link, art in rows]

    def consistency(self, project_id: uuid.UUID) -> tuple[dict[str, Any], dict[str, list[str]]]:
        """Cross-artifact link check: features -> requirements -> components / domain entities."""
        self._project(project_id)
        ctx = self.build_context(project_id)
        r = Report()
        cov: dict[str, list[str]] = {
            "features_without_requirement": [],
            "requirements_without_component": [],
            "components_without_requirement": [],
            "functional_requirements_without_domain_entity": [],
            "domain_entities_without_requirement": [],
        }
        links = [lk for lk, _ in self.dependencies(project_id)]
        r.check("dangling_references")
        for lk in links:
            if lk.target_kind == "REQUIREMENT" and ctx.requirements is not None \
                    and lk.target_ref not in ctx.requirements:
                r.error("LINK_REQUIREMENT_MISSING",
                        f"{lk.source_kind} {lk.source_ref} references missing requirement "
                        f"{lk.target_ref}.", "", "Fix or remove the reference.")
            if lk.target_kind == "COMPONENT" and ctx.components is not None \
                    and lk.target_ref not in ctx.components:
                r.error("LINK_COMPONENT_MISSING",
                        f"{lk.source_kind} {lk.source_ref} references missing component "
                        f"{lk.target_ref}.", "", "Fix or remove the reference.")
            if lk.target_kind == "FEATURE" and lk.target_ref not in ctx.feature_status:
                r.error("LINK_FEATURE_MISSING",
                        f"{lk.source_kind} {lk.source_ref} references missing feature "
                        f"{lk.target_ref}.", "", "Fix or remove the reference.")
        r.check("coverage")
        has = {(lk.source_kind, lk.source_ref, lk.target_kind) for lk in links}
        tgt = {(lk.target_kind, lk.target_ref, lk.source_kind) for lk in links}
        for fid, st in ctx.feature_status.items():
            if st == "APPROVED" and ("FEATURE", fid, "REQUIREMENT") not in tgt:
                cov["features_without_requirement"].append(fid)
        for rid, req in (ctx.requirements or {}).items():
            if ctx.components is not None and ("REQUIREMENT", rid, "COMPONENT") not in tgt:
                cov["requirements_without_component"].append(rid)
            if (ctx.domain_entities is not None and req.get("type") == "FUNCTIONAL"
                    and ("REQUIREMENT", rid, "DOMAIN_ENTITY") not in tgt):
                cov["functional_requirements_without_domain_entity"].append(rid)
        for cid in ctx.components or {}:
            if ctx.requirements is not None and ("COMPONENT", cid, "REQUIREMENT") not in has:
                cov["components_without_requirement"].append(cid)
        for eid in ctx.domain_entities or {}:
            if ctx.requirements is not None and ("DOMAIN_ENTITY", eid, "REQUIREMENT") not in has:
                cov["domain_entities_without_requirement"].append(eid)
        messages = {
            "features_without_requirement": "Approved feature {} has no requirement.",
            "requirements_without_component": "Requirement {} is not allocated to a component.",
            "components_without_requirement": "Component {} is not linked to a requirement.",
            "functional_requirements_without_domain_entity":
                "Functional requirement {} is not modelled by any domain entity.",
            "domain_entities_without_requirement":
                "Domain entity {} is not linked to a requirement.",
        }
        for key, items in cov.items():
            for item in items:
                r.warning(key.upper(), messages[key].format(item), "",
                          "Add the missing link in the relevant artifact.")
        return r.to_dict(), cov

    # ------------------------------------------------------------------
    # Version comparison
    # ------------------------------------------------------------------
    def diff(self, artifact_id: uuid.UUID, from_v: int | None, to_v: int | None) -> dict[str, Any]:
        a = self.get(artifact_id)
        to_no = to_v if to_v is not None else a.current_version
        from_no = from_v if from_v is not None else max(1, to_no - 1)
        old = self.get_version(artifact_id, from_no).content_snapshot
        new = self.get_version(artifact_id, to_no).content_snapshot

        def dump(x: Any) -> list[str]:
            return json.dumps(x, indent=2, ensure_ascii=False).splitlines()

        lines = list(difflib.unified_diff(dump(old), dump(new), fromfile=f"v{from_no}",
                                          tofile=f"v{to_no}", lineterm=""))
        return {"artifact_id": a.id, "from_version": from_no, "to_version": to_no,
                "identical": old == new,
                "additions": sum(1 for x in lines if x.startswith("+") and not x.startswith("+++")),
                "deletions": sum(1 for x in lines if x.startswith("-") and not x.startswith("---")),
                "diff": "\n".join(lines)}

    # ------------------------------------------------------------------
    # Requirement id compatibility
    # ------------------------------------------------------------------
    def normalize_requirement_ids(self, project_id: uuid.UUID) -> dict[str, Any]:
        """Rename legacy ids (e.g. REQ-001) to FR-/NFR- ids everywhere they are referenced.

        Existing versions are kept; each touched artifact gets a new EDITED version and keeps
        its approval status, because the rename changes no meaning."""
        self._project(project_id)
        req = self.get_by_type(project_id, T.REQUIREMENTS)
        if req is None:
            raise HTTPException(status_code=404, detail="No requirements artifact exists.")
        history = requirement_ids.historic_ids([*self._snapshots(req.id), req.content])
        mapping = requirement_ids.legacy_id_mapping(req.content, history)
        if not mapping:
            return {"mapping": {}, "updated_artifacts": []}
        pattern = re.compile(r"\b(" + "|".join(map(re.escape, mapping)) + r")\b")

        def remap(obj: Any, key: str | None = None, in_req: bool = False) -> Any:
            if isinstance(obj, dict):
                return {k: remap(v, k, in_req) for k, v in obj.items()}
            if isinstance(obj, list):
                return [remap(v, key, in_req) for v in obj]
            if isinstance(obj, str):
                if key in ("requirement_ids", "requirement_id"):
                    return mapping.get(obj, obj)
                if key == "id" and in_req:
                    return mapping.get(obj, obj)
                if key == "body":
                    return pattern.sub(lambda m: mapping[m.group(1)], obj)
            return obj

        updated: list[str] = []
        for a in self.list_artifacts(project_id):
            if not isinstance(a.content, dict):
                continue
            if a.type == T.REQUIREMENTS:
                new = {**remap({k: v for k, v in a.content.items() if k != "requirements"}),
                       "requirements": [remap(r, None, True) for r in a.content["requirements"]]}
            else:
                new = remap(a.content)
            if new == a.content:
                continue
            a.content = new
            a.current_version += 1
            self.db.flush()
            self._validate_and_store(a)
            self._add_version(a, ArtifactChangeType.EDITED,
                              "Requirement ids normalized: " + ", ".join(
                                  f"{k} -> {v}" for k, v in mapping.items()))
            rebuild_links(self.db, a)
            updated.append(str(a.id))
        self.db.commit()
        return {"mapping": mapping, "updated_artifacts": updated}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _add_version(
        self, artifact: Artifact, change_type: ArtifactChangeType, note: str | None
    ) -> ArtifactVersion:
        v = ArtifactVersion(
            id=uuid.uuid4(),
            artifact_id=artifact.id,
            version_number=artifact.current_version,
            content_snapshot=copy.deepcopy(artifact.content),
            status_snapshot=artifact.status,
            validation_snapshot=copy.deepcopy(artifact.validation_result),
            change_type=change_type,
            change_note=note,
            created_at=_now(),
        )
        self.db.add(v)
        return v

    def _add_decision(self, artifact: Artifact, decision: str, reason: str | None) -> None:
        self.db.add(
            ArtifactDecision(
                id=uuid.uuid4(),
                artifact_id=artifact.id,
                project_id=artifact.project_id,
                artifact_version=artifact.current_version,
                decision=decision,
                reason=reason,
                created_at=_now(),
            )
        )
