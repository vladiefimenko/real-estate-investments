"""Custom instructions and remembered notes for the AI analyst (workspace standards + personal)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..deps import OrgContext, admin, viewer
from ..models import ROLE_RANK
from ..services import analyst_prefs as ap

router = APIRouter(tags=["analyst"])


class Prefs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: str | None = Field(default=None, max_length=2000)
    dscr_floor: float | None = Field(default=None, ge=1.0, le=3.0)
    exit_cap_stress_bps: int | None = Field(default=None, ge=10, le=300)

    @field_validator("instructions")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return v or None


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=500)


def _view(ctx: OrgContext) -> dict:
    return {"workspace": ap.workspace(ctx), "personal": ap.personal(ctx), "effective": ap.effective(ctx),
            "can_edit_workspace": ROLE_RANK[ctx.role] >= ROLE_RANK["admin"]}


@router.get("/analyst/preferences")
def get_preferences(ctx: OrgContext = Depends(viewer)):
    return _view(ctx)


@router.put("/analyst/preferences/personal")
def set_personal(body: Prefs, ctx: OrgContext = Depends(viewer)):
    ap.save_personal(ctx, body.model_dump())
    ctx.db.commit()
    return _view(ctx)


@router.put("/analyst/preferences/workspace")
def set_workspace(body: Prefs, ctx: OrgContext = Depends(admin)):
    ap.save_workspace(ctx, body.model_dump())
    ctx.audit("analyst.workspace_instructions", "organization", ctx.org.id,
              dscr_floor=body.dscr_floor, exit_cap_stress_bps=body.exit_cap_stress_bps,
              has_instructions=bool(body.instructions))
    ctx.db.commit()
    return _view(ctx)


@router.post("/analyst/notes", status_code=201)
def add_note(body: NoteIn, ctx: OrgContext = Depends(viewer)):
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "Write the note first")
    try:
        note = ap.add_note(ctx, text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    ctx.db.commit()
    return note


@router.delete("/analyst/notes/{note_id}", status_code=204)
def delete_note(note_id: str, ctx: OrgContext = Depends(viewer)):
    if not ap.delete_note(ctx, note_id):
        raise HTTPException(404, "Note not found")
    ctx.db.commit()
    return Response(status_code=204)
