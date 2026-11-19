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


def _ask(s, pid, message, learning):
    import json

    r = s.post(f"/api/properties/{pid}/analyst/chat", json={"message": message, "learning_mode": learning})
    assert r.status_code == 200, r.text
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    return "".join(e.get("text", "") for e in events if e["type"] == "delta")


def test_learning_mode_teaches_with_the_deals_own_numbers(demo):
    mf = next(p for p in demo.get("/api/properties").json() if p["property_type"] == "multifamily")
    plain = _ask(demo, mf["id"], "Teach me how DSCR and the cap rate work here", learning=False)
    taught = _ask(demo, mf["id"], "Teach me how DSCR and the cap rate work here", learning=True)
    assert "Learn:" not in plain
    assert "**Learn: DSCR" in taught and "**Learn: cap rate" in taught
    a = demo.get(f"/api/properties/{mf['id']}/scenarios").json()[0]["assumptions"]
    assert f"${a['purchase_price']:,.0f}" in taught  # the lesson uses this deal's price
    # With nothing specific asked, learning mode suggests what to ask.
    assert "Teach me how DSCR works here" in _ask(demo, mf["id"], "hello", learning=True)


def test_junior_pack_pdf(demo):
    import io

    from pypdf import PdfReader

    mf = next(p for p in demo.get("/api/properties").json() if p["property_type"] == "multifamily")
    r = demo.get(f"/api/properties/{mf['id']}/reports/junior-pack",
                 params={"reviewed_by": "Dana Senior", "note": "First pass <draft> & questions"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert "junior-pack.pdf" in r.headers["content-disposition"]
    pages = PdfReader(io.BytesIO(r.content)).pages
    text = "\n".join(p.extract_text() for p in pages)
    assert len(pages) >= 4
    for expected in ("Cover note", "Prepared by", "Dana Senior", "First pass <draft> & questions",
                     "Key assumptions, annotated", "What to check", "Glossary", "DSCR"):
        assert expected in text, expected
    audit = demo.get(f"/api/org/audit?property_id={mf['id']}").json()
    assert any(e["action"] == "report.junior_pack" for e in audit)
    assert demo.get("/api/org/onboarding").json()["steps"]["report_generated"] is True


def test_junior_pack_without_reviewer_marks_pending(owner, prop):
    r = owner.get(f"/api/properties/{prop['id']}/reports/junior-pack")
    assert r.status_code == 200
    import io

    from pypdf import PdfReader

    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "pending review" in text and "Unlevered" in text
    assert owner.get(f"/api/properties/{prop['id']}/reports/junior-pack", params={"note": "x" * 1501}).status_code == 422
