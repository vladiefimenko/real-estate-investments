"""Compare the values extracted from two documents of the same deal (e.g. this month's rent roll vs last)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Document, ExtractedData
from .extraction_fields import FIELDS

# Which value represents a document: a reviewed one beats a pending one; rejected values don't count.
_RANK = {"accepted": 3, "edited": 3, "superseded": 2, "pending": 1}
NUMERIC = {"currency", "percent", "integer", "number", "years"}


def current_values(db: Session, doc: Document) -> dict[str, ExtractedData]:
    rows = db.scalars(select(ExtractedData).where(ExtractedData.document_id == doc.id,
                                                  ExtractedData.status != "rejected")).all()
    best: dict[str, ExtractedData] = {}
    for r in rows:
        cur = best.get(r.field_path)
        if cur is None or (_RANK.get(r.status, 0), r.version) > (_RANK.get(cur.status, 0), cur.version):
            best[r.field_path] = r
    return best


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _unit_mix_diff(before: Any, after: Any) -> list[dict[str, Any]]:
    b = {u.get("name"): u for u in (before or []) if isinstance(u, dict)}
    a = {u.get("name"): u for u in (after or []) if isinstance(u, dict)}
    out = []
    for name in list(dict.fromkeys([*b, *a])):
        x, y = b.get(name) or {}, a.get(name) or {}
        out.append({"name": name, "units_before": x.get("units"), "units_after": y.get("units"),
                    "rent_before": x.get("in_place_rent_monthly"), "rent_after": y.get("in_place_rent_monthly"),
                    "status": "added" if not x else "removed" if not y else
                    "changed" if (x.get("units"), x.get("in_place_rent_monthly")) != (y.get("units"),
                                                                                 y.get("in_place_rent_monthly"))
                    else "same"})
    return out


def compare(db: Session, older: Document, newer: Document) -> dict[str, Any]:
    old, new = current_values(db, older), current_values(db, newer)
    rows = []
    for path, meta in FIELDS.items():
        o, n = old.get(path), new.get(path)
        if o is None and n is None:
            continue
        before, after = (o.value if o else None), (n.value if n else None)
        if o is None:
            change = "added"
        elif n is None:
            change = "removed"
        elif before == after:
            change = "same"
        else:
            change = "changed"
        row: dict[str, Any] = {
            "field_path": path, "label": meta["label"], "group": meta["group"], "kind": meta["kind"],
            "before": before, "after": after, "change": change,
            "before_status": o.status if o else None, "after_status": n.status if n else None,
            "before_page": o.source_page if o else None, "after_page": n.source_page if n else None,
            "delta": None, "delta_pct": None,
        }
        bn, an = _num(before), _num(after)
        if meta["kind"] in NUMERIC and bn is not None and an is not None and change == "changed":
            row["delta"] = an - bn
            row["delta_pct"] = (an - bn) / abs(bn) if bn else None
        if meta["kind"] == "unit_mix" and change != "same":
            row["unit_mix"] = _unit_mix_diff(before, after)
        rows.append(row)
    counts = {k: sum(r["change"] == k for r in rows) for k in ("changed", "added", "removed", "same")}
    return {"rows": rows, "counts": counts}
