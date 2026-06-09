"""Renders one story spread onto a ReportLab canvas.

Spec: book-design-spec.md §Spread layout system + §Typography system.
Each spread type gets its own _render_* function; all share the same
safe-zone and contrast-check logic.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image as PilImage
from reportlab.lib.colors import Color
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas

from app.compositor import color as colormod
from app.compositor.spread_types import SpreadType
from app.compositor.typography import (
    FONT_BODY,
    LEADING_MULTIPLIER,
    SIZE_BODY_YOUNG,
    ensure_fonts_registered,
    needs_contrast_pill,
    pick_text_color,
    wrap_text,
)

# Spec dimensions (all in points at 72 pt/inch).
PAGE_W = 8.75 * inch   # bleed page width
PAGE_H = 8.75 * inch   # bleed page height
BLEED = 0.125 * inch
SAFE_INSET = 0.375 * inch   # safe content zone from trim edge = 3× bleed
GUTTER = 0.5 * inch         # spine-side margin

# Double-spread is two pages side by side
SPREAD_W = 2 * PAGE_W

_PILL_ALPHA = 0.55
_PILL_RADIUS = 8


def _to_rl_color(rgb: tuple[int, int, int], alpha: float = 1.0) -> Color:
    return Color(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, alpha)


def _load_image_bytes(image_bytes: bytes) -> PilImage.Image:
    return PilImage.open(io.BytesIO(image_bytes))


def _draw_full_bleed_image(c: Canvas, image_bytes: bytes, x: float, y: float, w: float, h: float) -> None:
    """Draw an image scaled to fill (x,y)→(x+w, y+h), converting to CMYK."""
    pil = _load_image_bytes(image_bytes)
    cmyk = colormod.to_cmyk(pil)
    buf = io.BytesIO()
    cmyk.save(buf, format="JPEG", quality=92)
    buf.seek(0)
    c.drawImage(
        __import__("reportlab.lib.utils", fromlist=["ImageReader"]).ImageReader(buf),
        x, y, width=w, height=h, preserveAspectRatio=False, mask="auto",
    )


def _sample_bg_color(image_bytes: bytes, region: str = "bottom") -> tuple[int, int, int]:
    """Sample average RGB of a region of the image for contrast calculation."""
    pil = _load_image_bytes(image_bytes).convert("RGB")
    w, h = pil.size
    if region == "bottom":
        crop = pil.crop((0, int(h * 0.75), w, h))
    elif region == "top":
        crop = pil.crop((0, 0, w, int(h * 0.25)))
    else:
        crop = pil
    small = crop.resize((8, 8), PilImage.LANCZOS)
    pixels = list(small.getdata())
    r = sum(p[0] for p in pixels) // len(pixels)
    g = sum(p[1] for p in pixels) // len(pixels)
    b = sum(p[2] for p in pixels) // len(pixels)
    return (r, g, b)


def _draw_text_block(
    c: Canvas,
    lines: list[str],
    x: float,
    y: float,
    font_size: float,
    text_color: tuple[int, int, int],
    bg_sample: tuple[int, int, int] | None = None,
    max_width: float | None = None,
) -> None:
    """Draw left-aligned text lines with optional semi-transparent contrast pill."""
    ensure_fonts_registered()
    leading = font_size * LEADING_MULTIPLIER

    if bg_sample and needs_contrast_pill(text_color, bg_sample):
        block_h = len(lines) * leading + 16
        block_w = (max_width or 400) + 32
        c.saveState()
        c.setFillColor(Color(0, 0, 0, _PILL_ALPHA))
        c.roundRect(x - 16, y - block_h + leading, block_w, block_h, _PILL_RADIUS, fill=1, stroke=0)
        c.restoreState()

    c.setFont(FONT_BODY, font_size)
    c.setFillColor(_to_rl_color(text_color))
    ty = y
    for line in lines:
        c.drawString(x, ty, line)
        ty -= leading


def render_spread(
    c: Canvas,
    spread_type: SpreadType,
    text: str,
    image_bytes: bytes | None,
    font_size: float = SIZE_BODY_YOUNG,
    page_num: int = 0,
) -> None:
    """Render one story spread (left page already at c's current position).

    For double spreads: draws across full spread width on two pages.
    For single spreads: draws on the right page, text on left (or overlay).
    Caller must call c.showPage() after this function (once per physical page).
    """
    ensure_fonts_registered()
    lines = wrap_text(text, max_chars=40)
    text_x = SAFE_INSET
    text_y = PAGE_H - SAFE_INSET - font_size * LEADING_MULTIPLIER

    if spread_type == SpreadType.FULL_BLEED_DOUBLE:
        # Image spans both pages; text floats in lower-left safe zone.
        if image_bytes:
            _draw_full_bleed_image(c, image_bytes, 0, 0, PAGE_W, PAGE_H)
            bg = _sample_bg_color(image_bytes, "bottom")
        else:
            bg = (180, 200, 220)
        tc = pick_text_color(bg)
        _draw_text_block(c, lines, text_x, text_y * 0.5, font_size, tc, bg, PAGE_W - 2 * SAFE_INSET)

    elif spread_type == SpreadType.FULL_BLEED_SINGLE_WITH_TEXT_PAGE:
        # Right page: illustration (shown on next showPage call by caller).
        # Current page: clean white + text.
        text_x_adj = SAFE_INSET
        _draw_text_block(c, lines, text_x_adj, text_y, font_size, (26, 26, 26))

    elif spread_type == SpreadType.FULL_BLEED_SINGLE_OVERLAY:
        # Image on this page; text overlays in bottom-left corner.
        if image_bytes:
            _draw_full_bleed_image(c, image_bytes, 0, 0, PAGE_W, PAGE_H)
            bg = _sample_bg_color(image_bytes, "bottom")
        else:
            bg = (180, 200, 220)
        tc = pick_text_color(bg)
        overlay_y = SAFE_INSET + font_size * LEADING_MULTIPLIER * len(lines) + 8
        _draw_text_block(c, lines, text_x, overlay_y, font_size, tc, bg, PAGE_W * 0.6)

    elif spread_type == SpreadType.PORTRAIT_WITH_CAPTION_BELOW:
        # Image fills top 65-70% of page; text in generous white below.
        illus_h = PAGE_H * 0.66
        if image_bytes:
            _draw_full_bleed_image(c, image_bytes, 0, PAGE_H - illus_h, PAGE_W, illus_h)
        text_y_adj = PAGE_H - illus_h - SAFE_INSET
        _draw_text_block(c, lines, text_x, text_y_adj, font_size, (26, 26, 26))

    elif spread_type == SpreadType.VIGNETTE:
        # Illustration floats centered on white; text below.
        vign_size = PAGE_W * 0.70
        vign_x = (PAGE_W - vign_size) / 2
        vign_y = (PAGE_H - vign_size) / 2 + vign_size * 0.1
        if image_bytes:
            pil = _load_image_bytes(image_bytes)
            cmyk = colormod.to_cmyk(pil)
            buf = io.BytesIO()
            cmyk.save(buf, format="JPEG", quality=92)
            buf.seek(0)
            from reportlab.lib.utils import ImageReader
            c.drawImage(ImageReader(buf), vign_x, vign_y, width=vign_size, height=vign_size * 0.8,
                        preserveAspectRatio=True, mask="auto")
        text_y_adj = vign_y - SAFE_INSET
        _draw_text_block(c, lines, text_x, text_y_adj, font_size, (26, 26, 26))
