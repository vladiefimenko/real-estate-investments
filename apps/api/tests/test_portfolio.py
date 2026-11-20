"""Portfolio analytics, concentration, sponsors and the portfolio report."""

import io

import pytest
from conftest import MF_PROPERTY, register
from pypdf import PdfReader
from test_roles import _join


def _deal(s, **kw):
    r = s.post("/api/properties", json={**MF_PROPERTY, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_segments_by_market_and_concentration(owner):
    _deal(owner, name="A", city="Austin", state="TX", purchase_price=30_000_000)
    _deal(owner, name="B", city="Austin", state="TX", purchase_price=20_000_000)
    _deal(owner, name="C", city="Denver", state="CO", purchase_price=10_000_000)
    r = owner.get("/api/portfolio", params={"dimension": "market"}).json()
    seg = {s["segment"]: s for s in r["segments"]}
    assert set(seg) == {"Austin, TX", "Denver, CO"}
    assert seg["Austin, TX"]["deals"] == 2 and seg["Austin, TX"]["volume"] == 50_000_000
    assert seg["Austin, TX"]["share"] == pytest.approx(50 / 60)
    assert r["totals"]["volume"] == 60_000_000 and r["totals"]["deals"] == 3
    assert abs(sum(s["noi_share"] for s in r["segments"]) - 1) < 1e-9
    for s in r["segments"]:
        assert s["cap_rate"] is not None and s["irr_levered"] is not None and s["risk_score"] is not None
        if s["risk_score"]:
            assert s["return_per_risk"] == pytest.approx(s["irr_levered"] / (s["risk_score"] / 10))
        else:  # no risk flags at all: the ratio is undefined
            assert s["return_per_risk"] is None
    c = r["concentration"]
    assert c["hhi"] == pytest.approx((50 / 60) ** 2 + (10 / 60) ** 2)
    assert c["level"] == "high" and c["flags"] == ["Austin, TX is 83% of volume"]


def test_other_dimensions_and_filters(owner):
    _deal(owner, name="Old", year_built=1975, attributes={"sponsor": "Summit Partners"})
    _deal(owner, name="New", year_built=2021)
    gone = _deal(owner, name="Passed deal")
    owner.patch(f"/api/properties/{gone['id']}", json={"status": "passed"})
    vint = {s["segment"] for s in owner.get("/api/portfolio", params={"dimension": "vintage"}).json()["segments"]}
    assert vint == {"Before 1980", "2020 or newer"}  # passed deals excluded by default
    by_sponsor = owner.get("/api/portfolio", params={"dimension": "sponsor"}).json()
    assert {s["segment"] for s in by_sponsor["segments"]} == {"Summit Partners", "No sponsor set"}
    assert by_sponsor["concentration"]["flags"] == ["Summit Partners is 50% of volume"]  # never "No sponsor set"
    stages = owner.get("/api/portfolio", params={"dimension": "stage", "status": "passed"}).json()
    assert [s["segment"] for s in stages["segments"]] == ["Passed"]
    assert owner.get("/api/portfolio", params={"dimension": "galaxy"}).status_code == 422
    assert owner.get("/api/portfolio", params={"status": "won"}).status_code == 422


def test_demo_toggle_and_tenancy(client, demo):
    with_demo = demo.get("/api/portfolio").json()
    assert with_demo["totals"]["deals"] > 0 and with_demo["demo_deals"] > 0
    assert demo.get("/api/portfolio", params={"include_demo": "false"}).json()["totals"]["deals"] == 0
    assert register(client).get("/api/portfolio").json()["totals"]["deals"] == 0


def test_sponsor_edit_merges_and_protects_feature_data(owner, prop):
    pid = prop["id"]
    wf = {"lp_share": 0.9, "pref_rate": 0.08, "tiers": [{"gp_share": 0.2}]}
    assert owner.put(f"/api/properties/{pid}/waterfall", json=wf).status_code == 200
    # A stale edit form sends old attributes plus a sponsor; feature data must survive and can't be overwritten.
    r = owner.patch(f"/api/properties/{pid}", json={"attributes": {"sponsor": "Summit Partners", "waterfall": None,
                                                                  "ic": {"decision": "approved"}}})
    attrs = r.json()["attributes"]
    assert attrs["sponsor"] == "Summit Partners" and attrs["waterfall"]["pref_rate"] == 0.08 and "ic" not in attrs
    attrs = owner.patch(f"/api/properties/{pid}", json={"attributes": {"sponsor": ""}}).json()["attributes"]
    assert "sponsor" not in attrs and "waterfall" in attrs


def test_portfolio_report(client, owner):
    _deal(owner, name="Report Deal One", city="Austin", state="TX", attributes={"sponsor": "Summit"})
    _deal(owner, name="Report Deal Two", city="Denver", state="CO")
    r = owner.post("/api/reports/portfolio", json={"title": "Q4 Board Package",
                                                   "dimensions": ["market", "sponsor", "vintage"]})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert "Q4-Board-Package" in r.headers["content-disposition"]
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    for expected in ("Q4 Board Package", "By market", "By sponsor", "By vintage", "Austin, TX", "Summit",
                     "Report Deal Two", "deterministic"):
        assert expected in text, expected
    no_list = owner.post("/api/reports/portfolio", json={"dimensions": ["stage"], "include_deal_list": False})
    assert "Deals in this report" not in "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(no_list.content)).pages)
    assert owner.post("/api/reports/portfolio", json={"dimensions": []}).status_code == 422
    assert owner.post("/api/reports/portfolio", json={"statuses": ["closed"]}).status_code == 422  # nothing closed
    assert any(e["action"] == "report.portfolio" for e in owner.get("/api/org/audit").json())
    assert _join(client, owner, "viewer").post("/api/reports/portfolio", json={}).status_code == 200
    assert _join(client, owner, "external").get("/api/portfolio").status_code == 403
