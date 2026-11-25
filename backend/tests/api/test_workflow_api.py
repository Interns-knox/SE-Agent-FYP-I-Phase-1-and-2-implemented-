"""Guided workflow: stage status, backend approval gates, bypass attempts, invalidation."""

import copy
import uuid

import pytest

from app.domains.artifacts.models import Artifact, ArtifactStatus, ArtifactType
from tests.api.helpers import (
    ARCHITECTURE,
    CLASS_DIAGRAMS,
    DOMAIN_MODEL,
    SEQUENCE_DIAGRAMS,
    build_pipeline,
    generate,
    make_project_with_features,
    requirements_payload,
)


def workflow(client, pid):
    r = client.get(f"/projects/{pid}/workflow")
    assert r.status_code == 200, r.text
    return {s["key"]: s for s in r.json()["stages"]}, r.json()


def statuses(client, pid):
    return {k: v["status"] for k, v in workflow(client, pid)[0].items()}


def blocked(r):
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["blocked"] is True
    for key in ("reason", "required_stage", "current_stage_status", "suggested_action", "message"):
        assert d[key], key
    return d


# ---------------------------------------------------------------------------
# Stage status
# ---------------------------------------------------------------------------
def test_workflow_for_new_project(client):
    pid = client.post("/projects", json={"name": "P", "description": "D"}).json()["id"]
    stages, body = workflow(client, pid)
    assert list(stages) == ["FEATURES", "REQUIREMENTS", "SRS", "ARCHITECTURE", "UML"]
    assert [s["number"] for s in stages.values()] == [1, 2, 3, 4, 5]
    assert stages["FEATURES"]["status"] == "NOT_STARTED"
    assert stages["REQUIREMENTS"]["status"] == "BLOCKED"
    assert stages["REQUIREMENTS"]["accessible"] is False
    assert stages["REQUIREMENTS"]["required_stage"] == "FEATURES"
    assert body["current_stage"] == "FEATURES" and body["complete"] is False
    assert client.get(f"/projects/{uuid.uuid4()}/workflow").status_code == 404


def test_feature_stage_counts_and_gate(client, provider):
    pid, fids = make_project_with_features(client, provider, approve=1, settle=False)
    f = workflow(client, pid)[0]["FEATURES"]
    assert f["counts"] == {"total": 3, "approved": 1, "pending": 2, "rejected": 0}
    assert f["status"] == "PENDING_REVIEW" and f["completed"] is False
    assert "2 features are still pending review" in f["gate_reason"]
    feats = client.get(f"/projects/{pid}/features").json()["features"]
    for x in feats:
        if x["id"] != fids[0]:
            client.post(f"/features/{x['id']}/reject")
    f = workflow(client, pid)[0]["FEATURES"]
    assert f["counts"] == {"total": 3, "approved": 1, "pending": 0, "rejected": 2}
    assert f["status"] == "APPROVED" and f["completed"] is True


def test_stage_statuses_advance_with_approvals(client, provider):
    pid, fids = make_project_with_features(client, provider)
    assert statuses(client, pid)["REQUIREMENTS"] == "NOT_STARTED"
    req = generate(client, provider, pid, "REQUIREMENTS", requirements_payload(fids)).json()
    st = statuses(client, pid)
    assert st["REQUIREMENTS"] == "PENDING_REVIEW" and st["SRS"] == "BLOCKED"
    client.post(f"/artifacts/{req['id']}/approve")
    st = statuses(client, pid)
    assert st["REQUIREMENTS"] == "APPROVED" and st["SRS"] == "NOT_STARTED"
    stages, body = workflow(client, pid)
    assert body["current_stage"] == "SRS" and stages["SRS"]["accessible"] is True
    assert stages["REQUIREMENTS"]["can_proceed"] is True
    assert stages["SRS"]["can_proceed"] is False
    assert "has not been generated" in stages["SRS"]["proceed_blocked_reason"]


def test_full_workflow_reaches_complete(client, provider):
    pid, _ = build_pipeline(client, provider)
    stages, body = workflow(client, pid)
    assert body["complete"] is True and body["current_stage"] == "UML"
    assert all(s["status"] == "APPROVED" and s["approval_status"] == "APPROVED"
               for s in stages.values())
    assert {a["type"] for a in stages["UML"]["artifacts"]} == {
        "DOMAIN_MODEL", "UML_CLASS", "UML_SEQUENCE"}


def test_uml_stage_needs_all_three_artifacts(client, provider):
    pid, _ = build_pipeline(client, provider, upto="UML_CLASS")
    st, _ = workflow(client, pid)
    assert st["UML"]["status"] == "IN_PROGRESS"
    assert st["UML"]["missing_artifact_types"] == ["UML_SEQUENCE"]
    r = generate(client, provider, pid, "UML_SEQUENCE", SEQUENCE_DIAGRAMS)
    assert statuses(client, pid)["UML"] == "PENDING_REVIEW"
    client.post(f"/artifacts/{r.json()['id']}/approve")
    assert statuses(client, pid)["UML"] == "APPROVED"


# ---------------------------------------------------------------------------
# Gates enforced by the backend
# ---------------------------------------------------------------------------
def test_requirements_blocked_until_features_are_reviewed(client, provider):
    pid = client.post("/projects", json={"name": "P", "description": "D"}).json()["id"]
    d = blocked(client.post(f"/projects/{pid}/artifacts/generate", json={"type": "REQUIREMENTS"}))
    assert d["required_stage"] == "FEATURES" and "No features" in d["reason"]
    pid, fids = make_project_with_features(client, provider, approve=1, settle=False)
    provider.set("REQUIREMENTS", requirements_payload(fids))
    d = blocked(client.post(f"/projects/{pid}/artifacts/generate", json={"type": "REQUIREMENTS"}))
    assert d["current_stage_status"] == "PENDING_REVIEW"
    assert "pending review" in d["reason"] and d["message"] == "Feature approval required"
    pid, _ = make_project_with_features(client, provider, approve=0)
    d = blocked(client.post(f"/projects/{pid}/artifacts/generate", json={"type": "REQUIREMENTS"}))
    assert "At least one feature must be approved" in d["reason"]
    pid, fids = make_project_with_features(client, provider)  # ok: 2 approved, 1 rejected
    assert generate(client, provider, pid, "REQUIREMENTS",
                    requirements_payload(fids)).status_code == 201


def test_rejected_features_are_not_used_downstream(client, provider):
    pid, fids = make_project_with_features(client, provider)
    generate(client, provider, pid, "REQUIREMENTS", requirements_payload(fids))
    prompt = provider.prompts[-1]
    assert all(f in prompt for f in fids) and "Export reports" not in prompt


@pytest.mark.parametrize("kind,upto,required,message", [
    ("SRS", None, "REQUIREMENTS", "Requirements approval required"),
    ("ARCHITECTURE", "REQUIREMENTS", "SRS", "SRS approval required"),
    ("DOMAIN_MODEL", "SRS", "ARCHITECTURE", "Architecture approval required"),
    ("UML_CLASS", "SRS", "ARCHITECTURE", "Architecture approval required"),
    ("UML_SEQUENCE", "SRS", "ARCHITECTURE", "Architecture approval required"),
])
def test_each_stage_is_blocked_until_prerequisite_is_approved(client, provider, kind, upto,
                                                              required, message):
    if upto is None:
        pid, fids = make_project_with_features(client, provider)
        a = generate(client, provider, pid, "REQUIREMENTS", requirements_payload(fids)).json()
    else:
        pid, arts = build_pipeline(client, provider, upto=upto)
        a = None
    if upto == "SRS":  # architecture exists but is only pending review
        generate(client, provider, pid, "ARCHITECTURE", ARCHITECTURE)
    provider.set(kind, {})
    d = blocked(client.post(f"/projects/{pid}/artifacts/generate", json={"type": kind}))
    assert d["required_stage"] == required and d["message"] == message
    assert d["current_stage_status"] == "PENDING_REVIEW" if (a or upto == "SRS") else True
    assert a is None or client.get(f"/artifacts/{a['id']}").json()["status"] == "PENDING_REVIEW"


def test_class_and_sequence_diagrams_need_an_approved_domain_model(client, provider):
    pid, _ = build_pipeline(client, provider, upto="ARCHITECTURE")
    for kind in ("UML_CLASS", "UML_SEQUENCE"):
        provider.set(kind, {})
        d = blocked(client.post(f"/projects/{pid}/artifacts/generate", json={"type": kind}))
        assert d["required_artifact"] == "DOMAIN_MODEL"
        assert d["message"] == "Domain model approval required"
    dm = generate(client, provider, pid, "DOMAIN_MODEL", DOMAIN_MODEL).json()  # pending only
    provider.set("UML_CLASS", CLASS_DIAGRAMS)
    blocked(client.post(f"/projects/{pid}/artifacts/generate", json={"type": "UML_CLASS"}))
    client.post(f"/artifacts/{dm['id']}/approve")
    assert generate(client, provider, pid, "UML_CLASS", CLASS_DIAGRAMS).status_code == 201


def test_direct_api_calls_cannot_bypass_the_gates(client, provider):
    """edit, regenerate and approve are gated, not just generate."""
    pid, arts = build_pipeline(client, provider, upto="SRS")
    arch = generate(client, provider, pid, "ARCHITECTURE", ARCHITECTURE).json()  # pending
    reqs = arts["REQUIREMENTS"]
    client.put(f"/artifacts/{reqs['id']}", json={"content": reqs["content"]})  # reopen upstream
    assert statuses(client, pid)["SRS"] == "REQUIRES_REVIEW"
    blocked(client.put(f"/artifacts/{arch['id']}", json={"content": ARCHITECTURE}))
    blocked(client.post(f"/artifacts/{arch['id']}/approve"))
    blocked(client.post(f"/artifacts/{arch['id']}/regenerate", json={}))
    blocked(client.post(f"/projects/{pid}/artifacts/generate", json={"type": "DOMAIN_MODEL"}))
    assert client.get(f"/artifacts/{arch['id']}").json()["status"] == "PENDING_REVIEW"
    assert client.get(f"/artifacts/{arch['id']}").json()["current_version"] == 1  # untouched


def test_reject_is_allowed_regardless_of_gates(client, provider):
    pid, arts = build_pipeline(client, provider, upto="SRS")
    arch = generate(client, provider, pid, "ARCHITECTURE", ARCHITECTURE).json()
    reqs = arts["REQUIREMENTS"]
    client.put(f"/artifacts/{reqs['id']}", json={"content": reqs["content"]})
    assert client.post(f"/artifacts/{arch['id']}/reject", json={}).status_code == 200


def test_chain_recovers_after_upstream_is_reapproved(client, provider):
    pid, arts = build_pipeline(client, provider, upto="SRS")
    reqs = arts["REQUIREMENTS"]
    client.put(f"/artifacts/{reqs['id']}", json={"content": reqs["content"]})
    assert client.post(f"/artifacts/{reqs['id']}/approve").status_code == 200
    st = statuses(client, pid)
    assert st["REQUIREMENTS"] == "APPROVED" and st["SRS"] == "REQUIRES_REVIEW"
    assert generate(client, provider, pid, "ARCHITECTURE", ARCHITECTURE).status_code == 409
    assert client.post(f"/artifacts/{arts['SRS']['id']}/approve").status_code == 200
    assert statuses(client, pid)["SRS"] == "APPROVED"
    assert generate(client, provider, pid, "ARCHITECTURE", ARCHITECTURE).status_code == 201


# ---------------------------------------------------------------------------
# Invalidation of downstream approvals
# ---------------------------------------------------------------------------
def test_editing_upstream_marks_all_downstream_for_review(client, provider):
    pid, arts = build_pipeline(client, provider)
    srs = arts["SRS"]
    r = client.put(f"/artifacts/{srs['id']}", json={"content": srs["content"]})
    assert r.json()["status"] == "PENDING_REVIEW"
    for kind in ("ARCHITECTURE", "DOMAIN_MODEL", "UML_CLASS", "UML_SEQUENCE"):
        a = client.get(f"/artifacts/{arts[kind]['id']}").json()
        assert a["status"] == "REQUIRES_REVIEW", kind
        last = client.get(f"/artifacts/{a['id']}/versions").json()["versions"][-1]
        assert last["change_type"] == "STATUS_CHANGE" and "review required" in last["change_note"]
        assert last["status_snapshot"] == "REQUIRES_REVIEW"
    assert statuses(client, pid)["REQUIREMENTS"] == "APPROVED"  # upstream of the change
    # Stale approvals are not usable inputs: downstream stages are locked until re-approval.
    st = statuses(client, pid)
    assert st["ARCHITECTURE"] == "REQUIRES_REVIEW" and st["UML"] == "REQUIRES_REVIEW"
    blocked(client.post(f"/artifacts/{arts['UML_CLASS']['id']}/regenerate", json={}))


def test_regenerate_and_reject_also_invalidate_downstream(client, provider):
    pid, arts = build_pipeline(client, provider)
    client.post(f"/artifacts/{arts['ARCHITECTURE']['id']}/reject", json={"reason": "x"})
    assert client.get(f"/artifacts/{arts['DOMAIN_MODEL']['id']}").json()[
        "status"] == "REQUIRES_REVIEW"
    pid, arts = build_pipeline(client, provider)
    provider.set("DOMAIN_MODEL", DOMAIN_MODEL)
    assert client.post(f"/artifacts/{arts['DOMAIN_MODEL']['id']}/regenerate",
                       json={}).status_code == 200
    assert client.get(f"/artifacts/{arts['UML_CLASS']['id']}").json()[
        "status"] == "REQUIRES_REVIEW"
    # the sequence diagrams derive from the domain model too
    assert client.get(f"/artifacts/{arts['UML_SEQUENCE']['id']}").json()[
        "status"] == "REQUIRES_REVIEW"
    # artifacts upstream of the regenerated one keep their approval
    assert client.get(f"/artifacts/{arts['ARCHITECTURE']['id']}").json()["status"] == "APPROVED"


def test_requires_review_artifact_can_be_reapproved_after_validation(client, provider):
    pid, arts = build_pipeline(client, provider)
    srs = arts["SRS"]
    client.put(f"/artifacts/{srs['id']}", json={"content": srs["content"]})
    client.post(f"/artifacts/{srs['id']}/approve")
    arch = arts["ARCHITECTURE"]
    assert client.get(f"/artifacts/{arch['id']}").json()["status"] == "REQUIRES_REVIEW"
    r = client.post(f"/artifacts/{arch['id']}/approve")
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    dec = client.get(f"/artifacts/{arch['id']}/decisions").json()["decisions"]
    assert [d["decision"] for d in dec] == ["APPROVED", "APPROVED"]


def test_feature_changes_after_approval_flag_requirements(client, provider):
    pid, arts = build_pipeline(client, provider, upto="SRS")
    feats = client.get(f"/projects/{pid}/features").json()["features"]
    rejected = next(f for f in feats if f["status"] == "REJECTED")
    assert client.post(f"/features/{rejected['id']}/restore").status_code == 200
    st = statuses(client, pid)
    assert st["FEATURES"] == "PENDING_REVIEW"  # a pending feature reopens the stage
    assert client.get(f"/artifacts/{arts['REQUIREMENTS']['id']}").json()[
        "status"] == "REQUIRES_REVIEW"
    assert client.get(f"/artifacts/{arts['SRS']['id']}").json()["status"] == "REQUIRES_REVIEW"
    d = blocked(client.post(f"/artifacts/{arts['REQUIREMENTS']['id']}/approve"))
    assert d["required_stage"] == "FEATURES"
    client.post(f"/features/{rejected['id']}/reject")
    assert client.post(f"/artifacts/{arts['REQUIREMENTS']['id']}/approve").status_code == 200


def test_legacy_approvals_without_srs_are_not_treated_as_valid(client, provider, db_factory):
    """An architecture approved before the SRS gate existed counts as needing review."""
    pid, arts = build_pipeline(client, provider, upto="REQUIREMENTS")
    db = db_factory()
    db.add(Artifact(id=uuid.uuid4(), project_id=uuid.UUID(pid), type=ArtifactType.ARCHITECTURE,
                    title="Legacy architecture", content=copy.deepcopy(ARCHITECTURE),
                    status=ArtifactStatus.APPROVED, current_version=2, source_refs={},
                    validation_result=None))
    db.commit()
    db.close()
    st, _ = workflow(client, pid)
    assert st["SRS"]["status"] == "NOT_STARTED"
    assert st["ARCHITECTURE"]["status"] == "REQUIRES_REVIEW"
    assert st["ARCHITECTURE"]["completed"] is False
    assert st["UML"]["status"] == "BLOCKED"
    blocked(client.post(f"/projects/{pid}/artifacts/generate", json={"type": "DOMAIN_MODEL"}))
    assert st["ARCHITECTURE"]["approval_status"] == "REQUIRES_REVIEW"
