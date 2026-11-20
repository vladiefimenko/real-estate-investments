"""Deal data room: the curated documents external members can see, watermarked downloads,
time-limited access, publishing report packages, and the external access log."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..deps import OrgContext, admin, analyst, deal_reader
from ..models import AuditLog, Document, OrganizationMember, User
from ..services import branding as br
from ..services.storage import get_storage
from ..services.watermark import stamp_pdf

router = APIRouter(tags=["data room"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ACCESS_ACTIONS = ("dataroom.view", "dataroom.download", "dataroom.add", "dataroom.remove", "dataroom.publish",
                  "deal.share", "deal.unshare")


def _doc_out(d: Document) -> dict:
    return {"id": str(d.id), "name": d.name, "type": d.type, "mime_type": d.mime_type, "size_bytes": d.size_bytes,
            "status": d.status, "data_room": d.data_room, "created_at": d.created_at.isoformat(),
            "published": d.extractor == "axiom-report"}


@router.get("/properties/{property_id}/data-room")
def data_room(property_id: uuid.UUID, ctx: OrgContext = Depends(deal_reader)):
    """Guests get the data room's documents and their own access terms; members also see every other document."""
    prop = ctx.get_property(property_id)
    q = select(Document).where(Document.property_id == prop.id, Document.deleted_at.is_(None))
    if ctx.is_external:
        q = q.where(Document.data_room.is_(True))
    docs = ctx.db.scalars(q.order_by(Document.data_room.desc(), Document.created_at.desc())).all()
    out = {"documents": [_doc_out(d) for d in docs], "my_access": None}
    if ctx.is_external:
        share = ctx.share_for(prop.id)
        out["my_access"] = {"can_download": share.can_download,
                            "expires_at": share.expires_at.isoformat() if share.expires_at else None}
    return out


class RoomIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    in_room: bool


@router.put("/documents/{document_id}/data-room")
def set_in_room(document_id: uuid.UUID, body: RoomIn, ctx: OrgContext = Depends(analyst)):
    d = ctx.db.get(Document, document_id)
    if d is None or d.org_id != ctx.org.id or d.deleted_at is not None:
        raise HTTPException(404, "Document not found")
    ctx.get_property(d.property_id)
    if d.data_room != body.in_room:
        d.data_room = body.in_room
        ctx.audit("dataroom.add" if body.in_room else "dataroom.remove", "document", d.id,
                  property_id=d.property_id, name=d.name)
        ctx.db.commit()
    return _doc_out(d)


@router.get("/documents/{document_id}/download")
def download(document_id: uuid.UUID, ctx: OrgContext = Depends(deal_reader)):
    """Download a document. Guests need download permission; PDFs they download carry their name and the date."""
    from .documents import _doc

    d = _doc(ctx, document_id)  # guests: only data-room documents on deals still shared with them
    data = get_storage().get(d.file_url)
    if ctx.is_external:
        share = ctx.share_for(d.property_id)
        if not share.can_download:
            raise HTTPException(403, "This data room is view-only for you")
        if d.mime_type == "application/pdf":
            data = stamp_pdf(data, f"Shared with {ctx.user.email} · {date.today():%b %d, %Y}")
    ctx.audit("dataroom.download", "document", d.id, property_id=d.property_id, name=d.name,
              watermarked=ctx.is_external and d.mime_type == "application/pdf")
    ctx.db.commit()
    safe = re.sub(r'[^A-Za-z0-9._ -]+', "_", d.name)[:150] or "document"
    return Response(data, media_type=d.mime_type, headers={"Content-Disposition": f'attachment; filename="{safe}"',
                                                           "Cache-Control": "no-store"})


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[Literal["one_pager", "ic_memo", "excel"]] = Field(min_length=1, max_length=3)


@router.post("/properties/{property_id}/data-room/publish", status_code=201)
def publish(property_id: uuid.UUID, body: PublishIn, ctx: OrgContext = Depends(analyst)):
    """Generate the latest reports from the base case and put them straight into the data room."""
    from ..services.analyst import verified_fields
    from ..services.report_excel import build_workbook
    from ..services.report_pdf import ic_memo, one_pager
    from .reports import _filename, _irr_sensitivity, _load
    from .scenarios import scenario_comparison

    prop, sc, result = _load(ctx, property_id, None)
    stamp = f"{date.today():%Y-%m-%d}"
    made = []
    with br.active(ctx.org):
        for item in dict.fromkeys(body.items):
            if item == "one_pager":
                data, mime, suffix = one_pager(prop, sc.name, result), "application/pdf", f"summary-{stamp}.pdf"
            elif item == "ic_memo":  # no IC votes or deliberations: this copy is for outside parties
                data = ic_memo(prop, sc.name, result, scenario_comparison(prop.id, ctx),
                               _irr_sensitivity(sc.assumptions_json), verified_fields(ctx, prop), None, ic=None)
                mime, suffix = "application/pdf", f"IC-memo-{stamp}.pdf"
            else:
                data = build_workbook(prop, sc.name, sc.assumptions_json, result, _irr_sensitivity(sc.assumptions_json))
                mime, suffix = XLSX, f"model-{stamp}.xlsx"
            doc_id = uuid.uuid4()
            key = f"{ctx.org.id}/{prop.id}/{doc_id}"
            get_storage().put(key, data, mime)
            d = Document(id=doc_id, org_id=ctx.org.id, property_id=prop.id, name=_filename(prop, suffix),
                         type="model" if item == "excel" else "other", mime_type=mime, size_bytes=len(data),
                         sha256=hashlib.sha256(data).hexdigest(), file_url=key, status="extracted",
                         extractor="axiom-report", uploaded_by=ctx.user.id, data_room=True)
            ctx.db.add(d)
            made.append(d)
    ctx.db.flush()
    ctx.audit("dataroom.publish", "property", prop.id, property_id=prop.id, items=list(dict.fromkeys(body.items)),
              scenario=sc.name)
    ctx.db.commit()
    return {"documents": [_doc_out(d) for d in made]}


@router.get("/properties/{property_id}/data-room/access-log")
def access_log(property_id: uuid.UUID, ctx: OrgContext = Depends(admin)):
    """Who outside the firm viewed or downloaded what, plus changes to the data room and its shares."""
    prop = ctx.get_property(property_id)
    rows = ctx.db.execute(
        select(AuditLog, User.name, User.email, OrganizationMember.role)
        .outerjoin(User, User.id == AuditLog.user_id)
        .outerjoin(OrganizationMember, (OrganizationMember.user_id == AuditLog.user_id)
                   & (OrganizationMember.org_id == ctx.org.id))
        .where(AuditLog.org_id == ctx.org.id, AuditLog.property_id == prop.id,
               AuditLog.action.in_(ACCESS_ACTIONS))
        .order_by(AuditLog.created_at.desc()).limit(300)).all()
    return [{"at": a.created_at.isoformat(), "action": a.action, "who": name or "System", "email": email,
             "external": role == "external", "document": (a.details or {}).get("name"),
             "details": {k: v for k, v in (a.details or {}).items() if k in ("items", "watermarked", "expires_at",
                                                                            "can_download", "user_id")}}
            for a, name, email, role in rows]
