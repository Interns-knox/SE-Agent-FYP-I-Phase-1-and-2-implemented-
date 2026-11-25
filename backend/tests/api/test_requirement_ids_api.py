"""FR-/NFR- identifier rules, requirement schema v2 and legacy compatibility."""

import copy
import json
import uuid

from app.domains.artifacts.models import Artifact, ArtifactVersion
from tests.api.helpers import (
    ARCHITECTURE,
    build_pipeline,
    generate,
    make_project_with_features,
    requirements_payload,
)


def raw_requirements(fids):
    """Model output: wrong, missing and duplicate ids; the backend must not trust them."""
    p = requirements_payload(fids)
    reqs = p["requirements"]
    reqs[0]["id"] = "REQ-001"
    reqs[1]["id"] = "REQ-001"
    del reqs[2]["id"]
    return p


def ids(a):
    return [(r["id"], r["type"]) for r in a["content"]["requirements"]]


def test_ids_are_assigned_by_backend_with_fr_and_nfr_prefixes(client, provider):
    pid, fids = make_project_with_features(client, provider)
    a = generate(client, provider, pid, "REQUIREMENTS", raw_requirements(fids)).json()
    assert ids(a) == [("FR-001", "FUNCTIONAL"), ("FR-002", "FUNCTIONAL"),
                      ("NFR-001", "NON_FUNCTIONAL")]
    assert a["content"]["schema_version"] == 2
    assert a["validation_result"]["status"] in ("PASSED", "PASSED_WITH_WARNINGS")
    assert not a["validation_result"]["errors"]


def test_types_are_inferred_when_the_model_omits_them(client, provider):
    pid, fids = make_project_with_features(client, provider)
    p = requirements_payload(fids)
    for r in p["requirements"]:
        del r["type"]
        del r["id"]
    a = generate(client, provider, pid, "REQUIREMENTS", p).json()
    assert ids(a) == [("FR-001", "FUNCTIONAL"), ("FR-002", "FUNCTIONAL"),
                      ("NFR-001", "NON_FUNCTIONAL")]


def test_ids_stay_stable_on_regeneration_and_removed_ids_are_never_reused(client, provider):
    pid, fids = make_project_with_features(client, provider)
    a = generate(client, provider, pid, "REQUIREMENTS", raw_requirements(fids)).json()
    # Regenerate: keep "Register account" (renamed id from the model is ignored by title),
    # drop "Create report", add a new functional and a new non-functional requirement.
    p = requirements_payload(fids)
    keep, _drop, nfr = p["requirements"]
    for r in (keep, nfr):
        r.pop("id")
    new_fr = copy.deepcopy(keep) | {"title": "Reset password"}
    new_nfr = copy.deepcopy(nfr) | {"title": "Audit logging", "category": "SECURITY"}
    p["requirements"] = [keep, nfr, new_fr, new_nfr]
    provider.set("REQUIREMENTS", p)
    b = client.post(f"/artifacts/{a['id']}/regenerate", json={}).json()
    assert ids(b) == [("FR-001", "FUNCTIONAL"), ("NFR-001", "NON_FUNCTIONAL"),
                      ("FR-003", "FUNCTIONAL"), ("NFR-002", "NON_FUNCTIONAL")]
    # FR-002 was removed: it must not come back for a different requirement.
    again = copy.deepcopy(p)
    again["requirements"].append(copy.deepcopy(keep) | {"title": "Brand new"})
    provider.set("REQUIREMENTS", again)
    c = client.post(f"/artifacts/{a['id']}/regenerate", json={}).json()
    assert [i for i, _ in ids(c)].count("FR-002") == 0
    assert ("FR-004", "FUNCTIONAL") in ids(c)
    assert len({i for i, _ in ids(c)}) == len(ids(c))  # unique


def test_regeneration_keeps_ids_when_model_echoes_them(client, provider):
    pid, fids = make_project_with_features(client, provider)
    a = generate(client, provider, pid, "REQUIREMENTS", requirements_payload(fids)).json()
    p = requirements_payload(fids)
    p["requirements"][1]["title"] = "Create a report"  # renamed but the id is echoed
    provider.set("REQUIREMENTS", p)
    b = client.post(f"/artifacts/{a['id']}/regenerate", json={}).json()
    assert ids(b) == ids(a)
    assert b["content"]["requirements"][1]["title"] == "Create a report"


def test_editing_keeps_ids_stable(client, provider):
    pid, fids = make_project_with_features(client, provider)
    a = generate(client, provider, pid, "REQUIREMENTS", requirements_payload(fids)).json()
    content = copy.deepcopy(a["content"])
    content["requirements"][0]["title"] = "Sign up"
    content["requirements"][0]["description"] = "The system shall allow sign up."
    b = client.put(f"/artifacts/{a['id']}", json={"content": content}).json()
    assert ids(b) == ids(a)
    assert b["validation_result"]["errors"] == []


def test_duplicate_and_malformed_ids_are_rejected_before_approval(client, provider):
    pid, fids = make_project_with_features(client, provider)
    a = generate(client, provider, pid, "REQUIREMENTS", requirements_payload(fids)).json()
    bad = copy.deepcopy(a["content"])
    bad["requirements"][1]["id"] = "FR-001"
    bad["requirements"][2]["id"] = "FR-003"  # NFR with an FR prefix
    res = client.put(f"/artifacts/{a['id']}", json={"content": bad}).json()
    codes = {e["code"] for e in res["validation_result"]["errors"]}
    assert {"REQ_ID_DUPLICATE", "REQ_ID_TYPE_MISMATCH"} <= codes
    assert client.post(f"/artifacts/{a['id']}/approve").status_code == 422
    worse = copy.deepcopy(a["content"])
    worse["requirements"][0]["id"] = "REQ-001"
    res = client.put(f"/artifacts/{a['id']}", json={"content": worse}).json()
    err = next(e for e in res["validation_result"]["errors"] if e["code"] == "REQ_ID_FORMAT")
    assert "normalize" in err["suggestion"]


def test_retired_id_cannot_be_reused_for_a_different_requirement(client, provider):
    pid, fids = make_project_with_features(client, provider)
    a = generate(client, provider, pid, "REQUIREMENTS", requirements_payload(fids)).json()
    without = copy.deepcopy(a["content"])
    removed = without["requirements"].pop(1)  # FR-002
    client.put(f"/artifacts/{a['id']}", json={"content": without})
    clash = copy.deepcopy(without)
    clash["requirements"].append(copy.deepcopy(removed) | {"title": "Something else entirely"})
    res = client.put(f"/artifacts/{a['id']}", json={"content": clash}).json()
    codes = {e["code"] for e in res["validation_result"]["errors"]}
    assert "REQ_ID_REUSED" in codes
    # Restoring the same requirement (from the state without it) is allowed, with a warning.
    client.put(f"/artifacts/{a['id']}", json={"content": without})
    restore = copy.deepcopy(without)
    restore["requirements"].append(removed)
    res = client.put(f"/artifacts/{a['id']}", json={"content": restore}).json()
    assert not res["validation_result"]["errors"]
    assert "REQ_ID_RESTORED" in {w["code"] for w in res["validation_result"]["warnings"]}


def test_ids_are_unique_across_the_whole_project_history(client, provider):
    """Ids come from the requirements artifact only, so they cannot clash across artifacts."""
    pid, arts = build_pipeline(client, provider, upto="SRS")
    srs_ids = arts["SRS"]["content"]["requirement_ids"]
    assert srs_ids == [i for i, _ in ids(arts["REQUIREMENTS"])]
    arch = generate(client, provider, pid, "ARCHITECTURE", ARCHITECTURE).json()
    refs = {r for c in arch["content"]["components"] for r in c["requirement_ids"]}
    assert refs <= set(srs_ids)


def test_nfr_fields_and_clarification_flag(client, provider):
    pid, fids = make_project_with_features(client, provider)
    p = requirements_payload(fids)
    nfr = p["requirements"][2]
    nfr["category"] = "AVAILABILITY"
    nfr["measurable_criterion"] = "TBD: availability target not stated in the project context"
    nfr["needs_clarification"] = True
    nfr["clarification_note"] = "No uptime target in the context"
    a = generate(client, provider, pid, "REQUIREMENTS", p).json()
    v = a["validation_result"]
    assert not v["errors"]
    w = next(w for w in v["warnings"] if w["code"] == "REQ_NFR_NEEDS_CLARIFICATION")
    assert "No uptime target" in w["message"]
    assert client.post(f"/artifacts/{a['id']}/approve").status_code == 200  # human decides


def test_nfr_without_criterion_or_valid_category_fails(client, provider):
    pid, fids = make_project_with_features(client, provider)
    p = requirements_payload(fids)
    nfr = p["requirements"][2]
    nfr["category"] = "COOLNESS"
    del nfr["measurable_criterion"]
    del nfr["acceptance_criteria"]
    a = generate(client, provider, pid, "REQUIREMENTS", p).json()
    codes = {e["code"] for e in a["validation_result"]["errors"]}
    assert {"REQ_NFR_CATEGORY_INVALID", "REQ_NFR_CRITERION_MISSING"} <= codes


def test_functional_requirement_needs_actor_and_behavior(client, provider):
    pid, fids = make_project_with_features(client, provider)
    p = requirements_payload(fids)
    del p["requirements"][0]["actor"]
    p["requirements"][1]["expected_behavior"] = ""
    a = generate(client, provider, pid, "REQUIREMENTS", p).json()
    codes = {e["code"] for e in a["validation_result"]["errors"]}
    assert {"REQ_ACTOR_MISSING", "REQ_BEHAVIOR_MISSING"} <= codes
    assert client.post(f"/artifacts/{a['id']}/approve").status_code == 422


def test_srs_renders_new_requirement_fields(client, provider):
    pid, arts = build_pipeline(client, provider, upto="SRS")
    body = {s["id"]: s["body"] for s in arts["SRS"]["content"]["sections"]}
    assert "Actor: Visitor" in body["functional_requirements"]
    assert "Expected behavior:" in body["functional_requirements"]
    assert "Measurable criterion: p95 latency" in body["non_functional_requirements"]
    assert "**NFR-001 Response time**" in body["non_functional_requirements"]


def test_legacy_requirements_without_schema_version_still_validate(client, provider, db_factory):
    """Content created before schema v2 keeps working; new fields only produce a warning."""
    pid, fids = make_project_with_features(client, provider)
    legacy = requirements_payload(fids)
    for r in legacy["requirements"]:
        r.pop("actor", None)
        r.pop("expected_behavior", None)
        r.pop("category", None)
        r.pop("measurable_criterion", None)
        r.pop("preconditions", None)
    a = generate(client, provider, pid, "REQUIREMENTS", legacy).json()
    db = db_factory()
    row = db.get(Artifact, uuid.UUID(a["id"]))
    content = dict(row.content)
    content.pop("schema_version")
    row.content = content  # simulate a record stored before schema versions existed
    db.commit()
    db.close()
    v = client.post(f"/artifacts/{a['id']}/validate").json()["validation_result"]
    assert v["errors"] == []
    assert "REQ_LEGACY_FORMAT" in {w["code"] for w in v["warnings"]}
    assert client.post(f"/artifacts/{a['id']}/approve").status_code == 200


def test_normalize_legacy_req_ids_everywhere_and_keep_history(client, provider, db_factory):
    pid, arts = build_pipeline(client, provider, upto="ARCHITECTURE")
    mapping = {"NFR-001": "REQ-003", "FR-001": "REQ-001", "FR-002": "REQ-002"}

    def to_legacy(obj):
        text = json.dumps(obj)
        for new, old in mapping.items():
            text = text.replace(new, old)
        return json.loads(text)

    db = db_factory()  # rewrite current content AND history: a project created with REQ- ids
    for art in db.query(Artifact).filter(Artifact.project_id == uuid.UUID(pid)):
        art.content = to_legacy(art.content)
    for ver in db.query(ArtifactVersion):
        ver.content_snapshot = to_legacy(ver.content_snapshot)
    db.commit()
    db.close()
    before = {k: client.get(f"/artifacts/{a['id']}").json() for k, a in arts.items()}
    assert before["REQUIREMENTS"]["content"]["requirements"][0]["id"] == "REQ-001"
    r = client.post(f"/projects/{pid}/artifacts/requirements/normalize-ids")
    assert r.status_code == 200
    out = r.json()
    assert out["mapping"] == {"REQ-001": "FR-001", "REQ-002": "FR-002", "REQ-003": "NFR-001"}
    assert len(out["updated_artifacts"]) == 3  # requirements, srs, architecture
    for kind in ("REQUIREMENTS", "SRS", "ARCHITECTURE"):
        a = client.get(f"/artifacts/{arts[kind]['id']}").json()
        assert a["status"] == "APPROVED", kind  # a pure rename keeps approval
        assert a["current_version"] == before[kind]["current_version"] + 1
        assert "REQ-" not in str(a["content"]), kind
        vers = client.get(f"/artifacts/{a['id']}/versions").json()["versions"]
        assert vers[-1]["change_type"] == "EDITED" and "REQ-001 -> FR-001" in vers[-1][
            "change_note"]
        assert "REQ-001" in str(vers[-2]["content_snapshot"]) or kind == "ARCHITECTURE"
    assert [i for i, _ in ids(client.get(
        f"/artifacts/{arts['REQUIREMENTS']['id']}").json())] == ["FR-001", "FR-002", "NFR-001"]
    # idempotent
    assert client.post(f"/projects/{pid}/artifacts/requirements/normalize-ids").json() == {
        "mapping": {}, "updated_artifacts": []}
    assert client.post(f"/projects/{uuid.uuid4()}/artifacts/requirements/normalize-ids"
                       ).status_code == 404
