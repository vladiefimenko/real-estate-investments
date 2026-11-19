"""Bulk stage changes, multi-deal summary pack and client presentation export."""

import io

from conftest import MF_PROPERTY, register
from pypdf import PdfReader


def _text(content: bytes) -> tuple[int, str]:
    pages = PdfReader(io.BytesIO(content)).pages
    return len(pages), "\n".join(p.extract_text() for p in pages)


def test_bulk_status(owner):
    ids = [owner.post("/api/properties", json={**MF_PROPERTY, "name": f"Bulk {i}"}).json()["id"] for i in range(3)]
    owner.patch(f"/api/properties/{ids[0]}", json={"status": "ic"})
    r = owner.post("/api/properties/bulk-status", json={"ids": ids, "status": "ic"})
    assert r.status_code == 200, r.text
    assert set(r.json()["updated"]) == set(ids[1:]) and r.json()["unchanged"] == 1
    assert all(owner.get(f"/api/properties/{i}").json()["status"] == "ic" for i in ids)
    audit = owner.get(f"/api/org/audit?property_id={ids[1]}").json()
    assert any(e["action"] == "property.update" and e["details"].get("bulk") for e in audit)
    assert owner.post("/api/properties/bulk-status", json={"ids": ids, "status": "won"}).status_code == 422
    assert owner.post("/api/properties/bulk-status", json={"ids": [], "status": "ic"}).status_code == 422


def test_bulk_status_is_all_or_nothing_and_tenant_scoped(client, owner, prop):
    other = register(client)
    theirs = other.post("/api/properties", json=MF_PROPERTY).json()["id"]
    r = owner.post("/api/properties/bulk-status", json={"ids": [prop["id"], theirs], "status": "passed"})
    assert r.status_code == 404
    assert owner.get(f"/api/properties/{prop['id']}").json()["status"] != "passed"  # nothing changed
    assert other.get(f"/api/properties/{theirs}").json()["status"] != "passed"


def test_summary_pack(demo):
    deals = demo.get("/api/properties").json()[:3]
    r = demo.get("/api/reports/summary-pack", params={"ids": ",".join(d["id"] for d in deals)})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    n, text = _text(r.content)
    assert n >= 4 and "Deal summary pack" in text and "demo deals" in text
    for d in deals:
        assert d["name"] in text
    assert demo.get("/api/reports/summary-pack", params={"ids": "not-a-uuid"}).status_code == 422
    assert demo.get("/api/reports/summary-pack", params={"ids": ",".join([deals[0]["id"]] * 2)}).status_code == 200


def test_summary_pack_rejects_other_workspaces_deals(client, owner, prop):
    theirs = register(client).post("/api/properties", json=MF_PROPERTY).json()["id"]
    assert owner.get("/api/reports/summary-pack", params={"ids": f"{prop['id']},{theirs}"}).status_code == 404


def test_presentation(owner, prop):
    r = owner.get(f"/api/properties/{prop['id']}/reports/presentation",
                  params={"title": "Test Apartments Acquisition", "prepared_for": "Acme Lender <LLC>",
                          "firm_name": "Summit Capital"})
    assert r.status_code == 200 and "presentation.pdf" in r.headers["content-disposition"]
    n, text = _text(r.content)
    assert n == 4
    for expected in ("SUMMIT CAPITAL", "Test Apartments Acquisition", "Acme Lender <LLC>", "Investment highlights",
                     "Cash flow and capital", "Key considerations"):
        assert expected in text, expected
    assert "DEMONSTRATION" not in text
    n2, _ = _text(owner.get(f"/api/properties/{prop['id']}/reports/presentation",
                            params={"include_risk": "false"}).content)
    assert n2 == 3
    assert owner.get(f"/api/org/onboarding").json()["steps"]["report_generated"] is True


def test_presentation_watermarks_demo_deals(demo):
    mf = next(p for p in demo.get("/api/properties").json() if p["is_demo"])
    _, text = _text(demo.get(f"/api/properties/{mf['id']}/reports/presentation").content)
    assert "DEMONSTRATION" in text and "fictional" in text
