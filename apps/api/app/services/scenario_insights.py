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
