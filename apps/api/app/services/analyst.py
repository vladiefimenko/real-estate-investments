"""Deal context assembly for the AI Analyst, plus a deterministic fallback analyst."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ..deps import OrgContext
from ..models import Document, ExtractedData, Property, Scenario
from .report_pdf import mult, pct, usd

TRACE_KEYS = ("metric", "formula", "value")


def verified_fields(ctx: OrgContext, prop: Property) -> list[dict[str, Any]]:
    rows = ctx.db.execute(
        select(ExtractedData, Document.name).join(Document, Document.id == ExtractedData.document_id)
        .where(ExtractedData.property_id == prop.id, ExtractedData.status.in_(("accepted", "edited")))
        .order_by(ExtractedData.field_path)
    ).all()
    return [{"field_path": e.field_path, "label": e.label, "value": e.value, "status": e.status,
             "document": name, "source_page": e.source_page, "source_ref": e.source_ref,
             "source_excerpt": e.source_excerpt} for e, name in rows]


def build_context(ctx: OrgContext, prop: Property, scenario: Scenario, result: dict[str, Any],
                  scenarios: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    annual = [{k: round(v, 2) if isinstance(v, float) else v for k, v in row.items() if k != "expense_detail"}
              for row in result["annual"]]
    return {
        "deal": {"name": prop.name, "property_type": prop.property_type, "city": prop.city, "state": prop.state,
                 "status": prop.status, "units": prop.units, "rentable_sf": prop.rentable_sf,
                 "year_built": prop.year_built, "is_demo_data": prop.is_demo, "attributes": prop.attributes},
        "scenario": {"name": scenario.name, "is_base": scenario.is_base, "description": scenario.description},
        "assumptions": result["assumptions"],
        "metrics": result["metrics"],
        "sources_and_uses": result["sources_and_uses"],
        "exit": result["exit"],
        "annual_cash_flows": annual,
        "year1_expense_detail": result["annual"][0]["expense_detail"],
        "risk": result.get("risk"),
        "assumption_warnings": result.get("warnings"),
        "covenant_breaches": result.get("covenant_breaches"),
        "audit_trace": [{k: t.get(k) for k in TRACE_KEYS} for t in result.get("audit_trace", [])],
        "verified_document_data": verified_fields(ctx, prop),
        "other_scenarios": scenarios or [],
        "engine_version": result["engine_version"],
    }


def _lessons(context: dict[str, Any], q: str) -> list[str]:
    """Learning-mode explanations built only from the deal's own engine output."""
    m, a, ex = context["metrics"], context["assumptions"], context["exit"]
    su, y1 = context["sources_and_uses"], context["annual_cash_flows"][0]
    out: list[str] = []
    if "irr" in q or "return" in q:
        out.append(
            "**Learn: IRR (internal rate of return).** IRR is the yearly return that accounts for *when* money moves. "
            f"On this deal you invest {usd(su['common_equity'])} of equity at the start, receive "
            f"{usd(y1['btcf'])} of cash flow in year 1 (more or less in later years), and get "
            f"{usd(ex['net_proceeds_to_equity'])} back when you sell in year {ex['exit_year']}. The single yearly rate "
            f"that makes all of those flows worth exactly what you put in is the levered IRR: **{pct(m['irr_levered'])}**. "
            f"Read it together with the equity multiple ({mult(m['equity_multiple_levered'])}): the multiple says how much "
            "money you get back; IRR says how fast.")
    if any(k in q for k in ("dscr", "debt", "coverage", "loan", "leverage", "ltv")):
        if m["dscr_year1"] is None:
            out.append("**Learn: DSCR (debt service coverage ratio).** DSCR = NOI ÷ yearly loan payments. It shows how "
                       "many times the property's income covers its loan. This scenario has no loan, so there is "
                       "nothing to cover yet; add one on the Financing tab to see it.")
        else:
            out.append(
                "**Learn: DSCR (debt service coverage ratio).** DSCR = NOI ÷ yearly loan payments. Here: "
                f"{usd(m['noi_year1'])} ÷ {usd(y1['debt_service'])} = **{mult(m['dscr_year1'])}**, so year-1 income "
                "covers the loan payment that many times. Lenders commonly look for roughly 1.20–1.35x; below 1.00x "
                "the property cannot pay its loan from its own income.")
    if "cap" in q:
        out.append(
            "**Learn: cap rate.** The going-in cap rate is year-1 NOI ÷ purchase price: "
            f"{usd(m['noi_year1'])} ÷ {usd(a['purchase_price'])} = **{pct(m['going_in_cap_rate'])}**. It is the yield "
            "you would earn in year 1 if you paid all cash. The exit cap rate sets the sale price: "
            f"next year's NOI at sale ({usd(ex['forward_noi'])}) ÷ exit cap ({pct(ex['exit_cap_rate'])}) = "
            f"{usd(ex['gross_sale_price'])}. A higher exit cap means a lower sale price, which is the cautious choice.")
    if any(k in q for k in ("noi", "income", "expense", "opex", "revenue")):
        out.append(
            "**Learn: NOI (net operating income).** NOI is what the property earns from operations before loan "
            f"payments: income you expect to collect ({usd(m['egi_year1'])}) minus operating expenses "
            f"({usd(m['opex_year1'])}) = **{usd(m['noi_year1'])}**. Lenders size loans from it and buyers price the "
            "property from it, so every expense you miss makes the deal look better than it is.")
    if "risk" in q or "concern" in q or "weak" in q:
        out.append(
            "**Learn: the risk screen.** Axiom adds up penalty points for specific warning signs, such as thin debt "
            "coverage, high leverage, fast rent growth or an exit cap below the entry cap. Under 20 is low, 20–44 "
            "moderate, 45 and up high. It is a checklist to start the conversation, not a credit rating: click any "
            "flag on the Overview tab to see why it was raised.")
    return out


def _dscr_flag(m: dict[str, Any], floor: float | None) -> str | None:
    if not floor or m.get("dscr_year1") is None:
        return None
    low = [(label, v) for label, v in (("year-1", m["dscr_year1"]), ("minimum", m.get("min_dscr"))) if v is not None
           and v < floor]
    if not low:
        return None
    return (f"⚠️ **Below your {floor:.2f}x DSCR floor:** "
            + ", ".join(f"{label} DSCR {mult(v)}" for label, v in low) + ".")


def rules_answer(context: dict[str, Any], question: str, learning: bool = False,
                 prefs: dict[str, Any] | None = None) -> str:
    """Template answers drawn only from engine output – used when no AI model is configured.

    With ``learning`` on, each answered topic is followed by a plain-language lesson using the
    deal's own figures.
    """
    q = question.lower()
    m, a, ex = context["metrics"], context["assumptions"], context["exit"]
    trace = {t["metric"]: t for t in context["audit_trace"]}
    demo = "\n\n_Note: this is fictional demo data._" if context["deal"]["is_demo_data"] else ""
    parts: list[str] = []
    prefs = prefs or {}
    flag = _dscr_flag(m, prefs.get("dscr_floor"))
    stress = prefs.get("exit_cap_stress_bps")
    if "irr" in q or "return" in q:
        parts.append(
            f"**Returns.** Levered IRR is **{pct(m['irr_levered'])}** and unlevered IRR is "
            f"**{pct(m['irr_unlevered'])}**. {trace['Levered IRR']['formula']}. The levered flows start with "
            f"{usd(-context['sources_and_uses']['common_equity'])} of common equity and end with "
            f"{usd(ex['net_proceeds_to_equity'])} of net sale proceeds to equity in year {ex['exit_year']}. "
            f"Equity multiple: {mult(m['equity_multiple_levered'])}.")
    if any(k in q for k in ("dscr", "debt", "coverage", "loan", "leverage", "ltv")):
        if m["dscr_year1"] is None:
            parts.append("**Debt.** The scenario is unlevered (no senior loan), so DSCR and debt yield do not apply.")
        else:
            parts.append(
                f"**Debt.** Year-1 DSCR is **{mult(m['dscr_year1'])}** (NOI {usd(m['noi_year1'])} ÷ debt service "
                f"{usd(context['annual_cash_flows'][0]['debt_service'])}); minimum over the hold is "
                f"{mult(m['min_dscr'])}. Debt yield {pct(m['debt_yield_year1'])}, LTV {pct(m['ltv'], 1)}, "
                f"LTC {pct(m['ltc'], 1)}.")
            if flag:
                parts[-1] += "\n\n" + flag
    if "cap" in q:
        spread = (a["exit_cap_rate"] - m["going_in_cap_rate"]) * 10000
        parts.append(
            f"**Cap rates.** Going-in cap rate is {pct(m['going_in_cap_rate'])} (Year-1 NOI ÷ price). Exit cap is "
            f"{pct(a['exit_cap_rate'])}, a {spread:+.0f} bps spread. "
            + ("Exit below entry assumes cap-rate compression – test a higher exit cap."
               if spread < 0 else "Exit above entry builds in a cushion for cap-rate expansion."))
        if stress:
            parts[-1] += (f" Your standard stress test: exit cap {pct(a['exit_cap_rate'] + stress / 10000)} "
                          f"(+{stress} bps). Run it in the Scenarios tab.")
    if any(k in q for k in ("noi", "income", "expense", "opex", "revenue")):
        detail = ", ".join(f"{k} {usd(v)}" for k, v in context["year1_expense_detail"].items())
        parts.append(
            f"**NOI build-up (Year 1).** {trace['Effective Gross Income (Y1)']['formula']} = "
            f"{usd(m['egi_year1'])}; operating expenses {usd(m['opex_year1'])} ({detail}); "
            f"NOI = {usd(m['noi_year1'])}. Expense ratio {pct(m['expense_ratio_year1'], 1)}.")
    if "risk" in q or "concern" in q or "weak" in q:
        risk = context.get("risk") or {}
        items = [f"- {f['message']}" for f in risk.get("factors", [])]
        items += [f"- Assumption flag: {w['message']}" for w in context.get("assumption_warnings") or []]
        if flag:
            items.append(f"- {flag}")
        parts.append(f"**Risk screen** (score {risk.get('score')} / 100, {risk.get('level')}):\n"
                     + ("\n".join(items) if items else "- No screening flags triggered."))
    if "sensitiv" in q or "stress" in q or "downside" in q:
        parts.append(
            "**Suggested sensitivity ranges** (run them in the Scenarios tab – I don't compute new figures):\n"
            f"- Rent growth {pct(a['rent_growth'] - 0.01)} – {pct(a['rent_growth'] + 0.01)}\n"
            + (f"- Exit cap {pct(a['exit_cap_rate'])} – {pct(a['exit_cap_rate'] + stress / 10000)} "
               f"(your standard +{stress} bps stress)\n" if stress else
               f"- Exit cap {pct(a['exit_cap_rate'] - 0.005)} – {pct(a['exit_cap_rate'] + 0.005)}\n")
            +
            f"- Vacancy {pct(a['vacancy_rate'])} – {pct(a['vacancy_rate'] + 0.03)}\n"
            f"- Expense growth {pct(a['opex_growth'])} – {pct(a['opex_growth'] + 0.01)}")
    if not parts:
        parts.append(
            f"**{context['deal']['name']} – {context['scenario']['name']}.** NOI {usd(m['noi_year1'])}, going-in cap "
            f"{pct(m['going_in_cap_rate'])}, levered IRR {pct(m['irr_levered'])}, equity multiple "
            f"{mult(m['equity_multiple_levered'])}, DSCR {mult(m['dscr_year1'])}.\n\nAsk me about returns, debt "
            "coverage, cap rates, the NOI build-up, risks, or sensitivity ranges.")
        if flag:
            parts[-1] += "\n\n" + flag
    if learning:
        lessons = _lessons(context, q)
        parts.extend(lessons or [
            "**Learning mode.** Ask me to *teach* you a concept on this deal, for example: \"Teach me how DSCR "
            "works here\", \"Teach me what IRR means\" or \"Teach me how NOI is built\"."])
        parts.append("_Go deeper: open the Glossary from the left menu for definitions and rules of thumb._")
    return "\n\n".join(parts) + demo + "\n\n_Rule-based analyst (AI model not configured)._"
