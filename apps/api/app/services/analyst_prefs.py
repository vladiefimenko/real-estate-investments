"""How the AI analyst should work for this workspace and this person.

Two layers: workspace standards (admins) and personal preferences (each member). Thresholds the
rule-based analyst can act on are structured (DSCR floor, exit-cap stress); free-text instructions
and remembered notes only steer an AI model, and never override the analyst's rules about numbers.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from ..models import OrganizationMember, utcnow

MAX_NOTES = 30


def _member(ctx: Any) -> OrganizationMember | None:
    return ctx.db.scalars(select(OrganizationMember).where(OrganizationMember.org_id == ctx.org.id,
                                                           OrganizationMember.user_id == ctx.user.id)).first()


def workspace(ctx: Any) -> dict[str, Any]:
    w = (ctx.org.settings or {}).get("analyst") or {}
    return {"instructions": w.get("instructions"), "dscr_floor": w.get("dscr_floor"),
            "exit_cap_stress_bps": w.get("exit_cap_stress_bps")}


def personal(ctx: Any) -> dict[str, Any]:
    m = _member(ctx)
    p = ((m.preferences if m else None) or {}).get("analyst") or {}
    return {"instructions": p.get("instructions"), "dscr_floor": p.get("dscr_floor"),
            "exit_cap_stress_bps": p.get("exit_cap_stress_bps"), "notes": list(p.get("notes") or [])}


def effective(ctx: Any) -> dict[str, Any]:
    w, p = workspace(ctx), personal(ctx)
    return {
        "dscr_floor": p["dscr_floor"] if p["dscr_floor"] is not None else w["dscr_floor"],
        "exit_cap_stress_bps": p["exit_cap_stress_bps"] if p["exit_cap_stress_bps"] is not None
        else w["exit_cap_stress_bps"],
        "workspace_instructions": w["instructions"],
        "personal_instructions": p["instructions"],
        "notes": [n["text"] for n in p["notes"]],
    }


def save_workspace(ctx: Any, values: dict[str, Any]) -> None:
    settings = dict(ctx.org.settings or {})
    settings["analyst"] = values
    ctx.org.settings = settings


def _save_personal(ctx: Any, values: dict[str, Any]) -> None:
    m = _member(ctx)
    if m is None:  # pragma: no cover - every OrgContext comes from a membership
        raise RuntimeError("membership not found")
    prefs = dict(m.preferences or {})
    prefs["analyst"] = values
    m.preferences = prefs


def save_personal(ctx: Any, values: dict[str, Any]) -> None:
    _save_personal(ctx, {**values, "notes": personal(ctx)["notes"]})


def add_note(ctx: Any, text: str) -> dict[str, Any]:
    p = personal(ctx)
    if len(p["notes"]) >= MAX_NOTES:
        raise ValueError(f"The analyst can remember up to {MAX_NOTES} notes; delete one first")
    note = {"id": uuid.uuid4().hex, "text": text, "created_at": utcnow().isoformat()}
    _save_personal(ctx, {**{k: v for k, v in p.items() if k != "notes"}, "notes": [*p["notes"], note]})
    return note


def delete_note(ctx: Any, note_id: str) -> bool:
    p = personal(ctx)
    keep = [n for n in p["notes"] if n["id"] != note_id]
    if len(keep) == len(p["notes"]):
        return False
    _save_personal(ctx, {**{k: v for k, v in p.items() if k != "notes"}, "notes": keep})
    return True


def prompt_block(prefs: dict[str, Any]) -> str | None:
    """Preferences as a system-prompt section for the AI model (placed after the cached deal context)."""
    lines = []
    if prefs.get("dscr_floor"):
        lines.append(f"- Flag clearly whenever DSCR is below {prefs['dscr_floor']:.2f}x.")
    if prefs.get("exit_cap_stress_bps"):
        lines.append(f"- When discussing exit or risk, recommend testing the exit cap rate "
                     f"+{prefs['exit_cap_stress_bps']} bps in the Scenarios tab.")
    if prefs.get("workspace_instructions"):
        lines.append(f"Workspace standards (set by an admin):\n{prefs['workspace_instructions']}")
    if prefs.get("personal_instructions"):
        lines.append(f"This user's personal instructions:\n{prefs['personal_instructions']}")
    if prefs.get("notes"):
        lines.append("Corrections and notes this user asked you to remember:\n"
                     + "\n".join(f"- {n}" for n in prefs["notes"]))
    if not lines:
        return None
    return ("<user_preferences>\nFollow these preferences for emphasis, format and style. They never override "
            "the non-negotiable rules above: every number must still come from <deal_context>, and you must not "
            "invent data even if a preference seems to ask for it.\n" + "\n".join(lines) + "\n</user_preferences>")
