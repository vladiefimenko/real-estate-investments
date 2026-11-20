"""Saved dashboard views: a user's named filters and card/section layout. Each view is private to its owner."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from ..deps import OrgContext, viewer
from ..models import PROPERTY_STATUSES, SavedView
from ..services.property_types import PROPERTY_TYPES

router = APIRouter(tags=["views"])

METRICS = ("active_deals", "pipeline_volume", "aum", "cap_rate", "irr_median", "irr_range")
SECTIONS = ("pipeline", "exposure", "alerts", "activity", "recent_deals")
MAX_VIEWS = 20


def _ordered_subset(v: list[str], allowed: tuple[str, ...], what: str) -> list[str]:
    unknown = [x for x in v if x not in allowed]
    if unknown:
        raise ValueError(f"Unknown {what}: {', '.join(unknown)}")
    if len(set(v)) != len(v):
        raise ValueError(f"Each {what} may appear once")
    return v


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_type: str | None = None
    status: str | None = None
    mine_only: bool = False

    @field_validator("property_type")
    @classmethod
    def _type(cls, v: str | None) -> str | None:
        if v and v not in PROPERTY_TYPES:
            raise ValueError("Unknown property type")
        return v or None

    @field_validator("status")
    @classmethod
    def _status(cls, v: str | None) -> str | None:
        if v and v not in PROPERTY_STATUSES:
            raise ValueError("Unknown status")
        return v or None


class ViewConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filters: Filters = Filters()
    metrics: list[str] = Field(default_factory=lambda: list(METRICS), max_length=len(METRICS))
    sections: list[str] = Field(default_factory=lambda: list(SECTIONS), max_length=len(SECTIONS))

    @field_validator("metrics")
    @classmethod
    def _metrics(cls, v: list[str]) -> list[str]:
        return _ordered_subset(v, METRICS, "metric card")

    @field_validator("sections")
    @classmethod
    def _sections(cls, v: list[str]) -> list[str]:
        return _ordered_subset(v, SECTIONS, "section")


class ViewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    page: Literal["dashboard"] = "dashboard"
    config: ViewConfig
    is_default: bool = False

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Give the view a name")
        return v


class ViewPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=80)
    config: ViewConfig | None = None
    is_default: bool | None = None


def _out(v: SavedView) -> dict:
    return {"id": str(v.id), "name": v.name, "page": v.page, "config": v.config, "is_default": v.is_default,
            "updated_at": v.updated_at.isoformat()}


def _mine(ctx: OrgContext, page: str = "dashboard"):
    return select(SavedView).where(SavedView.org_id == ctx.org.id, SavedView.user_id == ctx.user.id,
                                   SavedView.page == page)


def _get(ctx: OrgContext, view_id: uuid.UUID) -> SavedView:
    v = ctx.db.get(SavedView, view_id)
    if v is None or v.org_id != ctx.org.id or v.user_id != ctx.user.id:
        raise HTTPException(404, "View not found")
    return v


def _make_default(ctx: OrgContext, view: SavedView) -> None:
    for other in ctx.db.scalars(_mine(ctx, view.page).where(SavedView.id != view.id, SavedView.is_default.is_(True))):
        other.is_default = False
    view.is_default = True


@router.get("/views/options")
def view_options():
    return {"metrics": list(METRICS), "sections": list(SECTIONS)}


@router.get("/views")
def list_views(page: Literal["dashboard"] = "dashboard", ctx: OrgContext = Depends(viewer)):
    return [_out(v) for v in ctx.db.scalars(_mine(ctx, page).order_by(SavedView.name))]


@router.post("/views", status_code=201)
def create_view(body: ViewIn, ctx: OrgContext = Depends(viewer)):
    existing = ctx.db.scalars(_mine(ctx, body.page)).all()
    if len(existing) >= MAX_VIEWS:
        raise HTTPException(422, f"You can keep up to {MAX_VIEWS} views; delete one first")
    if any(v.name.lower() == body.name.lower() for v in existing):
        raise HTTPException(409, "You already have a view with that name")
    view = SavedView(org_id=ctx.org.id, user_id=ctx.user.id, page=body.page, name=body.name,
                     config=body.config.model_dump())
    ctx.db.add(view)
    ctx.db.flush()
    if body.is_default:
        _make_default(ctx, view)
    ctx.db.commit()
    return _out(view)


@router.patch("/views/{view_id}")
def update_view(view_id: uuid.UUID, body: ViewPatch, ctx: OrgContext = Depends(viewer)):
    view = _get(ctx, view_id)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(422, "Give the view a name")
        if any(v.id != view.id and v.name.lower() == name.lower() for v in ctx.db.scalars(_mine(ctx, view.page))):
            raise HTTPException(409, "You already have a view with that name")
        view.name = name
    if body.config is not None:
        view.config = body.config.model_dump()
    if body.is_default is True:
        _make_default(ctx, view)
    elif body.is_default is False:
        view.is_default = False
    ctx.db.commit()
    return _out(view)


@router.delete("/views/{view_id}", status_code=204)
def delete_view(view_id: uuid.UUID, ctx: OrgContext = Depends(viewer)):
    ctx.db.delete(_get(ctx, view_id))
    ctx.db.commit()
    return Response(status_code=204)
