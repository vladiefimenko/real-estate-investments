"""White-labeling: brand settings, logo upload validation, and branded PDF reports."""

import io

from conftest import MF_PROPERTY, register
from PIL import Image
from pypdf import PdfReader
from test_roles import _join


def _png(w=1200, h=400, color=(30, 90, 200, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _text(content: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages)


def test_branding_defaults_and_update(owner):
    b = owner.get("/api/org/branding").json()
    assert b == {"brand_name": None, "accent_color": None, "report_footer": None, "logo_version": None,
                 "has_logo": False}
    r = owner.put("/api/org/branding", json={"brand_name": "  Summit Capital ", "accent_color": "#1f6feb",
                                             "report_footer": "Confidential. Prepared by Summit Capital."})
    assert r.status_code == 200, r.text
    assert r.json()["brand_name"] == "Summit Capital" and r.json()["accent_color"] == "#1F6FEB"
    assert owner.get("/api/org/branding").json()["report_footer"].startswith("Confidential")
    audit = owner.get("/api/org/audit").json()
    assert any(e["action"] == "branding.update" for e in audit)
    # Clearing values falls back to the Axiom defaults.
    r = owner.put("/api/org/branding", json={"brand_name": "", "accent_color": "", "report_footer": None})
    assert r.json()["brand_name"] is None and r.json()["accent_color"] is None


def test_branding_validation(owner):
    for bad in ({"accent_color": "blue"}, {"accent_color": "#12345"}, {"accent_color": "#12345G"},
                {"brand_name": "x" * 61}, {"report_footer": "x" * 201}, {"logo_key": "../../etc/passwd"}):
        assert owner.put("/api/org/branding", json=bad).status_code == 422, bad


def test_logo_upload_is_validated_and_reencoded(owner):
    assert owner.get("/api/org/branding/logo").status_code == 404
    r = owner.post("/api/org/branding/logo", files={"file": ("logo.png", _png(), "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["has_logo"] and r.json()["logo_version"] == 1
    logo = owner.get("/api/org/branding/logo")
    assert logo.status_code == 200 and logo.headers["content-type"] == "image/png"
    img = Image.open(io.BytesIO(logo.content))
    assert img.format == "PNG" and img.width <= 600 and img.height <= 200  # resized
    # Re-uploading bumps the version so browsers refetch.
    assert owner.post("/api/org/branding/logo", files={"file": ("l.png", _png(100, 50), "image/png")}).json()[
        "logo_version"] == 2
    # Non-images, SVG (script-capable) and oversized files are refused.
    for name, data, ctype in (("x.png", b"not an image", "image/png"),
                              ("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>",
                               "image/svg+xml"),
                              ("big.png", b"\x89PNG" + b"0" * (2 * 1024 * 1024 + 10), "image/png")):
        assert owner.post("/api/org/branding/logo", files={"file": (name, data, ctype)}).status_code == 422, name
    assert owner.delete("/api/org/branding/logo").status_code == 204
    assert owner.get("/api/org/branding").json()["has_logo"] is False
    assert owner.get("/api/org/branding/logo").status_code == 404


def test_only_admins_edit_but_everyone_reads(client, owner):
    owner.put("/api/org/branding", json={"brand_name": "Summit Capital"})
    for role in ("analyst", "viewer", "external"):
        s = _join(client, owner, role)
        assert s.get("/api/org/branding").json()["brand_name"] == "Summit Capital", role
        assert s.put("/api/org/branding", json={"brand_name": "Hijack"}).status_code == 403, role
        assert s.post("/api/org/branding/logo", files={"file": ("l.png", _png(), "image/png")}).status_code == 403
        assert s.delete("/api/org/branding/logo").status_code == 403
    admin = _join(client, owner, "admin")
    assert admin.put("/api/org/branding", json={"brand_name": "Summit Partners"}).status_code == 200


def test_branding_is_tenant_scoped(client, owner):
    owner.put("/api/org/branding", json={"brand_name": "Summit Capital"})
    owner.post("/api/org/branding/logo", files={"file": ("logo.png", _png(), "image/png")})
    other = register(client)
    assert other.get("/api/org/branding").json()["brand_name"] is None
    assert other.get("/api/org/branding/logo").status_code == 404


def test_reports_use_branding(owner):
    pid = owner.post("/api/properties", json=MF_PROPERTY).json()["id"]
    before = owner.get(f"/api/properties/{pid}/reports/one-pager")
    assert "AXIOM" in _text(before.content)
    owner.put("/api/org/branding", json={"brand_name": "Summit Capital", "accent_color": "#F5F5F5",
                                         "report_footer": "Confidential: Summit Capital LP"})
    owner.post("/api/org/branding/logo", files={"file": ("logo.png", _png(), "image/png")})
    for path in ("one-pager", "ic-memo", "junior-pack", "presentation"):
        r = owner.get(f"/api/properties/{pid}/reports/{path}")
        assert r.status_code == 200, (path, r.text)
        text = _text(r.content)
        assert "Summit Capital" in text or "SUMMIT CAPITAL" in text, path
        assert "Confidential: Summit Capital LP" in text, path
        assert "deterministic" in text, path  # the engine disclaimer always stays
        assert any(p.images for p in PdfReader(io.BytesIO(r.content)).pages), path  # logo drawn
    # An explicit firm name on the presentation still wins.
    r = owner.get(f"/api/properties/{pid}/reports/presentation", params={"firm_name": "Other Firm"})
    assert "OTHER FIRM" in _text(r.content)
    r = owner.get("/api/reports/summary-pack", params={"ids": pid})
    assert "Summit Capital" in _text(r.content)


def test_demo_watermark_survives_branding(demo):
    demo.put("/api/org/branding", json={"brand_name": "Summit Capital"})
    pid = demo.get("/api/properties").json()[0]["id"]
    text = _text(demo.get(f"/api/properties/{pid}/reports/one-pager").content)
    assert "Summit Capital" in text and "DEMONSTRATION" in text
