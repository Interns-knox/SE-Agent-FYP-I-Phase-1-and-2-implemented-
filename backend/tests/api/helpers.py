"""Builders for valid artifact payloads used across API tests."""


def requirements_payload(feature_ids: list[str]) -> dict:
    """Valid requirements content (all v2 fields; also valid in the legacy format)."""
    return {
        "requirements": [
            {
                "id": "FR-001", "type": "FUNCTIONAL", "title": "Register account",
                "description": "The system shall let a visitor register an account.",
                "actor": "Visitor", "preconditions": ["The visitor has a valid email address."],
                "expected_behavior": "An account is created and a confirmation is shown.",
                "priority": "MUST",
                "acceptance_criteria": ["A new user can register with a valid email."],
                "source_feature_ids": [feature_ids[0]],
            },
            {
                "id": "FR-002", "type": "FUNCTIONAL", "title": "Create report",
                "description": "The system shall let a user create a report.",
                "actor": "Registered user",
                "expected_behavior": "The report is stored and appears in the report list.",
                "priority": "SHOULD",
                "acceptance_criteria": ["A report is stored and listed."],
                "source_feature_ids": [feature_ids[-1]],
            },
            {
                "id": "NFR-001", "type": "NON_FUNCTIONAL", "category": "PERFORMANCE",
                "title": "Response time",
                "description": "The system shall answer 95% of requests within 500 ms.",
                "measurable_criterion": "p95 latency under 500 ms in a load test.",
                "priority": "SHOULD",
                "acceptance_criteria": ["p95 latency under 500 ms in load test."],
                "source_feature_ids": [feature_ids[0]],
            },
        ]
    }


SRS_NARRATIVE = {
    "sections": [
        {"id": "purpose", "title": "Purpose", "body": "Describes the system."},
        {"id": "scope", "title": "Scope", "body": "Web application."},
        {"id": "overall_description", "title": "Overall Description", "body": "Users and data."},
        {"id": "assumptions_constraints", "title": "Assumptions", "body": "Runs on Linux."},
    ]
}

ARCHITECTURE = {
    "style": "layered client-server",
    "components": [
        {"id": "CMP-001", "name": "Web UI", "type": "frontend",
         "responsibility": "Render screens and call the API.", "technology": "React",
         "depends_on": ["CMP-002"], "requirement_ids": ["FR-001", "FR-002"]},
        {"id": "CMP-002", "name": "API Service", "type": "api",
         "responsibility": "Business logic and persistence.", "technology": "FastAPI",
         "depends_on": [], "requirement_ids": ["FR-001", "FR-002", "NFR-001"]},
    ],
}

DOMAIN_MODEL = {
    "model": {
        "entities": [
            {"name": "AppUser", "kind": "ACTOR", "description": "A registered person.",
             "attributes": [{"name": "email", "type": "String"}],
             "requirement_ids": ["FR-001"]},
            {"name": "Report", "kind": "ENTITY", "description": "A report written by a user.",
             "attributes": [{"name": "title", "type": "String"}],
             "requirement_ids": ["FR-002"]},
            {"name": "ReportStatus", "kind": "ENUMERATION", "description": "Lifecycle state.",
             "attributes": [{"name": "value", "type": "String"}],
             "requirement_ids": ["FR-002"]},
        ],
        "relationships": [
            {"from": "AppUser", "to": "Report", "label": "writes", "from_cardinality": "1",
             "to_cardinality": "0..*", "kind": "ASSOCIATION"},
            {"from": "Report", "to": "ReportStatus", "label": "has", "from_cardinality": "*",
             "to_cardinality": "1", "kind": "ASSOCIATION"},
        ],
        "business_rules": [
            {"description": "A report always has exactly one author.",
             "entities": ["Report", "AppUser"], "requirement_ids": ["FR-002"]},
        ],
    }
}

CLASS_DIAGRAMS = {
    "diagrams": [{
        "id": "CLS-001", "title": "Application classes",
        "plantuml": "@startuml\nclass AppUser {\n  +id: UUID\n  +email: String\n}\n"
                    "class Report {\n  +id: UUID\n}\nAppUser \"1\" --> \"*\" Report : owns\n"
                    "@enduml",
        "requirement_ids": ["FR-001"], "domain_entity_ids": ["ENT-001", "ENT-002"],
        "component_ids": ["CMP-002"],
    }]
}

SEQUENCE_DIAGRAMS = {
    "diagrams": [{
        "id": "SEQ-001", "title": "Register",
        "plantuml": "@startuml\nactor User\nparticipant API\ndatabase DB\n"
                    "User -> API : register\nalt valid\nAPI -> DB : insert\nelse invalid\n"
                    "API --> User : error\nend\n@enduml",
        "requirement_ids": ["FR-001"], "domain_entity_ids": ["ENT-001"],
        "component_ids": ["CMP-001", "CMP-002"],
    }]
}

def make_project_with_features(client, provider, approve: int = 2,
                               settle: bool = True) -> tuple[str, list[str]]:
    """Run the real Phase 1 flow: create project, extract, approve ``approve`` features.

    With ``settle`` (default) the remaining features are rejected, because the workflow does
    not allow requirements while any feature is still pending review."""
    provider.set("FEATURES", {"features": [
        {"name": "Accounts", "description": "Registration and login"},
        {"name": "Reports", "description": "Create and list reports"},
        {"name": "Export", "description": "Export reports"},
    ]})
    pid = client.post("/projects", json={"name": "Demo", "description": "A reporting app"}).json()[
        "id"
    ]
    assert client.post(f"/projects/{pid}/extract").status_code == 200
    features = client.get(f"/projects/{pid}/features").json()["features"]
    ids = [f["id"] for f in features]
    for fid in ids[:approve]:
        assert client.post(f"/features/{fid}/approve").status_code == 200
    if settle:
        for fid in ids[approve:]:
            assert client.post(f"/features/{fid}/reject").status_code == 200
    return pid, ids[:approve]


def generate(client, provider, pid: str, kind: str, payload: dict):
    provider.set(kind, payload)
    return client.post(f"/projects/{pid}/artifacts/generate", json={"type": kind})


def build_pipeline(client, provider, upto: str = "UML_SEQUENCE") -> tuple[str, dict[str, dict]]:
    """Generate and approve artifacts in workflow order; returns project id and artifacts."""
    pid, fids = make_project_with_features(client, provider)
    payloads = [
        ("REQUIREMENTS", requirements_payload(fids)),
        ("SRS", SRS_NARRATIVE),
        ("ARCHITECTURE", ARCHITECTURE),
        ("DOMAIN_MODEL", DOMAIN_MODEL),
        ("UML_CLASS", CLASS_DIAGRAMS),
        ("UML_SEQUENCE", SEQUENCE_DIAGRAMS),
    ]
    out: dict[str, dict] = {}
    for kind, payload in payloads:
        r = generate(client, provider, pid, kind, payload)
        assert r.status_code == 201, r.text
        a = r.json()
        ap = client.post(f"/artifacts/{a['id']}/approve")
        assert ap.status_code == 200, ap.text
        out[kind] = ap.json()
        if kind == upto:
            break
    return pid, out
