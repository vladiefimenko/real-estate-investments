"""Stamp a viewer-specific watermark on every page of a PDF before a guest downloads it."""

from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.pdfgen import canvas


def _overlay(width: float, height: float, text: str) -> PdfReader:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.saveState()
    c.setFillColor(colors.Color(0.55, 0.1, 0.1, alpha=0.13))
    size = max(18.0, min(width, height) / 16)
    c.setFont("Helvetica-Bold", size)
    c.translate(width / 2, height / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, text)
    c.restoreState()
    c.setFillColor(colors.Color(0.35, 0.35, 0.35, alpha=0.9))
    c.setFont("Helvetica", 7)
    c.drawString(18, 10, f"{text} · Confidential – do not forward")
    c.save()
    buf.seek(0)
    return PdfReader(buf)


def stamp_pdf(data: bytes, text: str) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))  # pages must belong to the writer to be stamped
    cache: dict[tuple[float, float], object] = {}
    for page in writer.pages:
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        if (w, h) not in cache:
            cache[(w, h)] = _overlay(w, h, text).pages[0]
        page.merge_page(cache[(w, h)])
    writer.add_metadata({"/Producer": "Axiom data room"})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
