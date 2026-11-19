"""Plain-language "what changed" explanations for a scenario versus the base case.

Attribution is computed by the deterministic engine, not estimated: the base case is
re-run with one changed assumption at a time set to the scenario's value. Each
driver's impact is the change that assumption alone causes. Because effects
interact (e.g. higher vacancy matters more when rents also grow slower), single
impacts do not have to add up to the total; the remainder is reported separately.
"""

from __future__ import annotations

import copy
from typing import Any

from axiom_engine import AssumptionError, run_underwriting

# Assumptions that are inputs for every deal but not "changes" worth explaining.
_IGNORED = {"revenue_mode"}

LABELS: dict[str, tuple[str, str]] = {
    # key: (label, kind) where kind is pct | usd | int | other
    "rent_growth": ("Rent growth", "pct"),
    "vacancy_rate": ("Vacancy", "pct"),
    "credit_loss_rate": ("Credit loss", "pct"),
    "opex_growth": ("Expense growth", "pct"),
    "exit_cap_rate": ("Exit cap rate", "pct"),
    "discount_rate": ("Discount rate", "pct"),
    "management_fee_pct": ("Management fee", "pct"),
    "selling_costs_pct": ("Selling costs", "pct"),
    "closing_costs_pct": ("Closing costs", "pct"),
    "other_income_growth": ("Other income growth", "pct"),
    "capex_growth": ("Reserve growth", "pct"),
    "purchase_price": ("Purchase price", "usd"),
    "upfront_capex": ("Upfront capex", "usd"),
    "capex_reserve_annual": ("Capital reserve", "usd"),
    "other_income": ("Other income", "usd"),
    "gross_potential_rent": ("Gross potential rent", "usd"),
    "rent_psf_annual": ("Rent per SF", "usd"),
    "hold_period_years": ("Hold period", "int"),
    "loan": ("Loan terms", "other"),
    "preferred_equity": ("Preferred equity", "other"),
    "unit_mix": ("Unit mix / rents", "other"),
    "expense_lines": ("Operating expense lines", "other"),
    "rent_growth_by_year": ("Year-by-year rent growth", "other"),
}

def _irr(assumptions: dict[str, Any], metric: str) -> float | None:
    try:
        return getattr(run_underwriting(assumptions).metrics, metric)
    except AssumptionError:
        return None


def _label(key: str) -> tuple[str, str]:
    return LABELS.get(key, (key.replace("_", " ").capitalize(), "other"))


def explain_scenario(base: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    """Compare a scenario's assumptions with the base case and attribute the IRR change.

    Uses levered IRR, or unlevered IRR when the base case has no levered IRR (e.g. no loan yet).
    """
    metric = "irr_levered" if _irr(base, "irr_levered") is not None else "irr_unlevered"
    base_irr, other_irr = _irr(base, metric), _irr(other, metric)
    changed = sorted(k for k in set(base) | set(other) if k not in _IGNORED and base.get(k) != other.get(k))
    drivers = []
    for key in changed:
        trial = copy.deepcopy(base)
        if key in other:
            trial[key] = copy.deepcopy(other[key])
        else:
            trial.pop(key, None)
        trial_irr = _irr(trial, metric)
        label, kind = _label(key)
        b, o = base.get(key), other.get(key)
        simple = isinstance(b, (int, float)) and isinstance(o, (int, float)) and not isinstance(b, bool)
        drivers.append({
            "key": key, "label": label, "kind": kind if simple else "other",
            "base_value": b if simple else None, "scenario_value": o if simple else None,
            "irr_impact": None if trial_irr is None or base_irr is None else trial_irr - base_irr,
        })
    drivers.sort(key=lambda d: -abs(d["irr_impact"] or 0))
    total = None if base_irr is None or other_irr is None else other_irr - base_irr
    explained = sum(d["irr_impact"] for d in drivers if d["irr_impact"] is not None)
    return {
        "metric": metric,
        "base_irr": base_irr,
        "scenario_irr": other_irr,
        "total_change": total,
        "interaction": None if total is None else total - explained,
        "drivers": drivers,
    }


# ------------------------------------------------------------------ tornado
# (path, label, kind, step, mode): mode "abs" adds ±step, "rel" multiplies by (1 ± step).
TORNADO_DRIVERS: list[tuple[str, str, str, float, str]] = [
    ("rent_growth", "Rent growth", "pct", 0.01, "abs"),
    ("vacancy_rate", "Vacancy", "pct", 0.02, "abs"),
    ("opex_growth", "Expense growth", "pct", 0.01, "abs"),
    ("exit_cap_rate", "Exit cap rate", "pct", 0.005, "abs"),
    ("purchase_price", "Purchase price", "usd", 0.05, "rel"),
    ("loan.interest_rate", "Interest rate", "pct", 0.01, "abs"),
    ("hold_period_years", "Hold period", "int", 2, "abs"),
]


def _metrics(assumptions: dict[str, Any]) -> dict[str, float | None] | None:
    try:
        m = run_underwriting(assumptions).metrics
    except AssumptionError:
        return None
    return {"irr_levered": m.irr_levered, "irr_unlevered": m.irr_unlevered,
            "equity_multiple": m.equity_multiple_levered}


def tornado(base: dict[str, Any]) -> dict[str, Any]:
    """One-at-a-time low/high runs for the main drivers, ranked by IRR swing.

    Each bar is two full engine runs of ``base`` with only that driver moved down and
    up by a fixed, documented step. Drivers that do not apply (e.g. interest rate on an
    unlevered deal) or whose moved value is invalid are left out.
    """
    from axiom_engine.scenarios import get_path, set_path

    base_m = _metrics(base) or {}
    metric = "irr_levered" if base_m.get("irr_levered") is not None else "irr_unlevered"
    rows = []
    for path, label, kind, step, mode in TORNADO_DRIVERS:
        try:
            value = get_path(base, path)
        except KeyError:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        if mode == "rel":
            low, high = value * (1 - step), value * (1 + step)
        else:
            low, high = value - step, value + step
        if kind == "int":
            low, high = max(1, int(low)), int(high)
        if path in ("vacancy_rate",):
            low = max(0.0, low)
        results = []
        for v in (low, high):
            trial = copy.deepcopy(base)
            set_path(trial, path, v)
            results.append(_metrics(trial))
        if any(r is None or r.get(metric) is None for r in results):
            continue
        lo, hi = results
        rows.append({
            "path": path, "label": label, "kind": kind, "base_value": value, "low_value": low, "high_value": high,
            "irr_low": lo[metric], "irr_high": hi[metric],
            "em_low": lo["equity_multiple"], "em_high": hi["equity_multiple"],
        })
    rows.sort(key=lambda r: -abs(r["irr_high"] - r["irr_low"]))
    return {"metric": metric, "base_irr": base_m.get(metric), "base_em": base_m.get("equity_multiple"), "drivers": rows}
