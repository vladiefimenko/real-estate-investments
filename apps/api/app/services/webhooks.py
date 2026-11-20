"""Outbound webhooks: signed HTTPS notifications for selected workspace events.

Flow: ``OrgContext.audit`` maps an audited action to a webhook event and queues it on
the database session. Only after that session commits are queued events delivered (in
a background thread by default), so rolled-back work never notifies anyone.

Safety (SSRF): only ``https`` URLs on port 443 are accepted; the host must resolve
exclusively to public IP addresses, checked when the webhook is saved and again just
before every delivery; redirects are not followed; each request has a short timeout.
Secrets are stored encrypted (AES-GCM) and used to sign ``timestamp.body`` with
HMAC-SHA256. After ``MAX_FAILURES`` consecutive failures a webhook is switched off.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import threading
import time
import uuid
from typing import Any
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from ..config import get_settings

log = logging.getLogger("axiom.webhooks")

EVENTS: dict[str, str] = {
    "deal.created": "A deal is created (demo seeding excluded)",
    "deal.stage_changed": "A deal moves to a new stage",
    "deal.deleted": "A deal is deleted",
    "report.generated": "Any report or export is generated",
    "verified_data.applied": "Verified document data is applied to a scenario",
}
MAX_FAILURES = 10
TIMEOUT_SECONDS = 5.0
DISPATCH_IN_THREAD = True  # tests switch this off to deliver synchronously


class UnsafeUrl(ValueError):
    pass


# ------------------------------------------------------------------ event mapping
def event_for(action: str, details: dict[str, Any]) -> str | None:
    if action == "property.create":
        return None if details.get("demo") else "deal.created"
    if action == "property.update":
        return "deal.stage_changed" if "status" in (details.get("changes") or {}) else None
    if action == "property.delete":
        return "deal.deleted"
    if action.startswith("report."):
        return "report.generated"
    if action == "extraction.apply":
        return "verified_data.applied"
    return None


def queue(db: Session, org_id: uuid.UUID, event_type: str, payload: dict[str, Any]) -> None:
    db.info.setdefault("webhook_events", []).append((str(org_id), event_type, payload))


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    pending = session.info.pop("webhook_events", None)
    if not pending:
        return
    if DISPATCH_IN_THREAD:
        threading.Thread(target=deliver_all, args=(pending,), daemon=True, name="axiom-webhooks").start()
    else:
        deliver_all(pending)


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop("webhook_events", None)


# ------------------------------------------------------------------ secrets
def _aead() -> AESGCM:
    key = hashlib.sha256(get_settings().encryption_key_bytes() + b":webhooks").digest()
    return AESGCM(key)


def new_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def encrypt_secret(secret: str) -> str:
    nonce = secrets.token_bytes(12)
    return base64.b64encode(nonce + _aead().encrypt(nonce, secret.encode(), b"webhook")).decode()


def decrypt_secret(blob: str) -> str:
    raw = base64.b64decode(blob)
    return _aead().decrypt(raw[:12], raw[12:], b"webhook").decode()


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


# ------------------------------------------------------------------ URL safety
def resolve(host: str) -> list[str]:  # separated so tests can stub DNS
    return [info[4][0] for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)]


def check_url(url: str) -> str:
    """Return the normalised URL, or raise UnsafeUrl if it could reach a non-public address."""
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UnsafeUrl("Webhook URLs must start with https://")
    if not parts.hostname or parts.username or parts.password:
        raise UnsafeUrl("Enter a plain https:// address without a username or password")
    if parts.port not in (None, 443):
        raise UnsafeUrl("Webhook URLs must use the standard HTTPS port (443)")
    host = parts.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise UnsafeUrl("Webhook URLs must point to a public internet address")
    try:
        addresses = resolve(host)
    except OSError as exc:
        raise UnsafeUrl(f"Couldn't find the host {host}") from exc
    if not addresses:
        raise UnsafeUrl(f"Couldn't find the host {host}")
    for a in addresses:
        ip = ipaddress.ip_address(a.split("%")[0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeUrl("Webhook URLs must point to a public internet address")
    return url


# ------------------------------------------------------------------ delivery
def _post(url: str, body: bytes, headers: dict[str, str]) -> int:  # separated so tests can capture requests
    with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
        return client.post(url, content=body, headers=headers).status_code


def build_request(hook_id: uuid.UUID, secret: str, event_type: str, org_id: str,
                  data: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    delivery = str(uuid.uuid4())
    body = json.dumps({"id": delivery, "type": event_type, "created_at": int(time.time()), "organization_id": org_id,
                       "data": data}, default=str, separators=(",", ":")).encode()
    ts = str(int(time.time()))
    return body, {"Content-Type": "application/json", "User-Agent": "Axiom-Webhooks/1.0",
                  "X-Axiom-Event": event_type, "X-Axiom-Delivery": delivery, "X-Axiom-Webhook-Id": str(hook_id),
                  "X-Axiom-Timestamp": ts, "X-Axiom-Signature": sign(secret, ts, body)}


def send(hook: Any, event_type: str, data: dict[str, Any]) -> tuple[bool, str]:
    """Deliver one event to one webhook. Returns (ok, status text); never raises."""
    try:
        url = check_url(hook.url)  # re-check: DNS may have changed since the webhook was saved
        body, headers = build_request(hook.id, decrypt_secret(hook.secret_encrypted), event_type,
                                      str(hook.org_id), data)
        code = _post(url, body, headers)
    except UnsafeUrl as exc:
        return False, f"Blocked: {exc}"
    except httpx.TimeoutException:
        return False, "Timed out"
    except Exception as exc:  # noqa: BLE001 - record any failure on the webhook instead of raising
        return False, f"Failed: {type(exc).__name__}"
    return 200 <= code < 300, f"HTTP {code}"


def record(hook: Any, ok: bool, status: str) -> None:
    from ..models import utcnow

    hook.last_delivery_at = utcnow()
    hook.last_status = status[:200]
    hook.consecutive_failures = 0 if ok else hook.consecutive_failures + 1
    if hook.consecutive_failures >= MAX_FAILURES:
        hook.active = False
        hook.last_status = f"{status[:120]} · switched off after {MAX_FAILURES} failures"


def deliver_all(pending: list[tuple[str, str, dict[str, Any]]]) -> None:
    from ..db import SessionLocal, set_tenant
    from ..models import Webhook

    for org_id, event_type, data in pending:
        with SessionLocal() as db:
            set_tenant(db, uuid.UUID(org_id))
            hooks = [h for h in db.scalars(select(Webhook).where(
                Webhook.org_id == uuid.UUID(org_id), Webhook.active.is_(True))).all() if event_type in (h.events or [])]
            for hook in hooks:
                ok, status = send(hook, event_type, data)
                record(hook, ok, status)
                if not ok:
                    log.warning("webhook delivery failed", extra={"webhook_id": str(hook.id), "status": status})
            if hooks:
                db.info.pop("webhook_events", None)
                db.commit()
