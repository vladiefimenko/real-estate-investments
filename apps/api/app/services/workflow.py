"""Deal workflow: stage requirements ("gates") and Investment Committee rounds.

Every stage change goes through ``change_status`` so gates, IC rounds and audit
entries are applied the same way for single edits, bulk moves and the pipeline board.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from ..deps import OrgContext
from ..models import ROLE_RANK, AuditLog, ExtractedData, Property, Scenario

# key: (label shown to users, stages it can gate)
REQUIREMENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "verified_data": ("At least one value verified from a document", ("underwriting", "ic", "closed")),
    "loan": ("The base case includes a loan", ("ic", "closed")),
    "ic_memo": ("An IC memo has been generated", ("ic", "closed")),
    "ic_approved": ("The Investment Committee approved the deal", ("closed",)),
}
GATED_STAGES = ("underwriting", "ic", "closed")


def org_requirements(ctx: OrgContext) -> dict[str, list[str]]:
    raw = (ctx.org.settings or {}).get("stage_requirements") or {}
    return {stage: [r for r in raw.get(stage, []) if r in REQUIREMENTS and stage in REQUIREMENTS[r][1]]
            for stage in GATED_STAGES}


def _met(ctx: OrgContext, prop: Property, req: str) -> bool:
    if req == "verified_data":
        return ctx.db.scalar(select(ExtractedData.id).where(
            ExtractedData.property_id == prop.id, ExtractedData.status.in_(("accepted", "edited"))).limit(1)) is not None
    if req == "loan":
        base = ctx.db.scalars(select(Scenario).where(Scenario.property_id == prop.id, Scenario.is_base.is_(True),
                                                     Scenario.deleted_at.is_(None))).first()
        return bool(base and (base.assumptions_json or {}).get("loan"))
    if req == "ic_memo":
        return ctx.db.scalar(select(AuditLog.id).where(
            AuditLog.org_id == ctx.org.id, AuditLog.property_id == prop.id,
            AuditLog.action == "report.ic_memo").limit(1)) is not None
    if req == "ic_approved":
        return (ic_state(prop).get("decision") or {}).get("decision") in ("approved", "conditional")
    return True


def unmet(ctx: OrgContext, prop: Property, stage: str) -> list[str]:
    return [REQUIREMENTS[r][0] for r in org_requirements(ctx).get(stage, []) if not _met(ctx, prop, r)]


def ic_state(prop: Property) -> dict[str, Any]:
    return (prop.attributes or {}).get("ic") or {}


def org_chain(ctx: OrgContext) -> list[dict[str, Any]]:
    """The workspace's IC approval chain: ordered steps of {name, approvers: [user ids], min_approvals}."""
    return list((ctx.org.settings or {}).get("approval_chain") or [])


def chain_status(state: dict[str, Any]) -> str | None:
    chain = state.get("chain")
    if not chain:
        return None
    if any(st["status"] == "declined" for st in chain):
        return "declined"
    return "approved" if all(st["status"] == "approved" for st in chain) else "pending"


def current_step(state: dict[str, Any]) -> int | None:
    for i, st in enumerate(state.get("chain") or []):
        if st["status"] == "pending":
            return i
    return None


def deal_link(prop: Property) -> str:
    return f"/deals/{prop.id}"


def notify_ic_start(ctx: OrgContext, prop: Property, state: dict[str, Any]) -> None:
    from .notify import admins, notify

    chain = state.get("chain")
    if chain:
        first = chain[0]
        notify(ctx, first["approvers"], "ic.approval_requested", f"Your approval is needed: {prop.name}",
               f"Step 1 of {len(chain)} ({first['name']}) of the Investment Committee approval chain.",
               deal_link(prop), prop.id)
    else:
        notify(ctx, admins(ctx), "ic.started", f"{prop.name} is at Investment Committee",
               "Members can vote now; an admin records the decision.", deal_link(prop), prop.id)


def change_status(ctx: OrgContext, prop: Property, new: str, *, override: bool = False, bulk: bool = False) -> bool:
    """Move a deal to ``new``, enforcing the workspace's stage requirements.

    Admins may pass ``override`` to skip unmet requirements; the override is audited.
    Returns False when the deal is already at that stage.
    """
    if prop.status == new:
        return False
    missing = unmet(ctx, prop, new)
    if missing and not (override and ROLE_RANK[ctx.role] >= ROLE_RANK["admin"]):
        raise HTTPException(422, {"message": f"{prop.name} isn't ready for this stage", "unmet": missing,
                                  "can_override": ROLE_RANK[ctx.role] >= ROLE_RANK["admin"]})
    before = prop.status
    prop.status = new
    prop.updated_by = ctx.user.id
    if new == "ic":  # entering IC starts a fresh voting round, with a snapshot of the approval chain
        state = ic_state(prop)
        fresh: dict[str, Any] = {"round": int(state.get("round", 0)) + 1, "decision": None}
        chain = org_chain(ctx)
        if chain:
            fresh["chain"] = [{"name": st["name"], "approvers": list(st["approvers"]),
                               "min_approvals": int(st["min_approvals"]), "status": "pending", "actions": []}
                              for st in chain]
        prop.attributes = {**(prop.attributes or {}), "ic": fresh}
        notify_ic_start(ctx, prop, fresh)
    details: dict[str, Any] = {"changes": {"status": {"before": before, "after": new}}}
    if bulk:
        details["bulk"] = True
    if missing:
        details["overridden_requirements"] = missing
    ctx.audit("property.update", "property", prop.id, property_id=prop.id, **details)
    return True
