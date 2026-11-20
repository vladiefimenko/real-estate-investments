"""Request dependencies: authentication, organization context and RBAC."""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db, set_tenant
from .models import ROLE_RANK, ApiKey, AuditLog, DealShare, Organization, OrganizationMember, Property, User, utcnow
from .security import decode_access_token, hash_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


@dataclass
class OrgContext:
    user: User
    org: Organization
    role: str
    db: Session
    api_key_id: uuid.UUID | None = None

    def require(self, role: str) -> None:
        if ROLE_RANK[self.role] < ROLE_RANK[role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires {role} role or higher")

    @property
    def can_edit(self) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK["analyst"]

    def audit(
        self,
        action: str,
        entity_type: str,
        entity_id: Any = None,
        property_id: uuid.UUID | None = None,
        **details: Any,
    ) -> None:
        if self.api_key_id is not None:
            details = {**details, "via_api_key": str(self.api_key_id)}
        from .services import webhooks

        hook_event = webhooks.event_for(action, details)
        if hook_event:  # delivered only after this session commits
            webhooks.queue(self.db, self.org.id, hook_event, {
                "action": action, "entity_type": entity_type,
                "entity_id": str(entity_id) if entity_id is not None else None,
                "property_id": str(property_id) if property_id else None,
                "actor": self.user.name, "details": details})
        self.db.add(
            AuditLog(
                org_id=self.org.id,
                user_id=self.user.id,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                property_id=property_id,
                details=details,
            )
        )

    @property
    def is_external(self) -> bool:
        return self.role == "external"

    def get_property(self, property_id: uuid.UUID) -> Property:
        prop = self.db.get(Property, property_id)
        if prop is None or prop.org_id != self.org.id or prop.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
        if self.is_external and not self.db.scalar(select(DealShare.id).where(
                DealShare.property_id == prop.id, DealShare.user_id == self.user.id)):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
        return prop


API_KEY_PREFIX = "axk_"
# API keys are read-only and limited to deal data. Members, settings, keys, audit and billing are never reachable.
API_KEY_PATHS = ("/api/properties", "/api/scenarios", "/api/compare", "/api/dashboard", "/api/property-types")
API_KEY_RATE = (120, 60.0)  # requests per window (seconds), per key, per process
_rate_lock = threading.Lock()
_rate_hits: dict[uuid.UUID, deque[float]] = {}


def _rate_limited(key_id: uuid.UUID) -> bool:
    limit, window = API_KEY_RATE
    now = time.monotonic()
    with _rate_lock:
        hits = _rate_hits.setdefault(key_id, deque())
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            return True
        hits.append(now)
        return False


def _api_key_context(token: str, request: Request, db: Session) -> OrgContext:
    if request.method not in ("GET", "HEAD"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "API keys are read-only")
    path = request.url.path
    if not any(path == p or path.startswith(p + "/") for p in API_KEY_PATHS):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "API keys cannot access this endpoint")
    key = db.scalars(select(ApiKey).where(ApiKey.key_hash == hash_token(token))).first()
    now = utcnow()
    if key is None or key.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    expires = key.expires_at.replace(tzinfo=now.tzinfo) if key.expires_at and key.expires_at.tzinfo is None \
        else key.expires_at
    if expires is not None and expires <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key has expired")
    user = db.get(User, key.created_by)
    member = db.scalars(select(OrganizationMember).where(
        OrganizationMember.org_id == key.org_id, OrganizationMember.user_id == key.created_by)).first()
    org = db.get(Organization, key.org_id)
    if user is None or not user.is_active or user.deleted_at is not None or member is None \
            or org is None or org.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key is no longer valid")
    if _rate_limited(key.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "API key rate limit exceeded",
                            headers={"Retry-After": str(int(API_KEY_RATE[1]))})
    last = key.last_used_at.replace(tzinfo=now.tzinfo) if key.last_used_at and key.last_used_at.tzinfo is None \
        else key.last_used_at
    if last is None or now - last > timedelta(minutes=1):
        key.last_used_at = now
        db.commit()
    set_tenant(db, org.id)
    return OrgContext(user=user, org=org, role="viewer", db=db, api_key_id=key.id)


def get_org_context(
    request: Request,
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> OrgContext:
    if creds is not None and creds.scheme.lower() == "bearer" and creds.credentials.startswith(API_KEY_PREFIX):
        return _api_key_context(creds.credentials, request, db)
    user = get_current_user(creds, db)
    q = select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    if x_org_id:
        try:
            q = q.where(OrganizationMember.org_id == uuid.UUID(x_org_id))
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid X-Org-Id") from exc
    membership = db.scalars(q.order_by(OrganizationMember.joined_at)).first()
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this organization")
    org = db.get(Organization, membership.org_id)
    if org is None or org.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    set_tenant(db, org.id)
    return OrgContext(user=user, org=org, role=membership.role, db=db)


def require_role(role: str):
    def dep(ctx: OrgContext = Depends(get_org_context)) -> OrgContext:
        ctx.require(role)
        return ctx

    return dep


# Deal-scoped, read-only routes that external members may use (still limited to shared deals
# by OrgContext.get_property). Every other route keeps `viewer` or higher, which excludes them.
deal_reader = require_role("external")
viewer = require_role("viewer")
analyst = require_role("analyst")
admin = require_role("admin")
owner = require_role("owner")


def audit_reader(ctx: OrgContext = Depends(get_org_context)) -> OrgContext:
    """Owners, admins and auditors: the full audit trail and usage, without edit rights."""
    if ctx.role not in ("owner", "admin", "auditor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requires admin or auditor role")
    return ctx
