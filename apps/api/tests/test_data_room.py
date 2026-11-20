"""Data room: curated guest documents, time-limited and view-only access, watermarked downloads, publishing
report packages, and the external access log."""

import io
import uuid
from datetime import datetime, timedelta, timezone

from conftest import register
from pypdf import PdfReader
from test_roles import _join, two_deals  # noqa: F401 - fixture

from app.services.demo_docs import offering_memorandum_pdf


def _guest(client, owner):
    ext = _join(client, owner, "external")
    ext.email = ext.get("/api/auth/me").json()["user"]["email"]
    return ext


def _share(owner, pid, ext, **kw):
    r = owner.post(f"/api/properties/{pid}/shares", json={"user_id": ext.user_id, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_guests_only_see_data_room_documents(client, owner, two_deals):  # noqa: F811
    shared, _, _ = two_deals
    sid = shared["id"]
    doc = owner.post(f"/api/properties/{sid}/documents",
                     files={"file": ("om.pdf", offering_memorandum_pdf(), "application/pdf")}).json()
    ext = _guest(client, owner)
    _share(owner, sid, ext)
    # Not in the data room yet: invisible to the guest, everywhere.
    assert ext.get(f"/api/properties/{sid}/documents").json() == []
    assert ext.get(f"/api/properties/{sid}/data-room").json()["documents"] == []
    for path in (f"/api/documents/{doc['id']}", f"/api/documents/{doc['id']}/pages",
                 f"/api/documents/{doc['id']}/download", f"/api/documents/{doc['id']}/extractions"):
        assert ext.get(path).status_code == 404, path
    assert ext.get(f"/api/properties/{sid}/extractions").json() == []
    # Members see every document with its data room flag.
    assert [d["data_room"] for d in owner.get(f"/api/properties/{sid}/data-room").json()["documents"]] == [False]
    assert owner.put(f"/api/documents/{doc['id']}/data-room", json={"in_room": True}).json()["data_room"] is True
    room = ext.get(f"/api/properties/{sid}/data-room").json()
    assert [d["name"] for d in room["documents"]] == ["om.pdf"]
    assert room["my_access"] == {"can_download": True, "expires_at": None}
    assert ext.get(f"/api/documents/{doc['id']}/pages").status_code == 200
    # Guests can't get raw signed links; downloads go through the watermarking endpoint.
    assert ext.get(f"/api/documents/{doc['id']}/url").status_code == 403
    r = ext.get(f"/api/documents/{doc['id']}/download")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    text = PdfReader(io.BytesIO(r.content)).pages[0].extract_text()
    assert f"Shared with {ext.email}" in text and "Confidential" in text
    # Members download the original, unstamped.
    own = owner.get(f"/api/documents/{doc['id']}/download").content
    assert "Shared with" not in PdfReader(io.BytesIO(own)).pages[0].extract_text()
    # Removing it from the room hides it again; only analysts+ can change the room.
    assert ext.put(f"/api/documents/{doc['id']}/data-room", json={"in_room": False}).status_code == 403
    owner.put(f"/api/documents/{doc['id']}/data-room", json={"in_room": False})
    assert ext.get(f"/api/documents/{doc['id']}/download").status_code == 404


def test_view_only_and_expiring_access(client, owner, two_deals):  # noqa: F811
    shared, _, _ = two_deals
    sid = shared["id"]
    doc = owner.post(f"/api/properties/{sid}/documents",
                     files={"file": ("om.pdf", offering_memorandum_pdf(), "application/pdf")}).json()
    owner.put(f"/api/documents/{doc['id']}/data-room", json={"in_room": True})
    ext = _guest(client, owner)
    soon = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    _share(owner, sid, ext, can_download=False, expires_at=soon)
    room = ext.get(f"/api/properties/{sid}/data-room").json()
    assert room["my_access"]["can_download"] is False and room["my_access"]["expires_at"]
    assert ext.get(f"/api/documents/{doc['id']}/download").status_code == 403  # view-only
    assert ext.get(f"/api/documents/{doc['id']}/pages").status_code == 200
    listing = owner.get(f"/api/properties/{sid}/shares").json()[0]
    assert listing["shared"] is True and listing["can_download"] is False and listing["expires_at"]
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert owner.post(f"/api/properties/{sid}/shares", json={"user_id": ext.user_id, "expires_at": past}).status_code == 422
    # Simulate the end date passing: access stops everywhere, and the listing shows it expired.
    from app.db import SessionLocal
    from app.models import DealShare

    with SessionLocal() as db:
        from app.db import set_tenant

        set_tenant(db, uuid.UUID(owner.org_id))
        s = db.query(DealShare).filter(DealShare.property_id == uuid.UUID(sid)).one()
        s.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert ext.get(f"/api/properties/{sid}").status_code == 404
    assert ext.get(f"/api/properties/{sid}/data-room").status_code == 404
    assert ext.get("/api/properties").json() == [] or sid not in [p["id"] for p in ext.get("/api/properties").json()]
    expired = owner.get(f"/api/properties/{sid}/shares").json()[0]
    assert expired["shared"] is False and expired["expired"] is True


def test_publish_package_and_access_log(client, owner, two_deals):  # noqa: F811
    shared, _, _ = two_deals
    sid = shared["id"]
    r = owner.post(f"/api/properties/{sid}/data-room/publish", json={"items": ["one_pager", "ic_memo", "excel"]})
    assert r.status_code == 201, r.text
    docs = r.json()["documents"]
    assert len(docs) == 3 and all(d["data_room"] and d["published"] for d in docs)
    assert {d["mime_type"] for d in docs} == {"application/pdf",
                                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    ext = _guest(client, owner)
    _share(owner, sid, ext)
    memo = next(d for d in docs if "IC-memo" in d["name"])
    pdf = ext.get(f"/api/documents/{memo['id']}/download")
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "Investment Committee Memorandum" in text and f"Shared with {ext.email}" in text
    xlsx = next(d for d in docs if d["name"].endswith(".xlsx"))
    assert ext.get(f"/api/documents/{xlsx['id']}/download").status_code == 200
    ext.get(f"/api/documents/{memo['id']}/pages")
    log = owner.get(f"/api/properties/{sid}/data-room/access-log").json()
    guest = [e for e in log if e["external"]]
    assert {e["action"] for e in guest} >= {"dataroom.download", "dataroom.view"}
    assert all(e["email"] == ext.email for e in guest)
    assert any(e["action"] == "dataroom.publish" for e in log)
    assert ext.get(f"/api/properties/{sid}/data-room/access-log").status_code == 403
    assert _join(client, owner, "analyst").get(f"/api/properties/{sid}/data-room/access-log").status_code == 403
    assert owner.post(f"/api/properties/{sid}/data-room/publish", json={"items": []}).status_code == 422
    assert ext.post(f"/api/properties/{sid}/data-room/publish", json={"items": ["one_pager"]}).status_code == 403
    stranger = register(client)
    assert stranger.get(f"/api/properties/{sid}/data-room").status_code == 404
    assert stranger.get(f"/api/documents/{memo['id']}/download").status_code == 404
