"""Equity distribution waterfall: how a deal's levered cash flows split between LP investors and the GP.

American-style, IRR-hurdle waterfall on annual periods:

1. **Return of capital + preferred return.** Distributions go to LP and GP in proportion to the equity
   each contributed until the LP has received its capital back plus the preferred return (an IRR of
   ``pref_rate``).
2. **Promote tiers.** Each further tier splits cash at a fixed GP share until the LP reaches that tier's
   IRR hurdle; the last tier has no hurdle and takes everything that is left.

Hurdles are tracked with one LP balance per hurdle rate: the balance starts at the LP's contribution,
compounds annually at the hurdle rate, rises with any capital call and falls with every LP distribution.
A tier is satisfied when its balance reaches zero, which is exactly when the LP's IRR equals the hurdle.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .assumptions import AssumptionError
from .tvm import irr, safe_div


def _validate(flows: Sequence[float], lp_share: float, pref_rate: float, tiers: list[dict[str, Any]]) -> None:
    errors: list[dict[str, str]] = []
    if len(flows) < 2 or flows[0] >= 0:
        errors.append({"field": "flows", "message": "Need an equity investment followed by at least one year of cash flow"})
    if not 0 < lp_share < 1:
        errors.append({"field": "lp_share", "message": "LP share of equity must be between 0% and 100%"})
    if not 0 <= pref_rate <= 0.5:
        errors.append({"field": "pref_rate", "message": "Preferred return must be between 0% and 50%"})
    if not tiers:
        errors.append({"field": "tiers", "message": "Add at least one promote tier"})
    last = pref_rate
    for i, t in enumerate(tiers):
        hurdle, gp = t.get("hurdle"), t.get("gp_share")
        if not isinstance(gp, (int, float)) or not 0 <= gp < 1:
            errors.append({"field": f"tiers[{i}].gp_share", "message": "GP share must be at least 0% and below 100%"})
        is_last = i == len(tiers) - 1
        if is_last and hurdle is not None:
            errors.append({"field": f"tiers[{i}].hurdle", "message": "The last tier takes everything left and has no hurdle"})
        if not is_last:
            if not isinstance(hurdle, (int, float)) or hurdle <= last or hurdle > 1:
                errors.append({"field": f"tiers[{i}].hurdle",
                               "message": "Each hurdle must be above the preferred return and the previous hurdle"})
            else:
                last = hurdle
    if errors:
        raise AssumptionError(errors)


def run_waterfall(flows: Sequence[float], lp_share: float, pref_rate: float,
                  tiers: list[dict[str, Any]]) -> dict[str, Any]:
    """Split levered equity cash flows (year 0 negative) between LP and GP.

    ``tiers``: ``[{"hurdle": 0.12, "gp_share": 0.20}, ..., {"hurdle": None, "gp_share": 0.30}]`` where
    ``gp_share`` is the GP's share of every dollar distributed in that tier (including its co-invest).
    """
    _validate(flows, lp_share, pref_rate, tiers)
    gp_pro_rata = 1 - lp_share
    rates = [pref_rate] + [t["hurdle"] for t in tiers[:-1]]
    splits = [gp_pro_rata] + [t["gp_share"] for t in tiers]
    names = ["Return of capital + preferred return"] + [
        f"Promote to {t['hurdle'] * 100:g}% LP IRR" if t["hurdle"] is not None else "Residual split" for t in tiers]

    lp_flows, gp_flows = [flows[0] * lp_share], [flows[0] * gp_pro_rata]
    balances = [-flows[0] * lp_share for _ in rates]
    tier_totals = [{"name": n, "gp_share": s, "lp": 0.0, "gp": 0.0} for n, s in zip(names, splits)]
    years = []
    for year, cash in enumerate(flows[1:], start=1):
        balances = [b * (1 + r) if b > 0 else b for b, r in zip(balances, rates)]
        by_tier = [0.0] * len(splits)
        if cash < 0:  # capital call, funded pro rata
            lp_amt, gp_amt = cash * lp_share, cash * gp_pro_rata
            balances = [b - lp_amt for b in balances]
        else:
            lp_amt = gp_amt = 0.0
            left = cash
            for j, gp_s in enumerate(splits):
                if left <= 0:
                    break
                if j < len(rates):
                    need = max(balances[j], 0.0)
                    take = min(left, need / (1 - gp_s))
                else:
                    take = left
                lp_part, gp_part = take * (1 - gp_s), take * gp_s
                lp_amt += lp_part
                gp_amt += gp_part
                by_tier[j] += take
                tier_totals[j]["lp"] += lp_part
                tier_totals[j]["gp"] += gp_part
                balances = [b - lp_part for b in balances]
                left -= take
        lp_flows.append(lp_amt)
        gp_flows.append(gp_amt)
        years.append({"year": year, "distributable": cash, "lp": lp_amt, "gp": gp_amt, "by_tier": by_tier})

    def side(f: list[float]) -> dict[str, Any]:
        contributed = -sum(x for x in f if x < 0)
        distributed = sum(x for x in f if x > 0)
        return {"contributed": contributed, "distributed": distributed, "profit": distributed - contributed,
                "irr": irr(f), "multiple": safe_div(distributed, contributed), "cash_flows": f}

    lp, gp = side(lp_flows), side(gp_flows)
    total_distributed = lp["distributed"] + gp["distributed"]
    gp["promote"] = gp["distributed"] - gp_pro_rata * total_distributed
    return {"lp": lp, "gp": gp, "tiers": tier_totals, "years": years, "deal_irr": irr(list(flows)),
            "lp_share": lp_share, "pref_rate": pref_rate}
