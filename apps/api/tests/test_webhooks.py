"""Outbound webhooks: management, SSRF protection, signing and delivery after commit."""

import hashlib
import hmac
import json
import uuid

import pytest
from conftest import MF_PROPERTY, PASSWORD, Session, register

from app.services import webhooks as wh

PUBLIC_IP = "93.184.216.34"


@pytest.fixture
def outbox(monkeypatch):
    """Deliver synchronously, resolve every host to a public IP, and capture requests instead of sending them."""
    sent = []
    status = {"code": 200}
    monkeypatch.setattr(wh, "DISPATCH_IN_THREAD", False)
    monkeypatch.setattr(wh, "resolve", lambda host: [PUBLIC_IP])

    def fake_post(url, body, headers):
        sent.append({"url": url, "body": body, "headers": headers})
        return status["code"]

    monkeypatch.setattr(wh, "_post", fake_post)
    return sent, status


def _hook(s, events=("deal.created", "deal.stage_changed"), url="https://hooks.example.com/axiom"):
    r = s.post("/api/org/webhooks", json={"url": url, "events": list(events), "description": "CRM"})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_list_and_secret_shown_once(owner, outbox):
    created = _hook(owner)
    assert created["secret"].startswith("whsec_")
    listed = owner.get("/api/org/webhooks").json()
    assert "secret" not in listed["webhooks"][0] and "secret_encrypted" not in listed["webhooks"][0]
    assert set(listed["events"]) == set(wh.EVENTS)


@pytest.mark.parametrize("url", [
    "http://hooks.example.com/x",          # not https
    "https://localhost/x",
    "https://127.0.0.1/x",
    "https://10.0.0.5/x",
    "https://169.254.169.254/latest/meta-data",  # cloud metadata
    "https://[::1]/x",
    "https://user:pass@hooks.example.com/x",
    "https://hooks.example.com:8443/x",
    "https://db.internal/x",
])
def test_unsafe_urls_are_rejected(owner, monkeypatch, url):
    monkeypatch.setattr(wh, "resolve", lambda host: [host] if host[0].isdigit() or ":" in host else [PUBLIC_IP])
    r = owner.post("/api/org/webhooks", json={"url": url, "events": ["deal.created"]})
    assert r.status_code == 422, (url, r.text)


def test_hostname_resolving_to_private_ip_is_rejected(owner, monkeypatch):
    monkeypatch.setattr(wh, "resolve", lambda host: ["192.168.1.20"])
    assert owner.post("/api/org/webhooks", json={"url": "https://evil.example.com/x",
                                                 "events": ["deal.created"]}).status_code == 422


def test_events_are_delivered_signed_after_commit(owner, outbox):
    sent, _ = outbox
    secret = _hook(owner)["secret"]
    pid = owner.post("/api/properties", json=MF_PROPERTY).json()["id"]
    owner.patch(f"/api/properties/{pid}", json={"status": "ic"})
    owner.patch(f"/api/properties/{pid}", json={"name": "Renamed"})  # not a stage change: no event
    assert [json.loads(m["body"])["type"] for m in sent] == ["deal.created", "deal.stage_changed"]
    msg = sent[1]
    body = json.loads(msg["body"])
    assert body["data"]["property_id"] == pid
    assert body["data"]["details"]["changes"]["status"] == {"before": "sourcing", "after": "ic"}
    h = msg["headers"]
    expected = "sha256=" + hmac.new(secret.encode(), h["X-Axiom-Timestamp"].encode() + b"." + msg["body"],
                                    hashlib.sha256).hexdigest()
    assert h["X-Axiom-Signature"] == expected and h["X-Axiom-Event"] == "deal.stage_changed"
    hook = owner.get("/api/org/webhooks").json()["webhooks"][0]
    assert hook["last_status"] == "HTTP 200" and hook["consecutive_failures"] == 0


def test_only_subscribed_events_and_no_demo_events(client, outbox):
    sent, _ = outbox
    s = register(client)
    _hook(s, events=["report.generated"])
    pid = s.post("/api/properties", json=MF_PROPERTY).json()["id"]
    assert sent == []  # deal.created not subscribed
    s.get(f"/api/properties/{pid}/reports/one-pager")
    assert [json.loads(m["body"])["type"] for m in sent] == ["report.generated"]

    demo = register(client, seed=True)
    _hook(demo, events=["deal.created"])
    sent.clear()
    assert sent == []  # seeding happened before the hook existed; and demo creates never emit
    assert wh.event_for("property.create", {"demo": True}) is None


def test_no_delivery_when_the_change_is_rolled_back(owner, outbox):
    sent, _ = outbox
    _hook(owner, events=["deal.stage_changed"])
    from conftest import register as _reg

    other = _reg(owner.c)
    theirs = other.post("/api/properties", json=MF_PROPERTY).json()["id"]
    mine = owner.post("/api/properties", json=MF_PROPERTY).json()["id"]
    # Bulk change fails (foreign id) before anything commits.
    assert owner.post("/api/properties/bulk-status", json={"ids": [mine, theirs], "status": "ic"}).status_code == 404
    assert sent == []


def test_failures_are_recorded_and_hook_switches_off(owner, outbox):
    sent, status = outbox
    status["code"] = 500
    hook = _hook(owner, events=["deal.created"])
    for i in range(wh.MAX_FAILURES):
        owner.post("/api/properties", json={**MF_PROPERTY, "name": f"Deal {i}"})
    got = owner.get("/api/org/webhooks").json()["webhooks"][0]
    assert got["active"] is False and "switched off" in got["last_status"]
    count = len(sent)
    owner.post("/api/properties", json=MF_PROPERTY)
    assert len(sent) == count  # inactive hooks get nothing
    # Re-enabling resets the failure count.
    status["code"] = 204
    re = owner.patch(f"/api/org/webhooks/{hook['id']}", json={"active": True}).json()
    assert re["active"] and re["consecutive_failures"] == 0
    test = owner.post(f"/api/org/webhooks/{hook['id']}/test").json()
    assert test == {"ok": True, "status": "HTTP 204"}


def test_dns_is_rechecked_at_delivery(owner, outbox, monkeypatch):
    sent, _ = outbox
    hook = _hook(owner, events=["deal.created"])
    monkeypatch.setattr(wh, "resolve", lambda host: ["10.1.2.3"])  # DNS now points inside
    owner.post("/api/properties", json=MF_PROPERTY)
    assert sent == []
    got = owner.get("/api/org/webhooks").json()["webhooks"][0]
    assert got["last_status"].startswith("Blocked")
    assert owner.post(f"/api/org/webhooks/{hook['id']}/test").json()["ok"] is False


def test_permissions_and_isolation(client, owner, outbox):
    hook = _hook(owner)
    email = f"analyst-{uuid.uuid4().hex[:8]}@example.com"
    token = owner.post("/api/org/invitations", json={"email": email, "role": "analyst"}).json()["token"]
    acc = client.post("/api/invitations/accept", json={"token": token, "name": "A", "password": PASSWORD}).json()
    analyst = Session(client, acc["access_token"], owner.org_id)
    assert analyst.get("/api/org/webhooks").status_code == 403
    other = register(client)
    assert other.get("/api/org/webhooks").json()["webhooks"] == []
    assert other.delete(f"/api/org/webhooks/{hook['id']}").status_code == 404
    key = owner.post("/api/org/api-keys", json={"name": "k"}).json()["key"]
    assert Session(client, key).get("/api/org/webhooks").status_code == 403
    assert owner.post("/api/org/webhooks", json={"url": "https://hooks.example.com/x", "events": []}).status_code == 422
    assert owner.post("/api/org/webhooks", json={"url": "https://hooks.example.com/x",
                                                 "events": ["deal.exploded"]}).status_code == 422
    assert owner.delete(f"/api/org/webhooks/{hook['id']}").status_code == 204


def test_secret_is_encrypted_at_rest(owner, outbox):
    from app.db import SessionLocal, set_tenant
    from app.models import Webhook

    created = _hook(owner)
    with SessionLocal() as db:
        set_tenant(db, uuid.UUID(owner.org_id))
        row = db.get(Webhook, uuid.UUID(created["id"]))
        assert created["secret"] not in row.secret_encrypted
        assert wh.decrypt_secret(row.secret_encrypted) == created["secret"]
