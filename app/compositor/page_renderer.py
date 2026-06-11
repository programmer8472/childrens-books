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
from reportlab.pdfgen.canvas import Canvas

from app.compositor import color as colormod
# Page geometry is owned by spread_types; re-exported here for back-compat
# (pdf_writer and tests import PAGE_W/PAGE_H/SAFE_INSET from page_renderer).
from app.compositor.spread_types import (
    BLEED,
    GUTTER,
    PAGE_H,
    PAGE_W,
    SAFE_INSET,
    SpreadType,
    text_box,
)
from app.compositor.typography import (
    FONT_BODY,
    LEADING_MULTIPLIER,
    SIZE_BODY_YOUNG,
    ensure_fonts_registered,
    fit_text_block,
    needs_contrast_pill,
    pick_text_color,
)

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


def _draw_fitted_text(
    c: Canvas,
    text: str,
    spread_type: SpreadType,
    font_size: float,
    text_color: tuple[int, int, int],
    bg_sample: tuple[int, int, int] | None,
) -> None:
    """Fit text into the spread's reserved box and draw it top-anchored.

    Uses fit_text_block so the block can never extend below its box — the
    guarantee that makes clipping structurally impossible. When text cannot fit
    even at the minimum size (which preflight independently rejects), it is
    still rendered at the floor size so the rejected PDF is inspectable.
    """
    box = text_box(spread_type)
    fit = fit_text_block(text, box.w, box.h, font_size)
    top_baseline = box.y + box.h - fit.size  # first line near box top, descends
    _draw_text_block(c, fit.lines, box.x, top_baseline, fit.size, text_color, bg_sample, box.w)


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

    if spread_type == SpreadType.FULL_BLEED_SINGLE_WITH_TEXT_PAGE:
        # Right page: illustration (shown on next showPage call by caller).
        # Current page: clean white + text.
        _draw_fitted_text(c, text, spread_type, font_size, (26, 26, 26), None)

    elif spread_type == SpreadType.PORTRAIT_WITH_CAPTION_BELOW:
        # Image fills the top of the page; text in generous white below.
        illus_h = PAGE_H * 0.58
        if image_bytes:
            _draw_full_bleed_image(c, image_bytes, 0, PAGE_H - illus_h, PAGE_W, illus_h)
        _draw_fitted_text(c, text, spread_type, font_size, (26, 26, 26), None)

    elif spread_type == SpreadType.VIGNETTE:
        # Illustration floats centered in the upper area; text in a lower band.
        vign_size = PAGE_W * 0.55
        vign_x = (PAGE_W - vign_size) / 2
        vign_y = PAGE_H - SAFE_INSET - vign_size  # anchored to top safe edge
        if image_bytes:
            pil = _load_image_bytes(image_bytes)
            cmyk = colormod.to_cmyk(pil)
            buf = io.BytesIO()
            cmyk.save(buf, format="JPEG", quality=92)
            buf.seek(0)
            from reportlab.lib.utils import ImageReader
            c.drawImage(ImageReader(buf), vign_x, vign_y, width=vign_size, height=vign_size,
                        preserveAspectRatio=True, mask="auto")
        _draw_fitted_text(c, text, spread_type, font_size, (26, 26, 26), None)

    else:
        # FULL_BLEED_DOUBLE / FULL_BLEED_SINGLE_OVERLAY: full-bleed image with a
        # text band over the lower-left, contrast-treated against the image.
        if image_bytes:
            _draw_full_bleed_image(c, image_bytes, 0, 0, PAGE_W, PAGE_H)
            bg = _sample_bg_color(image_bytes, "bottom")
        else:
            bg = (180, 200, 220)
        tc = pick_text_color(bg)
        _draw_fitted_text(c, text, spread_type, font_size, tc, bg)
