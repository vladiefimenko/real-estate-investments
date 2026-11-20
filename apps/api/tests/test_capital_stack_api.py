"""Second (mezzanine) loan, prepayment penalty, Excel reconciliation and copying structures between deals."""

import io

import openpyxl
import pytest
from conftest import MF_PROPERTY, register
from test_documents_reports import _excel_values
from test_roles import _join

STRUCT = {"name": "Agency + Mezz", "type": "permanent", "ltv": 0.6, "interest_rate": 0.055, "term_years": 10,
          "amortization_years": 30, "fees": {"origination_fee_pct": 0.01, "prepayment_penalty_pct": 0.02},
          "mezzanine": {"amount": 2_000_000, "interest_rate": 0.11, "origination_fee_pct": 0.01}}


def test_mezzanine_structure_compare_and_activate(owner, prop):
    pid = prop["id"]
    f = owner.post(f"/api/properties/{pid}/financing", json=STRUCT)
    assert f.status_code == 201, f.text
    assert f.json()["mezzanine"]["amount"] == 2_000_000
    rows = owner.get(f"/api/properties/{pid}/financing/compare").json()
    row = next(r for r in rows if r["name"] == "Agency + Mezz")
    assert row["mezzanine"] == 2_000_000
    act = owner.post(f"/api/financing/{f.json()['id']}/activate")
    assert act.status_code == 200
    sc = next(s for s in owner.get(f"/api/properties/{pid}/scenarios").json() if s["is_base"])
    assert sc["assumptions"]["mezzanine"]["amount"] == 2_000_000
    assert sc["assumptions"]["loan"]["prepayment_penalty_pct"] == 0.02
    res = owner.get(f"/api/scenarios/{sc['id']}/result").json()
    assert res["sources_and_uses"]["mezzanine_loan"] == 2_000_000
    assert res["exit"]["prepayment_penalty"] > 0  # 5-year hold on a 10-year loan


def test_invalid_mezzanine_rejected(owner, prop):
    for mezz in ({"amount": 2_000_000, "interest_rate": 0.9}, {"amount": 50_000_000, "interest_rate": 0.1},
                 {"amount": 1_000_000, "interest_rate": 0.1, "surprise": 1}):
        r = owner.post(f"/api/properties/{prop['id']}/financing", json={**STRUCT, "mezzanine": mezz})
        assert r.status_code == 422, mezz


def test_excel_reconciles_with_mezzanine_and_prepayment(owner, prop):
    pid = prop["id"]
    f = owner.post(f"/api/properties/{pid}/financing", json=STRUCT).json()
    owner.post(f"/api/financing/{f['id']}/activate")
    r = owner.get(f"/api/properties/{pid}/reports/excel")
    assert r.status_code == 200
    labels = [c.value for c in openpyxl.load_workbook(io.BytesIO(r.content))["Returns"]["A"]]
    assert "Mezzanine loan" in labels and "Prepayment penalty" in labels
    ws = _excel_values(r.content)["Returns"]
    start = next(c.row for c in ws["A"] if c.value == "Metric")
    checked = 0
    for row in ws.iter_rows(min_row=start + 1, max_col=3):
        label, model, engine = row[0].value, row[1].value, row[2].value
        if isinstance(model, (int, float)) and isinstance(engine, (int, float)):
            assert model == pytest.approx(engine, rel=1e-6, abs=1e-6), f"{label}: {model} vs {engine}"
            checked += 1
    assert checked >= 10


def test_copy_structure_from_another_deal(client, owner, prop):
    src = owner.post(f"/api/properties/{prop['id']}/financing", json=STRUCT).json()
    other = owner.post("/api/properties", json={**MF_PROPERTY, "name": "Second Deal"}).json()
    lib = owner.get("/api/financing", params={"exclude_property": other["id"]}).json()
    assert [(x["name"], x["property_name"]) for x in lib] == [("Agency + Mezz", "Test Apartments")]
    assert owner.get("/api/financing", params={"exclude_property": prop["id"]}).json() == []
    c = owner.post(f"/api/properties/{other['id']}/financing/clone", json={"financing_id": src["id"]})
    assert c.status_code == 201, c.text
    copy = c.json()
    assert copy["name"] == "Agency + Mezz (copy)" and copy["property_id"] == other["id"]
    assert copy["is_active"] is False and copy["mezzanine"] == STRUCT["mezzanine"] and copy["ltv"] == 0.6
    audit = owner.get(f"/api/org/audit?property_id={other['id']}").json()
    assert any(e["details"].get("copied_from") == src["id"] for e in audit)
    # Viewers can't copy or browse; other workspaces can't reach the source.
    viewer = _join(client, owner, "viewer")
    assert viewer.get("/api/financing").status_code == 403
    assert viewer.post(f"/api/properties/{other['id']}/financing/clone", json={"financing_id": src["id"]}).status_code == 403
    stranger = register(client)
    sp = stranger.post("/api/properties", json=MF_PROPERTY).json()["id"]
    assert stranger.post(f"/api/properties/{sp}/financing/clone", json={"financing_id": src["id"]}).status_code == 404
    assert stranger.get("/api/financing").json() == []
