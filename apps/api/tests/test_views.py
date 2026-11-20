"""Saved dashboard views: per-user, private, validated."""

from conftest import register
from test_roles import _join

VIEW = {"name": "My multifamily pipeline",
        "config": {"filters": {"property_type": "multifamily", "status": "underwriting", "mine_only": True},
                   "metrics": ["irr_median", "active_deals"], "sections": ["alerts", "pipeline"]}}


def test_create_list_update_delete(owner):
    assert owner.get("/api/views").json() == []
    r = owner.post("/api/views", json=VIEW)
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["config"]["metrics"] == ["irr_median", "active_deals"] and v["is_default"] is False
    assert [x["name"] for x in owner.get("/api/views").json()] == ["My multifamily pipeline"]
    u = owner.patch(f"/api/views/{v['id']}", json={"name": "Renamed", "config": {"metrics": ["aum"]}}).json()
    assert u["name"] == "Renamed" and u["config"]["metrics"] == ["aum"]
    assert u["config"]["sections"] == ["pipeline", "exposure", "alerts", "activity", "recent_deals"]  # defaults
    assert owner.delete(f"/api/views/{v['id']}").status_code == 204
    assert owner.get("/api/views").json() == []


def test_only_one_default(owner):
    a = owner.post("/api/views", json={**VIEW, "name": "A", "is_default": True}).json()
    b = owner.post("/api/views", json={**VIEW, "name": "B", "is_default": True}).json()
    views = {v["name"]: v["is_default"] for v in owner.get("/api/views").json()}
    assert views == {"A": False, "B": True}
    owner.patch(f"/api/views/{a['id']}", json={"is_default": True})
    assert {v["name"]: v["is_default"] for v in owner.get("/api/views").json()} == {"A": True, "B": False}
    owner.patch(f"/api/views/{a['id']}", json={"is_default": False})
    assert not any(v["is_default"] for v in owner.get("/api/views").json())
    assert b


def test_validation(owner):
    bad = [
        {"name": "  ", "config": {}},
        {"name": "x" * 81, "config": {}},
        {"name": "x", "config": {"metrics": ["profit"]}},
        {"name": "x", "config": {"metrics": ["aum", "aum"]}},
        {"name": "x", "config": {"sections": ["secrets"]}},
        {"name": "x", "config": {"filters": {"property_type": "castle"}}},
        {"name": "x", "config": {"filters": {"status": "won"}}},
        {"name": "x", "config": {"filters": {"owner_id": "someone"}}},
        {"name": "x", "page": "settings", "config": {}},
    ]
    for body in bad:
        assert owner.post("/api/views", json=body).status_code == 422, body
    owner.post("/api/views", json=VIEW)
    assert owner.post("/api/views", json={**VIEW, "name": VIEW["name"].upper()}).status_code == 409


def test_views_are_private_and_tenant_scoped(client, owner):
    mine = owner.post("/api/views", json=VIEW).json()
    teammate = _join(client, owner, "viewer")  # viewers can save their own views
    assert teammate.get("/api/views").json() == []
    assert teammate.post("/api/views", json=VIEW).status_code == 201  # same name is fine for another person
    for method in ("patch", "delete"):
        kw = {"json": {"name": "hijack"}} if method == "patch" else {}
        assert getattr(teammate, method)(f"/api/views/{mine['id']}", **kw).status_code == 404
    stranger = register(client)
    assert stranger.get("/api/views").json() == []
    assert stranger.delete(f"/api/views/{mine['id']}").status_code == 404
    assert _join(client, owner, "external").get("/api/views").status_code == 403
    assert owner.get("/api/views").json()[0]["name"] == VIEW["name"]


def test_view_limit(owner):
    for i in range(20):
        assert owner.post("/api/views", json={**VIEW, "name": f"V{i}"}).status_code == 201
    assert owner.post("/api/views", json={**VIEW, "name": "One too many"}).status_code == 422
