"""Renders the full flat cover PDF: back cover + spine + front cover.

Spec: book-design-spec.md §Cover specification.
Output is a single PDF page: width = back(8.75") + spine + front(8.75"), height = 8.75".
"""
from __future__ import annotations

import io

from PIL import Image as PilImage
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas

from app.compositor import color as colormod
from app.compositor.typography import (
    FONT_BODY,
    FONT_DISPLAY,
    SIZE_DISPLAY_MAX,
    SIZE_DISPLAY_MIN,
    ensure_fonts_registered,
)

_PAGE_H = 8.75 * inch
_COVER_W = 8.75 * inch   # front or back panel with bleed
_SPINE_PER_PAGE = 0.002252  # KDP formula: inches per page
_BARCODE_MARGIN_W = 2.0 * inch
_BARCODE_MARGIN_H = 1.2 * inch
_SAFE_INSET = 0.375 * inch


def _spine_width(page_count: int) -> float:
    return page_count * _SPINE_PER_PAGE * inch


def _flat_width(page_count: int) -> float:
    return 2 * _COVER_W + _spine_width(page_count)


def _draw_cover_image(c: Canvas, image_bytes: bytes | None, x: float, y: float, w: float, h: float) -> None:
    if image_bytes is None:
        c.setFillColor(HexColor("#3a5a8a"))
        c.rect(x, y, w, h, fill=1, stroke=0)
        return
    pil = PilImage.open(io.BytesIO(image_bytes))
    cmyk = colormod.to_cmyk(pil)
    buf = io.BytesIO()
    cmyk.save(buf, format="JPEG", quality=92)
    buf.seek(0)
    from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(buf), x, y, width=w, height=h, preserveAspectRatio=False, mask="auto")


def render_cover(
    output: io.BytesIO,
    front_image_bytes: bytes | None,
    metadata: dict,
    page_count: int = 32,
) -> None:
    """Render the complete flat cover to an in-memory PDF.

    metadata keys used: title (str), author (str, optional).
    """
    ensure_fonts_registered()

    spine_w = _spine_width(page_count)
    flat_w = _flat_width(page_count)

    c = Canvas(output, pagesize=(flat_w, _PAGE_H))

    # --- Back cover (left panel) ---
    back_x = 0.0
    # Plain colored background for back cover
    c.setFillColor(HexColor("#f5f0e8"))
    c.rect(back_x, 0, _COVER_W, _PAGE_H, fill=1, stroke=0)
    # Barcode clearance zone — bottom right of back cover, blank
    c.setFillColor(Color(1, 1, 1))
    c.rect(back_x + _COVER_W - _BARCODE_MARGIN_W - _SAFE_INSET,
           _SAFE_INSET, _BARCODE_MARGIN_W, _BARCODE_MARGIN_H, fill=1, stroke=0)

    # --- Spine ---
    spine_x = _COVER_W
    c.setFillColor(HexColor("#2c3e50"))
    c.rect(spine_x, 0, spine_w, _PAGE_H, fill=1, stroke=0)
    if spine_w >= 10:
        c.saveState()
        c.translate(spine_x + spine_w / 2, _PAGE_H / 2)
        c.rotate(90)
        title = metadata.get("title", "")
        c.setFillColor(Color(1, 1, 1))
        spine_font_size = min(max(spine_w * 0.6, 6), 14)
        c.setFont(FONT_DISPLAY, spine_font_size)
        c.drawCentredString(0, 0, title)
        c.restoreState()

    # --- Front cover (right panel) ---
    front_x = _COVER_W + spine_w
    _draw_cover_image(c, front_image_bytes, front_x, 0, _COVER_W, _PAGE_H)

    # Title overlay on front cover
    title = metadata.get("title", "")
    author = metadata.get("author", "")

    title_font_size = SIZE_DISPLAY_MAX if len(title) < 20 else SIZE_DISPLAY_MIN
    c.setFont(FONT_DISPLAY, title_font_size)
    c.setFillColor(Color(1, 1, 1))
    title_x = front_x + _SAFE_INSET
    title_y = _PAGE_H - _SAFE_INSET - title_font_size
    c.drawString(title_x, title_y, title)

    if author:
        c.setFont(FONT_BODY, 14)
        c.drawString(title_x, _SAFE_INSET + 20, author)

    c.showPage()
    c.save()
