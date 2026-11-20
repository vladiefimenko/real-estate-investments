"""Underwriting versions (every calculation is an immutable snapshot) and batch document processing."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from ..deps import OrgContext, analyst, deal_reader, viewer
from ..models import Document, Property, Scenario, UnderwritingResult, User
from ..services.extraction import process_document
from ..services.underwriting import ensure_result, run_and_store

router = APIRouter(tags=["versions"])

METRICS = [("noi_year1", "Year-1 NOI", "usd"), ("going_in_cap_rate", "Going-in cap rate", "pct"),
           ("irr_levered", "Levered IRR", "pct"), ("irr_unlevered", "Unlevered IRR", "pct"),
           ("equity_multiple_levered", "Equity multiple", "x"), ("dscr_year1", "Year-1 DSCR", "x"),
           ("cash_on_cash_year1", "Cash-on-cash (Yr 1)", "pct"), ("equity_invested", "Equity invested", "usd"),
           ("profit_levered", "Levered profit", "usd")]


def _scenario(ctx: OrgContext, scenario_id: uuid.UUID) -> tuple[Property, Scenario]:
    sc = ctx.db.get(Scenario, scenario_id)
    if sc is None or sc.org_id != ctx.org.id or sc.deleted_at is not None:
        raise HTTPException(404, "Scenario not found")
    return ctx.get_property(sc.property_id), sc


def _result(ctx: OrgContext, sc: Scenario, result_id: uuid.UUID) -> UnderwritingResult:
    r = ctx.db.get(UnderwritingResult, result_id)
    if r is None or r.org_id != ctx.org.id or r.scenario_id != sc.id:
        raise HTTPException(404, "Version not found")
    return r


def _out(r: UnderwritingResult, name: str | None, current: dict[str, Any]) -> dict[str, Any]:
    m = (r.full_cashflow_json or {}).get("metrics") or {}
    return {"id": str(r.id), "calculated_at": r.calculated_at.isoformat(), "by": name, "label": r.label,
            "engine_version": r.engine_version, "is_current": r.assumptions_snapshot == current,
            "metrics": {k: m.get(k) for k, _, _ in METRICS}}


@router.get("/scenarios/{scenario_id}/versions")
def list_versions(scenario_id: uuid.UUID, labelled_only: bool = False, ctx: OrgContext = Depends(deal_reader)):
    _, sc = _scenario(ctx, scenario_id)
    q = (select(UnderwritingResult, User.name).outerjoin(User, User.id == UnderwritingResult.calculated_by)
         .where(UnderwritingResult.scenario_id == sc.id, UnderwritingResult.org_id == ctx.org.id))
    if labelled_only:
        q = q.where(UnderwritingResult.label.is_not(None))
    rows = ctx.db.execute(q.order_by(UnderwritingResult.calculated_at.desc()).limit(100)).all()
    out, seen_current = [], False
    for r, name in rows:
        v = _out(r, name, sc.assumptions_json)
        v["is_current"] = v["is_current"] and not seen_current  # only the newest matching run is "current"
        seen_current = seen_current or v["is_current"]
        out.append(v)
    return {"scenario": {"id": str(sc.id), "name": sc.name}, "metrics": [{"key": k, "label": lbl, "fmt": f}
                                                                          for k, lbl, f in METRICS], "versions": out}


class LabelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = Field(default=None, max_length=120)


@router.post("/scenarios/{scenario_id}/versions/save")
def save_version(scenario_id: uuid.UUID, body: LabelIn, ctx: OrgContext = Depends(analyst)):
    """Name the current state of the scenario so it's easy to find and restore later."""
    prop, sc = _scenario(ctx, scenario_id)
    label = (body.label or "").strip()
    if not label:
        raise HTTPException(422, "Give the version a name")
    row = ensure_result(ctx, prop, sc)
    row.label = label
    ctx.audit("scenario.version_saved", "scenario", sc.id, property_id=prop.id, result_id=str(row.id), label=label)
    ctx.db.commit()
    return _out(row, ctx.user.name, sc.assumptions_json)


@router.put("/scenarios/{scenario_id}/versions/{result_id}/label")
def label_version(scenario_id: uuid.UUID, result_id: uuid.UUID, body: LabelIn, ctx: OrgContext = Depends(analyst)):
    prop, sc = _scenario(ctx, scenario_id)
    row = _result(ctx, sc, result_id)
    row.label = (body.label or "").strip() or None
    ctx.audit("scenario.version_labelled", "scenario", sc.id, property_id=prop.id, result_id=str(row.id),
              label=row.label)
    ctx.db.commit()
    return {"id": str(row.id), "label": row.label}


def _flatten(d: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    else:
        out[prefix] = d
    return out


@router.get("/scenarios/{scenario_id}/versions/compare")
def compare_versions(scenario_id: uuid.UUID, a: uuid.UUID, b: uuid.UUID, ctx: OrgContext = Depends(deal_reader)):
    """Assumption and metric differences between two versions (``a`` = older, ``b`` = newer)."""
    _, sc = _scenario(ctx, scenario_id)
    ra, rb = _result(ctx, sc, a), _result(ctx, sc, b)
    if ra.calculated_at > rb.calculated_at:
        ra, rb = rb, ra
    fa, fb = _flatten(ra.assumptions_snapshot), _flatten(rb.assumptions_snapshot)
    changes = [{"path": k, "before": fa.get(k), "after": fb.get(k)} for k in sorted(set(fa) | set(fb))
               if fa.get(k) != fb.get(k)]
    ma = (ra.full_cashflow_json or {}).get("metrics") or {}
    mb = (rb.full_cashflow_json or {}).get("metrics") or {}
    metrics = []
    for k, label, fmt in METRICS:
        x, y = ma.get(k), mb.get(k)
        metrics.append({"key": k, "label": label, "fmt": fmt, "before": x, "after": y,
                        "delta": (y - x) if isinstance(x, (int, float)) and isinstance(y, (int, float)) else None})
    return {"before": {"id": str(ra.id), "label": ra.label, "calculated_at": ra.calculated_at.isoformat()},
            "after": {"id": str(rb.id), "label": rb.label, "calculated_at": rb.calculated_at.isoformat()},
            "assumption_changes": changes, "metrics": metrics}


@router.post("/scenarios/{scenario_id}/versions/{result_id}/restore")
def restore_version(scenario_id: uuid.UUID, result_id: uuid.UUID, ctx: OrgContext = Depends(analyst)):
    """Put an earlier version's assumptions back and recalculate. Nothing is deleted: this adds a new version."""
    prop, sc = _scenario(ctx, scenario_id)
    row = _result(ctx, sc, result_id)
    sc.assumptions_json = dict(row.assumptions_snapshot)
    if sc.is_base:
        for f in ("purchase_price", "hold_period_years"):
            if f in sc.assumptions_json:
                setattr(prop, f, sc.assumptions_json[f])
    new = run_and_store(ctx, prop, sc)
    new.label = f"Restored: {row.label}"[:120] if row.label else None
    ctx.audit("scenario.restore", "scenario", sc.id, property_id=prop.id, restored_from=str(row.id),
              label=row.label, engine_version_then=row.engine_version, engine_version_now=new.engine_version)
    ctx.db.commit()
    return _out(new, ctx.user.name, sc.assumptions_json)


# ---------------------------------------------------------------- batch document processing
STAGE_PRIORITY = {"ic": 0, "underwriting": 1, "sourcing": 2, "closed": 3, "passed": 4}


@router.get("/org/document-queue")
def document_queue(status: str | None = None, ctx: OrgContext = Depends(viewer)):
    """Documents across the workspace's deals, with counts by processing status."""
    base = (select(Document, Property.name, Property.status).join(Property, Property.id == Document.property_id)
            .where(Document.org_id == ctx.org.id, Document.deleted_at.is_(None), Property.deleted_at.is_(None)))
    counts = dict(ctx.db.execute(
        select(Document.status, func.count()).join(Property, Property.id == Document.property_id)
        .where(Document.org_id == ctx.org.id, Document.deleted_at.is_(None), Property.deleted_at.is_(None))
        .group_by(Document.status)).all())
    if status:
        base = base.where(Document.status.in_(status.split(",")))
    rows = ctx.db.execute(base.order_by(Document.created_at.desc()).limit(500)).all()
    return {"counts": counts,
            "documents": [{"id": str(d.id), "name": d.name, "type": d.type, "status": d.status, "error": d.error,
                           "extractor": d.extractor, "property_id": str(d.property_id), "property_name": pname,
                           "property_stage": pstage, "created_at": d.created_at.isoformat()}
                          for d, pname, pstage in rows]}


class BatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    rules_only: bool = False


def _process_batch(ids: list[uuid.UUID], org_id: uuid.UUID, user_id: uuid.UUID, rules_only: bool) -> None:
    for doc_id in ids:  # one at a time, in priority order; a failure on one document doesn't stop the rest
        try:
            process_document(doc_id, org_id, user_id, rules_only)
        except Exception:  # noqa: BLE001 - process_document records its own errors on the document
            continue


@router.post("/documents/batch-extract", status_code=202)
def batch_extract(body: BatchIn, background: BackgroundTasks, ctx: OrgContext = Depends(analyst)):
    """Re-process many documents at once. Deals at IC go first, then underwriting, then the rest."""
    ids = list(dict.fromkeys(body.document_ids))
    rows = ctx.db.execute(select(Document, Property).join(Property, Property.id == Document.property_id).where(
        Document.id.in_(ids), Document.org_id == ctx.org.id, Document.deleted_at.is_(None),
        Property.deleted_at.is_(None))).all()
    if len(rows) != len(ids):
        raise HTTPException(404, "One or more documents weren't found")
    rows.sort(key=lambda dp: (STAGE_PRIORITY.get(dp[1].status, 9), dp[0].created_at))
    for d, _ in rows:
        d.status = "uploaded"
        d.error = None
    order = [d.id for d, _ in rows]
    ctx.audit("documents.batch_extract", "organization", ctx.org.id, count=len(order), rules_only=body.rules_only)
    ctx.db.commit()
    background.add_task(_process_batch, order, ctx.org.id, ctx.user.id, body.rules_only)
    return {"queued": len(order), "order": [str(i) for i in order]}
