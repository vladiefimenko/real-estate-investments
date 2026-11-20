"""Properties / deals CRUD and pipeline listing."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select

from ..deps import OrgContext, admin, analyst, deal_reader, viewer
from ..features import PLANS
from ..models import (
    PROPERTY_STATUSES,
    ROLE_RANK,
    DealShare,
    OrganizationMember,
    Property,
    Scenario,
    UnderwritingResult,
    User,
)
from ..services.workflow import change_status, unmet
from ..schemas import PropertyCreate, PropertyOut, PropertySummary, PropertyUpdate
from ..services.property_types import catalogue, default_assumptions
from ..services.underwriting import headline, run_and_store, sync_property_to_scenarios

SYSTEM_ATTRIBUTES = ("ic", "waterfall", "development")

router = APIRouter(tags=["properties"])


@router.get("/property-types")
def property_types():
    return catalogue()


def _latest_by_property(ctx: OrgContext, ids: list[uuid.UUID]) -> dict[uuid.UUID, UnderwritingResult]:
    """Latest base-scenario result per property in one query."""
    if not ids:
        return {}
    base_ids = select(Scenario.id).where(Scenario.property_id.in_(ids), Scenario.is_base.is_(True),
                                         Scenario.deleted_at.is_(None))
    rows = ctx.db.scalars(
        select(UnderwritingResult)
        .where(UnderwritingResult.org_id == ctx.org.id, UnderwritingResult.scenario_id.in_(base_ids))
        .order_by(UnderwritingResult.calculated_at.desc())
    ).all()
    out: dict[uuid.UUID, UnderwritingResult] = {}
    for r in rows:
        out.setdefault(r.property_id, r)
    return out


@router.get("/properties", response_model=list[PropertySummary])
def list_properties(
    status: str | None = None,
    property_type: str | None = None,
    owner_id: uuid.UUID | None = None,
    q: str | None = None,
    ctx: OrgContext = Depends(deal_reader),
):
    stmt = select(Property, User.name).outerjoin(User, User.id == Property.owner_id).where(
        Property.org_id == ctx.org.id, Property.deleted_at.is_(None))
    if ctx.is_external:  # lenders and partners see only the deals shared with them
        stmt = stmt.where(Property.id.in_(select(DealShare.property_id).where(DealShare.user_id == ctx.user.id)))
    if status:
        stmt = stmt.where(Property.status.in_(status.split(",")))
    if property_type:
        stmt = stmt.where(Property.property_type.in_(property_type.split(",")))
    if owner_id:
        stmt = stmt.where(Property.owner_id == owner_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Property.name).like(like), func.lower(Property.city).like(like),
                              func.lower(Property.state).like(like)))
    rows = ctx.db.execute(stmt.order_by(Property.updated_at.desc())).all()
    latest = _latest_by_property(ctx, [p.id for p, _ in rows])
    return [
        PropertySummary(**PropertyOut.model_validate(p).model_dump(), owner_name=name, latest=headline(latest.get(p.id)))
        for p, name in rows
    ]


@router.post("/properties", response_model=PropertySummary, status_code=201)
def create_property(body: PropertyCreate, ctx: OrgContext = Depends(analyst)):
    plan = PLANS.get(ctx.org.plan, PLANS["starter"])
    count = ctx.db.scalar(select(func.count()).select_from(Property).where(
        Property.org_id == ctx.org.id, Property.deleted_at.is_(None))) or 0
    if plan["max_deals"] is not None and count >= plan["max_deals"]:
        raise HTTPException(402, f"The {plan['label']} plan allows {plan['max_deals']} active deals")
    data = body.model_dump(exclude={"owner_id", "starter"})
    prop = Property(org_id=ctx.org.id, created_by=ctx.user.id, updated_by=ctx.user.id,
                    owner_id=body.owner_id or ctx.user.id, **data)
    ctx.db.add(prop)
    ctx.db.flush()
    assumptions = default_assumptions(body.property_type, body.purchase_price, body.hold_period_years,
                                      body.units, body.rentable_sf,
                                      starter=body.starter.model_dump() if body.starter else None)
    base = Scenario(org_id=ctx.org.id, property_id=prop.id, name="Base Case", is_base=True,
                    description="Template assumptions – replace with verified document data.",
                    assumptions_json=assumptions, created_by=ctx.user.id)
    ctx.db.add(base)
    ctx.db.flush()
    ctx.audit("property.create", "property", prop.id, property_id=prop.id, name=prop.name)
    row = run_and_store(ctx, prop, base)
    ctx.db.commit()
    return PropertySummary(**PropertyOut.model_validate(prop).model_dump(), owner_name=None, latest=headline(row))


@router.get("/properties/{property_id}", response_model=PropertySummary)
def get_property(property_id: uuid.UUID, ctx: OrgContext = Depends(deal_reader)):
    prop = ctx.get_property(property_id)
    owner = ctx.db.get(User, prop.owner_id) if prop.owner_id else None
    latest = _latest_by_property(ctx, [prop.id]).get(prop.id)
    return PropertySummary(**PropertyOut.model_validate(prop).model_dump(), owner_name=owner.name if owner else None,
                           latest=headline(latest))


@router.patch("/properties/{property_id}", response_model=PropertyOut)
def update_property(property_id: uuid.UUID, body: PropertyUpdate, ctx: OrgContext = Depends(analyst)):
    prop = ctx.get_property(property_id)
    changes = body.model_dump(exclude_unset=True)
    override = changes.pop("override_requirements", False)
    new_status = changes.pop("status", None)
    if new_status is not None:
        change_status(ctx, prop, new_status, override=override)
    if not changes:
        ctx.db.commit()
        return prop
    if "attributes" in changes:
        # Merge, never replace: keys owned by other features (IC votes, profit split, development inputs) can only
        # change through their own endpoints, so a stale edit form can't overwrite them. Empty values remove a key.
        merged = dict(prop.attributes or {})
        for k, v in (changes["attributes"] or {}).items():
            if k in SYSTEM_ATTRIBUTES:
                continue
            if v is None or v == "":
                merged.pop(k, None)
            else:
                merged[k] = v
        changes["attributes"] = merged
    before = {k: getattr(prop, k) for k in changes}
    for k, v in changes.items():
        setattr(prop, k, v)
    prop.updated_by = ctx.user.id
    sync_property_to_scenarios(ctx, prop, changes)
    ctx.audit("property.update", "property", prop.id, property_id=prop.id,
              changes={k: {"before": _jsonable(before[k]), "after": _jsonable(v)} for k, v in changes.items()})
    ctx.db.commit()
    return prop


class BulkStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    status: str
    override_requirements: bool = False

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in PROPERTY_STATUSES:
            raise ValueError(f"Status must be one of: {', '.join(PROPERTY_STATUSES)}")
        return v


@router.post("/properties/bulk-status")
def bulk_status(body: BulkStatusIn, ctx: OrgContext = Depends(analyst)):
    """Move several deals to one stage. All-or-nothing: any unknown deal aborts the change."""
    props = [ctx.get_property(pid) for pid in dict.fromkeys(body.ids)]
    override = body.override_requirements and ROLE_RANK[ctx.role] >= ROLE_RANK["admin"]
    if not override:  # check every deal before changing any of them
        blocked = {p.name: miss for p in props if p.status != body.status and (miss := unmet(ctx, p, body.status))}
        if blocked:
            raise HTTPException(422, {"message": f"{len(blocked)} deal(s) aren't ready for this stage",
                                      "blocked": blocked, "can_override": ROLE_RANK[ctx.role] >= ROLE_RANK["admin"]})
    changed = [str(p.id) for p in props if change_status(ctx, p, body.status, override=override, bulk=True)]
    ctx.db.commit()
    return {"status": body.status, "updated": changed, "unchanged": len(props) - len(changed)}


@router.delete("/properties/{property_id}", status_code=204)
def delete_property(property_id: uuid.UUID, ctx: OrgContext = Depends(admin)):
    from ..models import utcnow

    prop = ctx.get_property(property_id)
    prop.deleted_at = utcnow()
    ctx.audit("property.delete", "property", prop.id, property_id=prop.id, name=prop.name)
    ctx.db.commit()
    return Response(status_code=204)


def _jsonable(v):
    if isinstance(v, (str, int, float, bool, dict, list)) or v is None:
        return v
    return str(v)


# ------------------------------------------------------------------ sharing with external members
class ShareIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: uuid.UUID


@router.get("/properties/{property_id}/shares")
def list_shares(property_id: uuid.UUID, ctx: OrgContext = Depends(admin)):
    """External members of this workspace, and whether each can see this deal."""
    prop = ctx.get_property(property_id)
    shared = set(ctx.db.scalars(select(DealShare.user_id).where(DealShare.property_id == prop.id)))
    rows = ctx.db.execute(select(User.id, User.name, User.email).join(
        OrganizationMember, OrganizationMember.user_id == User.id).where(
        OrganizationMember.org_id == ctx.org.id, OrganizationMember.role == "external").order_by(User.name)).all()
    return [{"user_id": str(uid), "name": name, "email": email, "shared": uid in shared} for uid, name, email in rows]


@router.post("/properties/{property_id}/shares", status_code=201)
def share_deal(property_id: uuid.UUID, body: ShareIn, ctx: OrgContext = Depends(admin)):
    prop = ctx.get_property(property_id)
    member = ctx.db.scalars(select(OrganizationMember).where(
        OrganizationMember.org_id == ctx.org.id, OrganizationMember.user_id == body.user_id)).first()
    if member is None or member.role != "external":
        raise HTTPException(422, "Deals can only be shared with external members of this workspace")
    exists = ctx.db.scalar(select(DealShare.id).where(DealShare.property_id == prop.id,
                                                      DealShare.user_id == body.user_id))
    if not exists:
        ctx.db.add(DealShare(org_id=ctx.org.id, property_id=prop.id, user_id=body.user_id, created_by=ctx.user.id))
        ctx.audit("deal.share", "property", prop.id, property_id=prop.id, user_id=str(body.user_id))
        ctx.db.commit()
    return {"property_id": str(prop.id), "user_id": str(body.user_id), "shared": True}


@router.delete("/properties/{property_id}/shares/{user_id}", status_code=204)
def unshare_deal(property_id: uuid.UUID, user_id: uuid.UUID, ctx: OrgContext = Depends(admin)):
    prop = ctx.get_property(property_id)
    share = ctx.db.scalars(select(DealShare).where(DealShare.property_id == prop.id,
                                                   DealShare.user_id == user_id)).first()
    if share is not None:
        ctx.db.delete(share)
        ctx.audit("deal.unshare", "property", prop.id, property_id=prop.id, user_id=str(user_id))
        ctx.db.commit()
    return Response(status_code=204)
