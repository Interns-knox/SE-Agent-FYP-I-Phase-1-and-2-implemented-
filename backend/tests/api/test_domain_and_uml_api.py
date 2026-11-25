"""Domain model artifact, UML visual rendering, version diff."""

import copy
import os
import shutil
import stat
import uuid

import pytest

from app.domains.artifacts import domain_model as dm
from tests.api.helpers import (
    CLASS_DIAGRAMS,
    DOMAIN_MODEL,
    SEQUENCE_DIAGRAMS,
    build_pipeline,
    generate,
)

REAL = os.environ.get("PLANTUML_TEST_COMMAND") or shutil.which("plantuml")
needs_plantuml = pytest.mark.skipif(not REAL, reason="PlantUML is not installed")


@pytest.fixture()
def plantuml(monkeypatch):
    monkeypatch.setattr("app.config.settings.PLANTUML_COMMAND", REAL)
    return REAL


def to_arch(client, provider):
    return build_pipeline(client, provider, upto="ARCHITECTURE")


# ---------------------------------------------------------------------------
# Domain model artifact
# ---------------------------------------------------------------------------
def test_domain_model_generation_normalizes_ids_and_renders_diagram(client, provider):
    pid, _ = to_arch(client, provider)
    a = generate(client, provider, pid, "DOMAIN_MODEL", DOMAIN_MODEL).json()
    m = a["content"]["model"]
    assert [e["id"] for e in m["entities"]] == ["ENT-001", "ENT-002", "ENT-003"]
    assert [r["id"] for r in m["relationships"]] == ["REL-001", "REL-002"]
    assert m["business_rules"][0]["id"] == "BR-001"
    d = a["content"]["diagrams"][0]
    assert d["id"] == "DM-001" and d["requirement_ids"] == ["FR-001", "FR-002"]
    assert 'AppUser "1" -- "0..*" Report : writes' in d["plantuml"]
    assert "class ReportStatus <<enumeration>>" in d["plantuml"]
    assert d["plantuml"] == dm.render_plantuml(m)  # the picture is derived from the data
    assert a["status"] == "PENDING_REVIEW" and a["validation_result"]["errors"] == []
    assert a["source_refs"]["artifacts"][0]["type"] == "REQUIREMENTS"
    assert [s["type"] for s in a["source_refs"]["artifacts"]] == ["REQUIREMENTS", "ARCHITECTURE"]


def test_domain_model_ids_are_stable_on_regeneration(client, provider):
    pid, _ = to_arch(client, provider)
    a = generate(client, provider, pid, "DOMAIN_MODEL", DOMAIN_MODEL).json()
    new = copy.deepcopy(DOMAIN_MODEL)
    new["model"]["entities"].reverse()  # model returns a different order
    new["model"]["entities"].append({"name": "Attachment", "kind": "ENTITY",
                                     "description": "A file on a report.",
                                     "attributes": [{"name": "name", "type": "String"}],
                                     "requirement_ids": ["FR-002"]})
    new["model"]["relationships"].append({"from": "Report", "to": "Attachment", "label": "has",
                                          "from_cardinality": "1", "to_cardinality": "0..*",
                                          "kind": "COMPOSITION"})
    provider.set("DOMAIN_MODEL", new)
    b = client.post(f"/artifacts/{a['id']}/regenerate", json={}).json()
    by_name = {e["name"]: e["id"] for e in b["content"]["model"]["entities"]}
    assert by_name["AppUser"] == "ENT-001" and by_name["Report"] == "ENT-002"
    assert by_name["Attachment"] == "ENT-004"
    assert b["current_version"] == 2 and "Attachment" in b["content"]["diagrams"][0]["plantuml"]


def test_domain_model_validation_errors(client, provider):
    pid, _ = to_arch(client, provider)
    bad = copy.deepcopy(DOMAIN_MODEL)
    m = bad["model"]
    m["entities"][1]["name"] = "AppUser"  # duplicate
    m["entities"][2]["name"] = "Bad Name"
    m["entities"][2]["description"] = ""
    m["relationships"][0]["to"] = "Ghost"
    m["relationships"][1]["to_cardinality"] = "lots"
    m["relationships"][1]["kind"] = "FRIENDSHIP"
    m["business_rules"][0]["entities"] = ["Nope"]
    m["entities"][0]["requirement_ids"] = ["FR-404"]
    a = generate(client, provider, pid, "DOMAIN_MODEL", bad).json()
    codes = {e["code"] for e in a["validation_result"]["errors"]}
    assert {"DM_ENTITY_NAME_DUPLICATE", "DM_ENTITY_NAME_INVALID", "DM_ENTITY_DESCRIPTION_MISSING",
            "DM_REL_ENTITY_UNKNOWN", "DM_REL_CARDINALITY_INVALID", "DM_REL_KIND_INVALID",
            "DM_RULE_ENTITY_UNKNOWN", "DM_REQUIREMENT_UNKNOWN"} <= codes
    assert client.post(f"/artifacts/{a['id']}/approve").status_code == 422


def test_domain_model_warnings_for_isolated_and_uncovered(client, provider):
    pid, _ = to_arch(client, provider)
    m = copy.deepcopy(DOMAIN_MODEL)
    m["model"]["entities"].append({"name": "Orphan", "kind": "ENTITY", "description": "x",
                                   "attributes": [{"name": "a", "type": "String"}]})
    m["model"]["entities"][0]["requirement_ids"] = []
    a = generate(client, provider, pid, "DOMAIN_MODEL", m).json()
    w = {x["code"] for x in a["validation_result"]["warnings"]}
    assert {"DM_ENTITY_ISOLATED", "DM_ENTITY_UNTRACED", "REQ_NOT_IN_DOMAIN_MODEL"} <= w
    assert not a["validation_result"]["errors"]


def test_editing_the_model_rebuilds_the_diagram_but_source_edits_are_kept(client, provider):
    pid, _ = to_arch(client, provider)
    a = generate(client, provider, pid, "DOMAIN_MODEL", DOMAIN_MODEL).json()
    c = copy.deepcopy(a["content"])
    c["model"]["entities"][1]["name"] = "Document"
    c["model"]["relationships"][0]["to"] = "Document"
    c["model"]["relationships"][1]["from"] = "Document"
    c["model"]["business_rules"][0]["entities"] = ["Document", "AppUser"]
    b = client.put(f"/artifacts/{a['id']}", json={"content": c}).json()
    assert "class Document" in b["content"]["diagrams"][0]["plantuml"]
    assert "class Report <<" not in b["content"]["diagrams"][0]["plantuml"]
    assert b["validation_result"]["errors"] == []
    # editing only the PlantUML source keeps the user's source and warns about the mismatch
    s = copy.deepcopy(b["content"])
    s["diagrams"][0]["plantuml"] = s["diagrams"][0]["plantuml"].replace(
        "@enduml", "note right of Document : custom\n@enduml")
    r = client.put(f"/artifacts/{a['id']}", json={"content": s}).json()
    assert "custom" in r["content"]["diagrams"][0]["plantuml"]
    assert "DM_DIAGRAM_CUSTOMIZED" in {w["code"] for w in r["validation_result"]["warnings"]}
    assert r["validation_result"]["errors"] == []


def test_domain_model_trace_links(client, provider):
    pid, _ = build_pipeline(client, provider)
    links = client.get(f"/projects/{pid}/dependencies").json()["links"]
    triples = {(k["source_kind"], k["relation"], k["target_kind"]) for k in links}
    assert ("DOMAIN_ENTITY", "MODELS", "REQUIREMENT") in triples
    assert ("UML_DIAGRAM", "DESCRIBES", "DOMAIN_ENTITY") in triples
    assert any(k["source_ref"] == "ENT-001" and k["target_ref"] == "FR-001" for k in links)


def test_unknown_domain_entity_reference_in_class_diagram(client, provider):
    pid, _ = build_pipeline(client, provider, upto="DOMAIN_MODEL")
    bad = copy.deepcopy(CLASS_DIAGRAMS)
    bad["diagrams"][0]["domain_entity_ids"] = ["ENT-001", "ENT-099"]
    a = generate(client, provider, pid, "UML_CLASS", bad).json()
    assert any(e["code"] == "UML_DOMAIN_ENTITY_UNKNOWN" for e in a["validation_result"]["errors"])


def test_class_diagram_warns_about_missing_domain_entities_and_isolated_classes(client, provider):
    pid, _ = build_pipeline(client, provider, upto="DOMAIN_MODEL")
    c = copy.deepcopy(CLASS_DIAGRAMS)
    c["diagrams"][0]["plantuml"] = ("@startuml\nclass AppUser\nclass Helper\nclass Other\n"
                                    "AppUser --> Other\n@enduml")
    a = generate(client, provider, pid, "UML_CLASS", c).json()
    w = {x["code"]: x["message"] for x in a["validation_result"]["warnings"]}
    assert "Report" in w["UML_DOMAIN_ENTITY_MISSING"]
    assert "Helper" in w["UML_CLASS_ISOLATED"]


def test_sequence_and_class_prompts_include_the_approved_domain_model(client, provider):
    pid, _ = build_pipeline(client, provider, upto="DOMAIN_MODEL")
    generate(client, provider, pid, "UML_CLASS", CLASS_DIAGRAMS)
    assert '"AppUser"' in provider.prompts[-1] and "ENT-001" in provider.prompts[-1]
    generate(client, provider, pid, "UML_SEQUENCE", SEQUENCE_DIAGRAMS)
    assert "ENT-001" in provider.prompts[-1]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
@needs_plantuml
def test_render_endpoint_returns_svg_for_valid_source(client, plantuml):
    src = dm.render_plantuml(DOMAIN_MODEL["model"] | {"entities": [
        {**e, "id": f"ENT-{i}"} for i, e in enumerate(DOMAIN_MODEL["model"]["entities"])]})
    r = client.post("/uml/render", json={"source": src})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["svg"].startswith("<svg") and body["error"] is None
    assert "AppUser" in body["svg"] and body["renderer_available"] is True
    again = client.post("/uml/render", json={"source": src}).json()
    assert again["cached"] is True and again["svg"] == body["svg"]


@needs_plantuml
def test_render_reports_syntax_errors_without_an_image(client, plantuml):
    r = client.post("/uml/render", json={"source": "@startuml\nclass A {\n@enduml"}).json()
    assert r["ok"] is False and r["svg"] is None and r["renderer_available"] is True
    assert r["error"] and r["line"] is not None


@needs_plantuml
def test_render_sequence_diagram(client, plantuml):
    src = SEQUENCE_DIAGRAMS["diagrams"][0]["plantuml"]
    r = client.post("/uml/render", json={"source": src}).json()
    assert r["ok"] is True and "<svg" in r["svg"]


@pytest.mark.parametrize("src,needle", [
    ("", "empty"),
    ("class A", "@startuml"),
    ("@startuml\n!include /etc/passwd\n@enduml", "not allowed"),
    ("@startuml\n!includeurl http://example.com/x.puml\n@enduml", "not allowed"),
    ("@startuml\nnote: %getenv('HOME')\n@enduml", "not allowed"),
])
def test_render_rejects_unsafe_or_malformed_source(client, plantuml_stub, src, needle):
    r = client.post("/uml/render", json={"source": src}).json()
    assert r["ok"] is False and needle in r["error"]
    assert not plantuml_stub.calls  # nothing reached the renderer


def test_render_rejects_oversized_source_and_invalid_body(client, plantuml_stub):
    r = client.post("/uml/render", json={"source": "@startuml\n" + "x" * 200_000 + "\n@enduml"})
    assert r.status_code == 422  # schema limit
    assert client.post("/uml/render", json={}).status_code == 422
    assert client.post("/uml/render", json={"source": 5}).status_code == 422


def test_renderer_unavailable_is_reported_and_source_is_untouched(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.PLANTUML_COMMAND", "no-such-plantuml")
    s = client.get("/uml/renderer").json()
    assert s["available"] is False and "not installed" in s["reason"]
    r = client.post("/uml/render", json={"source": "@startuml\nclass A\n@enduml"}).json()
    assert r["ok"] is False and r["renderer_available"] is False and "not installed" in r["error"]


class Stub:
    """Handle on the fake plantuml executable's call log."""

    def __init__(self, log):
        self.log = log

    @property
    def calls(self) -> bool:
        return self.log.exists() and bool(self.log.read_text().strip())


@pytest.fixture()
def plantuml_stub(tmp_path, monkeypatch):
    """A fake plantuml executable that records calls and fails on request."""
    log = tmp_path / "calls.log"
    exe = tmp_path / "plantuml"
    exe.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> {log}\n'
        'src=$(cat)\n'
        'case "$src" in *BOOM*) echo ERROR; echo 2; echo "Syntax boom"; exit 0;; esac\n'
        'case "$src" in *SLEEP*) sleep 5;; esac\n'
        'case "$src" in *CRASH*) echo "java exploded" >&2; exit 3;; esac\n'
        'if [ "$1" = "-syntax" ]; then echo CLASS; echo "(1 entities)"; exit 0; fi\n'
        'echo "<?xml version=\\"1.0\\"?><svg xmlns=\\"http://www.w3.org/2000/svg\\">'
        '<script>alert(1)</script><text>ok</text></svg>"\n'
    )
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr("app.config.settings.PLANTUML_COMMAND", str(exe))
    from app.domains.artifacts import uml_render
    uml_render._CACHE.clear()
    stub = Stub(log)
    return stub


def test_render_failure_modes_with_stub(client, plantuml_stub, monkeypatch):
    ok = client.post("/uml/render", json={"source": "@startuml\nclass A\n@enduml"}).json()
    assert ok["ok"] is True and "<script" not in ok["svg"] and ok["svg"].startswith("<svg")
    bad = client.post("/uml/render", json={"source": "@startuml\nBOOM\n@enduml"}).json()
    assert bad["ok"] is False and bad["error"] == "Syntax boom" and bad["line"] == 2
    crash = client.post("/uml/render", json={"source": "@startuml\nCRASH\n@enduml"}).json()
    assert crash["ok"] is False and "java exploded" in crash["error"]
    monkeypatch.setattr("app.domains.artifacts.uml_render.TIMEOUT_SECONDS", 1)
    slow = client.post("/uml/render", json={"source": "@startuml\nSLEEP\n@enduml"}).json()
    assert slow["ok"] is False and "exceeded" in slow["error"]
    calls = plantuml_stub.log.read_text()
    assert "-syntax" in calls and "-tsvg -pipe" in calls


def test_failed_render_is_not_cached(client, plantuml_stub):
    bad = {"source": "@startuml\nBOOM\n@enduml"}
    assert client.post("/uml/render", json=bad).json()["cached"] is False
    again = client.post("/uml/render", json=bad).json()
    assert again["ok"] is False
    # an error result may be cached, but never as an image
    assert again["svg"] is None


@needs_plantuml
def test_validation_uses_the_real_plantuml_syntax_checker(client, provider, plantuml):
    pid, _ = build_pipeline(client, provider, upto="DOMAIN_MODEL")
    bad = copy.deepcopy(CLASS_DIAGRAMS)
    bad["diagrams"][0]["plantuml"] = ("@startuml\nclass AppUser\nclass Report\n"
                                      "AppUser --> Report : \n@enduml\n@startuml\n")
    a = generate(client, provider, pid, "UML_CLASS", bad).json()
    checks = a["validation_result"]["checks_run"]
    assert any(c.startswith("plantuml_cli:") for c in checks)
    bad2 = copy.deepcopy(CLASS_DIAGRAMS)
    bad2["diagrams"][0]["plantuml"] = "@startuml\nclass AppUser {\n@enduml"
    a2 = client.put(f"/artifacts/{a['id']}", json={"content": bad2}).json()
    codes = {e["code"] for e in a2["validation_result"]["errors"]}
    assert "UML_BRACE_UNBALANCED" in codes and "UML_SYNTAX_CLI" in codes


# ---------------------------------------------------------------------------
# Versions and history
# ---------------------------------------------------------------------------
def test_regenerate_keeps_previous_versions_and_diff_compares_them(client, provider):
    pid, _ = to_arch(client, provider)
    a = generate(client, provider, pid, "DOMAIN_MODEL", DOMAIN_MODEL).json()
    c = copy.deepcopy(a["content"])
    c["model"]["entities"][0]["description"] = "A changed description."
    client.put(f"/artifacts/{a['id']}", json={"content": c, "change_note": "wording"})
    provider.set("DOMAIN_MODEL", DOMAIN_MODEL)
    client.post(f"/artifacts/{a['id']}/regenerate", json={"feedback": "again"})
    v = client.get(f"/artifacts/{a['id']}/versions").json()["versions"]
    assert [(x["version_number"], x["change_type"]) for x in v] == [
        (1, "GENERATED"), (2, "EDITED"), (3, "REGENERATED")]
    assert "changed description" in str(v[1]["content_snapshot"])
    d = client.get(f"/artifacts/{a['id']}/diff?from_version=1&to_version=2").json()
    assert d["identical"] is False and d["additions"] >= 1 and d["deletions"] >= 1
    assert "+" in d["diff"] and "changed description" in d["diff"]
    default = client.get(f"/artifacts/{a['id']}/diff").json()  # previous -> current
    assert (default["from_version"], default["to_version"]) == (2, 3)
    same = client.get(f"/artifacts/{a['id']}/diff?from_version=1&to_version=1").json()
    assert same["identical"] is True and same["diff"] == ""
    assert client.get(f"/artifacts/{a['id']}/diff?from_version=0").status_code == 422
    assert client.get(f"/artifacts/{a['id']}/diff?from_version=9").status_code == 404
    assert client.get(f"/artifacts/{uuid.uuid4()}/diff").status_code == 404


def test_new_diagram_artifact_is_not_auto_approved_and_approval_is_recorded(client, provider):
    pid, arts = build_pipeline(client, provider, upto="DOMAIN_MODEL")
    c = generate(client, provider, pid, "UML_CLASS", CLASS_DIAGRAMS).json()
    assert c["status"] == "PENDING_REVIEW"
    assert client.post(f"/artifacts/{c['id']}/reject", json={"reason": "wrong"}).status_code == 200
    d = client.get(f"/artifacts/{c['id']}/decisions").json()["decisions"]
    assert d[0]["decision"] == "REJECTED" and d[0]["reason"] == "wrong"


def test_prompt_that_cannot_fit_the_context_window_is_a_clear_422_and_stores_nothing(
        client, provider, monkeypatch):
    pid, _ = to_arch(client, provider)
    monkeypatch.setattr("app.config.settings.OLLAMA_NUM_CTX", 300)
    provider.set("DOMAIN_MODEL", DOMAIN_MODEL)
    r = client.post(f"/projects/{pid}/artifacts/generate", json={"type": "DOMAIN_MODEL"})
    assert r.status_code == 422 and "OLLAMA_NUM_CTX=300" in r.json()["detail"]
    assert client.get(f"/projects/{pid}/artifacts?type=DOMAIN_MODEL").json()["artifacts"] == []
