"""Phase 1 workflows must keep working after the Phase 2 additions."""

import uuid

from tests.api.helpers import make_project_with_features


def test_health_and_project_crud(client):
    assert client.get("/health").json() == {"status": "ok"}
    r = client.post("/projects", json={"name": "P", "description": "D"})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert client.get(f"/projects/{pid}").json()["name"] == "P"
    assert [p["id"] for p in client.get("/projects").json()] == [pid]
    assert client.get(f"/projects/{uuid.uuid4()}").status_code == 404
    assert client.post("/projects", json={"name": "", "description": "D"}).status_code == 422


def test_extraction_edit_approve_reject_restore_versions(client, provider):
    pid, approved = make_project_with_features(client, provider, approve=1, settle=False)
    assert client.get(f"/projects/{pid}").json()["stage"] == "EXTRACTION_DONE"
    feats = client.get(f"/projects/{pid}/features").json()["features"]
    assert len(feats) == 3
    assert [f["status"] for f in feats].count("APPROVED") == 1
    pending = next(f for f in feats if f["status"] == "PENDING_REVIEW")
    r = client.patch(f"/features/{pending['id']}", json={"description": "new text"})
    assert r.status_code == 200 and r.json()["current_version"] == 2
    assert client.post(f"/features/{pending['id']}/reject").json()["status"] == "REJECTED"
    assert client.post(f"/features/{pending['id']}/restore").json()["status"] == "PENDING_REVIEW"
    versions = client.get(f"/features/{pending['id']}/versions").json()["versions"]
    assert [v["version_number"] for v in versions] == [1, 2, 3, 4]
    only = client.get(f"/projects/{pid}/features?status=APPROVED").json()["features"]
    assert [f["id"] for f in only] == approved
    assert client.post(f"/features/{approved[0]}/approve").status_code == 422


def test_context_and_listing_include_feature_counts(client, provider):
    pid, approved = make_project_with_features(client, provider, approve=2)
    ctx = client.get(f"/projects/{pid}/context").json()
    assert len(ctx["approved_features"]) == 2
    assert len(ctx["all_features_summary"]) == 3
    item = client.get("/projects").json()[0]
    assert item["feature_counts"]["APPROVED"] == 2
    assert client.get(f"/projects/{uuid.uuid4()}/context").status_code == 404


def test_extraction_missing_project_and_feature_404(client):
    assert client.post(f"/projects/{uuid.uuid4()}/extract").status_code == 404
    assert client.post(f"/features/{uuid.uuid4()}/approve").status_code == 404
