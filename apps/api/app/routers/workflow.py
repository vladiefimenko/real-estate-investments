"""Investment Committee voting and decisions, and workspace stage requirements."""

from __future__ import annotations

import copy
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..deps import OrgContext, admin, analyst, viewer
from ..models import ROLE_RANK, IcVote, OrganizationMember, User, utcnow
from ..services.notify import admins, notify
from ..services.workflow import (
    GATED_STAGES,
    REQUIREMENTS,
    chain_status,
    change_status,
    current_step,
    deal_link,
    ic_state,
    org_chain,
    org_requirements,
    unmet,
)

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


class ChainStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60)
    approvers: list[uuid.UUID] = Field(min_length=1, max_length=20)
    min_approvals: int = Field(default=1, ge=1, le=20)


class ChainIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[ChainStep] = Field(default_factory=list, max_length=5)


@router.put("/org/workflow/chain")
def set_chain(body: ChainIn, ctx: OrgContext = Depends(admin)):
    """Ordered IC approval steps; an empty list turns the chain off. Applies from the next IC round."""
    members = {m.user_id: m.role for m in ctx.db.scalars(select(OrganizationMember).where(
        OrganizationMember.org_id == ctx.org.id))}
    steps = []
    for i, st in enumerate(body.steps, 1):
        ids = list(dict.fromkeys(st.approvers))
        bad = [u for u in ids if ROLE_RANK.get(members.get(u, ""), -1) < ROLE_RANK["viewer"]]
        if bad:
            raise HTTPException(422, f"Step {i}: approvers must be internal members of this workspace")
        if st.min_approvals > len(ids):
            raise HTTPException(422, f"Step {i}: needs {st.min_approvals} approvals but has {len(ids)} approver(s)")
        steps.append({"name": st.name.strip(), "approvers": [str(u) for u in ids], "min_approvals": st.min_approvals})
    settings = dict(ctx.org.settings or {})
    settings["approval_chain"] = steps
    ctx.org.settings = settings
    ctx.audit("org.approval_chain", "organization", ctx.org.id, steps=[(s["name"], len(s["approvers"]),
                                                                       s["min_approvals"]) for s in steps])
    ctx.db.commit()
    return {"steps": _chain_with_names(ctx, steps)}


def _names(ctx: OrgContext, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    return {str(u.id): u.name for u in ctx.db.scalars(select(User).where(User.id.in_([uuid.UUID(i) for i in ids])))}


def _chain_with_names(ctx: OrgContext, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = _names(ctx, {a for st in steps for a in st["approvers"]})
    return [{**st, "approver_names": [names.get(a, "Former member") for a in st["approvers"]]} for st in steps]


@router.get("/org/workflow/chain")
def get_chain(ctx: OrgContext = Depends(viewer)):
    return {"steps": _chain_with_names(ctx, org_chain(ctx))}


def _ic_view(ctx: OrgContext, prop: Any) -> dict[str, Any]:
    state = ic_state(prop)
    rnd = int(state.get("round", 0))
    rows = ctx.db.execute(select(IcVote, User.name).join(User, User.id == IcVote.user_id).where(
        IcVote.property_id == prop.id, IcVote.round == rnd).order_by(IcVote.created_at)).all() if rnd else []
    votes = [{"user_id": str(v.user_id), "name": name, "vote": v.vote, "comment": v.comment,
              "updated_at": v.updated_at.isoformat()} for v, name in rows]
    tally = {k: sum(1 for v in votes if v["vote"] == k) for k in VOTES}
    chain = state.get("chain")
    step = current_step(state)
    open_ = prop.status == "ic" and not state.get("decision")
    me = str(ctx.user.id)
    chain_view = None
    if chain:
        chain_view = _chain_with_names(ctx, chain)
    return {"stage": prop.status, "round": rnd, "open": open_,
            "votes": votes, "tally": tally, "decision": state.get("decision"),
            "my_vote": next((v for v in votes if v["user_id"] == me), None),
            "chain": chain_view, "chain_status": chain_status(state), "current_step": step,
            "can_approve": bool(open_ and chain and step is not None and chain_status(state) == "pending"
                                and me in chain[step]["approvers"]
                                and not any(a["user_id"] == me for a in chain[step]["actions"]))}


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


class ApprovalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["approve", "decline"]
    comment: str | None = Field(default=None, max_length=2000)


@router.post("/properties/{property_id}/ic/approval")
def act_on_approval(property_id: uuid.UUID, body: ApprovalIn, ctx: OrgContext = Depends(viewer)):
    """An approver acts on the current step of the deal's approval chain."""
    prop = ctx.get_property(property_id)
    state = copy.deepcopy(ic_state(prop))  # never mutate the stored JSON in place: the change must be detected
    chain = state.get("chain")
    if prop.status != "ic" or state.get("decision") or not chain or chain_status(state) != "pending":
        raise HTTPException(409, "There's no approval waiting on this deal")
    i = current_step(state)
    st = chain[i]
    me = str(ctx.user.id)
    if me not in st["approvers"]:
        raise HTTPException(403, f"You're not an approver for step {i + 1} ({st['name']})")
    if any(a["user_id"] == me for a in st["actions"]):
        raise HTTPException(409, "You've already acted on this step")
    st["actions"].append({"user_id": me, "name": ctx.user.name, "action": body.action,
                          "comment": (body.comment or "").strip() or None, "at": utcnow().isoformat()})
    approvals = sum(1 for a in st["actions"] if a["action"] == "approve")
    if body.action == "decline":
        st["status"] = "declined"
    elif approvals >= st["min_approvals"]:
        st["status"] = "approved"
    prop.attributes = {**(prop.attributes or {}), "ic": {**state, "chain": chain}}
    ctx.audit("ic.approval", "property", prop.id, property_id=prop.id, round=state.get("round"), step=i + 1,
              step_name=st["name"], decision=body.action)
    owner = [prop.owner_id] if prop.owner_id else []
    if st["status"] == "declined":
        notify(ctx, [*admins(ctx), *owner], "ic.approval_declined", f"Declined at {st['name']}: {prop.name}",
               f"{ctx.user.name} declined at step {i + 1} of {len(chain)}.", deal_link(prop), prop.id)
    elif st["status"] == "approved":
        nxt = current_step({"chain": chain})
        if nxt is not None:
            notify(ctx, chain[nxt]["approvers"], "ic.approval_requested", f"Your approval is needed: {prop.name}",
                   f"Step {nxt + 1} of {len(chain)} ({chain[nxt]['name']}). {st['name']} has approved.",
                   deal_link(prop), prop.id)
        else:
            notify(ctx, [*admins(ctx), *owner], "ic.approval_complete", f"Approval chain complete: {prop.name}",
                   "Every step approved. An admin can now record the IC decision.", deal_link(prop), prop.id)
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
    status = chain_status(state)
    if body.decision != "declined" and status == "pending":
        i = current_step(state)
        raise HTTPException(409, f"The approval chain isn't finished: step {i + 1} ({state['chain'][i]['name']}) "
                                 "is still pending")
    if body.decision != "declined" and status == "declined":
        raise HTTPException(409, "The approval chain was declined; record a declined decision or start a new IC round")
    view = _ic_view(ctx, prop)
    decision = {"decision": body.decision, "notes": body.notes, "by": ctx.user.name, "at": utcnow().isoformat(),
                "round": view["round"] or 1, "tally": view["tally"]}
    prop.attributes = {**(prop.attributes or {}), "ic": {**state, "round": view["round"] or 1, "decision": decision}}
    ctx.audit("ic.decision", "property", prop.id, property_id=prop.id, decision=body.decision,
              round=decision["round"], tally=view["tally"])
    if body.decision == "declined" and body.move_to_passed:
        change_status(ctx, prop, "passed", override=True)
    people = {*(v["user_id"] for v in view["votes"]),
              *(a for st in (state.get("chain") or []) for a in st["approvers"])}
    if prop.owner_id:
        people.add(str(prop.owner_id))
    notify(ctx, people, "ic.decision", f"IC decision on {prop.name}: {body.decision}",
           (body.notes or "")[:300] or None, deal_link(prop), prop.id)
    ctx.db.commit()
    return _ic_view(ctx, prop)
