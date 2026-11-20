"""Pipeline velocity: how deals move through stages, how fast, and how often they close.

Built from each deal's creation time plus the audited stage changes, so it needs no extra
bookkeeping. Pure functions here; the router loads the data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import mean, median
from typing import Any

FLOW = ("sourcing", "underwriting", "ic", "closed")
STAGES = (*FLOW, "passed")


def aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


@dataclass
class Deal:
    id: str
    owner_id: str | None
    status: str
    created_at: datetime
    # (when, before, after), oldest first
    moves: list[tuple[datetime, str, str]] = field(default_factory=list)
    irr: float | None = None


def stays(d: Deal, now: datetime) -> list[tuple[str, float, bool]]:
    """(stage, days spent, still there) for each stay, in order."""
    out = []
    stage = d.moves[0][1] if d.moves else d.status
    start = aware(d.created_at)
    for when, _, after in d.moves:
        when = aware(when)
        out.append((stage, max((when - start).total_seconds(), 0) / 86400, False))
        stage, start = after, when
    out.append((stage, max((now - start).total_seconds(), 0) / 86400, True))
    return out


def reached(d: Deal) -> set[str]:
    """Stages a deal has been in. A deal created at a later stage counts as having passed the earlier ones."""
    seen = {s for s, _, _ in stays(d, aware(d.created_at))}
    for s in list(seen):
        if s in FLOW:
            seen.update(FLOW[:FLOW.index(s) + 1])
    return seen


def _r(v: float | None, d: int = 1) -> float | None:
    return None if v is None else round(v, d)


def metrics(deals: list[Deal], now: datetime) -> dict[str, Any]:
    funnel = {s: 0 for s in STAGES}
    days: dict[str, list[float]] = {s: [] for s in STAGES}
    aging: dict[str, list[float]] = {s: [] for s in STAGES}
    cycle: list[float] = []
    for d in deals:
        for s in reached(d):
            funnel[s] += 1
        for s, n, current in stays(d, now):
            (aging if current else days)[s].append(n)
        if d.status == "closed":
            closed_at = next((aware(w) for w, _, a in reversed(d.moves) if a == "closed"), None)
            if closed_at:
                cycle.append((closed_at - aware(d.created_at)).total_seconds() / 86400)
    conversion = {}
    for a, b in zip(FLOW, FLOW[1:]):
        conversion[f"{a}_to_{b}"] = funnel[b] / funnel[a] if funnel[a] else None
    decided = funnel["closed"] + sum(1 for d in deals if d.status == "passed")
    closed_irrs = [d.irr for d in deals if d.status == "closed" and d.irr is not None]
    return {
        "deals": len(deals),
        "funnel": funnel,
        "conversion": conversion,
        "win_rate": funnel["closed"] / decided if decided else None,
        "decided": decided,
        "avg_days_in_stage": {s: _r(mean(v)) if v else None for s, v in days.items() if s != "passed"},
        "in_stage_now": {s: {"count": len(aging[s]), "avg_days": _r(mean(aging[s])) if aging[s] else None}
                         for s in FLOW[:3]},
        "median_days_to_close": _r(median(cycle)) if cycle else None,
        "avg_irr_closed": mean(closed_irrs) if closed_irrs else None,
        "closed_with_irr": len(closed_irrs),
    }


CSV_ROWS: list[tuple[str, str, Any]] = [
    ("Deals in period", "deals", None),
    ("Reached underwriting", "funnel", "underwriting"),
    ("Reached IC", "funnel", "ic"),
    ("Closed", "funnel", "closed"),
    ("Sourcing to underwriting", "conversion", "sourcing_to_underwriting"),
    ("Underwriting to IC", "conversion", "underwriting_to_ic"),
    ("IC to closed", "conversion", "ic_to_closed"),
    ("Win rate (closed / decided)", "win_rate", None),
    ("Avg days in sourcing", "avg_days_in_stage", "sourcing"),
    ("Avg days in underwriting", "avg_days_in_stage", "underwriting"),
    ("Avg days in IC", "avg_days_in_stage", "ic"),
    ("Median days to close", "median_days_to_close", None),
    ("Avg levered IRR of closed deals", "avg_irr_closed", None),
]


def csv_value(m: dict[str, Any], key: str, sub: Any) -> str:
    v = m[key][sub] if sub else m[key]
    if v is None:
        return ""
    if key in ("conversion", "win_rate", "avg_irr_closed"):
        return f"{v * 100:.1f}%"
    return str(v)
