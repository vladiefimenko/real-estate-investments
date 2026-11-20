"""Workspace white-labeling: brand name, accent color, report footer and logo.

Stored in ``organizations.settings["branding"]``; the logo lives in object storage as a
re-encoded PNG. PDF reports read the active branding from a context variable that the
report routes set, so the renderers don't need it threaded through every signature.
"""

from __future__ import annotations

import contextvars
import io
import re
from contextlib import contextmanager
from typing import Any, Iterator

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_LOGO_BYTES = 2 * 1024 * 1024
LOGO_BOX = (600, 200)  # max width, height after resizing

_current: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("axiom_branding", default=None)


def branding_of(org: Any) -> dict[str, Any]:
    b = (org.settings or {}).get("branding") or {}
    return {"brand_name": b.get("brand_name"), "accent_color": b.get("accent_color"),
            "report_footer": b.get("report_footer"), "logo_version": b.get("logo_version"),
            "has_logo": bool(b.get("logo_key"))}


def logo_key(org_id: Any) -> str:
    return f"{org_id}/branding/logo.png"


def contrast_text(hex_color: str) -> str:
    """Black or white, whichever reads better on ``hex_color`` (WCAG relative luminance)."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    lum = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    return "#101828" if lum > 0.4 else "#FFFFFF"


def clean_logo(data: bytes) -> bytes:
    """Validate an uploaded logo and re-encode it as a size-limited PNG (drops metadata/payloads)."""
    from PIL import Image, UnidentifiedImageError

    if len(data) > MAX_LOGO_BYTES:
        raise ValueError("Logos must be 2 MB or smaller")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        img = Image.open(io.BytesIO(data))
        if img.format not in ("PNG", "JPEG", "WEBP"):
            raise ValueError("Upload a PNG, JPEG or WebP image")
        if img.width * img.height > 40_000_000:
            raise ValueError("That image is too large")
        img = img.convert("RGBA")
        img.thumbnail(LOGO_BOX)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("That file isn't a readable image") from exc
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


@contextmanager
def active(org: Any) -> Iterator[None]:
    """Make this workspace's branding (plus the logo bytes) visible to the PDF renderers."""
    b = branding_of(org)
    if b["has_logo"]:
        from .storage import get_storage

        try:
            b["logo_png"] = get_storage().get(logo_key(org.id))
        except Exception:  # noqa: BLE001 - a missing logo must never break a report
            b["logo_png"] = None
    token = _current.set(b)
    try:
        yield
    finally:
        _current.reset(token)


def current() -> dict[str, Any]:
    return _current.get() or {}
