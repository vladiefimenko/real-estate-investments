"""Custom instructions, standards and remembered notes for the AI analyst."""

from conftest import register
from test_novice_tools import _ask
from test_roles import _join

from app.services import ai
from app.services.analyst_prefs import prompt_block


import pytest


@pytest.fixture
def demo(client):  # a fresh seeded workspace per test: preferences and notes are stateful
    return register(client, seed=True)


def _mf(s):
    return next(p for p in s.get("/api/properties").json() if p["property_type"] == "multifamily")


def test_defaults_and_personal_overrides_workspace(client, demo):
    p = demo.get("/api/analyst/preferences").json()
    assert p["effective"] == {"dscr_floor": None, "exit_cap_stress_bps": None, "workspace_instructions": None,
                              "personal_instructions": None, "notes": []}
    assert p["can_edit_workspace"] is True
    demo.put("/api/analyst/preferences/workspace",
             json={"dscr_floor": 1.25, "exit_cap_stress_bps": 50, "instructions": "IC memo style, bullets."})
    r = demo.put("/api/analyst/preferences/personal", json={"dscr_floor": 1.4, "instructions": "  Be brief.  "})
    eff = r.json()["effective"]
    assert eff["dscr_floor"] == 1.4 and eff["exit_cap_stress_bps"] == 50  # personal wins, workspace fills gaps
    assert eff["personal_instructions"] == "Be brief." and eff["workspace_instructions"] == "IC memo style, bullets."
    # A teammate sees the workspace standards but not my personal preferences.
    mate = _join(client, demo, "analyst")
    e2 = mate.get("/api/analyst/preferences").json()
    assert e2["effective"]["dscr_floor"] == 1.25 and e2["effective"]["personal_instructions"] is None
    assert e2["can_edit_workspace"] is False
    assert mate.put("/api/analyst/preferences/workspace", json={"dscr_floor": 2}).status_code == 403
    # Other workspaces see nothing.
    assert register(client).get("/api/analyst/preferences").json()["effective"]["dscr_floor"] is None


def test_validation(demo):
    for body in ({"dscr_floor": 0.5}, {"dscr_floor": 9}, {"exit_cap_stress_bps": 5}, {"exit_cap_stress_bps": 1000},
                 {"instructions": "x" * 2001}, {"notes": []}):
        assert demo.put("/api/analyst/preferences/personal", json=body).status_code == 422, body
    assert demo.post("/api/analyst/notes", json={"text": "   "}).status_code == 422
    assert demo.post("/api/analyst/notes", json={"text": "x" * 501}).status_code == 422


def test_notes_are_remembered_and_capped(demo):
    n = demo.post("/api/analyst/notes", json={"text": "Our lenders size to a 1.35x DSCR, not 1.25x."}).json()
    demo.put("/api/analyst/preferences/personal", json={"instructions": "Be brief."})  # keeps notes
    notes = demo.get("/api/analyst/preferences").json()["personal"]["notes"]
    assert [x["text"] for x in notes] == ["Our lenders size to a 1.35x DSCR, not 1.25x."]
    assert demo.delete(f"/api/analyst/notes/{n['id']}").status_code == 204
    assert demo.delete(f"/api/analyst/notes/{n['id']}").status_code == 404
    for i in range(30):
        assert demo.post("/api/analyst/notes", json={"text": f"note {i}"}).status_code == 201
    assert demo.post("/api/analyst/notes", json={"text": "one more"}).status_code == 422


def test_rule_based_analyst_applies_thresholds(demo):
    mf = _mf(demo)
    before = _ask(demo, mf["id"], "What is the DSCR and what sensitivity should I run?", learning=False)
    assert "DSCR floor" not in before and "your standard" not in before
    demo.put("/api/analyst/preferences/personal", json={"dscr_floor": 3.0, "exit_cap_stress_bps": 75})
    after = _ask(demo, mf["id"], "What is the DSCR and what sensitivity should I run?", learning=False)
    assert "Below your 3.00x DSCR floor" in after
    assert "your standard +75 bps stress" in after
    risk = _ask(demo, mf["id"], "What are the main risks?", learning=False)
    assert "Below your 3.00x DSCR floor" in risk


def test_ai_prompt_gets_preferences(demo, monkeypatch):
    captured = {}

    def fake_stream(context, history, question, learning=False, preferences=None):
        captured["preferences"] = preferences
        yield "ok"

    monkeypatch.setattr(ai, "ai_available", lambda: True)
    monkeypatch.setattr(ai, "stream_analyst", fake_stream)
    monkeypatch.setattr(ai, "model_name", lambda: "test-model")
    demo.put("/api/analyst/preferences/workspace", json={"instructions": "Write in IC memo style."})
    demo.post("/api/analyst/notes", json={"text": "Treat RUBS income as other income."})
    _ask(demo, _mf(demo)["id"], "Summarize the deal", learning=False)
    block = captured["preferences"]
    assert "Write in IC memo style." in block and "Treat RUBS income as other income." in block
    assert "never override the non-negotiable rules" in block


def test_prompt_block_empty_when_nothing_set():
    assert prompt_block({"dscr_floor": None, "exit_cap_stress_bps": None, "workspace_instructions": None,
                         "personal_instructions": None, "notes": []}) is None
