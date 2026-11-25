"""Dependency model: derive trace links from artifact content.

Link direction is "source depends on / derives from target". Links are owned by
the artifact whose content declares them and are rebuilt on every content change.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.domains.artifacts.models import Artifact, ArtifactType, TraceLink


def _strs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str) and v.strip()]


Link = tuple[str, str, str, str, str]


def derive_links(artifact_type: ArtifactType, content: dict[str, Any]) -> list[Link]:
    """Return (source_kind, source_ref, target_kind, target_ref, relation) tuples."""
    out: list[Link] = []
    if not isinstance(content, dict):
        return out

    def items(key: str) -> list[dict]:
        v = content.get(key)
        return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []

    if artifact_type == ArtifactType.REQUIREMENTS:
        for req in items("requirements"):
            rid = req.get("id")
            if isinstance(rid, str) and rid:
                for fid in _strs(req.get("source_feature_ids")):
                    out.append(("REQUIREMENT", rid, "FEATURE", fid, "DERIVED_FROM"))
    elif artifact_type == ArtifactType.ARCHITECTURE:
        for c in items("components"):
            cid = c.get("id")
            if not (isinstance(cid, str) and cid):
                continue
            for rid in _strs(c.get("requirement_ids")):
                out.append(("COMPONENT", cid, "REQUIREMENT", rid, "IMPLEMENTS"))
            for dep in _strs(c.get("depends_on")):
                out.append(("COMPONENT", cid, "COMPONENT", dep, "DEPENDS_ON"))
    elif artifact_type in (ArtifactType.UML_CLASS, ArtifactType.UML_SEQUENCE,
                           ArtifactType.DOMAIN_MODEL):
        model = content.get("model")
        for e in (model.get("entities") if isinstance(model, dict) else None) or []:
            eid = e.get("id") if isinstance(e, dict) else None
            if isinstance(eid, str) and eid:
                for rid in _strs(e.get("requirement_ids")):
                    out.append(("DOMAIN_ENTITY", eid, "REQUIREMENT", rid, "MODELS"))
        for d in items("diagrams"):
            did = d.get("id")
            if not (isinstance(did, str) and did):
                continue
            for eid in _strs(d.get("domain_entity_ids")):
                out.append(("UML_DIAGRAM", did, "DOMAIN_ENTITY", eid, "DESCRIBES"))
            for cid in _strs(d.get("component_ids")):
                out.append(("UML_DIAGRAM", did, "COMPONENT", cid, "DESCRIBES"))
            for rid in _strs(d.get("requirement_ids")):
                out.append(("UML_DIAGRAM", did, "REQUIREMENT", rid, "DESCRIBES"))
    return list(dict.fromkeys(out))


def rebuild_links(db: Session, artifact: Artifact) -> None:
    """Replace all links owned by ``artifact`` with ones derived from its content."""
    db.query(TraceLink).filter(TraceLink.owner_artifact_id == artifact.id).delete()
    for sk, sr, tk, tr, rel in derive_links(artifact.type, artifact.content):
        db.add(
            TraceLink(
                id=uuid.uuid4(),
                project_id=artifact.project_id,
                owner_artifact_id=artifact.id,
                source_kind=sk,
                source_ref=sr,
                target_kind=tk,
                target_ref=tr,
                relation=rel,
            )
        )
