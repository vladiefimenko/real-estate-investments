"""Getting Started checklist progress (/api/org/onboarding)."""

from app.services.demo_docs import offering_memorandum_pdf
from conftest import MF_PROPERTY, register

STEPS = {"deal_created", "document_uploaded", "field_verified", "scenario_explored", "report_generated"}


def test_demo_data_does_not_count_as_progress(client):
    s = register(client, seed=True, org="Fresh Demo Co")
    body = s.get("/api/org/onboarding").json()
    assert set(body["steps"]) == STEPS
    assert body == {"steps": dict.fromkeys(STEPS, False), "completed": 0, "total": 5}


def test_steps_complete_as_the_user_works(owner):
    assert owner.get("/api/org/onboarding").json()["completed"] == 0

    pid = owner.post("/api/properties", json=MF_PROPERTY).json()["id"]
    r = owner.post(f"/api/properties/{pid}/documents",
                   files={"file": ("om.pdf", offering_memorandum_pdf(), "application/pdf")}, data={"doc_type": "om"})
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    # TestClient runs the extraction background task before returning.
    field = owner.get(f"/api/documents/{doc_id}/extractions").json()[0]
    assert owner.patch(f"/api/extractions/{field['id']}", json={"action": "accept"}).status_code == 200

    steps = owner.get("/api/org/onboarding").json()["steps"]
    assert steps == {"deal_created": True, "document_uploaded": True, "field_verified": True,
                     "scenario_explored": False, "report_generated": False}


def test_onboarding_is_scoped_to_the_workspace(client, owner, prop):
    other = register(client)
    assert owner.get("/api/org/onboarding").json()["steps"]["deal_created"] is True
    assert other.get("/api/org/onboarding").json()["steps"]["deal_created"] is False


def test_progress_counts_only_my_recent_work(client):
    s = register(client, seed=True, org="Progress Co")
    assert s.get("/api/org/progress").json() == {
        "days": 7, "counts": {"deals_created": 0, "documents_uploaded": 0, "fields_verified": 0,
                              "scenarios_explored": 0, "reports_generated": 0, "analyst_questions": 0}}
    pid = s.post("/api/properties", json=MF_PROPERTY).json()["id"]
    s.post(f"/api/properties/{pid}/scenarios/defaults")
    s.get(f"/api/properties/{pid}/reports/one-pager")
    counts = s.get("/api/org/progress").json()["counts"]
    assert counts["deals_created"] == 1 and counts["reports_generated"] == 1
    assert counts["scenarios_explored"] == 1  # 'Create default cases'
    # Another member's view only counts their own work.
    assert register(client).get("/api/org/progress?days=500").json()["days"] == 90
