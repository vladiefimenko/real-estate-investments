"""Comparing the values extracted from two versions of a deal document."""

from conftest import MF_PROPERTY, register
from test_documents_reports import upload
from test_roles import _join

T12_MAY = b"Line Item,Total\nReal Estate Taxes,250000\nInsurance,90000\nUtilities,40000\n"
T12_JUNE = b"Line Item,Total\nReal Estate Taxes,262500\nInsurance,90000\nPayroll,120000\n"


def _pair(owner, pid):
    a = upload(owner, pid, "t12-may.csv", T12_MAY, "text/csv", "t12")
    b = upload(owner, pid, "t12-june.csv", T12_JUNE, "text/csv", "t12")
    return a, b


def test_compare_shows_changes(owner, prop):
    may, june = _pair(owner, prop["id"])
    # Order doesn't matter: the older upload is always "before".
    r = owner.get(f"/api/documents/{june['id']}/compare", params={"other": may["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["before"]["name"] == "t12-may.csv" and body["after"]["name"] == "t12-june.csv"
    rows = {x["field_path"]: x for x in body["rows"]}
    taxes = rows["expenses.real_estate_taxes"]
    assert taxes["change"] == "changed" and taxes["before"] == 250_000 and taxes["after"] == 262_500
    assert taxes["delta"] == 12_500 and abs(taxes["delta_pct"] - 0.05) < 1e-9
    assert rows["expenses.insurance"]["change"] == "same" and rows["expenses.insurance"]["delta"] is None
    assert rows["expenses.utilities"]["change"] == "removed"
    assert rows["expenses.payroll"]["change"] == "added"
    assert body["counts"]["changed"] >= 1 and body["counts"]["added"] >= 1 and body["counts"]["removed"] >= 1


def test_compare_prefers_reviewed_values_and_ignores_rejected(owner, prop):
    may, june = _pair(owner, prop["id"])
    ext = {x["field_path"]: x for x in owner.get(f"/api/documents/{june['id']}/extractions").json()}
    owner.patch(f"/api/extractions/{ext['expenses.real_estate_taxes']['id']}", json={"action": "edit", "value": 255000})
    owner.patch(f"/api/extractions/{ext['expenses.payroll']['id']}", json={"action": "reject"})
    rows = {x["field_path"]: x for x in
            owner.get(f"/api/documents/{may['id']}/compare", params={"other": june["id"]}).json()["rows"]}
    assert rows["expenses.real_estate_taxes"]["after"] == 255_000
    assert rows["expenses.real_estate_taxes"]["after_status"] == "edited"
    assert "expenses.payroll" not in rows


def test_compare_guards(client, owner, prop):
    may, june = _pair(owner, prop["id"])
    assert owner.get(f"/api/documents/{may['id']}/compare", params={"other": may["id"]}).status_code == 422
    other_deal = owner.post("/api/properties", json={**MF_PROPERTY, "name": "Other"}).json()
    elsewhere = upload(owner, other_deal["id"], "x.csv", T12_MAY + b"Marketing,5000\n", "text/csv")
    assert owner.get(f"/api/documents/{may['id']}/compare", params={"other": elsewhere["id"]}).status_code == 422
    # Another workspace's document is invisible.
    stranger = register(client)
    sp = stranger.post("/api/properties", json=MF_PROPERTY).json()["id"]
    theirs = upload(stranger, sp, "t.csv", T12_JUNE, "text/csv")
    assert owner.get(f"/api/documents/{may['id']}/compare", params={"other": theirs["id"]}).status_code == 404
    assert stranger.get(f"/api/documents/{theirs['id']}/compare", params={"other": may["id"]}).status_code == 404
    # External members only see it once the deal is shared with them.
    ext = _join(client, owner, "external")
    url = f"/api/documents/{may['id']}/compare"
    assert ext.get(url, params={"other": june["id"]}).status_code == 404
    owner.post(f"/api/properties/{prop['id']}/shares", json={"user_id": ext.user_id})
    # ...and only for documents in the deal's data room.
    assert ext.get(url, params={"other": june["id"]}).status_code == 404
    for d in (may, june):
        owner.put(f"/api/documents/{d['id']}/data-room", json={"in_room": True})
    assert ext.get(url, params={"other": june["id"]}).status_code == 200
