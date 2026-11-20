"""The signed-in member's in-app notifications."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update

from ..deps import OrgContext, get_org_context
from ..models import Notification, utcnow

router = APIRouter(tags=["notifications"])


def _mine(ctx: OrgContext):
    return (Notification.org_id == ctx.org.id) & (Notification.user_id == ctx.user.id)


@router.get("/notifications")
def list_notifications(limit: int = 30, ctx: OrgContext = Depends(get_org_context)):
    rows = ctx.db.scalars(select(Notification).where(_mine(ctx)).order_by(Notification.created_at.desc())
                          .limit(max(1, min(limit, 100)))).all()
    unread = ctx.db.scalar(select(func.count()).select_from(Notification).where(_mine(ctx), Notification.read_at.is_(None)))
    return {"unread": unread or 0,
            "items": [{"id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
                       "read": n.read_at is not None, "created_at": n.created_at.isoformat()} for n in rows]}


class ReadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[uuid.UUID] | None = Field(default=None, max_length=200)  # omit to mark everything read


@router.post("/notifications/read")
def mark_read(body: ReadIn, ctx: OrgContext = Depends(get_org_context)):
    q = update(Notification).where(_mine(ctx), Notification.read_at.is_(None))
    if body.ids is not None:
        q = q.where(Notification.id.in_(body.ids))
    ctx.db.execute(q.values(read_at=utcnow()))
    ctx.db.commit()
    return {"ok": True}
