"""In-app notifications. Email delivery can be added later behind the same call."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select

from ..models import ROLE_RANK, Notification, OrganizationMember


def notify(ctx: Any, user_ids: Iterable[uuid.UUID | str], kind: str, title: str, body: str | None = None,
           link: str | None = None, property_id: uuid.UUID | None = None) -> int:
    """Queue a notification for each current member in ``user_ids`` except the person acting."""
    wanted = {uuid.UUID(str(u)) for u in user_ids} - {ctx.user.id}
    if not wanted:
        return 0
    members = set(ctx.db.scalars(select(OrganizationMember.user_id).where(
        OrganizationMember.org_id == ctx.org.id, OrganizationMember.user_id.in_(wanted))))
    for uid in members:
        ctx.db.add(Notification(org_id=ctx.org.id, user_id=uid, kind=kind, title=title[:200], body=body,
                                link=link, property_id=property_id))
    return len(members)


def admins(ctx: Any) -> list[uuid.UUID]:
    return [m.user_id for m in ctx.db.scalars(select(OrganizationMember).where(
        OrganizationMember.org_id == ctx.org.id)) if ROLE_RANK.get(m.role, -1) >= ROLE_RANK["admin"]]
