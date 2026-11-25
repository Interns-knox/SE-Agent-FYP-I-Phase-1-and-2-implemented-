"""Unit tests for the deterministic validators (no database, no LLM)."""

import pytest

from app.domains.artifacts.validation.architecture import validate_architecture
from app.domains.artifacts.validation.requirements import validate_requirements
from app.domains.artifacts.validation.result import Report, ValidationContext
from app.domains.artifacts.validation.srs import validate_srs
from app.domains.artifacts.validation.uml import validate_plantuml, validate_uml
from tests.api.helpers import ARCHITECTURE, SRS_NARRATIVE, requirements_payload

F1, F2 = "f-1", "f-2"
CTX = ValidationContext(feature_status={F1: "APPROVED", F2: "APPROVED"})


def codes(report: Report, kind: str = "errors") -> set[str]:
    return {i["code"] for i in getattr(report, kind)}


def ctx_with(reqs=None, comps=None):
    c = ValidationContext(feature_status=dict(CTX.feature_status))
    if reqs is not None:
        c.requirements = {r["id"]: r for r in reqs}
    if comps is not None:
        c.components = {x["id"]: x for x in comps}
    return c


# ----------------------------- requirements --------------------------------


def test_valid_requirements_pass():
    r = validate_requirements(requirements_payload([F1, F2]), CTX)
    assert r.errors == []
    assert r.to_dict()["status"] in ("PASSED", "PASSED_WITH_WARNINGS")


@pytest.mark.parametrize("content,code", [
    ({}, "REQ_EMPTY"),
    ({"requirements": []}, "REQ_EMPTY"),
    ({"requirements": ["x"]}, "REQ_NOT_OBJECT"),
])
def test_requirements_structure_errors(content, code):
    assert code in codes(validate_requirements(content, CTX))


def test_requirement_field_errors():
    p = requirements_payload([F1, F2])
    reqs = p["requirements"]
    reqs[0]["id"] = "REQ-1"
    reqs[1]["title"] = " "
    reqs[2]["type"] = "FUNCTIONAL"  # NFR-001 declared functional
    reqs[2]["acceptance_criteria"] = [""]
    found = codes(validate_requirements(p, CTX))
    assert {"REQ_ID_FORMAT", "REQ_TITLE_MISSING", "REQ_ID_TYPE_MISMATCH",
            "REQ_ACCEPTANCE_MISSING"} <= found


def test_requirement_duplicate_id_message_names_indexes():
    p = requirements_payload([F1, F2])
    p["requirements"][1]["id"] = "FR-001"
    r = validate_requirements(p, CTX)
    dup = [e for e in r.errors if e["code"] == "REQ_ID_DUPLICATE"]
    assert dup and "FR-001" in dup[0]["message"] and dup[0]["suggestion"]


def test_requirement_warnings():
    p = requirements_payload([F1, F2])
    p["requirements"][0]["priority"] = "URGENT"
    p["requirements"][0]["description"] = "Registration is possible."
    p["requirements"] = p["requirements"][:2]  # no NFR
    w = codes(validate_requirements(p, CTX), "warnings")
    assert {"REQ_PRIORITY_INVALID", "REQ_NOT_NORMATIVE", "REQ_NO_NON_FUNCTIONAL"} <= w


def test_uncovered_approved_feature_warns():
    p = requirements_payload([F1, F1])
    assert "FEATURE_UNCOVERED" in codes(validate_requirements(p, CTX), "warnings")


# --------------------------------- SRS --------------------------------------


def _srs(extra_ids=()):
    import copy

    secs = copy.deepcopy(SRS_NARRATIVE["sections"]) + [
        {"id": "functional_requirements", "title": "FR", "body": "x"},
        {"id": "non_functional_requirements", "title": "NFR", "body": "x"},
    ]
    return {"sections": secs, "requirement_ids": ["FR-001", *extra_ids]}


def test_srs_valid():
    ctx = ctx_with(reqs=[{"id": "FR-001"}])
    assert validate_srs(_srs(), ctx).errors == []


def test_srs_errors():
    ctx = ctx_with(reqs=[{"id": "FR-001"}, {"id": "FR-002"}])
    c = _srs(["FR-009", "FR-009"])
    c["sections"] = [s for s in c["sections"] if s["id"] != "scope"]
    c["sections"][0]["body"] = ""
    c["sections"].append(dict(c["sections"][1]))
    found = codes(validate_srs(c, ctx))
    assert {"SRS_SECTION_MISSING", "SRS_SECTION_BODY_EMPTY", "SRS_SECTION_ID_DUPLICATE",
            "SRS_REQUIREMENT_UNKNOWN", "SRS_REQUIREMENT_REF_DUPLICATE",
            "SRS_REQUIREMENT_OMITTED"} <= found


# ----------------------------- architecture ---------------------------------


def test_architecture_valid():
    ctx = ctx_with(reqs=[{"id": "FR-001"}, {"id": "FR-002"}, {"id": "NFR-001"}])
    assert validate_architecture(ARCHITECTURE, ctx).errors == []


def test_architecture_errors():
    import copy

    a = copy.deepcopy(ARCHITECTURE)
    a["components"][1]["id"] = "CMP-001"
    a["components"][0]["depends_on"] = ["CMP-077", "CMP-001"]
    a["components"][1]["responsibility"] = ""
    found = codes(validate_architecture(a, CTX))
    assert {"ARCH_ID_DUPLICATE", "ARCH_DEPENDENCY_UNKNOWN", "ARCH_DEPENDENCY_SELF",
            "ARCH_RESPONSIBILITY_MISSING"} <= found


# --------------------------------- UML --------------------------------------

VALID_CLASS = [
    "@startuml\ntitle T\nskinparam x y\ninterface Repo {\n  +find(): Entity\n}\n"
    "abstract class Base\nclass Impl {\n  -x: int\n  +run()\n}\nBase <|-- Impl\n"
    "Impl ..|> Repo\nImpl \"1\" *-- \"many\" Base : has\nnote right of Impl : hi\n@enduml",
    "@startuml\npackage core {\n class A\n class B\n}\nA --> B\nA : +name\n@enduml",
    "@startuml\nclass \"Long Name\" as L\nclass M\nL -left-> M\n' comment\n@enduml",
]

VALID_SEQ = [
    "@startuml\nactor User\nparticipant \"Web App\" as W\nUser -> W : go\nW --> User : ok\n@enduml",
    "@startuml\nautonumber\nA -> B : x\nactivate B\nB ->> C : y\nloop 3 times\nC -> B\nend\n"
    "deactivate B\nnote over A, B : hi\n@enduml",
    "@startuml\nparticipant A\nparticipant B\nopt cond\nA -> B : x\nelse other\nA -> B : y\nend\n"
    "@enduml",
]


@pytest.mark.parametrize("src", VALID_CLASS)
def test_valid_class_diagrams(src):
    r = Report()
    validate_plantuml(src, "class", "p", r)
    assert r.errors == [], r.errors


@pytest.mark.parametrize("src", VALID_SEQ)
def test_valid_sequence_diagrams(src):
    r = Report()
    validate_plantuml(src, "sequence", "p", r)
    assert r.errors == [], r.errors


@pytest.mark.parametrize("src,kind,code", [
    ("", "class", "UML_SOURCE_MISSING"),
    ("class A\n@enduml", "class", "UML_START_MISSING"),
    ("@startuml\nclass A\n", "class", "UML_END_MISSING"),
    ("@startuml\nclass A {\n+x\n@enduml", "class", "UML_BRACE_UNBALANCED"),
    ("@startuml\n}\n@enduml", "class", "UML_BRACE_UNBALANCED"),
    ("@startuml\nclass A\nclass A\n@enduml", "class", "UML_CLASS_DUPLICATE"),
    ("@startuml\nnote: x\n@enduml", "class", "UML_NO_CLASSES"),
    ("@startuml\nactor A\nalt x\nA -> A : m\n@enduml", "sequence", "UML_BLOCK_UNBALANCED"),
    ("@startuml\nA -> B : m\nend\n@enduml", "sequence", "UML_BLOCK_UNBALANCED"),
    ("@startuml\nparticipant A\nparticipant B\n@enduml", "sequence", "UML_NO_MESSAGES"),
])
def test_invalid_plantuml(src, kind, code):
    r = Report()
    validate_plantuml(src, kind, "p", r)
    assert code in codes(r)


def test_undeclared_class_and_participant_are_warnings():
    r = Report()
    validate_plantuml("@startuml\nclass A\nA --> Ghost\n@enduml", "class", "p", r)
    assert "UML_CLASS_UNDECLARED" in codes(r, "warnings") and not r.errors
    r = Report()
    validate_plantuml("@startuml\nparticipant A\nA -> Ghost : m\n@enduml", "sequence", "p", r)
    assert "UML_PARTICIPANT_UNDECLARED" in codes(r, "warnings") and not r.errors


def test_uml_artifact_structure_and_references():
    ctx = ctx_with(reqs=[{"id": "FR-001"}], comps=[{"id": "CMP-001"}])
    d = {"id": "CLS-1", "title": "t", "plantuml": VALID_CLASS[1],
         "requirement_ids": ["FR-404"], "component_ids": ["CMP-404"]}
    r = validate_uml({"diagrams": [d, dict(d)]}, ctx, "class")
    assert {"UML_ID_DUPLICATE", "UML_REQUIREMENT_UNKNOWN", "UML_COMPONENT_UNKNOWN"} <= codes(r)
    assert "UML_EMPTY" in codes(validate_uml({"diagrams": []}, ctx, "class"))


def test_plantuml_cli_skipped_when_not_installed(monkeypatch):
    monkeypatch.setattr("app.config.settings.PLANTUML_COMMAND", "definitely-not-installed")
    r = Report()
    validate_plantuml(VALID_CLASS[0], "class", "p", r)
    assert any(c.startswith("plantuml_cli_skipped") for c in r.checks)
