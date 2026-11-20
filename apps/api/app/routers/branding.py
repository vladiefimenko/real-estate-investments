"""White-label settings: brand name, accent color, report footer and logo."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..deps import OrgContext, admin, deal_reader
from ..services import branding as br
from ..services.storage import get_storage

router = APIRouter(tags=["branding"])


class BrandingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand_name: str | None = Field(default=None, max_length=60)
    accent_color: str | None = None
    report_footer: str | None = Field(default=None, max_length=200)

    @field_validator("accent_color")
    @classmethod
    def _color(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if not br.HEX.match(v):
            raise ValueError("Use a hex color like #1F6FEB")
        return v.upper()

    @field_validator("brand_name", "report_footer")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return v or None


def _save(ctx: OrgContext, **changes) -> None:
    settings = dict(ctx.org.settings or {})
    settings["branding"] = {**(settings.get("branding") or {}), **changes}
    ctx.org.settings = settings


@router.get("/org/branding")
def get_branding(ctx: OrgContext = Depends(deal_reader)):
    return br.branding_of(ctx.org)


@router.put("/org/branding")
def set_branding(body: BrandingIn, ctx: OrgContext = Depends(admin)):
    _save(ctx, **body.model_dump())
    ctx.audit("branding.update", "organization", ctx.org.id, **body.model_dump())
    ctx.db.commit()
    return br.branding_of(ctx.org)


@router.post("/org/branding/logo")
async def upload_logo(file: UploadFile = File(...), ctx: OrgContext = Depends(admin)):
    raw = await file.read(br.MAX_LOGO_BYTES + 1)
    try:
        png = br.clean_logo(raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    get_storage().put(br.logo_key(ctx.org.id), png, "image/png")
    version = int(((ctx.org.settings or {}).get("branding") or {}).get("logo_version") or 0) + 1
    _save(ctx, logo_key=br.logo_key(ctx.org.id), logo_version=version)
    ctx.audit("branding.logo", "organization", ctx.org.id, bytes=len(png))
    ctx.db.commit()
    return br.branding_of(ctx.org)


@router.delete("/org/branding/logo", status_code=204)
def delete_logo(ctx: OrgContext = Depends(admin)):
    get_storage().delete(br.logo_key(ctx.org.id))
    _save(ctx, logo_key=None)
    ctx.audit("branding.logo_removed", "organization", ctx.org.id)
    ctx.db.commit()
    return Response(status_code=204)


@router.get("/org/branding/logo")
def get_logo(ctx: OrgContext = Depends(deal_reader)):
    if not br.branding_of(ctx.org)["has_logo"]:
        raise HTTPException(404, "No logo uploaded")
    try:
        data = get_storage().get(br.logo_key(ctx.org.id))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, "No logo uploaded") from exc
    return Response(data, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})
