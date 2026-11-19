"""Assumption libraries: save standards once, apply them to any scenario."""

from conftest import MF_PROPERTY, register


def _base(s, pid):
    return s.get(f"/api/properties/{pid}/scenarios").json()[0]


def test_create_list_apply_and_delete(owner, prop):
    pid = prop["id"]
    r = owner.post("/api/libraries", json={"name": "Conservative MF", "property_type": "multifamily",
                                           "values": {"vacancy_rate": 0.08, "exit_cap_rate": 0.065,
                                                      "hold_period_years": 7}})
    assert r.status_code == 201, r.text
    lib = r.json()
    assert lib["mine"] and lib["values"]["hold_period_years"] == 7
    assert [x["name"] for x in owner.get("/api/libraries").json()] == ["Conservative MF"]

    base = _base(owner, pid)
    before_irr = owner.get(f"/api/properties/{pid}").json()["latest"]["irr_unlevered"]
    applied = owner.post(f"/api/scenarios/{base['id']}/apply-library", json={"library_id": lib["id"]})
    assert applied.status_code == 200, applied.text
    assert applied.json()["changed"] == ["exit_cap_rate", "hold_period_years", "vacancy_rate"]
    a = _base(owner, pid)["assumptions"]
    assert (a["vacancy_rate"], a["exit_cap_rate"], a["hold_period_years"]) == (0.08, 0.065, 7)
    deal = owner.get(f"/api/properties/{pid}").json()
    assert deal["hold_period_years"] == 7  # base case drives the deal's hold
    assert deal["latest"]["irr_unlevered"] != before_irr  # re-run and stored
    audit = owner.get(f"/api/org/audit?property_id={pid}").json()
    assert any(e["action"] == "library.apply" and e["details"]["library"] == "Conservative MF" for e in audit)

    assert owner.delete(f"/api/libraries/{lib['id']}").status_code == 204
    assert owner.get("/api/libraries").json() == []


def test_save_from_scenario(owner, prop):
    base = _base(owner, prop["id"])
    r = owner.post("/api/libraries/from-scenario", json={"scenario_id": base["id"], "name": "From Test Apartments",
                                                         "keys": ["rent_growth", "exit_cap_rate"]})
    assert r.status_code == 201, r.text
    assert r.json()["values"] == {"rent_growth": base["assumptions"]["rent_growth"],
                                  "exit_cap_rate": base["assumptions"]["exit_cap_rate"]}
    assert r.json()["property_type"] == "multifamily"
    bad = owner.post("/api/libraries/from-scenario", json={"scenario_id": base["id"], "name": "x",
                                                           "keys": ["purchase_price"]})
    assert bad.status_code == 422


def test_validation(owner):
    for values in ({}, {"purchase_price": 1}, {"vacancy_rate": 0.9}, {"exit_cap_rate": "6%"},
                   {"hold_period_years": True}):
        assert owner.post("/api/libraries", json={"name": "x", "values": values}).status_code == 422, values
    assert owner.post("/api/libraries", json={"name": "x", "property_type": "castle",
                                              "values": {"rent_growth": 0.02}}).status_code == 422


def _join(client, owner, role):
    import uuid

    from conftest import PASSWORD, Session

    email = f"{role}-{uuid.uuid4().hex[:8]}@example.com"
    token = owner.post("/api/org/invitations", json={"email": email, "role": role}).json()["token"]
    acc = client.post("/api/invitations/accept", json={"token": token, "name": f"Team {role}", "password": PASSWORD})
    assert acc.status_code == 200, acc.text
    return Session(client, acc.json()["access_token"], owner.org_id)


def test_private_libraries_roles_and_tenant_isolation(client, owner, prop):
    private = owner.post("/api/libraries", json={"name": "Mine only", "is_shared": False,
                                                 "values": {"rent_growth": 0.02}}).json()
    shared = owner.post("/api/libraries", json={"name": "Team", "values": {"rent_growth": 0.025}}).json()
    base_id = _base(owner, prop["id"])["id"]

    teammate = _join(client, owner, "analyst")
    assert [x["name"] for x in teammate.get("/api/libraries").json()] == ["Team"]
    assert teammate.post(f"/api/scenarios/{base_id}/apply-library",
                         json={"library_id": private["id"]}).status_code == 404
    assert teammate.delete(f"/api/libraries/{shared['id']}").status_code == 403  # not theirs, not admin

    viewer = _join(client, owner, "viewer")
    assert viewer.post("/api/libraries", json={"name": "x", "values": {"rent_growth": 0.02}}).status_code == 403
    assert viewer.post(f"/api/scenarios/{base_id}/apply-library",
                       json={"library_id": shared["id"]}).status_code == 403

    other_org = register(client)
    assert other_org.get("/api/libraries").json() == []
    assert other_org.delete(f"/api/libraries/{shared['id']}").status_code == 404

    assert owner.post(f"/api/scenarios/{base_id}/apply-library", json={"library_id": private["id"]}).status_code == 200
