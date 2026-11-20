"""Auditor and external roles, and sharing individual deals with external members."""

import uuid

import pytest
from conftest import MF_PROPERTY, PASSWORD, Session, register

from app.services.demo_docs import offering_memorandum_pdf


def _join(client, owner, role):
    email = f"{role}-{uuid.uuid4().hex[:8]}@example.com"
    token = owner.post("/api/org/invitations", json={"email": email, "role": role}).json()["token"]
    acc = client.post("/api/invitations/accept", json={"token": token, "name": f"Team {role}", "password": PASSWORD})
    assert acc.status_code == 200, acc.text
    s = Session(client, acc.json()["access_token"], owner.org_id)
    s.user_id = s.get("/api/auth/me").json()["user"]["id"]
    return s


@pytest.fixture
def two_deals(owner):
    a = owner.post("/api/properties", json={**MF_PROPERTY, "name": "Shared Deal"}).json()
    b = owner.post("/api/properties", json={**MF_PROPERTY, "name": "Private Deal"}).json()
    doc = owner.post(f"/api/properties/{b['id']}/documents",
                     files={"file": ("om.pdf", offering_memorandum_pdf(), "application/pdf")}).json()
    return a, b, doc


def test_external_sees_only_shared_deals(client, owner, two_deals):
    shared, private, private_doc = two_deals
    ext = _join(client, owner, "external")
    assert ext.get("/api/properties").json() == []  # nothing shared yet

    assert owner.post(f"/api/properties/{shared['id']}/shares", json={"user_id": ext.user_id}).status_code == 201
    assert [d["name"] for d in ext.get("/api/properties").json()] == ["Shared Deal"]
    # Shared deal: the read-only deal pages work.
    sid = shared["id"]
    for path in (f"/api/properties/{sid}", f"/api/properties/{sid}/scenarios", f"/api/properties/{sid}/scenario-comparison",
                 f"/api/properties/{sid}/tornado", f"/api/properties/{sid}/documents", f"/api/properties/{sid}/financing",
                 f"/api/properties/{sid}/reports/one-pager", "/api/features"):
        assert ext.get(path).status_code == 200, path
    assert ext.post(f"/api/properties/{sid}/sensitivity", json={"row_path": "rent_growth", "col_path": "exit_cap_rate",
                                                                  "metric": "irr_unlevered"}).status_code == 200
    # Private deal and its document: indistinguishable from not existing.
    pid = private["id"]
    for path in (f"/api/properties/{pid}", f"/api/properties/{pid}/scenarios", f"/api/properties/{pid}/documents",
                 f"/api/documents/{private_doc['id']}", f"/api/documents/{private_doc['id']}/url",
                 f"/api/properties/{pid}/reports/one-pager"):
        assert ext.get(path).status_code == 404, path
    assert ext.get("/api/reports/summary-pack", params={"ids": f"{sid},{pid}"}).status_code == 404
    scen = owner.get(f"/api/properties/{pid}/scenarios").json()[0]["id"]
    assert ext.get(f"/api/scenarios/{scen}").status_code == 404


def test_external_cannot_edit_or_see_the_workspace(client, owner, two_deals):
    shared, _, _ = two_deals
    ext = _join(client, owner, "external")
    owner.post(f"/api/properties/{shared['id']}/shares", json={"user_id": ext.user_id})
    sid = shared["id"]
    for path in ("/api/dashboard", "/api/compare?ids=" + sid, "/api/org", "/api/org/members", "/api/org/audit",
                 "/api/org/onboarding", "/api/org/progress", "/api/billing", "/api/libraries", "/api/analyst/status",
                 f"/api/properties/{sid}/analyst/messages", "/api/org/usage", "/api/org/audit/export"):
        assert ext.get(path).status_code == 403, path
    assert ext.patch(f"/api/properties/{sid}", json={"status": "passed"}).status_code == 403
    assert ext.post(f"/api/properties/{sid}/documents",
                    files={"file": ("om.pdf", offering_memorandum_pdf(), "application/pdf")}).status_code == 403
    assert ext.post("/api/properties", json=MF_PROPERTY).status_code == 403
    assert ext.post(f"/api/properties/{sid}/analyst/chat", json={"message": "hi"}).status_code == 403
    assert ext.post("/api/underwriting/calculate", json={"assumptions": {}, "property_type": "multifamily"}).status_code == 403


def test_sharing_rules(client, owner, two_deals):
    shared, _, _ = two_deals
    sid = shared["id"]
    ext = _join(client, owner, "external")
    viewer = _join(client, owner, "viewer")
    analyst = _join(client, owner, "analyst")
    # Only external members can be given a share; only admins manage shares.
    assert owner.post(f"/api/properties/{sid}/shares", json={"user_id": viewer.user_id}).status_code == 422
    assert owner.post(f"/api/properties/{sid}/shares", json={"user_id": str(uuid.uuid4())}).status_code == 422
    assert analyst.post(f"/api/properties/{sid}/shares", json={"user_id": ext.user_id}).status_code == 403
    assert owner.post(f"/api/properties/{sid}/shares", json={"user_id": ext.user_id}).status_code == 201
    assert owner.post(f"/api/properties/{sid}/shares", json={"user_id": ext.user_id}).status_code == 201  # idempotent
    listing = owner.get(f"/api/properties/{sid}/shares").json()
    assert [(x["name"], x["shared"]) for x in listing] == [("Team external", True)]
    actions = [e["action"] for e in owner.get(f"/api/org/audit?property_id={sid}").json()]
    assert actions.count("deal.share") == 1
    # Unsharing removes access immediately.
    assert owner.delete(f"/api/properties/{sid}/shares/{ext.user_id}").status_code == 204
    assert ext.get(f"/api/properties/{sid}").status_code == 404
    # Removing the member removes their shares.
    owner.post(f"/api/properties/{sid}/shares", json={"user_id": ext.user_id})
    assert owner.delete(f"/api/org/members/{ext.user_id}").status_code == 204
    assert owner.get(f"/api/properties/{sid}/shares").json() == []


def test_other_workspaces_cannot_share_into_or_see_deals(client, owner, two_deals):
    shared, _, _ = two_deals
    other = register(client)
    assert other.get(f"/api/properties/{shared['id']}/shares").status_code == 404
    assert other.post(f"/api/properties/{shared['id']}/shares", json={"user_id": other.user_id}).status_code == 404


def test_auditor_reads_and_exports_but_cannot_edit(client, owner, two_deals):
    shared, private, _ = two_deals
    aud = _join(client, owner, "auditor")
    assert {d["name"] for d in aud.get("/api/properties").json()} == {"Shared Deal", "Private Deal"}
    assert aud.get("/api/dashboard").status_code == 200
    assert aud.get("/api/org/audit").status_code == 200
    assert aud.get("/api/org/audit/export").status_code == 200
    assert aud.get("/api/org/usage").status_code == 200
    assert aud.patch(f"/api/properties/{private['id']}", json={"status": "passed"}).status_code == 403
    assert aud.post("/api/properties", json=MF_PROPERTY).status_code == 403
    assert aud.get("/api/org/api-keys").status_code == 403
    assert aud.get("/api/org/webhooks").status_code == 403
    assert aud.post(f"/api/properties/{shared['id']}/shares", json={"user_id": aud.user_id}).status_code == 403
    # Viewers still can't export.
    assert _join(client, owner, "viewer").get("/api/org/audit/export").status_code == 403


def test_role_changes_and_invites(client, owner, two_deals):
    shared, _, _ = two_deals
    viewer = _join(client, owner, "viewer")
    assert owner.patch(f"/api/org/members/{viewer.user_id}", json={"role": "external"}).status_code == 200
    assert viewer.get("/api/properties").json() == []  # now external, nothing shared
    assert viewer.get("/api/dashboard").status_code == 403
    assert owner.patch(f"/api/org/members/{viewer.user_id}", json={"role": "auditor"}).status_code == 200
    assert len(viewer.get("/api/properties").json()) == 2
    assert owner.post("/api/org/invitations", json={"email": "x@example.com", "role": "warlord"}).status_code == 422
