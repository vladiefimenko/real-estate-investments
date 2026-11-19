"""Read-only API keys, audit log export and workspace usage."""

import csv
import hashlib
import io
import json
import uuid

import pytest
from conftest import MF_PROPERTY, PASSWORD, Session, register


def _join(client, owner, role):
    email = f"{role}-{uuid.uuid4().hex[:8]}@example.com"
    token = owner.post("/api/org/invitations", json={"email": email, "role": role}).json()["token"]
    acc = client.post("/api/invitations/accept", json={"token": token, "name": f"Team {role}", "password": PASSWORD})
    return Session(client, acc.json()["access_token"], owner.org_id)


def _key(client, key):
    return Session(client, key)  # an API key is sent as the bearer token; no X-Org-Id needed


def test_api_key_lifecycle_and_read_only_scope(client, owner, prop):
    r = owner.post("/api/org/api-keys", json={"name": "Data warehouse"})
    assert r.status_code == 201, r.text
    created = r.json()
    plaintext = created["key"]
    assert plaintext.startswith("axk_") and created["prefix"] == plaintext[:12]
    listed = owner.get("/api/org/api-keys").json()
    assert "key" not in listed["keys"][0] and listed["keys"][0]["prefix"] == created["prefix"]
    assert listed["scope"]["access"] == "read-only"

    api = _key(client, plaintext)
    deals = api.get("/api/properties")
    assert deals.status_code == 200 and [d["id"] for d in deals.json()] == [prop["id"]]
    assert api.get(f"/api/properties/{prop['id']}/scenarios").status_code == 200
    assert api.get("/api/dashboard").status_code == 200
    # Read-only and limited to deal data.
    assert api.post("/api/properties", json=MF_PROPERTY).status_code == 403
    assert api.patch(f"/api/properties/{prop['id']}", json={"status": "passed"}).status_code == 403
    for path in ("/api/org/members", "/api/org/api-keys", "/api/org/audit", "/api/org/audit/export", "/api/org/usage",
                 "/api/libraries"):
        assert api.get(path).status_code == 403, path
    assert api.get("/api/auth/me").status_code == 401  # not a user session

    # last_used_at is recorded; revoking stops the key.
    assert owner.get("/api/org/api-keys").json()["keys"][0]["last_used_at"] is not None
    assert owner.delete(f"/api/org/api-keys/{created['id']}").status_code == 204
    assert api.get("/api/properties").status_code == 401
    actions = [e["action"] for e in owner.get("/api/org/audit").json()]
    assert "api_key.create" in actions and "api_key.revoke" in actions


def test_api_key_is_bound_to_its_workspace_and_creator(client, owner, prop):
    other = register(client)
    other.post("/api/properties", json={**MF_PROPERTY, "name": "Other Co deal"})
    key = other.post("/api/org/api-keys", json={"name": "theirs"}).json()["key"]
    api = _key(client, key)
    assert [d["name"] for d in api.get("/api/properties").json()] == ["Other Co deal"]
    assert api.get(f"/api/properties/{prop['id']}").status_code == 404
    # X-Org-Id cannot switch a key to another workspace.
    r = client.get("/api/properties", headers={"Authorization": f"Bearer {key}", "X-Org-Id": owner.org_id})
    assert [d["name"] for d in r.json()] == ["Other Co deal"]

    # A key stops working when its creator leaves the workspace.
    admin = _join(client, owner, "admin")
    admin_key = admin.post("/api/org/api-keys", json={"name": "admin's"}).json()["key"]
    assert _key(client, admin_key).get("/api/properties").status_code == 200
    member_id = next(m["user_id"] for m in owner.get("/api/org/members").json() if m["role"] == "admin")
    assert owner.delete(f"/api/org/members/{member_id}").status_code == 204
    assert _key(client, admin_key).get("/api/properties").status_code == 401


def test_api_key_permissions_expiry_and_validation(client, owner):
    analyst = _join(client, owner, "analyst")
    assert analyst.post("/api/org/api-keys", json={"name": "x"}).status_code == 403
    assert analyst.get("/api/org/api-keys").status_code == 403
    assert owner.post("/api/org/api-keys", json={"name": ""}).status_code == 422
    assert owner.post("/api/org/api-keys", json={"name": "x", "expires_in_days": 0}).status_code == 422
    assert _key(client, "axk_not-a-real-key").get("/api/properties").status_code == 401
    other = register(client)
    key_id = owner.post("/api/org/api-keys", json={"name": "mine"}).json()["id"]
    assert other.delete(f"/api/org/api-keys/{key_id}").status_code == 404

    from app.db import SessionLocal
    from app.models import ApiKey, utcnow
    from datetime import timedelta

    created = owner.post("/api/org/api-keys", json={"name": "short", "expires_in_days": 1}).json()
    with SessionLocal() as db:
        db.get(ApiKey, uuid.UUID(created["id"])).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert _key(client, created["key"]).get("/api/properties").status_code == 401


def test_api_key_rate_limit(client, owner, monkeypatch):
    from app import deps

    monkeypatch.setattr(deps, "API_KEY_RATE", (3, 60.0))
    api = _key(client, owner.post("/api/org/api-keys", json={"name": "burst"}).json()["key"])
    codes = [api.get("/api/properties").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


@pytest.mark.parametrize("fmt", ["csv", "json"])
def test_audit_export(owner, prop, fmt):
    owner.patch(f"/api/properties/{prop['id']}", json={"status": "ic"})
    r = owner.get("/api/org/audit/export", params={"format": fmt})
    assert r.status_code == 200
    assert hashlib.sha256(r.content).hexdigest() == r.headers["x-content-sha256"]
    if fmt == "csv":
        rows = list(csv.DictReader(io.StringIO(r.text)))
        assert {"property.create", "property.update"} <= {x["action"] for x in rows}
        assert all(x["user_email"] for x in rows) and json.loads(rows[0]["details"]) is not None
    else:
        body = r.json()
        assert body["count"] == len(body["events"]) and body["events"][0]["property_name"] == "Test Apartments"
    # The export itself is audited, with its checksum.
    last = owner.get("/api/org/audit").json()[0]
    assert last["action"] == "audit.export" and last["details"]["sha256"] == r.headers["x-content-sha256"]


def test_audit_export_filters_and_permissions(client, owner, prop):
    future = owner.get("/api/org/audit/export", params={"format": "json", "since": "2999-01-01"}).json()
    assert future["count"] == 0
    assert owner.get("/api/org/audit/export", params={"since": "not-a-date"}).status_code == 422
    assert owner.get("/api/org/audit/export", params={"format": "xml"}).status_code == 422
    assert _join(client, owner, "analyst").get("/api/org/audit/export").status_code == 403
    other = register(client)
    assert "Test Apartments" not in other.get("/api/org/audit/export").text


def test_usage(client, owner, prop):
    owner.get(f"/api/properties/{prop['id']}/reports/one-pager")
    u = owner.get("/api/org/usage", params={"days": 7}).json()
    assert u["days"] == 7 and len(u["events_per_day"]) == 7
    assert u["members"] == 1 and u["active_users"] == 1
    assert u["deals"] == {"active": 1, "created": 1}
    assert u["reports"].get("one_pager") == 1
    assert u["events_total"] == sum(d["events"] for d in u["events_per_day"])
    assert owner.get("/api/org/usage", params={"days": 9999}).json()["days"] == 365
    assert _join(client, owner, "viewer").get("/api/org/usage").status_code == 403
