"""Portfolio analytics: concentration and returns by market, type, sponsor, vintage and stage."""

from __future__ import annotations

from typing import Any

DIMENSIONS = {"market": "Market", "state": "State", "property_type": "Property type", "sponsor": "Sponsor",
              "vintage": "Vintage (year built)", "stage": "Stage"}
STAGE_LABELS = {"sourcing": "Sourcing", "underwriting": "Underwriting", "ic": "Investment Committee",
                "closed": "Closed", "passed": "Passed"}
TYPE_LABELS = {"multifamily": "Multifamily", "industrial": "Industrial", "office": "Office", "retail": "Retail",
               "mixed_use": "Mixed-Use", "hospitality": "Hospitality", "self_storage": "Self-Storage",
               "student_housing": "Student Housing", "land": "Development Land"}
CONCENTRATION_LIMIT = 0.40  # a single segment above this share of volume is flagged
UNASSIGNED = ("Unknown", "No sponsor set")  # placeholders, not real segments: never flagged as concentration


def vintage(year: int | None) -> str:
    if not year:
        return "Unknown"
    if year < 1980:
        return "Before 1980"
    if year < 2000:
        return "1980–1999"
    if year < 2010:
        return "2000–2009"
    if year < 2020:
        return "2010–2019"
    return "2020 or newer"


def segment_of(p: Any, dim: str) -> str:
    if dim == "market":
        return ", ".join(x for x in (p.city, p.state) if x) or "Unknown"
    if dim == "state":
        return p.state or "Unknown"
    if dim == "property_type":
        return TYPE_LABELS.get(p.property_type, p.property_type)
    if dim == "sponsor":
        s = (p.attributes or {}).get("sponsor")
        return s.strip() if isinstance(s, str) and s.strip() else "No sponsor set"
    if dim == "vintage":
        return vintage(p.year_built)
    return STAGE_LABELS.get(p.status, p.status)


def analyze(props: list[Any], results: dict[Any, Any], dim: str) -> dict[str, Any]:
    """``results`` maps property id -> latest base UnderwritingResult row (or is missing)."""
    groups: dict[str, dict[str, Any]] = {}
    for p in props:
        g = groups.setdefault(segment_of(p, dim), {"deals": 0, "volume": 0.0, "noi": 0.0, "cap_price": 0.0,
                                                   "irr_num": 0.0, "irr_den": 0.0, "risk_num": 0.0,
                                                   "risk_den": 0.0, "deal_names": []})
        price = p.purchase_price or 0.0
        g["deals"] += 1
        g["volume"] += price
        g["deal_names"].append(p.name)
        r = results.get(p.id)
        if r is None:
            continue
        g["noi"] += r.noi_year1 or 0.0
        g["cap_price"] += price
        equity = ((r.full_cashflow_json or {}).get("metrics") or {}).get("equity_invested") or 0.0
        if r.irr_levered is not None and equity > 0:
            g["irr_num"] += r.irr_levered * equity
            g["irr_den"] += equity
        if r.risk_score is not None and price > 0:
            g["risk_num"] += r.risk_score * price
            g["risk_den"] += price
    total_volume = sum(g["volume"] for g in groups.values())
    total_noi = sum(g["noi"] for g in groups.values())
    rows = []
    for key, g in groups.items():
        irr = g["irr_num"] / g["irr_den"] if g["irr_den"] else None
        risk = g["risk_num"] / g["risk_den"] if g["risk_den"] else None
        rows.append({
            "segment": key, "deals": g["deals"], "volume": g["volume"],
            "share": g["volume"] / total_volume if total_volume else None,
            "noi": g["noi"], "noi_share": g["noi"] / total_noi if total_noi else None,
            "cap_rate": g["noi"] / g["cap_price"] if g["cap_price"] else None,
            "irr_levered": irr, "risk_score": risk,
            # Levered IRR earned per 10 points of Axiom risk score: higher is better.
            "return_per_risk": irr / (risk / 10) if irr is not None and risk else None,
            "deal_names": sorted(g["deal_names"])[:12],
        })
    rows.sort(key=lambda r: -r["volume"])
    shares = [r["share"] for r in rows if r["share"]]
    hhi = sum(s * s for s in shares) if shares else None
    flags = [f"{r['segment']} is {r['share'] * 100:.0f}% of volume" for r in rows
             if r["share"] is not None and r["share"] > CONCENTRATION_LIMIT and len(rows) > 1
             and r["segment"] not in UNASSIGNED]
    all_irr = [(results[p.id].irr_levered, ((results[p.id].full_cashflow_json or {}).get("metrics") or {})
                .get("equity_invested") or 0.0) for p in props if p.id in results and results[p.id].irr_levered is not None]
    eq = sum(e for _, e in all_irr if e > 0)
    return {
        "dimension": dim, "dimension_label": DIMENSIONS[dim], "segments": rows,
        "totals": {"deals": len(props), "volume": total_volume, "noi": total_noi,
                   "irr_levered": sum(i * e for i, e in all_irr if e > 0) / eq if eq else None},
        "concentration": {"hhi": hhi, "top_share": rows[0]["share"] if rows else None,
                          "level": None if hhi is None else "high" if hhi > 0.25 else "moderate" if hhi > 0.15 else "low",
                          "flags": flags},
    }
