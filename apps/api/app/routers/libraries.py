"""Assumption libraries: an underwriter's standard assumptions, saved once and applied to any scenario."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select

from ..deps import OrgContext, analyst, viewer
from ..models import ROLE_RANK, AssumptionLibrary, Scenario
from ..services.property_types import PROPERTY_TYPES
from ..services.underwriting import run_and_store
from .scenarios import _scenario, _validate

router = APIRouter(tags=["libraries"])

# Assumptions a library may set: scalar, deal-independent standards. Price, size, revenue and
# expense line items are specific to each deal and stay out.
LIBRARY_KEYS: dict[str, tuple[str, float, float]] = {
    # key: (label, min, max)
    "vacancy_rate": ("Vacancy", 0.0, 0.5),
    "credit_loss_rate": ("Credit loss", 0.0, 0.2),
    "rent_growth": ("Rent growth", -0.1, 0.15),
    "opex_growth": ("Expense growth", -0.05, 0.15),
    "other_income_growth": ("Other income growth", -0.1, 0.15),
    "capex_growth": ("Reserve growth", -0.05, 0.15),
    "management_fee_pct": ("Management fee", 0.0, 0.15),
    "exit_cap_rate": ("Exit cap rate", 0.01, 0.2),
    "discount_rate": ("Discount rate", 0.0, 0.3),
    "selling_costs_pct": ("Selling costs", 0.0, 0.1),
    "closing_costs_pct": ("Closing costs", 0.0, 0.1),
    "hold_period_years": ("Hold period", 1, 30),
}


def _check_values(values: dict[str, Any]) -> dict[str, Any]:
    if not values:
        raise ValueError("A library needs at least one value")
    unknown = sorted(set(values) - set(LIBRARY_KEYS))
    if unknown:
        raise ValueError(f"Not allowed in a library: {', '.join(unknown)}")
    out: dict[str, Any] = {}
    for k, v in values.items():
        label, lo, hi = LIBRARY_KEYS[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
            raise ValueError(f"{label} must be a number between {lo} and {hi}")
        out[k] = int(v) if k == "hold_period_years" else float(v)
    return out


class LibraryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    property_type: str | None = None
    is_shared: bool = True
    values: dict[str, Any]

    @field_validator("values")
    @classmethod
    def _values(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _check_values(v)

    @field_validator("property_type")
    @classmethod
    def _ptype(cls, v: str | None) -> str | None:
        if v is not None and v not in PROPERTY_TYPES:
            raise ValueError("Unknown property type")
        return v


class LibraryFromScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    keys: list[str] = Field(min_length=1)
    is_shared: bool = True


class ApplyIn(BaseModel):
    library_id: uuid.UUID


def _out(lib: AssumptionLibrary, ctx: OrgContext) -> dict[str, Any]:
    return {"id": str(lib.id), "name": lib.name, "description": lib.description, "property_type": lib.property_type,
            "is_shared": lib.is_shared, "values": lib.values_json, "created_at": lib.created_at.isoformat(),
            "mine": lib.created_by == ctx.user.id}


def _visible(ctx: OrgContext):
    return select(AssumptionLibrary).where(
        AssumptionLibrary.org_id == ctx.org.id,
        or_(AssumptionLibrary.is_shared.is_(True), AssumptionLibrary.created_by == ctx.user.id))


def _get(ctx: OrgContext, library_id: uuid.UUID) -> AssumptionLibrary:
    lib = ctx.db.scalars(_visible(ctx).where(AssumptionLibrary.id == library_id)).first()
    if lib is None:
        raise HTTPException(404, "Library not found")
    return lib


@router.get("/libraries/fields")
def library_fields(ctx: OrgContext = Depends(viewer)):
    return [{"key": k, "label": label, "min": lo, "max": hi} for k, (label, lo, hi) in LIBRARY_KEYS.items()]


@router.get("/libraries")
def list_libraries(ctx: OrgContext = Depends(viewer)):
    rows = ctx.db.scalars(_visible(ctx).order_by(AssumptionLibrary.name)).all()
    return [_out(lib, ctx) for lib in rows]


@router.post("/libraries", status_code=201)
def create_library(body: LibraryIn, ctx: OrgContext = Depends(analyst)):
    lib = AssumptionLibrary(org_id=ctx.org.id, name=body.name, description=body.description,
                            property_type=body.property_type, is_shared=body.is_shared, values_json=body.values,
                            created_by=ctx.user.id)
    ctx.db.add(lib)
    ctx.db.flush()
    ctx.audit("library.create", "assumption_library", lib.id, name=lib.name)
    ctx.db.commit()
    return _out(lib, ctx)


@router.post("/libraries/from-scenario", status_code=201)
def create_from_scenario(body: LibraryFromScenario, ctx: OrgContext = Depends(analyst)):
    sc = _scenario(ctx, body.scenario_id)
    prop = ctx.get_property(sc.property_id)
    missing = [k for k in body.keys if k not in sc.assumptions_json]
    try:
        values = _check_values({k: sc.assumptions_json[k] for k in body.keys if k in sc.assumptions_json})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if missing:
        raise HTTPException(422, f"Not set on this scenario: {', '.join(missing)}")
    return create_library(LibraryIn(name=body.name, description=body.description, property_type=prop.property_type,
                                    is_shared=body.is_shared, values=values), ctx)


@router.delete("/libraries/{library_id}", status_code=204)
def delete_library(library_id: uuid.UUID, ctx: OrgContext = Depends(analyst)):
    lib = _get(ctx, library_id)
    if lib.created_by != ctx.user.id and ROLE_RANK[ctx.role] < ROLE_RANK["admin"]:
        raise HTTPException(403, "Only the creator or an admin can delete this library")
    ctx.audit("library.delete", "assumption_library", lib.id, name=lib.name)
    ctx.db.delete(lib)
    ctx.db.commit()
    return Response(status_code=204)


@router.post("/scenarios/{scenario_id}/apply-library")
def apply_library(scenario_id: uuid.UUID, body: ApplyIn, ctx: OrgContext = Depends(analyst)):
    """Overwrite the library's assumptions on a scenario, validate, re-run and store the result."""
    sc: Scenario = _scenario(ctx, scenario_id)
    prop = ctx.get_property(sc.property_id)
    lib = _get(ctx, body.library_id)
    before = sc.assumptions_json
    updated = {**before, **lib.values_json}
    _validate(updated)
    changes = {k: {"before": before.get(k), "after": v} for k, v in lib.values_json.items() if before.get(k) != v}
    sc.assumptions_json = updated
    if sc.is_base and "hold_period_years" in changes:
        prop.hold_period_years = updated["hold_period_years"]
    ctx.audit("library.apply", "scenario", sc.id, property_id=prop.id, library=lib.name, changes=changes)
    run_and_store(ctx, prop, sc)
    ctx.db.commit()
    return {"scenario_id": str(sc.id), "library": lib.name, "changed": sorted(changes)}
