"""Pipeline velocity analytics and the personal scorecard."""

import csv
import io
from datetime import datetime, timedelta, timezone

from conftest import MF_PROPERTY
from test_roles import _join

from app.services.velocity import Deal, metrics, reached

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def d(days: float) -> datetime:
    return T0 + timedelta(days=days)


def test_metrics_math():
    deals = [
        # sourcing 10d -> underwriting 20d -> ic 5d -> closed
        Deal("a", "u1", "closed", T0, [(d(10), "sourcing", "underwriting"), (d(30), "underwriting", "ic"),
                                       (d(35), "ic", "closed")], irr=0.15),
        # sourcing 4d -> underwriting 6d -> passed
        Deal("b", "u1", "passed", T0, [(d(4), "sourcing", "underwriting"), (d(10), "underwriting", "passed")]),
        # still sourcing (created day 40)
        Deal("c", "u2", "sourcing", d(40)),
        # closed with no recorded history (e.g. imported at that stage): counts in the funnel, not in timing
        Deal("e", "u2", "closed", T0, irr=0.11),
    ]
    m = metrics(deals, now=d(50))
    assert m["deals"] == 4
    assert m["funnel"] == {"sourcing": 4, "underwriting": 3, "ic": 2, "closed": 2, "passed": 1}
    assert m["conversion"] == {"sourcing_to_underwriting": 0.75, "underwriting_to_ic": 2 / 3, "ic_to_closed": 1.0}
    assert m["win_rate"] == 2 / 3 and m["decided"] == 3
    assert m["avg_days_in_stage"]["sourcing"] == 7.0  # (10 + 4) / 2
    assert m["avg_days_in_stage"]["underwriting"] == 13.0  # (20 + 6) / 2
    assert m["avg_days_in_stage"]["ic"] == 5.0
    assert m["in_stage_now"]["sourcing"] == {"count": 1, "avg_days": 10.0}
    assert m["median_days_to_close"] == 35.0
    assert abs(m["avg_irr_closed"] - 0.13) < 1e-9
    empty = metrics([], now=d(1))
    assert empty["win_rate"] is None and empty["conversion"]["ic_to_closed"] is None


def test_reached_includes_backward_moves():
    deal = Deal("x", None, "underwriting", T0, [(d(1), "sourcing", "ic"), (d(2), "ic", "underwriting")])
    assert reached(deal) == {"sourcing", "underwriting", "ic"}


def test_velocity_endpoint_mine_vs_workspace(client, owner):
    a = owner.post("/api/properties", json={**MF_PROPERTY, "name": "Mine A"}).json()
    b = owner.post("/api/properties", json={**MF_PROPERTY, "name": "Mine B"}).json()
    owner.patch(f"/api/properties/{a['id']}", json={"status": "underwriting"})
    owner.patch(f"/api/properties/{a['id']}", json={"status": "ic"})
    owner.patch(f"/api/properties/{a['id']}", json={"status": "closed"})
    owner.patch(f"/api/properties/{b['id']}", json={"status": "passed"})
    analyst = _join(client, owner, "analyst")
    analyst.post("/api/properties", json={**MF_PROPERTY, "name": "Theirs"})

    r = owner.get("/api/insights/velocity").json()
    assert r["mine"]["deals"] == 2 and r["workspace"]["deals"] == 3 and r["owners"] == 2
    assert r["mine"]["funnel"]["closed"] == 1 and r["mine"]["win_rate"] == 0.5
    assert r["mine"]["avg_irr_closed"] is not None and r["mine"]["median_days_to_close"] is not None
    assert analyst.get("/api/insights/velocity").json()["mine"]["deals"] == 1
    # Nothing identifies other members.
    assert "Theirs" not in str(r) and analyst.user_id not in str(r)


def test_demo_deals_and_other_workspaces_are_excluded(client, owner, demo):
    assert demo.get("/api/insights/velocity").json()["workspace"]["deals"] == 0
    owner.post("/api/properties", json=MF_PROPERTY)
    assert owner.get("/api/insights/velocity").json()["workspace"]["deals"] == 1


def test_scorecard_csv_and_access(client, owner):
    owner.post("/api/properties", json=MF_PROPERTY)
    r = owner.get("/api/insights/scorecard.csv", params={"days": 90})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[1] == ["Metric", "You", "Workspace"] and rows[2] == ["Deals in period", "1", "1"]
    assert owner.get("/api/insights/velocity", params={"days": -1}).status_code == 422
    assert _join(client, owner, "viewer").get("/api/insights/velocity").status_code == 200
    assert _join(client, owner, "external").get("/api/insights/velocity").status_code == 403
