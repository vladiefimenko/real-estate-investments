"""LP/GP waterfall endpoints."""

import pytest
from conftest import MF_PROPERTY, register
from test_roles import _join


def test_default_structure_and_totals(owner, prop):
    r = owner.get(f"/api/properties/{prop['id']}/waterfall")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["saved"] is False and body["config"]["pref_rate"] == 0.08
    res = body["result"]
    flows = res["equity_flows"]
    assert res["lp"]["contributed"] + res["gp"]["contributed"] == pytest.approx(-flows[0])
    assert res["lp"]["distributed"] + res["gp"]["distributed"] == pytest.approx(sum(f for f in flows[1:] if f > 0))
    assert [t["name"] for t in res["tiers"]] == ["Return of capital + preferred return", "Promote to 12% LP IRR",
                                                 "Residual split"]


def test_preview_save_and_audit(owner, prop):
    pid = prop["id"]
    cfg = {"lp_share": 0.95, "pref_rate": 0.06, "tiers": [{"hurdle": 0.10, "gp_share": 0.15},
                                                         {"hurdle": 0.15, "gp_share": 0.25},
                                                         {"hurdle": None, "gp_share": 0.35}]}
    prev = owner.post(f"/api/properties/{pid}/waterfall/preview", json=cfg).json()
    assert prev["saved"] is False and len(prev["result"]["tiers"]) == 4
    assert owner.get(f"/api/properties/{pid}/waterfall").json()["saved"] is False  # preview doesn't save
    saved = owner.put(f"/api/properties/{pid}/waterfall", json=cfg)
    assert saved.status_code == 200 and saved.json()["saved"] is True
    got = owner.get(f"/api/properties/{pid}/waterfall").json()
    assert got["config"] == cfg and got["result"]["lp"] == prev["result"]["lp"]
    assert any(e["action"] == "property.waterfall" for e in owner.get(f"/api/org/audit?property_id={pid}").json())


def test_validation(owner, prop):
    pid = prop["id"]
    bad = [
        {"lp_share": 1, "pref_rate": 0.08, "tiers": [{"gp_share": 0.2}]},
        {"lp_share": 0.9, "pref_rate": 0.8, "tiers": [{"gp_share": 0.2}]},
        {"lp_share": 0.9, "pref_rate": 0.08, "tiers": []},
        {"lp_share": 0.9, "pref_rate": 0.08, "tiers": [{"gp_share": 1.0}]},
        {"lp_share": 0.9, "pref_rate": 0.08, "tiers": [{"hurdle": 0.05, "gp_share": 0.2}, {"gp_share": 0.3}]},
        {"lp_share": 0.9, "pref_rate": 0.08, "tiers": [{"hurdle": 0.12, "gp_share": 0.2}]},
        {"lp_share": 0.9, "pref_rate": 0.08, "tiers": [{"gp_share": 0.2}], "catch_up": True},
    ]
    for body in bad:
        assert owner.put(f"/api/properties/{pid}/waterfall", json=body).status_code == 422, body
    assert owner.get(f"/api/properties/{pid}/waterfall").json()["saved"] is False


def test_access(client, owner, prop):
    pid = prop["id"]
    cfg = {"lp_share": 0.9, "pref_rate": 0.08, "tiers": [{"gp_share": 0.2}]}
    viewer = _join(client, owner, "viewer")
    assert viewer.get(f"/api/properties/{pid}/waterfall").status_code == 200
    assert viewer.put(f"/api/properties/{pid}/waterfall", json=cfg).status_code == 403
    ext = _join(client, owner, "external")
    assert ext.get(f"/api/properties/{pid}/waterfall").status_code == 404  # not shared
    owner.post(f"/api/properties/{pid}/shares", json={"user_id": ext.user_id})
    assert ext.get(f"/api/properties/{pid}/waterfall").status_code == 200
    assert register(client).get(f"/api/properties/{pid}/waterfall").status_code == 404
    other = owner.post("/api/properties", json={**MF_PROPERTY, "name": "Other"}).json()
    assert other["id"] != pid
