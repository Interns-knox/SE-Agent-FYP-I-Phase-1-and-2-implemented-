import copy
import uuid

import pytest

from tests.api.helpers import (
    ARCHITECTURE,
    SRS_NARRATIVE,
    build_pipeline,
    generate,
    make_project_with_features,
    requirements_payload,
)

# ---------------------------------------------------------------------------
# Generation and persistence
# ---------------------------------------------------------------------------


def test_generate_requirements_persists_artifact(client, provider):
    pid, fids = make_project_with_features(client, provider)
    r = generate(client, provider, pid, "REQUIREMENTS", requirements_payload(fids))
    assert r.status_code == 201
    a = r.json()
    assert a["project_id"] == pid
    assert a["type"] == "REQUIREMENTS"
    assert a["status"] == "PENDING_REVIEW"
    assert a["current_version"] == 1
    assert a["created_at"]
    assert a["source_refs"]["feature_ids"] == fids
    assert a["validation_result"]["validator"] == "deterministic"
    assert a["validation_result"]["status"] in ("PASSED", "PASSED_WITH_WARNINGS")
    # Retrievable and listed
    assert client.get(f"/artifacts/{a['id']}").json()["content"] == a["content"]
    listed = client.get(f"/projects/{pid}/artifacts").json()["artifacts"]
    assert [x["id"] for x in listed] == [a["id"]]
    assert client.get(f"/projects/{pid}/artifacts?type=SRS").json()["artifacts"] == []
    versions = client.get(f"/artifacts/{a['id']}/versions").json()["versions"]
    assert [v["version_number"] for v in versions] == [1]
    assert versions[0]["change_type"] == "GENERATED"


def test_generation_prompt_contains_only_approved_features(client, provider):
    pid, fids = make_project_with_features(client, provider, approve=2)
    generate(client, provider, pid, "REQUIREMENTS", requirements_payload(fids))
    prompt = provider.prompts[-1]
    for fid in fids:
        assert fid in prompt
    assert "Export reports" not in prompt  # unapproved feature excluded


def test_generate_requires_approved_features(client, provider):
    pid, _ = make_project_with_features(client, provider, approve=0, settle=False)
    r = generate(client, provider, pid, "REQUIREMENTS", {"requirements": []})
    assert r.status_code == 409
    assert r.json()["detail"]["blocked"] is True
    pid, _ = make_project_with_features(client, provider, approve=0)  # all rejected
    r = generate(client, provider, pid, "REQUIREMENTS", {"requirements": []})
    assert r.status_code == 409 and "No feature is approved" in r.json()["detail"]["reason"]


def test_generate_twice_conflicts(client, provider):
    pid, fids = make_project_with_features(client, provider)
    payload = requirements_payload(fids)
    assert generate(client, provider, pid, "REQUIREMENTS", payload).status_code == 201
    assert generate(client, provider, pid, "REQUIREMENTS", payload).status_code == 409


def test_unapproved_artifact_is_not_downstream_input(client, provider):
    pid, fids = make_project_with_features(client, provider)
    generate(client, provider, pid, "REQUIREMENTS", requirements_payload(fids))  # not approved
    r = generate(client, provider, pid, "ARCHITECTURE", ARCHITECTURE)
    assert r.status_code == 409
    assert r.json()["detail"]["required_stage"] == "SRS"
    r = generate(client, provider, pid, "SRS", SRS_NARRATIVE)
    assert r.status_code == 409
    assert r.json()["detail"]["required_stage"] == "REQUIREMENTS"
    assert r.json()["detail"]["current_stage_status"] == "PENDING_REVIEW"


def test_rejected_artifact_is_not_downstream_input(client, provider):
    pid, fids = make_project_with_features(client, provider)
    a = generate(client, provider, pid, "REQUIREMENTS", requirements_payload(fids)).json()
    client.post(f"/artifacts/{a['id']}/reject", json={"reason": "bad"})
    assert generate(client, provider, pid, "SRS", SRS_NARRATIVE).status_code == 409


def test_full_pipeline_generates_all_artifact_types(client, provider):
    pid, arts = build_pipeline(client, provider)
    assert set(arts) == {"REQUIREMENTS", "SRS", "ARCHITECTURE", "DOMAIN_MODEL", "UML_CLASS",
                         "UML_SEQUENCE"}
    assert all(a["status"] == "APPROVED" for a in arts.values())
    srs = arts["SRS"]["content"]
    ids = [s["id"] for s in srs["sections"]]
    assert "functional_requirements" in ids and "non_functional_requirements" in ids
    assert srs["requirement_ids"] == ["FR-001", "FR-002", "NFR-001"]
    assert [s["type"] for s in arts["ARCHITECTURE"]["source_refs"]["artifacts"]] == [
        "REQUIREMENTS", "SRS"]
    assert arts["DOMAIN_MODEL"]["content"]["model"]["entities"][0]["id"] == "ENT-001"


def test_llm_garbage_returns_422_and_persists_nothing(client, provider):
    pid, _ = make_project_with_features(client, provider)
    provider.set("REQUIREMENTS", "this is not json")
    r = client.post(f"/projects/{pid}/artifacts/generate", json={"type": "REQUIREMENTS"})
    assert r.status_code == 422
    assert client.get(f"/projects/{pid}/artifacts").json()["artifacts"] == []


def test_llm_unavailable_returns_503(client, provider):
    import httpx

    pid, _ = make_project_with_features(client, provider)
    provider.fail_with = httpx.ConnectError("down")
    r = client.post(f"/projects/{pid}/artifacts/generate", json={"type": "REQUIREMENTS"})
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# Invalid requests, missing resources
# ---------------------------------------------------------------------------


def test_missing_project_returns_404(client, provider):
    missing = uuid.uuid4()
    assert client.post(f"/projects/{missing}/artifacts/generate",
                       json={"type": "REQUIREMENTS"}).status_code == 404
    assert client.get(f"/projects/{missing}/artifacts").status_code == 404
    assert client.get(f"/projects/{missing}/dependencies").status_code == 404
    assert client.get(f"/projects/{missing}/consistency").status_code == 404


def test_missing_artifact_returns_404(client):
    missing = uuid.uuid4()
    assert client.get(f"/artifacts/{missing}").status_code == 404
    assert client.put(f"/artifacts/{missing}", json={"content": {}}).status_code == 404
    assert client.post(f"/artifacts/{missing}/approve").status_code == 404
    assert client.post(f"/artifacts/{missing}/reject").status_code == 404
    assert client.post(f"/artifacts/{missing}/validate").status_code == 404
    assert client.post(f"/artifacts/{missing}/regenerate").status_code == 404
    assert client.get(f"/artifacts/{missing}/versions").status_code == 404


def test_invalid_requests_return_422(client, provider):
    pid, fids = make_project_with_features(client, provider)
    assert client.post(f"/projects/{pid}/artifacts/generate",
                       json={"type": "NOPE"}).status_code == 422
    assert client.post(f"/projects/{pid}/artifacts/generate", json={}).status_code == 422
    assert client.get("/artifacts/not-a-uuid").status_code == 422
    a = generate(client, provider, pid, "REQUIREMENTS", requirements_payload(fids)).json()
    assert client.put(f"/artifacts/{a['id']}", json={"content": "text"}).status_code == 422
    assert client.put(f"/artifacts/{a['id']}", json={}).status_code == 422
    assert client.get(f"/artifacts/{a['id']}/versions/99").status_code == 404


# ---------------------------------------------------------------------------
# Edit, versioning, approval, rejection
# ---------------------------------------------------------------------------


def _req(client, provider):
    pid, fids = make_project_with_features(client, provider)
    a = generate(client, provider, pid, "REQUIREMENTS", requirements_payload(fids)).json()
    return pid, fids, a


def test_edit_creates_new_version_and_revalidates(client, provider):
    pid, fids, a = _req(client, provider)
    content = copy.deepcopy(a["content"])
    content["requirements"][0]["title"] = "Sign up"
    r = client.put(f"/artifacts/{a['id']}", json={"content": content, "change_note": "rename"})
    assert r.status_code == 200
    body = r.json()
    assert body["current_version"] == 2
    assert body["content"]["requirements"][0]["title"] == "Sign up"
    assert body["validation_result"]["content_version"] == 2
    versions = client.get(f"/artifacts/{a['id']}/versions").json()["versions"]
    assert [(v["version_number"], v["change_type"]) for v in versions] == [
        (1, "GENERATED"), (2, "EDITED")]
    assert versions[0]["content_snapshot"]["requirements"][0]["title"] == "Register account"
    assert versions[1]["change_note"] == "rename"
    v1 = client.get(f"/artifacts/{a['id']}/versions/1").json()
    assert v1["content_snapshot"] == a["content"]


def test_edit_approved_artifact_returns_to_review(client, provider):
    pid, arts = build_pipeline(client, provider, upto="REQUIREMENTS")
    a = arts["REQUIREMENTS"]
    assert a["status"] == "APPROVED"
    r = client.put(f"/artifacts/{a['id']}", json={"content": a["content"]})
    assert r.json()["status"] == "PENDING_REVIEW"
    # Downstream generation is blocked again until re-approval.
    assert generate(client, provider, pid, "SRS", SRS_NARRATIVE).status_code == 409


def test_approve_creates_version_and_decision(client, provider):
    pid, fids, a = _req(client, provider)
    r = client.post(f"/artifacts/{a['id']}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "APPROVED"
    assert r.json()["current_version"] == 2
    decisions = client.get(f"/artifacts/{a['id']}/decisions").json()["decisions"]
    assert [(d["decision"], d["artifact_version"]) for d in decisions] == [("APPROVED", 2)]
    versions = client.get(f"/artifacts/{a['id']}/versions").json()["versions"]
    assert versions[-1]["change_type"] == "STATUS_CHANGE"
    assert versions[-1]["status_snapshot"] == "APPROVED"
    # Cannot approve twice
    assert client.post(f"/artifacts/{a['id']}/approve").status_code == 422


def test_reject_records_reason_and_decision(client, provider):
    pid, fids, a = _req(client, provider)
    r = client.post(f"/artifacts/{a['id']}/reject", json={"reason": "too vague"})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    d = client.get(f"/artifacts/{a['id']}/decisions").json()["decisions"]
    assert d[0]["decision"] == "REJECTED" and d[0]["reason"] == "too vague"
    assert client.post(f"/artifacts/{a['id']}/reject").status_code == 422
    assert client.post(f"/artifacts/{a['id']}/approve").status_code == 422
    # Editing reopens a rejected artifact for review
    r = client.put(f"/artifacts/{a['id']}", json={"content": a["content"]})
    assert r.json()["status"] == "PENDING_REVIEW"


def test_regenerate_creates_new_version_with_feedback(client, provider):
    pid, fids, a = _req(client, provider)
    client.post(f"/artifacts/{a['id']}/approve")
    new = requirements_payload(fids)
    new["requirements"][0]["title"] = "Regenerated"
    provider.set("REQUIREMENTS", new)
    r = client.post(f"/artifacts/{a['id']}/regenerate", json={"feedback": "be more specific"})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == a["id"]
    assert body["status"] == "PENDING_REVIEW"
    assert body["current_version"] == 3
    assert body["content"]["requirements"][0]["title"] == "Regenerated"
    assert "be more specific" in provider.prompts[-1]
    versions = client.get(f"/artifacts/{a['id']}/versions").json()["versions"]
    assert versions[-1]["change_type"] == "REGENERATED"


def test_approval_blocked_when_upstream_no_longer_approved(client, provider):
    pid, arts = build_pipeline(client, provider, upto="SRS")
    arch = generate(client, provider, pid, "ARCHITECTURE", ARCHITECTURE).json()
    # Upstream edited after architecture was generated: the SRS is flagged for review too.
    reqs = arts["REQUIREMENTS"]
    client.put(f"/artifacts/{reqs['id']}", json={"content": reqs["content"]})
    r = client.post(f"/artifacts/{arch['id']}/approve")
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["blocked"] is True and d["required_stage"] == "SRS"
    assert d["current_stage_status"] == "REQUIRES_REVIEW"


# ---------------------------------------------------------------------------
# Deterministic validation through the API
# ---------------------------------------------------------------------------


def test_validation_failure_blocks_approval(client, provider):
    pid, fids, a = _req(client, provider)
    bad = copy.deepcopy(a["content"])
    bad["requirements"][1]["id"] = "FR-001"  # duplicate id
    bad["requirements"][0]["acceptance_criteria"] = []
    bad["requirements"][2]["description"] = ""
    r = client.put(f"/artifacts/{a['id']}", json={"content": bad})
    result = r.json()["validation_result"]
    assert result["status"] == "FAILED"
    codes = {e["code"] for e in result["errors"]}
    assert {"REQ_ID_DUPLICATE", "REQ_ACCEPTANCE_MISSING", "REQ_DESCRIPTION_MISSING"} <= codes
    assert all(e["message"] and e["path"] for e in result["errors"])
    ap = client.post(f"/artifacts/{a['id']}/approve")
    assert ap.status_code == 422
    assert ap.json()["detail"]["validation"]["status"] == "FAILED"
    assert client.get(f"/artifacts/{a['id']}").json()["status"] == "PENDING_REVIEW"


def test_requirement_referencing_unapproved_or_unknown_feature_fails(client, provider):
    pid, fids, a = _req(client, provider)
    all_feats = client.get(f"/projects/{pid}/features").json()["features"]
    unapproved = next(f["id"] for f in all_feats if f["id"] not in fids)
    bad = copy.deepcopy(a["content"])
    bad["requirements"][0]["source_feature_ids"] = [unapproved]
    bad["requirements"][1]["source_feature_ids"] = []  # a functional requirement needs a source
    bad["requirements"][2]["source_feature_ids"] = [str(uuid.uuid4())]
    res = client.put(f"/artifacts/{a['id']}", json={"content": bad}).json()["validation_result"]
    codes = {e["code"] for e in res["errors"]}
    assert {"REQ_SOURCE_NOT_APPROVED", "REQ_SOURCE_UNKNOWN", "REQ_SOURCE_MISSING"} <= codes


def test_validate_endpoint_stores_result_on_current_version(client, provider):
    pid, fids, a = _req(client, provider)
    r = client.post(f"/artifacts/{a['id']}/validate")
    assert r.status_code == 200
    result = r.json()["validation_result"]
    assert result["status"] in ("PASSED", "PASSED_WITH_WARNINGS")
    assert "requirement_ids" in result["checks_run"]
    v = client.get(f"/artifacts/{a['id']}/versions/1").json()
    assert v["validation_snapshot"]["status"] == result["status"]


def test_architecture_unknown_requirement_and_missing_link(client, provider):
    pid, arts = build_pipeline(client, provider, upto="SRS")
    arch = copy.deepcopy(ARCHITECTURE)
    arch["components"][0]["requirement_ids"] = ["FR-999"]
    arch["components"][1]["requirement_ids"] = ["FR-001"]  # FR-002 and NFR-001 unallocated
    a = generate(client, provider, pid, "ARCHITECTURE", arch).json()
    res = a["validation_result"]
    assert res["status"] == "FAILED"
    assert any(e["code"] == "ARCH_REQUIREMENT_UNKNOWN" for e in res["errors"])
    missing = [w["message"] for w in res["warnings"] if w["code"] == "REQ_NOT_IN_ARCHITECTURE"]
    assert any("FR-002" in m for m in missing) and any("NFR-001" in m for m in missing)


def test_uml_syntax_error_detected(client, provider):
    pid, arts = build_pipeline(client, provider, upto="DOMAIN_MODEL")
    bad = {"diagrams": [{"id": "CLS-001", "title": "x",
                         "plantuml": "class A {\n  +x: int\nclass B\n",
                         "requirement_ids": ["FR-001"], "component_ids": []}]}
    a = generate(client, provider, pid, "UML_CLASS", bad).json()
    codes = {e["code"] for e in a["validation_result"]["errors"]}
    assert {"UML_START_MISSING", "UML_END_MISSING", "UML_BRACE_UNBALANCED"} <= codes


def test_ai_critique_is_separate_from_validation(client, provider):
    pid, fids, a = _req(client, provider)
    provider.set("CRITIQUE", "<think>x</think>- Add more NFRs")
    r = client.post(f"/artifacts/{a['id']}/critique")
    body = r.json()
    assert body["ai_critique"]["text"] == "- Add more NFRs"
    assert body["ai_critique"]["source"] == "AI_GENERATED"
    assert body["validation_result"]["validator"] == "deterministic"
    assert body["status"] == "PENDING_REVIEW"  # critique never changes status


# ---------------------------------------------------------------------------
# Dependency model and consistency
# ---------------------------------------------------------------------------


def test_dependency_links_connect_all_artifact_kinds(client, provider):
    pid, arts = build_pipeline(client, provider)
    links = client.get(f"/projects/{pid}/dependencies").json()["links"]
    triples = {(k["source_kind"], k["relation"], k["target_kind"]) for k in links}
    assert {
        ("REQUIREMENT", "DERIVED_FROM", "FEATURE"),
        ("COMPONENT", "IMPLEMENTS", "REQUIREMENT"),
        ("COMPONENT", "DEPENDS_ON", "COMPONENT"),
        ("UML_DIAGRAM", "DESCRIBES", "COMPONENT"),
        ("UML_DIAGRAM", "DESCRIBES", "REQUIREMENT"),
        ("DOMAIN_ENTITY", "MODELS", "REQUIREMENT"),
        ("UML_DIAGRAM", "DESCRIBES", "DOMAIN_ENTITY"),
    } <= triples
    assert {"owner_type", "owner_status"} <= set(links[0])


def test_dependency_links_rebuilt_on_edit(client, provider):
    pid, arts = build_pipeline(client, provider, upto="ARCHITECTURE")
    arch = arts["ARCHITECTURE"]
    content = copy.deepcopy(arch["content"])
    content["components"][0]["requirement_ids"] = ["FR-001"]
    client.put(f"/artifacts/{arch['id']}", json={"content": content})
    links = client.get(f"/projects/{pid}/dependencies").json()["links"]
    ui = [k for k in links if k["source_ref"] == "CMP-001" and k["relation"] == "IMPLEMENTS"]
    assert [k["target_ref"] for k in ui] == ["FR-001"]


def test_consistency_reports_missing_links(client, provider):
    pid, arts = build_pipeline(client, provider)
    ok = client.get(f"/projects/{pid}/consistency").json()
    assert ok["validation"]["errors"] == []
    assert ok["coverage"]["requirements_without_component"] == []
    # Unlink FR-002 from the domain model first (needs approved architecture), then remove
    # requirement NFR-001 from the architecture.
    dm = arts["DOMAIN_MODEL"]
    d = copy.deepcopy(dm["content"])
    d["model"]["entities"][1]["requirement_ids"] = []
    d["model"]["entities"][2]["requirement_ids"] = []
    assert client.put(f"/artifacts/{dm['id']}", json={"content": d}).status_code == 200
    arch = arts["ARCHITECTURE"]
    c = copy.deepcopy(arch["content"])
    c["components"][1]["requirement_ids"] = ["FR-001", "FR-002"]
    assert client.put(f"/artifacts/{arch['id']}", json={"content": c}).status_code == 200
    res = client.get(f"/projects/{pid}/consistency").json()
    assert res["coverage"]["requirements_without_component"] == ["NFR-001"]
    assert res["coverage"]["functional_requirements_without_domain_entity"] == ["FR-002"]
    assert res["coverage"]["domain_entities_without_requirement"] == ["ENT-002", "ENT-003"]
    assert res["validation"]["status"] == "PASSED_WITH_WARNINGS"


def test_consistency_reports_dangling_reference_error(client, provider):
    pid, arts = build_pipeline(client, provider, upto="ARCHITECTURE")
    reqs = arts["REQUIREMENTS"]
    c = copy.deepcopy(reqs["content"])
    c["requirements"] = [r for r in c["requirements"] if r["id"] != "FR-002"]
    client.put(f"/artifacts/{reqs['id']}", json={"content": c})
    res = client.get(f"/projects/{pid}/consistency").json()
    assert res["validation"]["status"] == "FAILED"
    assert any(e["code"] == "LINK_REQUIREMENT_MISSING" for e in res["validation"]["errors"])


@pytest.mark.parametrize("kind", ["SRS", "ARCHITECTURE", "DOMAIN_MODEL", "UML_CLASS",
                                  "UML_SEQUENCE"])
def test_later_stages_require_upstream(client, provider, kind):
    pid, _ = make_project_with_features(client, provider)
    r = generate(client, provider, pid, kind, {"sections": []})
    assert r.status_code == 409 and r.json()["detail"]["blocked"] is True
