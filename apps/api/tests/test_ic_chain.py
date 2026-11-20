"""IC approval chains and in-app notifications."""

from conftest import MF_PROPERTY, register
from test_roles import _join


def _setup(client, owner):
    a = _join(client, owner, "analyst")
    b = _join(client, owner, "viewer")
    c = _join(client, owner, "admin")
    steps = [{"name": "Asset management", "approvers": [a.user_id, b.user_id], "min_approvals": 1},
             {"name": "CIO", "approvers": [c.user_id], "min_approvals": 1}]
    r = owner.put("/api/org/workflow/chain", json={"steps": steps})
    assert r.status_code == 200, r.text
    assert [s["approver_names"] for s in r.json()["steps"]] == [["Team analyst", "Team viewer"], ["Team admin"]]
    deal = owner.post("/api/properties", json=MF_PROPERTY).json()
    return a, b, c, deal


def _notes(s):
    return s.get("/api/notifications").json()


def test_chain_runs_in_order_and_notifies(client, owner):
    a, b, c, deal = _setup(client, owner)
    pid = deal["id"]
    owner.patch(f"/api/properties/{pid}", json={"status": "ic"})
    ic = owner.get(f"/api/properties/{pid}/ic").json()
    assert ic["chain_status"] == "pending" and ic["current_step"] == 0 and ic["can_approve"] is False
    # Step-1 approvers are notified; the CIO isn't yet.
    assert _notes(a)["unread"] == 1 and _notes(a)["items"][0]["kind"] == "ic.approval_requested"
    assert _notes(a)["items"][0]["link"] == f"/deals/{pid}"
    assert _notes(c)["unread"] == 0
    # Out of turn: the CIO can't act on step 1; an admin can't record approval yet.
    assert c.post(f"/api/properties/{pid}/ic/approval", json={"action": "approve"}).status_code == 403
    r = owner.post(f"/api/properties/{pid}/ic/decision", json={"decision": "approved"})
    assert r.status_code == 409 and "Asset management" in r.json()["detail"]
    # One of the two step-1 approvers is enough.
    assert a.get(f"/api/properties/{pid}/ic").json()["can_approve"] is True
    r = a.post(f"/api/properties/{pid}/ic/approval", json={"action": "approve", "comment": "Rent roll checks out"})
    assert r.status_code == 200 and r.json()["current_step"] == 1
    assert b.post(f"/api/properties/{pid}/ic/approval", json={"action": "approve"}).status_code == 403
    assert a.post(f"/api/properties/{pid}/ic/approval", json={"action": "approve"}).status_code == 403
    assert _notes(c)["unread"] == 1 and "Step 2 of 2 (CIO)" in _notes(c)["items"][0]["body"]
    r = c.post(f"/api/properties/{pid}/ic/approval", json={"action": "approve"})
    assert r.json()["chain_status"] == "approved"
    assert any(n["kind"] == "ic.approval_complete" for n in _notes(owner)["items"])
    r = owner.post(f"/api/properties/{pid}/ic/decision", json={"decision": "approved", "notes": "Go"})
    assert r.status_code == 200
    assert any(n["kind"] == "ic.decision" for n in _notes(a)["items"])
    audit = owner.get(f"/api/org/audit?property_id={pid}").json()
    assert sum(e["action"] == "ic.approval" for e in audit) == 2


def test_decline_stops_the_chain(client, owner):
    a, _b, _c, deal = _setup(client, owner)
    pid = deal["id"]
    owner.patch(f"/api/properties/{pid}", json={"status": "ic"})
    r = a.post(f"/api/properties/{pid}/ic/approval", json={"action": "decline", "comment": "Too much leverage"})
    assert r.json()["chain_status"] == "declined"
    assert any(n["kind"] == "ic.approval_declined" for n in _notes(owner)["items"])
    assert owner.post(f"/api/properties/{pid}/ic/decision", json={"decision": "approved"}).status_code == 409
    assert owner.post(f"/api/properties/{pid}/ic/decision", json={"decision": "declined"}).status_code == 200


def test_chain_snapshot_and_no_chain(client, owner):
    a, _b, _c, deal = _setup(client, owner)
    pid = deal["id"]
    owner.patch(f"/api/properties/{pid}", json={"status": "ic"})
    owner.put("/api/org/workflow/chain", json={"steps": []})  # turning it off doesn't touch the open round
    assert owner.get(f"/api/properties/{pid}/ic").json()["chain_status"] == "pending"
    other = owner.post("/api/properties", json={**MF_PROPERTY, "name": "No chain"}).json()
    owner.patch(f"/api/properties/{other['id']}", json={"status": "ic"})
    ic = owner.get(f"/api/properties/{other['id']}/ic").json()
    assert ic["chain"] is None and ic["chain_status"] is None
    assert owner.post(f"/api/properties/{other['id']}/ic/decision", json={"decision": "approved"}).status_code == 200


def test_chain_validation(client, owner):
    ext = _join(client, owner, "external")
    a = _join(client, owner, "analyst")
    stranger = register(client)
    bad = [
        {"steps": [{"name": "X", "approvers": [ext.user_id]}]},
        {"steps": [{"name": "X", "approvers": [stranger.user_id]}]},
        {"steps": [{"name": "X", "approvers": [a.user_id], "min_approvals": 2}]},
        {"steps": [{"name": "", "approvers": [a.user_id]}]},
        {"steps": [{"name": f"S{i}", "approvers": [a.user_id]} for i in range(6)]},
    ]
    for body in bad:
        assert owner.put("/api/org/workflow/chain", json=body).status_code == 422, body
    assert a.put("/api/org/workflow/chain", json={"steps": []}).status_code == 403


def test_notifications_read_and_privacy(client, owner):
    a, _b, _c, deal = _setup(client, owner)
    owner.patch(f"/api/properties/{deal['id']}", json={"status": "ic"})
    n = _notes(a)
    assert n["unread"] == 1
    assert owner.post("/api/notifications/read", json={"ids": [n["items"][0]["id"]]}).status_code == 200
    assert _notes(a)["unread"] == 1  # someone else can't mark my notifications read
    a.post("/api/notifications/read", json={})
    assert _notes(a)["unread"] == 0 and _notes(a)["items"][0]["read"] is True
    assert register(client).get("/api/notifications").json() == {"unread": 0, "items": []}


def test_ic_memo_includes_the_chain(client, owner):
    import io

    from pypdf import PdfReader

    a, _b, _c, deal = _setup(client, owner)
    pid = deal["id"]
    owner.patch(f"/api/properties/{pid}", json={"status": "ic"})
    a.post(f"/api/properties/{pid}/ic/approval", json={"action": "approve", "comment": "Rent roll ties out"})
    r = owner.get(f"/api/properties/{pid}/reports/ic-memo")
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "Approval chain" in text and "Asset management" in text and "Rent roll ties out" in text
    assert "Waiting on Team admin" in text
