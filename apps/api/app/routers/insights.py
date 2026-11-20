"""Pipeline velocity analytics and personal scorecards."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select

from ..deps import OrgContext, viewer
from ..models import AuditLog, Property
from ..services import velocity as vel
from .properties import _latest_by_property

router = APIRouter(tags=["insights"])


def _deals(ctx: OrgContext, days: int) -> tuple[list[vel.Deal], datetime]:
    now = datetime.now(timezone.utc)
    stmt = select(Property).where(Property.org_id == ctx.org.id, Property.deleted_at.is_(None),
                                  Property.is_demo.is_(False))
    props = [p for p in ctx.db.scalars(stmt).all() if not days or vel.aware(p.created_at) >= now - timedelta(days=days)]
    ids = [p.id for p in props]
    moves: dict = defaultdict(list)
    if ids:
        for a in ctx.db.scalars(select(AuditLog).where(
                AuditLog.org_id == ctx.org.id, AuditLog.action == "property.update",
                AuditLog.property_id.in_(ids)).order_by(AuditLog.created_at)):
            st = ((a.details or {}).get("changes") or {}).get("status")
            if st and st.get("before") != st.get("after"):
                moves[a.property_id].append((a.created_at, st["before"], st["after"]))
    latest = _latest_by_property(ctx, ids)
    return [vel.Deal(id=str(p.id), owner_id=str(p.owner_id) if p.owner_id else None, status=p.status,
                     created_at=p.created_at, moves=moves[p.id],
                     irr=latest[p.id].irr_levered if p.id in latest else None) for p in props], now


def _report(ctx: OrgContext, days: int) -> dict:
    deals, now = _deals(ctx, days)
    me = str(ctx.user.id)
    return {"days": days, "generated_at": now.isoformat(),
            "mine": vel.metrics([d for d in deals if d.owner_id == me], now),
            "workspace": vel.metrics(deals, now),
            "owners": len({d.owner_id for d in deals if d.owner_id})}


PERIOD = Query(default=365, ge=0, le=3650, description="Deals created in the last N days; 0 = all time")


@router.get("/insights/velocity")
def velocity(days: int = PERIOD, ctx: OrgContext = Depends(viewer)):
    """Your pipeline funnel, stage timing and win rate, next to the workspace as a whole (no names)."""
    return _report(ctx, days)


@router.get("/insights/scorecard.csv")
def scorecard(days: int = PERIOD, ctx: OrgContext = Depends(viewer)):
    r = _report(ctx, days)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Axiom pipeline scorecard", ctx.user.name or ctx.user.email,
                "All time" if not days else f"Deals created in the last {days} days", r["generated_at"][:10]])
    w.writerow(["Metric", "You", "Workspace"])
    for label, key, sub in vel.CSV_ROWS:
        w.writerow([label, vel.csv_value(r["mine"], key, sub), vel.csv_value(r["workspace"], key, sub)])
    ctx.audit("insights.scorecard_export", "organization", ctx.org.id, days=days)
    ctx.db.commit()
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="pipeline-scorecard.csv"'})
