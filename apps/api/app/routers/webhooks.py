"""Webhook management (owners and admins)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from ..deps import OrgContext, admin
from ..models import Webhook
from ..services import webhooks as wh

router = APIRouter(tags=["webhooks"])
MAX_WEBHOOKS = 10


def _events(v: list[str]) -> list[str]:
    unknown = sorted(set(v) - set(wh.EVENTS))
    if unknown:
        raise ValueError(f"Unknown events: {', '.join(unknown)}")
    if not v:
        raise ValueError("Choose at least one event")
    return sorted(set(v))


class WebhookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=8, max_length=500)
    description: str | None = Field(default=None, max_length=200)
    events: list[str]

    @field_validator("events")
    @classmethod
    def _ev(cls, v: list[str]) -> list[str]:
        return _events(v)


class WebhookUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str | None = Field(default=None, max_length=200)
    events: list[str] | None = None
    active: bool | None = None

    @field_validator("events")
    @classmethod
    def _ev(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _events(v)


def _out(h: Webhook) -> dict[str, Any]:
    return {"id": str(h.id), "url": h.url, "description": h.description, "events": h.events, "active": h.active,
            "last_delivery_at": h.last_delivery_at.isoformat() if h.last_delivery_at else None,
            "last_status": h.last_status, "consecutive_failures": h.consecutive_failures,
            "created_at": h.created_at.isoformat()}


def _get(ctx: OrgContext, webhook_id: uuid.UUID) -> Webhook:
    h = ctx.db.get(Webhook, webhook_id)
    if h is None or h.org_id != ctx.org.id:
        raise HTTPException(404, "Webhook not found")
    return h


def _human(ctx: OrgContext) -> None:
    if ctx.api_key_id is not None:
        raise HTTPException(403, "API keys cannot manage webhooks")


@router.get("/org/webhooks")
def list_webhooks(ctx: OrgContext = Depends(admin)):
    _human(ctx)
    rows = ctx.db.scalars(select(Webhook).where(Webhook.org_id == ctx.org.id).order_by(Webhook.created_at)).all()
    return {"webhooks": [_out(h) for h in rows], "events": wh.EVENTS,
            "signature": "X-Axiom-Signature: sha256=HMAC_SHA256(secret, X-Axiom-Timestamp + '.' + body)"}


@router.post("/org/webhooks", status_code=201)
def create_webhook(body: WebhookIn, ctx: OrgContext = Depends(admin)):
    _human(ctx)
    count = len(ctx.db.scalars(select(Webhook.id).where(Webhook.org_id == ctx.org.id)).all())
    if count >= MAX_WEBHOOKS:
        raise HTTPException(422, f"A workspace can have up to {MAX_WEBHOOKS} webhooks")
    try:
        url = wh.check_url(body.url)
    except wh.UnsafeUrl as exc:
        raise HTTPException(422, str(exc)) from exc
    secret = wh.new_secret()
    h = Webhook(org_id=ctx.org.id, url=url, description=body.description, events=body.events,
                secret_encrypted=wh.encrypt_secret(secret), created_by=ctx.user.id, consecutive_failures=0)
    ctx.db.add(h)
    ctx.db.flush()
    ctx.audit("webhook.create", "webhook", h.id, url=url, events=body.events)
    ctx.db.commit()
    return {**_out(h), "secret": secret}


@router.patch("/org/webhooks/{webhook_id}")
def update_webhook(webhook_id: uuid.UUID, body: WebhookUpdate, ctx: OrgContext = Depends(admin)):
    _human(ctx)
    h = _get(ctx, webhook_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(h, k, v)
    if changes.get("active"):
        h.consecutive_failures = 0
    ctx.audit("webhook.update", "webhook", h.id, changes=changes)
    ctx.db.commit()
    return _out(h)


@router.delete("/org/webhooks/{webhook_id}", status_code=204)
def delete_webhook(webhook_id: uuid.UUID, ctx: OrgContext = Depends(admin)):
    _human(ctx)
    h = _get(ctx, webhook_id)
    ctx.audit("webhook.delete", "webhook", h.id, url=h.url)
    ctx.db.delete(h)
    ctx.db.commit()
    return Response(status_code=204)


@router.post("/org/webhooks/{webhook_id}/test")
def test_webhook(webhook_id: uuid.UUID, ctx: OrgContext = Depends(admin)):
    """Send a 'webhook.test' event right now and report the result."""
    _human(ctx)
    h = _get(ctx, webhook_id)
    ok, status = wh.send(h, "webhook.test", {"message": "Test event from Axiom", "actor": ctx.user.name})
    wh.record(h, ok, status)
    ctx.db.commit()
    return {"ok": ok, "status": status}
