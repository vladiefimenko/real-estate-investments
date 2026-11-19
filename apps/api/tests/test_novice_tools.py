"""New Deal wizard starter values and scenario 'what changed' explanations."""

import pytest
from conftest import MF_PROPERTY


def _assumptions(s, pid):
    return s.get(f"/api/properties/{pid}/scenarios").json()[0]["assumptions"]


def test_starter_values_shape_the_new_deal(owner):
    body = {**MF_PROPERTY, "starter": {"noi_year1": 1_100_000, "vacancy_rate": 0.07, "rent_growth": 0.025,
                                      "exit_cap_rate": 0.06}}
    r = owner.post("/api/properties", json=body)
    assert r.status_code == 201, r.text
    a = _assumptions(owner, r.json()["id"])
    assert (a["vacancy_rate"], a["rent_growth"], a["exit_cap_rate"]) == (0.07, 0.025, 0.06)
    # Revenue and expenses are sized so year-1 NOI lands near the figure given.
    assert r.json()["latest"]["noi_year1"] == pytest.approx(1_100_000, rel=0.03)


def test_starter_values_are_optional_and_validated(owner):
    plain = owner.post("/api/properties", json=MF_PROPERTY).json()
    assert _assumptions(owner, plain["id"])["vacancy_rate"] == 0.05  # multifamily template
    partial = owner.post("/api/properties", json={**MF_PROPERTY, "starter": {"rent_growth": 0.02}}).json()
    a = _assumptions(owner, partial["id"])
    assert a["rent_growth"] == 0.02 and a["vacancy_rate"] == 0.05
    for bad in ({"vacancy_rate": 0.9}, {"exit_cap_rate": 0}, {"noi_year1": -5}, {"surprise": 1}):
        assert owner.post("/api/properties", json={**MF_PROPERTY, "starter": bad}).status_code == 422, bad


def test_explain_attributes_irr_change_to_each_assumption(owner, prop):
    pid = prop["id"]
    created = {s["name"]: s["id"] for s in owner.post(f"/api/properties/{pid}/scenarios/defaults").json()}
    body = owner.get(f"/api/scenarios/{created['Conservative']}/explain").json()
    assert body["base_name"] == "Base Case" and body["scenario_name"] == "Conservative"
    assert body["metric"] in ("irr_levered", "irr_unlevered")
    keys = {d["key"] for d in body["drivers"]}
    assert keys == {"rent_growth", "vacancy_rate", "opex_growth", "exit_cap_rate"}
    # Every conservative shift lowers returns, and drivers are sorted by size of impact.
    impacts = [d["irr_impact"] for d in body["drivers"]]
    assert all(i < 0 for i in impacts)
    assert impacts == sorted(impacts, key=lambda i: -abs(i))
    assert body["total_change"] == pytest.approx(body["scenario_irr"] - body["base_irr"])
    assert body["total_change"] == pytest.approx(sum(impacts) + body["interaction"])
    rg = next(d for d in body["drivers"] if d["key"] == "rent_growth")
    assert rg["scenario_value"] == pytest.approx(rg["base_value"] - 0.01) and rg["kind"] == "pct"


def test_explain_base_case_has_no_drivers(owner, prop):
    base_id = owner.get(f"/api/properties/{prop['id']}/scenarios").json()[0]["id"]
    body = owner.get(f"/api/scenarios/{base_id}/explain").json()
    assert body["drivers"] == [] and body["total_change"] == 0


def test_explain_is_tenant_scoped(client, owner, prop):
    from conftest import register

    base_id = owner.get(f"/api/properties/{prop['id']}/scenarios").json()[0]["id"]
    assert register(client).get(f"/api/scenarios/{base_id}/explain").status_code == 404
