"""LP/GP equity waterfall for a deal: preferred return, promote tiers, and who gets what."""

from __future__ import annotations

import uuid

from axiom_engine import AssumptionError
from axiom_engine.waterfall import run_waterfall
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from ..deps import OrgContext, analyst, deal_reader
from ..services.underwriting import calculate, engine_error, get_scenario

router = APIRouter(tags=["waterfall"])

DEFAULT = {"lp_share": 0.90, "pref_rate": 0.08,
           "tiers": [{"hurdle": 0.12, "gp_share": 0.20}, {"hurdle": None, "gp_share": 0.30}]}


class Tier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hurdle: float | None = Field(default=None, gt=0, le=1)
    gp_share: float = Field(ge=0, lt=1)


class WaterfallIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lp_share: float = Field(gt=0, lt=1)
    pref_rate: float = Field(ge=0, le=0.5)
    tiers: list[Tier] = Field(min_length=1, max_length=5)


def _config(prop) -> tuple[dict, bool]:
    saved = (prop.attributes or {}).get("waterfall")
    return (saved, True) if saved else (DEFAULT, False)


def _run(ctx: OrgContext, prop, config: dict, scenario_id) -> dict:
    sc = get_scenario(ctx, prop, scenario_id)
    flows = calculate(sc.assumptions_json, prop.property_type)["levered_cash_flows"]
    try:
        out = run_waterfall(flows, config["lp_share"], config["pref_rate"], config["tiers"])
    except AssumptionError as exc:
        raise engine_error(exc) from exc
    return {"scenario": {"id": str(sc.id), "name": sc.name}, "equity_flows": flows, **out}


@router.get("/properties/{property_id}/waterfall")
def get_waterfall(property_id: uuid.UUID, scenario_id: uuid.UUID | None = None,
                  ctx: OrgContext = Depends(deal_reader)):
    prop = ctx.get_property(property_id)
    config, saved = _config(prop)
    return {"config": config, "saved": saved, "result": _run(ctx, prop, config, scenario_id)}


@router.post("/properties/{property_id}/waterfall/preview")
def preview_waterfall(property_id: uuid.UUID, body: WaterfallIn, scenario_id: uuid.UUID | None = None,
                      ctx: OrgContext = Depends(deal_reader)):
    """Run a structure without saving it (for live editing)."""
    prop = ctx.get_property(property_id)
    return {"config": body.model_dump(), "saved": False, "result": _run(ctx, prop, body.model_dump(), scenario_id)}


@router.put("/properties/{property_id}/waterfall")
def save_waterfall(property_id: uuid.UUID, body: WaterfallIn, ctx: OrgContext = Depends(analyst)):
    prop = ctx.get_property(property_id)
    config = body.model_dump()
    result = _run(ctx, prop, config, None)  # validates against the engine before saving
    prop.attributes = {**(prop.attributes or {}), "waterfall": config}
    ctx.audit("property.waterfall", "property", prop.id, property_id=prop.id, lp_share=body.lp_share,
              pref_rate=body.pref_rate, tiers=len(body.tiers))
    ctx.db.commit()
    return {"config": config, "saved": True, "result": result}
