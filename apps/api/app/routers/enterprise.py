"""Enterprise administration: read-only API keys, audit log export and workspace usage."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from ..deps import API_KEY_PATHS, API_KEY_PREFIX, API_KEY_RATE, OrgContext, admin, audit_reader
from ..models import ApiKey, AuditLog, Document, OrganizationMember, Property, User, utcnow
from ..security import hash_token

router = APIRouter(tags=["enterprise"])

MAX_EXPORT_ROWS = 100_000


def _require_human(ctx: OrgContext) -> None:
    if ctx.api_key_id is not None:  # defence in depth; the API-key path allowlist already excludes these routes
        raise HTTPException(403, "API keys cannot manage the workspace")


# ------------------------------------------------------------------ API keys
class ApiKeyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    expires_in_days: int | None = Field(default=None, ge=1, le=730)


def _key_out(k: ApiKey, creator: str | None) -> dict[str, Any]:
    return {"id": str(k.id), "name": k.name, "prefix": k.prefix, "created_by": creator,
            "created_at": k.created_at.isoformat(),
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "revoked": k.revoked_at is not None}


@router.get("/org/api-keys")
def list_api_keys(ctx: OrgContext = Depends(admin)):
    _require_human(ctx)
    rows = ctx.db.execute(select(ApiKey, User.name).join(User, User.id == ApiKey.created_by)
                          .where(ApiKey.org_id == ctx.org.id).order_by(ApiKey.created_at.desc())).all()
    return {"keys": [_key_out(k, name) for k, name in rows],
            "scope": {"access": "read-only", "paths": list(API_KEY_PATHS),
                      "rate_limit": f"{API_KEY_RATE[0]} requests per {int(API_KEY_RATE[1])} seconds"}}


@router.post("/org/api-keys", status_code=201)
def create_api_key(body: ApiKeyIn, ctx: OrgContext = Depends(admin)):
    _require_human(ctx)
    plaintext = API_KEY_PREFIX + secrets.token_urlsafe(32)
    key = ApiKey(org_id=ctx.org.id, name=body.name, prefix=plaintext[:12], key_hash=hash_token(plaintext),
                 created_by=ctx.user.id,
                 expires_at=utcnow() + timedelta(days=body.expires_in_days) if body.expires_in_days else None)
    ctx.db.add(key)
    ctx.db.flush()
    ctx.audit("api_key.create", "api_key", key.id, name=key.name, prefix=key.prefix)
    ctx.db.commit()
    return {**_key_out(key, ctx.user.name), "key": plaintext}


@router.delete("/org/api-keys/{key_id}", status_code=204)
def revoke_api_key(key_id: uuid.UUID, ctx: OrgContext = Depends(admin)):
    _require_human(ctx)
    key = ctx.db.get(ApiKey, key_id)
    if key is None or key.org_id != ctx.org.id:
        raise HTTPException(404, "API key not found")
    if key.revoked_at is None:
        key.revoked_at = utcnow()
        ctx.audit("api_key.revoke", "api_key", key.id, name=key.name, prefix=key.prefix)
        ctx.db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ audit export
def _parse_day(v: str | None, end: bool = False) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(v)
    except ValueError as exc:
        raise HTTPException(422, "Dates must be YYYY-MM-DD") from exc
    d = d.replace(tzinfo=d.tzinfo or timezone.utc)
    return d + timedelta(days=1) if end and len(v) == 10 else d


EXPORT_FIELDS = ["created_at", "action", "entity_type", "entity_id", "property_id", "property_name", "user_name",
                 "user_email", "details"]


@router.get("/org/audit/export")
def export_audit(format: str = Query("csv", pattern="^(csv|json)$"), since: str | None = None,
                 until: str | None = None, ctx: OrgContext = Depends(audit_reader)):
    """The workspace's complete audit trail for compliance reviews. Each export is itself audited."""
    _require_human(ctx)
    start, end = _parse_day(since), _parse_day(until, end=True)
    q = (select(AuditLog, User.name, User.email, Property.name)
         .outerjoin(User, User.id == AuditLog.user_id)
         .outerjoin(Property, Property.id == AuditLog.property_id)
         .where(AuditLog.org_id == ctx.org.id))
    if start:
        q = q.where(AuditLog.created_at >= start)
    if end:
        q = q.where(AuditLog.created_at < end)
    rows = ctx.db.execute(q.order_by(AuditLog.created_at, AuditLog.id).limit(MAX_EXPORT_ROWS + 1)).all()
    if len(rows) > MAX_EXPORT_ROWS:
        raise HTTPException(422, f"More than {MAX_EXPORT_ROWS:,} events: narrow the date range")
    records = [{"created_at": a.created_at.isoformat(), "action": a.action, "entity_type": a.entity_type,
                "entity_id": a.entity_id, "property_id": str(a.property_id) if a.property_id else None,
                "property_name": pname, "user_name": uname, "user_email": email,
                "details": a.details or {}} for a, uname, email, pname in rows]
    stamp = f"{utcnow():%Y%m%d-%H%M%S}"
    if format == "json":
        body = json.dumps({"organization": ctx.org.name, "exported_at": utcnow().isoformat(),
                           "exported_by": ctx.user.email, "since": since, "until": until,
                           "count": len(records), "events": records}, default=str, indent=1).encode()
        media, name = "application/json", f"audit-{stamp}.json"
    else:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=EXPORT_FIELDS)
        w.writeheader()
        for r in records:
            w.writerow({**r, "details": json.dumps(r["details"], default=str, sort_keys=True)})
        body, media, name = buf.getvalue().encode(), "text/csv", f"audit-{stamp}.csv"
    digest = hashlib.sha256(body).hexdigest()
    ctx.audit("audit.export", "organization", ctx.org.id, format=format, since=since, until=until,
              count=len(records), sha256=digest)
    ctx.db.commit()
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"',
                                                     "X-Content-SHA256": digest})


# ------------------------------------------------------------------ usage
@router.get("/org/usage")
def usage(days: int = 30, ctx: OrgContext = Depends(audit_reader)):
    """Workspace usage for licensing and ROI: members, activity, deals, documents, reports, AI and API keys."""
    _require_human(ctx)
    days = max(1, min(days, 365))
    since = utcnow() - timedelta(days=days)
    org = ctx.org.id
    count = lambda q: ctx.db.scalar(q) or 0  # noqa: E731
    events = ctx.db.execute(select(AuditLog.action, AuditLog.user_id, AuditLog.created_at).where(
        AuditLog.org_id == org, AuditLog.created_at >= since)).all()
    by_action: dict[str, int] = {}
    per_day: dict[str, int] = {}
    for action, _, at in events:
        by_action[action] = by_action.get(action, 0) + 1
        per_day[at.date().isoformat()] = per_day.get(at.date().isoformat(), 0) + 1
    today = utcnow().date()
    series = [{"date": (today - timedelta(days=i)).isoformat(),
               "events": per_day.get((today - timedelta(days=i)).isoformat(), 0)} for i in range(days - 1, -1, -1)]
    sum_actions = lambda prefix: sum(n for a, n in by_action.items() if a.startswith(prefix))  # noqa: E731
    docs = ctx.db.execute(select(func.count(Document.id), func.coalesce(func.sum(Document.size_bytes), 0)).where(
        Document.org_id == org, Document.deleted_at.is_(None))).one()
    return {
        "days": days,
        "members": count(select(func.count()).select_from(OrganizationMember).where(OrganizationMember.org_id == org)),
        "active_users": len({u for _, u, _ in events if u is not None}),
        "deals": {"active": count(select(func.count(Property.id)).where(Property.org_id == org,
                                                                       Property.deleted_at.is_(None))),
                  "created": by_action.get("property.create", 0)},
        "documents": {"stored": docs[0], "storage_bytes": int(docs[1]),
                      "uploaded": by_action.get("document.upload", 0)},
        "reports": {k.removeprefix("report."): n for k, n in by_action.items() if k.startswith("report.")},
        "values_reviewed": sum(by_action.get(f"extraction.{a}", 0) for a in ("accept", "edit", "reject")),
        "analyst_questions": by_action.get("analyst.question", 0),
        "scenario_changes": sum_actions("scenario.") + by_action.get("library.apply", 0),
        "api_keys": {"active": count(select(func.count(ApiKey.id)).where(
            ApiKey.org_id == org, ApiKey.revoked_at.is_(None))),
            "used_in_period": count(select(func.count(ApiKey.id)).where(
                ApiKey.org_id == org, ApiKey.last_used_at >= since))},
        "events_total": len(events),
        "events_per_day": series,
    }
