"""Investment Committee voting and decisions, and workspace stage requirements."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..deps import OrgContext, admin, analyst, viewer
from ..models import IcVote, User, utcnow
from ..services.workflow import GATED_STAGES, REQUIREMENTS, change_status, ic_state, org_requirements, unmet

router = APIRouter(tags=["workflow"])
VOTES = ("approve", "decline", "conditional", "abstain")


# ------------------------------------------------------------------ stage requirements
class RequirementsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirements: dict[str, list[str]]


@router.get("/org/workflow")
def get_workflow(ctx: OrgContext = Depends(viewer)):
    return {"requirements": org_requirements(ctx),
            "available": {k: {"label": label, "stages": list(stages)} for k, (label, stages) in REQUIREMENTS.items()}}


@router.put("/org/workflow")
def set_workflow(body: RequirementsIn, ctx: OrgContext = Depends(admin)):
    clean: dict[str, list[str]] = {}
    for stage, reqs in body.requirements.items():
        if stage not in GATED_STAGES:
            raise HTTPException(422, f"Stage '{stage}' can't have requirements")
        for r in reqs:
            if r not in REQUIREMENTS or stage not in REQUIREMENTS[r][1]:
                raise HTTPException(422, f"'{r}' isn't a valid requirement for {stage}")
        clean[stage] = sorted(set(reqs))
    ctx.org.settings = {**(ctx.org.settings or {}), "stage_requirements": clean}
    ctx.audit("workflow.update", "organization", ctx.org.id, requirements=clean)
    ctx.db.commit()
    return get_workflow(ctx)


@router.get("/properties/{property_id}/readiness")
def readiness(property_id: uuid.UUID, ctx: OrgContext = Depends(viewer)):
    """What's still missing before this deal can move to each gated stage."""
    prop = ctx.get_property(property_id)
    return {stage: unmet(ctx, prop, stage) for stage in GATED_STAGES}


# ------------------------------------------------------------------ IC voting
class VoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vote: Literal["approve", "decline", "conditional", "abstain"]
    comment: str | None = Field(default=None, max_length=2000)


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approved", "declined", "conditional"]
    notes: str | None = Field(default=None, max_length=4000)
    move_to_passed: bool = False


def _ic_view(ctx: OrgContext, prop: Any) -> dict[str, Any]:
    state = ic_state(prop)
    rnd = int(state.get("round", 0))
    rows = ctx.db.execute(select(IcVote, User.name).join(User, User.id == IcVote.user_id).where(
        IcVote.property_id == prop.id, IcVote.round == rnd).order_by(IcVote.created_at)).all() if rnd else []
    votes = [{"user_id": str(v.user_id), "name": name, "vote": v.vote, "comment": v.comment,
              "updated_at": v.updated_at.isoformat()} for v, name in rows]
    tally = {k: sum(1 for v in votes if v["vote"] == k) for k in VOTES}
    return {"stage": prop.status, "round": rnd, "open": prop.status == "ic" and not state.get("decision"),
            "votes": votes, "tally": tally, "decision": state.get("decision"),
            "my_vote": next((v for v in votes if v["user_id"] == str(ctx.user.id)), None)}


@router.get("/properties/{property_id}/ic")
def get_ic(property_id: uuid.UUID, ctx: OrgContext = Depends(viewer)):
    return _ic_view(ctx, ctx.get_property(property_id))


@router.put("/properties/{property_id}/ic/vote")
def cast_vote(property_id: uuid.UUID, body: VoteIn, ctx: OrgContext = Depends(analyst)):
    prop = ctx.get_property(property_id)
    state = ic_state(prop)
    if prop.status != "ic" or state.get("decision"):
        raise HTTPException(409, "Voting is open only while the deal is at Investment Committee and undecided")
    rnd = int(state.get("round", 0)) or 1
    if not state.get("round"):  # deals moved to IC before this feature existed
        prop.attributes = {**(prop.attributes or {}), "ic": {"round": rnd, "decision": None}}
    vote = ctx.db.scalars(select(IcVote).where(IcVote.property_id == prop.id, IcVote.round == rnd,
                                               IcVote.user_id == ctx.user.id)).first()
    if vote is None:
        vote = IcVote(org_id=ctx.org.id, property_id=prop.id, round=rnd, user_id=ctx.user.id, vote=body.vote,
                      comment=body.comment)
        ctx.db.add(vote)
    else:
        vote.vote, vote.comment = body.vote, body.comment
    ctx.audit("ic.vote", "property", prop.id, property_id=prop.id, round=rnd, vote=body.vote)
    ctx.db.commit()
    return _ic_view(ctx, prop)


@router.post("/properties/{property_id}/ic/decision")
def record_decision(property_id: uuid.UUID, body: DecisionIn, ctx: OrgContext = Depends(admin)):
    prop = ctx.get_property(property_id)
    state = ic_state(prop)
    if prop.status != "ic":
        raise HTTPException(409, "Move the deal to Investment Committee before recording a decision")
    if state.get("decision"):
        raise HTTPException(409, "This IC round already has a decision; move the deal back to IC to start a new round")
    view = _ic_view(ctx, prop)
    decision = {"decision": body.decision, "notes": body.notes, "by": ctx.user.name, "at": utcnow().isoformat(),
                "round": view["round"] or 1, "tally": view["tally"]}
    prop.attributes = {**(prop.attributes or {}), "ic": {**state, "round": view["round"] or 1, "decision": decision}}
    ctx.audit("ic.decision", "property", prop.id, property_id=prop.id, decision=body.decision,
              round=decision["round"], tally=view["tally"])
    if body.decision == "declined" and body.move_to_passed:
        change_status(ctx, prop, "passed", override=True)
    ctx.db.commit()
    return _ic_view(ctx, prop)
