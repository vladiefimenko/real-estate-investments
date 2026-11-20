"""Stage requirements (gates) and Investment Committee voting and decisions."""

import io
import uuid

from conftest import MF_PROPERTY, PASSWORD, Session, register
from pypdf import PdfReader

from app.services.demo_docs import offering_memorandum_pdf


def _join(client, owner, role):
    email = f"{role}-{uuid.uuid4().hex[:8]}@example.com"
    token = owner.post("/api/org/invitations", json={"email": email, "role": role}).json()["token"]
    acc = client.post("/api/invitations/accept", json={"token": token, "name": f"Team {role}", "password": PASSWORD})
    s = Session(client, acc.json()["access_token"], owner.org_id)
    s.user_id = s.get("/api/auth/me").json()["user"]["id"]
    return s


def _pdf_text(content):
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages)


def test_no_requirements_by_default(owner, prop):
    assert owner.get("/api/org/workflow").json()["requirements"] == {"underwriting": [], "ic": [], "closed": []}
    assert owner.patch(f"/api/properties/{prop['id']}", json={"status": "ic"}).status_code == 200


def test_requirements_block_until_met_and_admins_can_override(client, owner, prop):
    pid = prop["id"]
    r = owner.put("/api/org/workflow", json={"requirements": {"ic": ["verified_data", "ic_memo"]}})
    assert r.status_code == 200 and r.json()["requirements"]["ic"] == ["ic_memo", "verified_data"]
    blocked = owner.patch(f"/api/properties/{pid}", json={"status": "ic"})
    assert blocked.status_code == 422
    assert len(blocked.json()["detail"]["unmet"]) == 2 and blocked.json()["detail"]["can_override"] is True
    assert owner.get(f"/api/properties/{pid}").json()["status"] == "sourcing"
    readiness = owner.get(f"/api/properties/{pid}/readiness").json()
    assert len(readiness["ic"]) == 2 and readiness["underwriting"] == []

    # Analysts can't override; admins can, and the override is audited.
    analyst = _join(client, owner, "analyst")
    assert analyst.patch(f"/api/properties/{pid}", json={"status": "ic", "override_requirements": True}).status_code == 422
    assert owner.patch(f"/api/properties/{pid}", json={"status": "ic", "override_requirements": True}).status_code == 200
    last = owner.get(f"/api/org/audit?property_id={pid}").json()[0]
    assert last["action"] == "property.update" and len(last["details"]["overridden_requirements"]) == 2


def test_requirements_are_met_by_real_work(owner, prop):
    pid = prop["id"]
    owner.put("/api/org/workflow", json={"requirements": {"ic": ["verified_data", "ic_memo"]}})
    doc = owner.post(f"/api/properties/{pid}/documents",
                     files={"file": ("om.pdf", offering_memorandum_pdf(), "application/pdf")}).json()
    field = owner.get(f"/api/documents/{doc['id']}/extractions").json()[0]
    owner.patch(f"/api/extractions/{field['id']}", json={"action": "accept"})
    assert owner.get(f"/api/properties/{pid}/readiness").json()["ic"] == ["An IC memo has been generated"]
    owner.get(f"/api/properties/{pid}/reports/ic-memo")
    assert owner.patch(f"/api/properties/{pid}", json={"status": "ic"}).status_code == 200


def test_bulk_moves_are_all_or_nothing_with_gates(owner):
    ready = owner.post("/api/properties", json={**MF_PROPERTY, "name": "Ready"}).json()["id"]
    not_ready = owner.post("/api/properties", json={**MF_PROPERTY, "name": "Not ready"}).json()["id"]
    owner.put("/api/org/workflow", json={"requirements": {"ic": ["ic_memo"]}})
    owner.get(f"/api/properties/{ready}/reports/ic-memo")
    r = owner.post("/api/properties/bulk-status", json={"ids": [ready, not_ready], "status": "ic"})
    assert r.status_code == 422 and list(r.json()["detail"]["blocked"]) == ["Not ready"]
    assert owner.get(f"/api/properties/{ready}").json()["status"] == "sourcing"  # nothing moved
    r = owner.post("/api/properties/bulk-status", json={"ids": [ready, not_ready], "status": "ic",
                                                         "override_requirements": True})
    assert r.status_code == 200 and len(r.json()["updated"]) == 2


def test_workflow_validation_and_permissions(client, owner):
    assert owner.put("/api/org/workflow", json={"requirements": {"passed": ["loan"]}}).status_code == 422
    assert owner.put("/api/org/workflow", json={"requirements": {"underwriting": ["ic_approved"]}}).status_code == 422
    assert owner.put("/api/org/workflow", json={"requirements": {"ic": ["telepathy"]}}).status_code == 422
    assert _join(client, owner, "analyst").put("/api/org/workflow", json={"requirements": {}}).status_code == 403


def test_ic_voting_decision_and_rounds(client, owner, prop):
    pid = prop["id"]
    analyst = _join(client, owner, "analyst")
    viewer = _join(client, owner, "viewer")
    assert analyst.put(f"/api/properties/{pid}/ic/vote", json={"vote": "approve"}).status_code == 409  # not at IC
    owner.patch(f"/api/properties/{pid}", json={"status": "ic"})
    assert analyst.put(f"/api/properties/{pid}/ic/vote", json={"vote": "approve", "comment": "Solid DSCR"}).status_code == 200
    analyst.put(f"/api/properties/{pid}/ic/vote", json={"vote": "conditional", "comment": "Need a lender quote"})  # change
    owner.put(f"/api/properties/{pid}/ic/vote", json={"vote": "approve"})
    assert viewer.put(f"/api/properties/{pid}/ic/vote", json={"vote": "approve"}).status_code == 403
    assert owner.put(f"/api/properties/{pid}/ic/vote", json={"vote": "maybe"}).status_code == 422
    ic = viewer.get(f"/api/properties/{pid}/ic").json()
    assert ic["round"] == 1 and ic["open"] and ic["tally"]["approve"] == 1 and ic["tally"]["conditional"] == 1
    assert len(ic["votes"]) == 2 and ic["my_vote"] is None

    assert analyst.post(f"/api/properties/{pid}/ic/decision", json={"decision": "approved"}).status_code == 403
    d = owner.post(f"/api/properties/{pid}/ic/decision", json={"decision": "conditional", "notes": "Subject to quote"})
    assert d.status_code == 200 and d.json()["decision"]["decision"] == "conditional" and d.json()["open"] is False
    assert owner.post(f"/api/properties/{pid}/ic/decision", json={"decision": "approved"}).status_code == 409
    assert analyst.put(f"/api/properties/{pid}/ic/vote", json={"vote": "decline"}).status_code == 409  # closed

    # The memo includes the committee record for members.
    memo = _pdf_text(owner.get(f"/api/properties/{pid}/reports/ic-memo").content)
    assert "Investment Committee (round 1)" in memo and "Conditional" in memo and "Need a lender quote" in memo

    # Moving back to IC starts round 2 with no votes.
    owner.patch(f"/api/properties/{pid}", json={"status": "underwriting"})
    owner.patch(f"/api/properties/{pid}", json={"status": "ic"})
    ic2 = owner.get(f"/api/properties/{pid}/ic").json()
    assert ic2["round"] == 2 and ic2["votes"] == [] and ic2["decision"] is None and ic2["open"]


def test_closing_can_require_ic_approval_and_declines_can_pass(owner):
    pid = owner.post("/api/properties", json=MF_PROPERTY).json()["id"]
    owner.put("/api/org/workflow", json={"requirements": {"closed": ["ic_approved"]}})
    owner.patch(f"/api/properties/{pid}", json={"status": "ic"})
    assert owner.patch(f"/api/properties/{pid}", json={"status": "closed"}).status_code == 422
    owner.post(f"/api/properties/{pid}/ic/decision", json={"decision": "approved"})
    assert owner.patch(f"/api/properties/{pid}", json={"status": "closed"}).status_code == 200

    other = owner.post("/api/properties", json=MF_PROPERTY).json()["id"]
    owner.patch(f"/api/properties/{other}", json={"status": "ic"})
    r = owner.post(f"/api/properties/{other}/ic/decision", json={"decision": "declined", "move_to_passed": True})
    assert r.json()["stage"] == "passed"


def test_external_members_never_see_ic_deliberations(client, owner, prop):
    pid = prop["id"]
    owner.patch(f"/api/properties/{pid}", json={"status": "ic"})
    owner.put(f"/api/properties/{pid}/ic/vote", json={"vote": "decline", "comment": "Sponsor risk is too high"})
    ext = _join(client, owner, "external")
    owner.post(f"/api/properties/{pid}/shares", json={"user_id": ext.user_id})
    assert ext.get(f"/api/properties/{pid}/ic").status_code == 403
    memo = _pdf_text(ext.get(f"/api/properties/{pid}/reports/ic-memo").content)
    assert "Sponsor risk" not in memo and "Investment Committee (round" not in memo


def test_ic_is_tenant_scoped(client, owner, prop):
    assert register(client).get(f"/api/properties/{prop['id']}/ic").status_code == 404
