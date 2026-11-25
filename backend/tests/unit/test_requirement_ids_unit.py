"""Requirement id assignment and schema v2 validation without a database."""

import copy

from app.domains.artifacts import requirement_ids as ri
from app.domains.artifacts.validation.requirements import validate_requirements
from app.domains.artifacts.validation.result import ValidationContext
from tests.api.helpers import requirements_payload

F = "f-1"
CTX = ValidationContext(feature_status={F: "APPROVED"})


def v2(**kw):
    p = requirements_payload([F, F])
    for r in p["requirements"]:
        r.pop("id")
    return ri.assign_ids({**p, **kw}, None, {})


def codes(r, kind="errors"):
    return {i["code"] for i in getattr(r, kind)}


def test_assign_ids_sequences_by_type_and_sets_schema_version():
    c = v2()
    assert [r["id"] for r in c["requirements"]] == ["FR-001", "FR-002", "NFR-001"]
    assert c["schema_version"] == 2


def test_assign_ids_skips_every_historical_id():
    history = {"FR-001": "a", "FR-002": "b", "FR-007": "c", "NFR-003": "d"}
    c = ri.assign_ids({"requirements": [{"type": "FUNCTIONAL", "title": "x"},
                                        {"type": "NON_FUNCTIONAL", "title": "y"}]}, None, history)
    assert [r["id"] for r in c["requirements"]] == ["FR-008", "NFR-004"]


def test_assign_ids_keeps_matching_ids_and_ignores_wrong_claims():
    prev = {"requirements": [{"id": "FR-005", "type": "FUNCTIONAL", "title": "Login"},
                             {"id": "NFR-002", "type": "NON_FUNCTIONAL", "category": "SECURITY"}]}
    new = {"requirements": [
        {"id": "FR-005", "type": "FUNCTIONAL", "title": "Log in"},          # echoed id kept
        {"type": "FUNCTIONAL", "title": "login"},                           # title match, taken
        {"id": "NFR-002", "type": "FUNCTIONAL", "title": "Wrong type"},     # id of other type
        {"id": "FR-099", "type": "FUNCTIONAL", "title": "Invented id"},     # unknown claim
    ]}
    hist = ri.historic_ids([prev])
    out = [r["id"] for r in ri.assign_ids(new, prev, hist)["requirements"]]
    assert out[0] == "FR-005" and out[1] != "FR-005"
    assert len(set(out)) == 4 and all(i.startswith("FR-") for i in out)
    assert "FR-099" not in out and "NFR-002" not in out


def test_untrusted_versions_mark_ids_used_but_do_not_define_titles():
    good = {"requirements": [{"id": "FR-001", "title": "Original"}]}
    draft = {"requirements": [{"id": "FR-001", "title": "Hijack"}, {"id": "FR-009", "title": "z"}]}
    h = ri.historic_ids([good, draft], [True, False])
    assert h["FR-001"] == "original" and h["FR-009"] == ""
    assert ri.retired_ids([good, draft], {"requirements": []}, [True, False]) == h


def test_legacy_id_mapping():
    content = {"requirements": [{"id": "REQ-1", "type": "FUNCTIONAL"},
                                {"id": "REQ-2", "category": "SECURITY"},
                                {"id": "FR-001", "type": "FUNCTIONAL"}]}
    assert ri.legacy_id_mapping(content, {"FR-001": "x", "FR-002": "y"}) == {
        "REQ-1": "FR-003", "REQ-2": "NFR-001"}


def test_valid_v2_requirements_pass():
    r = validate_requirements(v2(), CTX)
    assert r.errors == []


def test_v2_functional_fields_are_enforced():
    c = v2()
    c["requirements"][0].update(actor="", preconditions="not a list")
    del c["requirements"][1]["expected_behavior"]
    assert {"REQ_ACTOR_MISSING", "REQ_PRECONDITIONS_INVALID", "REQ_BEHAVIOR_MISSING"} <= codes(
        validate_requirements(c, CTX))


def test_v2_nfr_rules():
    c = v2()
    nfr = c["requirements"][2]
    nfr.update(category="speedy")
    nfr.pop("measurable_criterion")
    nfr.pop("acceptance_criteria")
    assert {"REQ_NFR_CATEGORY_INVALID", "REQ_NFR_CRITERION_MISSING"} <= codes(
        validate_requirements(c, CTX))
    nfr.update(category="security", needs_clarification=True,
               clarification_note="no target given")
    r = validate_requirements(c, CTX)
    assert not r.errors and "REQ_NFR_NEEDS_CLARIFICATION" in codes(r, "warnings")
    nfr.pop("needs_clarification")
    nfr["measurable_criterion"] = "responds quickly"
    assert "REQ_NFR_NOT_MEASURABLE" in codes(validate_requirements(c, CTX), "warnings")
    nfr.pop("source_feature_ids")  # optional for NFRs in v2
    assert "REQ_SOURCE_MISSING" not in codes(validate_requirements(c, CTX))
    for cat in ("PERFORMANCE", "SECURITY", "RELIABILITY", "AVAILABILITY", "USABILITY",
                "MAINTAINABILITY", "SCALABILITY"):
        nfr["category"] = cat
        assert "REQ_NFR_CATEGORY_INVALID" not in codes(validate_requirements(c, CTX))


def test_legacy_content_is_validated_leniently():
    p = requirements_payload([F, F])
    for r in p["requirements"]:
        for k in ("actor", "expected_behavior", "category", "measurable_criterion"):
            r.pop(k, None)
    r = validate_requirements(p, CTX)
    assert r.errors == [] and "REQ_LEGACY_FORMAT" in codes(r, "warnings")
    p["requirements"][2]["source_feature_ids"] = []  # legacy NFRs still need a source
    assert "REQ_SOURCE_MISSING" in codes(validate_requirements(p, CTX))


def test_req_prefix_gets_a_migration_hint_and_retired_ids_are_checked():
    c = v2()
    c["requirements"][0]["id"] = "REQ-001"
    err = next(e for e in validate_requirements(c, CTX).errors if e["code"] == "REQ_ID_FORMAT")
    assert "normalize" in err["suggestion"]
    c = v2()
    ctx = copy.deepcopy(CTX)
    ctx.retired_ids = {"FR-001": "old title", "FR-002": "", "NFR-001": "response time"}
    r = validate_requirements(c, ctx)
    assert [e["code"] for e in r.errors].count("REQ_ID_REUSED") == 1  # FR-001 only
    assert "REQ_ID_RESTORED" in codes(r, "warnings")  # NFR-001 has the same title again
