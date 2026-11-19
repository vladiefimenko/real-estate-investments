"""PDF reports: one-page deal summary and Investment Committee memorandum (reportlab)."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#0B1F3A")
GOLD = colors.HexColor("#C9A227")
INK = colors.HexColor("#101828")
MUTED = colors.HexColor("#667085")
LINE = colors.HexColor("#D0D5DD")
ZEBRA = colors.HexColor("#F5F7FA")

styles = getSampleStyleSheet()
S = {
    "h1": ParagraphStyle("h1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, textColor=NAVY,
                         spaceAfter=4, leading=22),
    "h2": ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11.5,
                         textColor=NAVY, spaceBefore=10, spaceAfter=4),
    "body": ParagraphStyle("body", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=12.5,
                           textColor=INK, alignment=TA_LEFT),
    "small": ParagraphStyle("small", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.5, leading=10,
                            textColor=MUTED),
    "metric_label": ParagraphStyle("ml", fontName="Helvetica", fontSize=7.5, textColor=MUTED, leading=9),
    "metric_value": ParagraphStyle("mv", fontName="Helvetica-Bold", fontSize=13, textColor=NAVY, leading=16),
}

TYPE_LABELS = {"multifamily": "Multifamily", "industrial": "Industrial", "office": "Office", "retail": "Retail",
               "mixed_use": "Mixed-Use", "hospitality": "Hospitality", "self_storage": "Self-Storage",
               "student_housing": "Student Housing", "land": "Development Land"}


def usd(v: float | None, decimals: int = 0) -> str:
    if v is None:
        return "n/a"
    s = f"${abs(v):,.{decimals}f}"
    return f"({s})" if v < 0 else s


def usd_short(v: float | None) -> str:
    if v is None:
        return "n/a"
    a = abs(v)
    if a >= 1e9:
        return f"${v / 1e9:,.2f}B"
    if a >= 1e6:
        return f"${v / 1e6:,.2f}M"
    if a >= 1e3:
        return f"${v / 1e3:,.0f}K"
    return usd(v)


def pct(v: float | None, d: int = 2) -> str:
    return "n/a" if v is None else f"{v * 100:.{d}f}%"


def mult(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.2f}x"


def _decorate(demo: bool, title: str):
    def draw(canvas, doc):
        canvas.saveState()
        w, h = LETTER
        canvas.setFillColor(NAVY)
        canvas.rect(0, h - 0.42 * inch, w, 0.42 * inch, fill=1, stroke=0)
        canvas.setFillColor(GOLD)
        canvas.rect(0, h - 0.46 * inch, w, 0.04 * inch, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(0.6 * inch, h - 0.28 * inch, "AXIOM")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(w - 0.6 * inch, h - 0.28 * inch, title)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.5)
        canvas.drawString(0.6 * inch, 0.4 * inch,
                          "Calculations by the Axiom deterministic financial engine. AI-drafted text, where present, "
                          "is labelled and must be reviewed. Not investment advice.")
        canvas.drawRightString(w - 0.6 * inch, 0.4 * inch, f"Page {doc.page}")
        if demo:
            canvas.setFillColor(colors.Color(0.85, 0.15, 0.15, alpha=0.12))
            canvas.setFont("Helvetica-Bold", 44)
            canvas.translate(w / 2, h / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 20, "FOR DEMONSTRATION")
            canvas.drawCentredString(0, -36, "PURPOSES ONLY")
        canvas.restoreState()

    return draw


def _metric_grid(items: list[tuple[str, str]], cols: int = 4) -> Table:
    cells = [[Paragraph(label, S["metric_label"]), Paragraph(value, S["metric_value"])] for label, value in items]
    rows = []
    for i in range(0, len(cells), cols):
        chunk = cells[i:i + cols]
        while len(chunk) < cols:
            chunk.append(["", ""])
        rows.append([Table([[c[0]], [c[1]]], style=[("LEFTPADDING", (0, 0), (-1, -1), 0)]) for c in chunk])
    t = Table(rows, colWidths=[1.75 * inch] * cols)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _table(data: list[list[Any]], col_widths: list[float], header: bool = True, align_right_from: int = 1) -> Table:
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("ALIGN", (align_right_from, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8)]
    for i in range(1 if header else 0, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
    t.setStyle(TableStyle(style))
    return t


def _noi_chart(annual: list[dict[str, Any]]) -> Drawing:
    d = Drawing(3.4 * inch, 1.7 * inch)
    ch = VerticalBarChart()
    ch.x, ch.y, ch.width, ch.height = 35, 18, 3.4 * inch - 45, 1.7 * inch - 30
    ch.data = [[r["noi"] / 1000 for r in annual], [r["btcf"] / 1000 for r in annual]]
    # Always include zero so bar lengths are comparable (a truncated axis exaggerates differences).
    ch.valueAxis.valueMin = min(0.0, *ch.data[0], *ch.data[1])
    ch.categoryAxis.categoryNames = [f"Y{r['year']}" for r in annual]
    ch.categoryAxis.labels.fontSize = 6
    ch.valueAxis.labels.fontSize = 6
    ch.valueAxis.labelTextFormat = "$%dK"
    ch.bars[0].fillColor = NAVY
    ch.bars[1].fillColor = GOLD
    ch.bars.strokeColor = None
    ch.barSpacing = 1
    d.add(ch)
    return d


def _header_block(prop: Any, scenario_name: str) -> list[Any]:
    loc = ", ".join(x for x in (prop.address, prop.city, prop.state) if x)
    sub = f"{TYPE_LABELS.get(prop.property_type, prop.property_type)} · {loc or 'Location n/a'} · " \
          f"Scenario: {scenario_name} · Status: {prop.status.upper()}"
    out = [Paragraph(prop.name, S["h1"]), Paragraph(sub, S["small"])]
    if prop.is_demo:
        out.append(Paragraph("<font color='#B42318'><b>SAMPLE DATA – FOR DEMONSTRATION PURPOSES ONLY. "
                             "All figures are fictional.</b></font>", S["small"]))
    out.append(Spacer(1, 8))
    return out


def _headline_metrics(m: dict[str, Any], a: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        ("Purchase price", usd_short(a["purchase_price"])),
        ("Going-in cap rate", pct(m["going_in_cap_rate"])),
        ("Levered IRR", pct(m["irr_levered"])),
        ("Unlevered IRR", pct(m["irr_unlevered"])),
        ("Equity multiple", mult(m["equity_multiple_levered"])),
        ("Cash-on-cash (Y1)", pct(m["cash_on_cash_year1"])),
        ("DSCR (Y1)", mult(m["dscr_year1"])),
        ("LTV", pct(m["ltv"], 1)),
        ("NOI (Y1)", usd_short(m["noi_year1"])),
        ("NPV @ discount", usd_short(m["npv_levered"])),
        ("Exit cap", pct(a["exit_cap_rate"])),
        ("Hold period", f"{a['hold_period_years']} yrs"),
    ]


def _sources_uses(r: dict[str, Any]) -> Table:
    su = r["sources_and_uses"]
    tot = su["total_uses"] or 1
    data = [["Uses", "Amount", "%", "Sources", "Amount", "%"]]
    uses = [("Purchase price", su["purchase_price"]), ("Closing costs", su["closing_costs"]),
            ("Upfront capex", su["upfront_capex"]), ("Loan fees", su["loan_fees"])]
    sources = [("Senior loan", su["senior_loan"]), ("Preferred equity", su["preferred_equity"]),
               ("Common equity", su["common_equity"]), ("", None)]
    for (ul, uv), (sl, sv) in zip(uses, sources):
        data.append([ul, usd(uv), pct(uv / tot, 1), sl, usd(sv) if sv is not None else "",
                     pct(sv / tot, 1) if sv is not None else ""])
    data.append(["Total uses", usd(su["total_uses"]), "100.0%", "Total sources", usd(su["total_sources"]), "100.0%"])
    t = _table(data, [1.25 * inch, 1.0 * inch, 0.55 * inch, 1.25 * inch, 1.0 * inch, 0.55 * inch])
    t.setStyle(TableStyle([("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8), ("ALIGN", (3, 0), (3, -1), "LEFT")]))
    return t


def _cash_flow_table(r: dict[str, Any], max_years: int = 10) -> Table:
    annual = r["annual"][:max_years]
    head = ["($)"] + [f"Y{x['year']}" for x in annual]
    rows = [
        ("Gross potential rent", "gross_potential_rent"), ("Vacancy & credit", None), ("Other income", "other_income"),
        ("EGI", "effective_gross_income"), ("Operating expenses", "operating_expenses"), ("NOI", "noi"),
        ("Capital reserve", "capex_reserve"), ("Debt service", "debt_service"), ("Cash flow to equity", "btcf"),
    ]
    data = [head]
    for label, key in rows:
        if key is None:
            vals = [-(x["vacancy_loss"] + x["credit_loss"]) for x in annual]
        else:
            vals = [x[key] * (-1 if key in ("operating_expenses", "capex_reserve", "debt_service") else 1)
                    for x in annual]
        data.append([label] + [f"{v / 1000:,.0f}K" if abs(v) >= 1000 else f"{v:,.0f}" for v in vals])
    width = 7.3 * inch
    first = 1.35 * inch
    t = _table(data, [first] + [(width - first) / len(annual)] * len(annual))
    t.setStyle(TableStyle([("FONT", (0, 4), (-1, 4), "Helvetica-Bold", 7.5), ("FONT", (0, 6), (-1, 6),
                                                                              "Helvetica-Bold", 7.5),
                           ("FONT", (0, 9), (-1, 9), "Helvetica-Bold", 7.5), ("FONTSIZE", (0, 1), (-1, -1), 7)]))
    return t


def one_pager(prop: Any, scenario_name: str, r: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.6 * inch, title=f"{prop.name} – Deal Summary",
                            author="Axiom")
    a, m = r["assumptions"], r["metrics"]
    story: list[Any] = _header_block(prop, scenario_name)
    story.append(_metric_grid(_headline_metrics(m, a)))
    story.append(Spacer(1, 8))
    left = [Paragraph("Sources &amp; Uses", S["h2"]), _sources_uses(r)]
    risk = r.get("risk", {})
    risk_lines = [Paragraph(f"Risk score: <b>{risk.get('score', 'n/a')}</b> ({risk.get('level', 'n/a')})",
                            S["body"])]
    for f in risk.get("factors", [])[:5]:
        risk_lines.append(Paragraph(f"• {f['message']}", S["body"]))
    if not risk.get("factors"):
        risk_lines.append(Paragraph("• No screening flags triggered.", S["body"]))
    story.append(KeepTogether(left))
    story.append(Spacer(1, 4))
    row = Table([[[Paragraph("NOI vs. cash flow to equity ($K)", S["h2"]), _noi_chart(r["annual"])],
                  [Paragraph("Risk screen", S["h2"]), *risk_lines]]], colWidths=[3.6 * inch, 3.7 * inch])
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(row)
    story.append(Paragraph("Annual cash flow", S["h2"]))
    story.append(_cash_flow_table(r))
    ex = r["exit"]
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"Exit in year {ex['exit_year']} at a {pct(ex['exit_cap_rate'])} cap on forward NOI of "
        f"{usd(ex['forward_noi'])}: gross value {usd(ex['gross_sale_price'])}, net proceeds to equity "
        f"{usd(ex['net_proceeds_to_equity'])}. Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}, "
        f"engine v{r['engine_version']}.", S["small"]))
    doc.build(story, onFirstPage=_decorate(prop.is_demo, "One-Page Deal Summary"),
              onLaterPages=_decorate(prop.is_demo, "One-Page Deal Summary"))
    return buf.getvalue()


def _executive_summary(prop: Any, r: dict[str, Any]) -> str:
    a, m = r["assumptions"], r["metrics"]
    lev = m["irr_levered"]
    parts = [
        f"Axiom underwrote the acquisition of {prop.name}, a {TYPE_LABELS.get(prop.property_type, '').lower()} "
        f"asset{' in ' + prop.city if prop.city else ''}, at {usd(a['purchase_price'])} "
        f"({pct(m['going_in_cap_rate'])} going-in cap rate on year-one NOI of {usd(m['noi_year1'])}).",
        f"Over a {a['hold_period_years']}-year hold with exit at a {pct(a['exit_cap_rate'])} cap rate, the base case "
        f"produces a {pct(lev)} levered IRR ({pct(m['irr_unlevered'])} unlevered) and a "
        f"{mult(m['equity_multiple_levered'])} equity multiple on {usd(m['equity_invested'])} of common equity.",
    ]
    if m["dscr_year1"] is not None:
        parts.append(f"Senior debt of {usd(m['loan_amount'])} ({pct(m['ltv'], 1)} LTV) is covered "
                     f"{mult(m['dscr_year1'])} in year one (minimum {mult(m['min_dscr'])} over the hold).")
    return " ".join(parts)


def ic_memo(prop: Any, scenario_name: str, r: dict[str, Any], scenarios: list[dict[str, Any]],
            sensitivity: dict[str, Any] | None, verified: list[dict[str, Any]],
            narrative: dict[str, str] | None = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.6 * inch, title=f"{prop.name} – IC Memorandum",
                            author="Axiom")
    a, m = r["assumptions"], r["metrics"]
    story: list[Any] = [Paragraph("Investment Committee Memorandum", S["small"])]
    story += _header_block(prop, scenario_name)
    story.append(Paragraph("1. Executive Summary", S["h2"]))
    story.append(Paragraph(_executive_summary(prop, r), S["body"]))
    if narrative and narrative.get("executive_summary"):
        story.append(Spacer(1, 4))
        story.append(Paragraph("<i>AI-drafted commentary (review before circulation):</i>", S["small"]))
        story.append(Paragraph(narrative["executive_summary"].replace("\n", "<br/>"), S["body"]))
    story.append(Spacer(1, 6))
    story.append(_metric_grid(_headline_metrics(m, a)))

    story.append(Paragraph("2. Property Overview", S["h2"]))
    facts = [["Attribute", "Value"],
             ["Property type", TYPE_LABELS.get(prop.property_type, prop.property_type)],
             ["Location", ", ".join(x for x in (prop.address, prop.city, prop.state, prop.zip_code) if x) or "n/a"],
             ["Units", f"{prop.units:,}" if prop.units else "n/a"],
             ["Rentable SF", f"{prop.rentable_sf:,.0f}" if prop.rentable_sf else "n/a"],
             ["Year built", str(prop.year_built or "n/a")],
             ["Price per unit / SF", f"{usd(m['price_per_unit'])} / {usd(m['price_per_sf'], 2)}"]]
    for k, v in (prop.attributes or {}).items():
        if not isinstance(v, (dict, list)):
            facts.append([k.replace("_", " ").title(), str(v)])
    story.append(_table(facts, [2.2 * inch, 5.1 * inch], align_right_from=2))

    story.append(Paragraph("3. Key Assumptions", S["h2"]))
    assum = [["Assumption", "Value", "Assumption", "Value"],
             ["Rent growth", pct(a["rent_growth"]), "Vacancy", pct(a["vacancy_rate"])],
             ["Expense growth", pct(a["opex_growth"]), "Credit loss", pct(a.get("credit_loss_rate", 0))],
             ["Exit cap rate", pct(a["exit_cap_rate"]), "Selling costs", pct(a.get("selling_costs_pct", 0))],
             ["Discount rate", pct(a["discount_rate"]), "Closing costs", pct(a.get("closing_costs_pct", 0))],
             ["Management fee", pct(a.get("management_fee_pct", 0)), "Upfront capex", usd(a.get("upfront_capex"))]]
    loan = a.get("loan")
    if loan:
        assum.append(["Loan amount", usd(m["loan_amount"]), "Interest rate",
                      pct((loan.get("index_rate", 0) + loan.get("spread", 0)) if loan.get("rate_type") == "floating"
                          else loan.get("interest_rate"))])
        assum.append(["Amortization", f"{loan.get('amortization_years')} yrs", "IO period",
                      f"{loan.get('io_years', 0)} yrs"])
    story.append(_table(assum, [1.6 * inch, 2.05 * inch, 1.6 * inch, 2.05 * inch]))

    story.append(Paragraph("4. Capitalization", S["h2"]))
    story.append(_sources_uses(r))
    story.append(PageBreak())
    story.append(Paragraph("5. Projected Cash Flow", S["h2"]))
    story.append(_cash_flow_table(r))
    story.append(Spacer(1, 6))
    story.append(_noi_chart(r["annual"][:10]))

    if scenarios:
        story.append(Paragraph("6. Scenario Analysis", S["h2"]))
        data = [["Scenario", "Rent gr.", "Vacancy", "Exit cap", "Levered IRR", "Eq. multiple", "DSCR Y1"]]
        for s in scenarios:
            k, h = s["key_assumptions"], s.get("metrics") or {}
            data.append([s["name"], pct(k.get("rent_growth")), pct(k.get("vacancy_rate")),
                         pct(k.get("exit_cap_rate")), pct(h.get("irr_levered")), mult(h.get("equity_multiple")),
                         mult(h.get("dscr"))])
        story.append(_table(data, [1.9 * inch] + [0.9 * inch] * 6))

    if sensitivity:
        story.append(Paragraph(f"7. Sensitivity – levered IRR ({sensitivity['row_path'].replace('_', ' ')} vs. "
                               f"{sensitivity['col_path'].replace('_', ' ')})", S["h2"]))
        data = [[""] + [pct(c) for c in sensitivity["col_values"]]]
        for rv, row in zip(sensitivity["row_values"], sensitivity["grid"]):
            data.append([pct(rv)] + [pct(v) for v in row])
        story.append(_table(data, [1.2 * inch] + [1.0 * inch] * len(sensitivity["col_values"])))

    story.append(Paragraph("8. Risk Factors", S["h2"]))
    risk = r.get("risk", {})
    story.append(Paragraph(f"Screening score {risk.get('score')} / 100 ({risk.get('level')}).", S["body"]))
    for f in risk.get("factors", []):
        story.append(Paragraph(f"• {f['message']} (+{f['points']})", S["body"]))
    for w in r.get("warnings", []):
        story.append(Paragraph(f"• Assumption flag – {w['message']}", S["body"]))
    for b in r.get("covenant_breaches", []):
        story.append(Paragraph(f"• Covenant – projected {b['covenant']} breach in year {b['year']} "
                               f"(threshold {b['threshold']}, projected {b['actual']:.2f})", S["body"]))
    if narrative and narrative.get("risks"):
        story.append(Paragraph("<i>AI-drafted risk commentary (review before circulation):</i>", S["small"]))
        story.append(Paragraph(narrative["risks"].replace("\n", "<br/>"), S["body"]))

    story.append(Paragraph("9. Sources &amp; Verification", S["h2"]))
    if verified:
        data = [["Field", "Verified value", "Source document", "Citation"]]
        for v in verified[:40]:
            val = v["value"]
            if isinstance(val, list):
                val = f"{len(val)} unit types"
            elif isinstance(val, float) and val < 1:
                val = pct(val)
            elif isinstance(val, (int, float)):
                val = f"{val:,.0f}"
            cite = f"p.{v['source_page']}" if v.get("source_page") else ""
            if v.get("source_ref"):
                cite = v["source_ref"]
            data.append([v["label"], str(val), v["document"][:38], cite])
        story.append(_table(data, [2.0 * inch, 1.4 * inch, 2.7 * inch, 1.2 * inch], align_right_from=4))
    else:
        story.append(Paragraph("No document-verified fields; assumptions are user-entered or template defaults.",
                               S["body"]))
    story.append(Paragraph("Appendix – Calculation Audit Trace", S["h2"]))
    trace = [["Metric", "Formula", "Value"]]
    for t in r.get("audit_trace", []):
        v = t.get("value")
        trace.append([t["metric"], Paragraph(t["formula"], S["small"]),
                      f"{v:,.4f}" if isinstance(v, float) and abs(v) < 10 else
                      (f"{v:,.0f}" if isinstance(v, (int, float)) else "n/a")])
    story.append(_table(trace, [2.0 * inch, 4.0 * inch, 1.3 * inch]))
    deco = _decorate(prop.is_demo, "Investment Committee Memorandum")
    doc.build(story, onFirstPage=deco, onLaterPages=deco)
    return buf.getvalue()


# ---------------------------------------------------------------- junior analyst pack
# Plain-language notes for the annotated-assumptions page. Kept short; the in-app
# glossary (apps/web/src/lib/glossary.ts) holds the full definitions.
ASSUMPTION_NOTES: list[tuple[str, str, str, str]] = [
    # (assumption key, label, kind, what to check)
    ("purchase_price", "Purchase price", "usd", "Compare price per unit or per SF with recent sales nearby."),
    ("hold_period_years", "Hold period", "years", "Match it to the business plan and the loan term."),
    ("vacancy_rate", "Vacancy", "pct", "Check the submarket's actual occupancy, not just the property's current rate."),
    ("credit_loss_rate", "Credit loss", "pct", "Tenants who don't pay; look for bad debt in the T12."),
    ("rent_growth", "Rent growth", "pct", "Above about 4% a year is aggressive in most markets; the risk screen flags it."),
    ("opex_growth", "Expense growth", "pct", "Taxes and insurance often rise faster than inflation."),
    ("management_fee_pct", "Management fee", "pct", "Usually charged as a share of collected income."),
    ("exit_cap_rate", "Exit cap rate", "pct", "Cautious models set it at or above the going-in cap rate."),
    ("selling_costs_pct", "Selling costs", "pct", "Broker fees and transfer costs at sale."),
    ("discount_rate", "Discount rate", "pct", "Your required return; used for NPV."),
]

GLOSSARY_APPENDIX: list[tuple[str, str]] = [
    ("NOI (net operating income)", "Income collected minus operating expenses, before loan payments."),
    ("Going-in cap rate", "Year-1 NOI ÷ purchase price: the first-year yield if you paid all cash."),
    ("Exit cap rate", "Cap rate assumed at sale. Sale price = next year's NOI ÷ exit cap."),
    ("IRR", "The yearly return that accounts for when money is invested and returned. Levered IRR uses the "
            "investor's cash flows after loan payments."),
    ("Equity multiple", "Total cash returned to investors ÷ cash invested. Ignores timing."),
    ("Cash-on-cash", "One year's cash flow to equity ÷ equity invested."),
    ("DSCR", "NOI ÷ yearly loan payments. Lenders commonly want about 1.20–1.35x."),
    ("LTV / LTC", "Loan as a share of value (LTV) or of total project cost (LTC)."),
    ("NPV", "Today's value of future cash flows at your required return, minus what you invest."),
    ("Vacancy & credit loss", "Rent lost to empty units and to tenants who don't pay."),
    ("Risk score", "Axiom's 0–100 screening score: penalty points for warning signs. Under 20 low, 45+ high."),
    ("Verification", "Values read from documents only enter the model after a person accepts or edits them."),
]


def _fmt(kind: str, v: Any) -> str:
    if v is None:
        return "n/a"
    if kind == "pct":
        return pct(v)
    if kind == "usd":
        return usd(v)
    if kind == "years":
        return f"{v} yrs"
    return str(v)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def junior_pack(prop: Any, scenario_name: str, r: dict[str, Any], prepared_by: str, reviewed_by: str | None,
                note: str | None, verified_count: int) -> bytes:
    """Cover note, one-page summary, annotated assumptions and a glossary appendix, for a junior analyst."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.6 * inch,
                            title=f"{prop.name} – Junior Analyst Report Pack", author=prepared_by)
    a, m = r["assumptions"], r["metrics"]
    now = datetime.now(timezone.utc)
    story: list[Any] = _header_block(prop, scenario_name)

    # 1. Cover note
    story.append(Paragraph("Cover note", S["h2"]))
    # Plain table cells are drawn verbatim (no markup), so they are not escaped.
    sign = _table([["Prepared by", prepared_by],
                   ["Reviewed by", reviewed_by or "________________________  (pending review)"],
                   ["Date", f"{now:%B %d, %Y}"], ["Scenario", scenario_name]],
                  [1.4 * inch, 5.9 * inch], header=False)
    sign.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "LEFT"), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8)]))
    story.append(sign)
    story.append(Spacer(1, 6))
    if note:
        story.append(Paragraph(_esc(note).replace("\n", "<br/>"), S["body"]))
        story.append(Spacer(1, 6))
    story.append(Paragraph("How to read this pack", S["h2"]))
    for line in (
        "<b>Page 2</b> summarises the deal: price, returns, leverage, sources &amp; uses and the risk screen.",
        "<b>Page 3</b> lists the key assumptions behind those numbers, with a note on what to check for each.",
        "<b>Page 4</b> defines the terms used. Every figure comes from Axiom's deterministic engine.",
        f"Verified document data: <b>{verified_count}</b> value(s) were accepted or edited by a person. "
        + ("Assumptions without verified data are starting estimates."
           if verified_count == 0 else "Other assumptions are the analyst's estimates or template defaults."),
    ):
        story.append(Paragraph(f"• {line}", S["body"]))
    story.append(PageBreak())

    # 2. Deal summary
    story.append(Paragraph("Deal summary", S["h2"]))
    story.append(_metric_grid(_headline_metrics(m, a)))
    story.append(Paragraph("Sources &amp; Uses", S["h2"]))
    story.append(_sources_uses(r))
    risk = r.get("risk", {})
    story.append(Paragraph(f"Risk screen: score <b>{risk.get('score', 'n/a')}</b> ({risk.get('level', 'n/a')})",
                           S["h2"]))
    for f in risk.get("factors", []) or [{"message": "No screening flags triggered."}]:
        story.append(Paragraph(f"• {_esc(f['message'])}", S["body"]))
    story.append(PageBreak())

    # 3. Annotated assumptions
    story.append(Paragraph("Key assumptions, annotated", S["h2"]))
    flagged = {w["field"]: w["message"] for w in r.get("warnings") or []}
    rows = [["Assumption", "Value", "What to check"]]
    for key, label, kind, check in ASSUMPTION_NOTES:
        if key not in a:
            continue
        comment = check + (f" <font color='#B54708'><b>Flag:</b> {_esc(flagged[key])}</font>" if key in flagged else "")
        rows.append([label, _fmt(kind, a.get(key)), Paragraph(comment, S["body"])])
    loan = a.get("loan")
    if loan:
        rows.append(["Loan", f"{pct(loan.get('interest_rate'))} rate",
                     Paragraph(f"LTV {pct(m['ltv'], 1)}, year-1 DSCR {mult(m['dscr_year1'])}. Confirm terms with a "
                               "lender quote.", S["body"])])
    else:
        rows.append(["Loan", "None", Paragraph("Unlevered: returns assume an all-cash purchase.", S["body"])])
    t = _table(rows, [1.5 * inch, 1.1 * inch, 4.7 * inch], align_right_from=1)
    t.setStyle(TableStyle([("ALIGN", (2, 0), (2, -1), "LEFT"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(t)
    story.append(PageBreak())

    # 4. Glossary appendix
    story.append(Paragraph("Glossary", S["h2"]))
    g = _table([["Term", "Meaning"]] + [[term, Paragraph(_esc(text), S["body"])] for term, text in GLOSSARY_APPENDIX],
               [1.9 * inch, 5.4 * inch])
    g.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "LEFT"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(g)
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Generated {now:%Y-%m-%d %H:%M UTC}, engine v{r['engine_version']}.", S["small"]))
    deco = _decorate(prop.is_demo, "Junior Analyst Report Pack")
    doc.build(story, onFirstPage=deco, onLaterPages=deco)
    return buf.getvalue()


# ---------------------------------------------------------------- multi-deal summary pack
def summary_pack(deals: list[tuple[Any, str, dict[str, Any]]]) -> bytes:
    """One comparison page across the selected deals, then a one-page summary of each."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.6 * inch, title="Deal summary pack", author="Axiom")
    any_demo = any(p.is_demo for p, _, _ in deals)
    story: list[Any] = [Paragraph("Deal summary pack", S["h1"]),
                        Paragraph(f"{len(deals)} deals · base-case figures recalculated at export · "
                                  f"{datetime.now(timezone.utc):%B %d, %Y}", S["small"]), Spacer(1, 8)]
    if any_demo:
        story.append(Paragraph("<font color='#B42318'><b>Includes fictional demo deals, marked [DEMO].</b></font>",
                               S["small"]))
    rows = [["Deal", "Type", "Stage", "Price", "Cap", "Lev. IRR", "Multiple", "DSCR", "Risk"]]
    for p, _, r in deals:
        m, a = r["metrics"], r["assumptions"]
        risk = r.get("risk") or {}
        rows.append([Paragraph(_esc(p.name), S["body"]), TYPE_LABELS.get(p.property_type, p.property_type),
                     p.status.upper() if p.status == "ic" else p.status.title(), usd_short(a["purchase_price"]),
                     pct(m["going_in_cap_rate"]), pct(m["irr_levered"]), mult(m["equity_multiple_levered"]),
                     mult(m["dscr_year1"]), f"{risk.get('score', 'n/a')} {risk.get('level', '')}".strip()])
    t = _table(rows, [1.75 * inch, 0.8 * inch, 0.8 * inch, 0.7 * inch, 0.55 * inch, 0.65 * inch, 0.65 * inch,
                      0.55 * inch, 0.85 * inch], align_right_from=3)
    t.setStyle(TableStyle([("ALIGN", (8, 0), (8, -1), "LEFT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(t)
    for p, scenario_name, r in deals:
        story.append(PageBreak())
        story.extend(_header_block(p, scenario_name))
        story.append(_metric_grid(_headline_metrics(r["metrics"], r["assumptions"])))
        story.append(Paragraph("Sources &amp; Uses", S["h2"]))
        story.append(_sources_uses(r))
        risk = r.get("risk") or {}
        story.append(Paragraph(f"Risk screen: score <b>{risk.get('score', 'n/a')}</b> ({risk.get('level', 'n/a')})",
                               S["h2"]))
        for f in risk.get("factors", []) or [{"message": "No screening flags triggered."}]:
            story.append(Paragraph(f"• {_esc(f['message'])}", S["body"]))
        story.append(Paragraph("Annual cash flow", S["h2"]))
        story.append(_cash_flow_table(r))
    deco = _decorate(any_demo, "Deal Summary Pack")
    doc.build(story, onFirstPage=deco, onLaterPages=deco)
    return buf.getvalue()


# ---------------------------------------------------------------- client presentation
def _presentation_frame(demo: bool, brand: str, title: str):
    from reportlab.lib.pagesizes import landscape

    def draw(canvas, doc):
        w, h = landscape(LETTER)
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, h - 0.5 * inch, w, 0.5 * inch, fill=1, stroke=0)
        canvas.setFillColor(GOLD)
        canvas.rect(0, h - 0.54 * inch, w, 0.04 * inch, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(0.6 * inch, h - 0.33 * inch, brand)
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(w - 0.6 * inch, h - 0.33 * inch, title)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.5)
        canvas.drawString(0.6 * inch, 0.35 * inch,
                          "Figures calculated by the Axiom deterministic engine from the stated assumptions. "
                          "For discussion only; not an offer or investment advice.")
        canvas.drawRightString(w - 0.6 * inch, 0.35 * inch, f"{doc.page}")
        if demo:
            canvas.setFillColor(colors.Color(0.85, 0.15, 0.15, alpha=0.12))
            canvas.setFont("Helvetica-Bold", 54)
            canvas.translate(w / 2, h / 2)
            canvas.rotate(25)
            canvas.drawCentredString(0, 20, "FOR DEMONSTRATION")
            canvas.drawCentredString(0, -46, "PURPOSES ONLY")
        canvas.restoreState()

    return draw


def presentation(prop: Any, scenario_name: str, r: dict[str, Any], *, title: str | None, prepared_for: str | None,
                 presenter: str, firm_name: str | None, include_risk: bool) -> bytes:
    """Landscape client deck: cover, investment highlights, cash flow, capital stack and exit."""
    from reportlab.lib.pagesizes import landscape

    buf = io.BytesIO()
    page = landscape(LETTER)
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                            topMargin=0.85 * inch, bottomMargin=0.6 * inch,
                            title=title or f"{prop.name} – Investment Overview", author=firm_name or presenter)
    a, m, ex, su = r["assumptions"], r["metrics"], r["exit"], r["sources_and_uses"]
    big = ParagraphStyle("big", parent=S["h1"], fontSize=30, leading=36, spaceAfter=10)
    lead = ParagraphStyle("lead", parent=S["body"], fontSize=13, leading=18, textColor=MUTED)
    kpi_v = ParagraphStyle("kv", parent=S["metric_value"], fontSize=22, leading=26)
    kpi_l = ParagraphStyle("kl", parent=S["metric_label"], fontSize=9, leading=11)
    loc = ", ".join(x for x in (prop.address, prop.city, prop.state) if x) or "Location on request"
    story: list[Any] = [Spacer(1, 1.1 * inch), Paragraph(_esc(title or prop.name), big),
                        Paragraph(f"{TYPE_LABELS.get(prop.property_type, prop.property_type)} · {_esc(loc)}", lead),
                        Spacer(1, 0.5 * inch)]
    meta = [["Prepared for", prepared_for or "—"],  # plain cells: drawn verbatim, not escaped
            ["Presented by", presenter + (f", {firm_name}" if firm_name else "")],
            ["Date", f"{datetime.now(timezone.utc):%B %d, %Y}"]]
    mt = Table(meta, colWidths=[1.6 * inch, 6 * inch])
    mt.setStyle(TableStyle([("FONT", (0, 0), (0, -1), "Helvetica-Bold", 10), ("FONT", (1, 0), (1, -1), "Helvetica", 10),
                            ("TEXTCOLOR", (0, 0), (-1, -1), INK), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(mt)
    if prop.is_demo:
        story.append(Spacer(1, 12))
        story.append(Paragraph("<font color='#B42318'><b>Sample deal: all figures are fictional.</b></font>", lead))
    story.append(PageBreak())

    # Investment highlights
    story.append(Paragraph("Investment highlights", S["h1"]))
    kpis = [("Purchase price", usd_short(a["purchase_price"])), ("Going-in cap rate", pct(m["going_in_cap_rate"])),
            ("Levered IRR", pct(m["irr_levered"])), ("Equity multiple", mult(m["equity_multiple_levered"])),
            ("Year-1 NOI", usd_short(m["noi_year1"])), ("Cash-on-cash (Y1)", pct(m["cash_on_cash_year1"])),
            ("DSCR (Y1)", mult(m["dscr_year1"])), ("Hold period", f"{a['hold_period_years']} years")]
    cells = [[Paragraph(v, kpi_v), Paragraph(lbl, kpi_l)] for lbl, v in kpis]
    grid = Table([[Table([[c[0]], [c[1]]]) for c in cells[i:i + 4]] for i in range(0, 8, 4)],
                 colWidths=[2.35 * inch] * 4, rowHeights=[1.05 * inch] * 2)
    grid.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 12)]))
    story.append(Spacer(1, 6))
    story.append(grid)
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        f"Scenario: <b>{_esc(scenario_name)}</b>. Exit in year {ex['exit_year']} at a {pct(ex['exit_cap_rate'])} cap "
        f"rate on forward NOI of {usd(ex['forward_noi'])}, for a gross sale price of {usd(ex['gross_sale_price'])}.",
        lead))
    story.append(PageBreak())

    # Cash flow + capital stack
    story.append(Paragraph("Cash flow and capital", S["h1"]))
    chart = _noi_chart(r["annual"])
    chart.scale(1.75, 1.75)
    chart.width, chart.height = chart.width * 1.75, chart.height * 1.75
    stack = [["Capital stack", ""], ["Senior loan", usd(su["senior_loan"])],
             ["Preferred equity", usd(su["preferred_equity"])], ["Common equity", usd(su["common_equity"])],
             ["Total", usd(su["total_sources"])]]
    st = _table(stack, [1.6 * inch, 1.4 * inch])
    st.setStyle(TableStyle([("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8)]))
    side = Table([[Paragraph("NOI (navy) and cash flow to equity (gold), $K", S["small"])], [chart]])
    row = Table([[side, st]], colWidths=[6.4 * inch, 3.2 * inch])
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(row)
    story.append(Spacer(1, 10))
    story.append(_cash_flow_table(r))

    if include_risk:
        story.append(PageBreak())
        story.append(Paragraph("Key considerations", S["h1"]))
        risk = r.get("risk") or {}
        for f in risk.get("factors", []) or [{"message": "No screening flags were triggered by the base case."}]:
            story.append(Paragraph(f"• {_esc(f['message'])}", lead))
        for w in r.get("warnings") or []:
            story.append(Paragraph(f"• Assumption to note: {_esc(w['message'])}", lead))

    frame = _presentation_frame(prop.is_demo, (firm_name or "AXIOM").upper()[:40], title or prop.name)
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()
