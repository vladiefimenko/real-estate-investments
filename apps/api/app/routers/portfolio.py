"""Portfolio-level analytics and a board / IC portfolio report."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..deps import OrgContext, viewer
from ..models import PROPERTY_STATUSES, Property
from ..services import branding as br
from ..services import portfolio as pf
from .properties import _latest_by_property

router = APIRouter(tags=["portfolio"])

Dimension = Literal["market", "state", "property_type", "sponsor", "vintage", "stage"]


def _props(ctx: OrgContext, statuses: list[str] | None, include_demo: bool):
    q = select(Property).where(Property.org_id == ctx.org.id, Property.deleted_at.is_(None))
    if statuses:
        bad = [s for s in statuses if s not in PROPERTY_STATUSES]
        if bad:
            raise HTTPException(422, f"Unknown stage: {', '.join(bad)}")
        q = q.where(Property.status.in_(statuses))
    else:
        q = q.where(Property.status != "passed")
    if not include_demo:
        q = q.where(Property.is_demo.is_(False))
    props = ctx.db.scalars(q).all()
    return props, _latest_by_property(ctx, [p.id for p in props])


@router.get("/portfolio")
def portfolio(dimension: Dimension = "market", status: str | None = None, include_demo: bool = True,
              ctx: OrgContext = Depends(viewer)):
    """Volume, NOI, weighted cap rate, equity-weighted IRR, risk and concentration per segment.
    Passed deals are excluded unless ``status`` asks for them."""
    props, results = _props(ctx, status.split(",") if status else None, include_demo)
    return {**pf.analyze(props, results, dimension), "dimensions": pf.DIMENSIONS,
            "demo_deals": sum(1 for p in props if p.is_demo)}


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="Portfolio Review", min_length=1, max_length=120)
    dimensions: list[Dimension] = Field(default_factory=lambda: ["market", "property_type"], min_length=1, max_length=6)
    statuses: list[str] | None = None
    include_demo: bool = True
    include_deal_list: bool = True
    include_concentration: bool = True


@router.post("/reports/portfolio")
def portfolio_report(body: ReportIn, ctx: OrgContext = Depends(viewer)):
    from ..services.report_pdf import portfolio_pack

    props, results = _props(ctx, body.statuses, body.include_demo)
    if not props:
        raise HTTPException(422, "No deals match these filters")
    sections = [pf.analyze(props, results, d) for d in dict.fromkeys(body.dimensions)]
    deals = sorted(([p, results.get(p.id)] for p in props), key=lambda x: -(x[0].purchase_price or 0))
    with br.active(ctx.org):
        data = portfolio_pack(body.title, sections, deals if body.include_deal_list else None,
                              include_concentration=body.include_concentration,
                              demo=any(p.is_demo for p in props), prepared_by=ctx.user.name or ctx.user.email)
    ctx.audit("report.portfolio", "organization", ctx.org.id, deals=len(props), dimensions=list(body.dimensions))
    ctx.db.commit()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", body.title).strip("-")[:50] or "portfolio"
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{slug}-{date.today():%Y-%m-%d}.pdf"'})
