"""Prompts must fit the model's context window; truncation would silently drop the instructions."""

import pytest

from app.domains.artifacts import generation as g
from app.domains.artifacts.models import ArtifactType as T
from tests.api.helpers import ARCHITECTURE, DOMAIN_MODEL, requirements_payload


def big_requirements(n=16):
    reqs = []
    for i in range(1, n + 1):
        fr = i <= 10
        kind = "FUNCTIONAL" if fr else "NON_FUNCTIONAL"
        r = {"id": f"{'FR' if fr else 'NFR'}-{i:03d}", "type": kind,
             "title": f"Requirement number {i} with a fairly long title",
             "description": "The system shall do something detailed and wordy. " * 8,
             "actor": "Member", "preconditions": ["precondition text " * 6] * 3,
             "expected_behavior": "behavior " * 40,
             "acceptance_criteria": ["criterion text that is quite long " * 5] * 4,
             "source_feature_ids": ["3f2c1b0a-1111-2222-3333-444455556666"]}
        if not fr:
            r["category"] = "SECURITY"
        reqs.append(r)
    return {"requirements": reqs, "schema_version": 2}


def big_domain_model(n=12):
    return {"model": {
        "entities": [{"id": f"ENT-{i:03d}", "name": f"Entity{i}", "kind": "ENTITY",
                      "description": "business meaning " * 12, "responsibilities": ["x " * 20] * 3,
                      "attributes": [{"name": f"attr{j}", "type": "String",
                                      "description": "attribute description " * 5}
                                     for j in range(1, 7)],
                      "requirement_ids": ["FR-001", "FR-002"]} for i in range(1, n + 1)],
        "relationships": [{"id": f"REL-{i:03d}", "from": f"Entity{i}", "to": f"Entity{i + 1}",
                           "label": "relates to", "from_cardinality": "1", "to_cardinality": "0..*",
                           "kind": "ASSOCIATION"} for i in range(1, n)],
        "business_rules": [{"id": "BR-001", "description": "rule " * 60, "entities": ["Entity1"]}],
    }, "diagrams": [{"id": "DM-001",
                     "plantuml": "@startuml\n" + "class Entity1\n" * 200 + "@enduml"}]}


FEATURES = [{"id": f"f{i}", "name": f"Feature {i}", "description": "feature description " * 5}
            for i in range(8)]
PROJECT = {"name": "Library", "description": "A library system. " * 20}


def prompt(kind, upstream, **kw):
    return g.build_prompt(kind, PROJECT, FEATURES, upstream, kw.get("feedback"), kw.get("previous"))


def test_condensed_views_keep_ids_and_names():
    req = g.condense("requirements", requirements_payload(["a", "b"]))
    assert [r["id"] for r in req] == ["FR-001", "FR-002", "NFR-001"]
    assert "acceptance_criteria" not in req[0] and req[2]["title"] == "Response time"
    arch = g.condense("architecture", ARCHITECTURE)
    assert [c["id"] for c in arch["components"]] == ["CMP-001", "CMP-002"]
    ents = [{**e, "id": f"ENT-{i}"} for i, e in enumerate(DOMAIN_MODEL["model"]["entities"], 1)]
    dm = g.condense("domain model", {**DOMAIN_MODEL, "model": {**DOMAIN_MODEL["model"],
                                                               "entities": ents}})
    assert {e["name"] for e in dm["entities"]} == {"AppUser", "Report", "ReportStatus"}
    assert dm["entities"][0]["attributes"] == ["email:String"]
    assert dm["relationships"][0]["cardinality"] == "1 to 0..*"
    assert "plantuml" not in str(dm)


def test_large_project_fits_the_context_window(monkeypatch):
    monkeypatch.setattr("app.config.settings.OLLAMA_NUM_CTX", 8192)
    limit = g.max_prompt_chars()
    assert limit == 13653
    upstream = {"requirements": big_requirements(), "architecture": ARCHITECTURE,
                "domain model": big_domain_model()}
    for kind in (T.UML_CLASS, T.UML_SEQUENCE):
        text = prompt(kind, upstream)
        assert len(text) <= limit, (kind, len(text))
        assert "ENT-012" in text and "FR-010" in text and "CMP-002" in text
    # the same content in the old pretty-printed full form would not have fit
    import json
    naive = sum(len(json.dumps(v, indent=1)) for v in upstream.values())
    assert naive > limit


def test_instruction_is_repeated_at_the_end():
    text = prompt(T.DOMAIN_MODEL, {"requirements": big_requirements(3)})
    assert text.startswith("You are a senior software engineer")
    assert text.rstrip().endswith("No explanation, no markdown.")
    assert "ONLY the single JSON object for the DOMAIN_MODEL artifact" in text


def test_requirements_prompt_keeps_full_feature_text_but_later_stages_only_names():
    assert "feature description" in prompt(T.REQUIREMENTS, {})
    later = prompt(T.SRS, {"requirements": big_requirements(3)})
    assert "feature description" not in later and '"name":"Feature 1"' in later


def test_oversized_prompt_fails_loudly(monkeypatch):
    monkeypatch.setattr("app.config.settings.OLLAMA_NUM_CTX", 1024)
    with pytest.raises(g.PromptTooLarge, match="OLLAMA_NUM_CTX=1024"):
        prompt(T.UML_CLASS, {"requirements": big_requirements(),
                             "domain model": big_domain_model()})


def test_no_limit_when_context_window_is_not_configured(monkeypatch):
    monkeypatch.setattr("app.config.settings.OLLAMA_NUM_CTX", None)
    assert g.max_prompt_chars() is None
    assert len(prompt(T.UML_CLASS, {"domain model": big_domain_model()})) > 5000
