"""QSR (quick-service restaurant) property type."""

from conftest import MF_PROPERTY


def test_qsr_is_offered_with_its_fields(owner):
    types = {t["key"]: t for t in owner.get("/api/property-types").json()}
    q = types["qsr"]
    assert q["label"].startswith("QSR") and q["revenue_mode"] == "lump_sum"
    assert {"brand", "guarantor", "lease_type", "remaining_term_years", "drive_thru"} <= {f["key"] for f in q["fields"]}


def test_qsr_deal_starts_with_net_lease_economics(owner):
    body = {**MF_PROPERTY, "name": "Taco Bell – Main St", "property_type": "qsr", "purchase_price": 2_500_000,
            "units": None, "rentable_sf": 2_400, "attributes": {"brand": "Taco Bell", "guarantor": "Franchisee",
                                                                 "lease_type": "Absolute NNN", "drive_thru": "Yes"}}
    r = owner.post("/api/properties", json=body)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["attributes"]["brand"] == "Taco Bell"
    sc = next(s for s in owner.get(f"/api/properties/{pid}/scenarios").json() if s["is_base"])
    a = sc["assumptions"]
    assert a["revenue_mode"] == "lump_sum" and a["opex_mode"] == "ratio" and a["opex_ratio"] == 0.03
    res = owner.get(f"/api/scenarios/{sc['id']}/result").json()
    m = res["metrics"]
    # Starter rent is sized so the going-in cap rate is about the 6% exit cap, and the owner keeps most of the rent.
    assert abs(m["going_in_cap_rate"] - 0.06) < 0.003
    assert m["expense_ratio_year1"] < 0.06
    assert not any(f["factor"] == "expense_ratio" for f in res["risk"]["factors"])
