"""Named underwriting versions, comparison, restore, and batch document processing."""

from conftest import MF_PROPERTY, register
from test_documents_reports import upload
from test_roles import _join


def _base(s, pid):
    return next(x for x in s.get(f"/api/properties/{pid}/scenarios").json() if x["is_base"])


def test_versions_save_compare_restore(client, owner, prop):
    pid = prop["id"]
    sc = _base(owner, pid)
    v1 = owner.post(f"/api/scenarios/{sc['id']}/versions/save", json={"label": "Sent to lender"})
    assert v1.status_code == 200 and v1.json()["label"] == "Sent to lender" and v1.json()["is_current"]
    a = sc["assumptions"]
    owner.patch(f"/api/scenarios/{sc['id']}", json={"assumptions": {**a, "vacancy_rate": 0.09, "exit_cap_rate": 0.06}})
    vs = owner.get(f"/api/scenarios/{sc['id']}/versions").json()["versions"]
    assert vs[0]["is_current"] and not vs[0]["label"] and sum(v["is_current"] for v in vs) == 1
    named = owner.get(f"/api/scenarios/{sc['id']}/versions", params={"labelled_only": True}).json()["versions"]
    assert [v["label"] for v in named] == ["Sent to lender"]
    cmp = owner.get(f"/api/scenarios/{sc['id']}/versions/compare", params={"a": vs[0]["id"], "b": v1.json()["id"]}).json()
    assert cmp["before"]["label"] == "Sent to lender"  # ordered oldest first whatever the order asked
    changed = {c["path"]: c for c in cmp["assumption_changes"]}
    assert changed["vacancy_rate"]["after"] == 0.09 and changed["exit_cap_rate"]["after"] == 0.06
    irr = next(m for m in cmp["metrics"] if m["key"] == "irr_levered")
    assert irr["delta"] < 0  # more vacancy and a higher exit cap lower the return
    r = owner.post(f"/api/scenarios/{sc['id']}/versions/{v1.json()['id']}/restore")
    assert r.status_code == 200 and r.json()["label"] == "Restored: Sent to lender"
    assert _base(owner, pid)["assumptions"]["vacancy_rate"] == a["vacancy_rate"]
    assert len(owner.get(f"/api/scenarios/{sc['id']}/versions").json()["versions"]) == len(vs) + 1  # nothing deleted
    audit = owner.get(f"/api/org/audit?property_id={pid}").json()
    assert any(e["action"] == "scenario.restore" for e in audit) and any(e["action"] == "scenario.version_saved" for e in audit)
    lab = owner.put(f"/api/scenarios/{sc['id']}/versions/{vs[0]['id']}/label", json={"label": "  Stress case  "})
    assert lab.json()["label"] == "Stress case"
    assert owner.post(f"/api/scenarios/{sc['id']}/versions/save", json={"label": "   "}).status_code == 422


def test_versions_access(client, owner, prop):
    sc = _base(owner, prop["id"])
    v = owner.post(f"/api/scenarios/{sc['id']}/versions/save", json={"label": "v1"}).json()
    viewer = _join(client, owner, "viewer")
    assert viewer.get(f"/api/scenarios/{sc['id']}/versions").status_code == 200
    assert viewer.post(f"/api/scenarios/{sc['id']}/versions/{v['id']}/restore").status_code == 403
    assert viewer.post(f"/api/scenarios/{sc['id']}/versions/save", json={"label": "x"}).status_code == 403
    stranger = register(client)
    assert stranger.get(f"/api/scenarios/{sc['id']}/versions").status_code == 404
    other = owner.post("/api/properties", json={**MF_PROPERTY, "name": "Other"}).json()
    osc = _base(owner, other["id"])
    # A version from another scenario can't be compared or restored through this one.
    assert owner.post(f"/api/scenarios/{osc['id']}/versions/{v['id']}/restore").status_code == 404


def test_document_queue_and_batch(client, owner, prop):
    pid = prop["id"]
    d1 = upload(owner, pid, "a.csv", b"Line Item,Total\nReal Estate Taxes,250000\n", "text/csv", "t12")
    other = owner.post("/api/properties", json={**MF_PROPERTY, "name": "At IC"}).json()
    owner.patch(f"/api/properties/{other['id']}", json={"status": "ic"})
    d2 = upload(owner, other["id"], "b.csv", b"Line Item,Total\nInsurance,90000\n", "text/csv", "t12")
    q = owner.get("/api/org/document-queue").json()
    assert q["counts"].get("extracted") == 2 and {d["property_name"] for d in q["documents"]} == {"Test Apartments", "At IC"}
    r = owner.post("/api/documents/batch-extract", json={"document_ids": [d1["id"], d2["id"]], "rules_only": True})
    assert r.status_code == 202 and r.json()["queued"] == 2
    assert r.json()["order"] == [d2["id"], d1["id"]]  # the deal at IC goes first
    statuses = {d["id"]: d["status"] for d in owner.get("/api/org/document-queue").json()["documents"]}
    assert statuses[d1["id"]] == statuses[d2["id"]] == "extracted"  # processed (TestClient runs tasks inline)
    assert owner.get("/api/org/document-queue", params={"status": "failed"}).json()["documents"] == []
    stranger = register(client)
    assert stranger.post("/api/documents/batch-extract", json={"document_ids": [d1["id"]]}).status_code == 404
    assert stranger.get("/api/org/document-queue").json()["documents"] == []
    assert _join(client, owner, "viewer").post("/api/documents/batch-extract",
                                               json={"document_ids": [d1["id"]]}).status_code == 403
    assert owner.post("/api/documents/batch-extract", json={"document_ids": []}).status_code == 422
