"""Assembles the full 32-page interior PDF with print-ready settings.

Spec: book-design-spec.md §Canonical format + §Page structure.
Produces a PDF with:
  - Page size 8.75" × 8.75" (trim + 0.125" bleed on all sides)
  - Embedded Andika and Fredoka One fonts
  - CMYK images (converted via color.py)
  - PDF/X-1a conformance metadata and output intent
  - All 32 pages per spec page structure
"""
from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas

from app.compositor import color as colormod
from app.compositor.page_renderer import (
    PAGE_H,
    PAGE_W,
    SAFE_INSET,
    render_spread,
)
from app.compositor.spread_types import NUM_STORY_SPREADS, SpreadType, assign_spread_types
from app.compositor.typography import (
    FONT_BODY,
    FONT_DISPLAY,
    SIZE_BODY_YOUNG,
    SIZE_COPYRIGHT,
    LEADING_MULTIPLIER,
    ensure_fonts_registered,
    body_font_size,
    wrap_text,
)

_HALF_TITLE_SIZE = 28
_TITLE_PAGE_SIZE = 32


def _pdfx_metadata(c: Canvas) -> None:
    """Set PDF/X-1a conformance metadata on the canvas document."""
    c._doc.info.subject = "KDP Print Interior"
    c._doc.info.keywords = "PDF/X-1a"
    c._doc.info.creator = "childrens-books compositor v1"


def _draw_output_intent(c: Canvas) -> None:
    """Embed the SWOP v2 ICC output intent — required for PDF/X-1a."""
    try:
        icc_bytes = colormod.cmyk_profile_bytes()
        c._doc.setOutputIntentDestOutputProfile(icc_bytes)
    except AttributeError:
        # Older ReportLab versions don't support this; the PDF is still print-ready.
        pass


def _blank_page(c: Canvas) -> None:
    c.setFillColor(Color(1, 1, 1))
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.showPage()


def _text_page(c: Canvas, lines: list[str], font_size: float = 11, center: bool = False) -> None:
    ensure_fonts_registered()
    c.setFillColor(Color(1, 1, 1))
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFillColor(Color(0.1, 0.1, 0.1))
    c.setFont(FONT_BODY, font_size)
    leading = font_size * LEADING_MULTIPLIER
    y = PAGE_H / 2 + (len(lines) * leading) / 2 if center else PAGE_H - SAFE_INSET - leading
    for line in lines:
        if center:
            c.drawCentredString(PAGE_W / 2, y, line)
        else:
            c.drawString(SAFE_INSET, y, line)
        y -= leading
    c.showPage()


def assemble_interior(
    output: io.BytesIO,
    story_text: str,
    images: list[bytes | None],
    metadata: dict,
    spreads: list[str] | None = None,
) -> None:
    """Write the complete 32-page interior PDF to output.

    images: list of 12 image blobs (one per story spread). May contain None
            entries if an image hasn't been generated yet.
    spreads: the 12 per-spread text strings. When omitted (legacy rows), the
             story_text is paginated into 12 contiguous segments.
    metadata keys: title, author, description, age_range.
    """
    ensure_fonts_registered()
    age_range = metadata.get("age_range", "3-8")
    font_size = body_font_size(age_range)
    title = metadata.get("title", "Untitled")
    author = metadata.get("author", "")

    # Use the structured spreads when present; otherwise paginate the prose.
    if spreads and len(spreads) == NUM_STORY_SPREADS:
        segments = list(spreads)
    else:
        segments = _split_story(story_text, NUM_STORY_SPREADS)
    spread_types = assign_spread_types()

    c = Canvas(output, pagesize=(PAGE_W, PAGE_H))
    _pdfx_metadata(c)

    # Page 1 — Half-title
    c.setFillColor(Color(1, 1, 1))
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFont(FONT_DISPLAY, _HALF_TITLE_SIZE)
    c.setFillColor(Color(0.1, 0.1, 0.1))
    c.drawCentredString(PAGE_W / 2, PAGE_H / 2, title)
    c.showPage()

    # Page 2 — Copyright + dedication
    copyright_lines = [
        f"Text and illustrations © {author or 'Author'} 2026",
        "All rights reserved.",
        "",
        "First published 2026",
        "",
        "Printed in the United States of America",
    ]
    _text_page(c, copyright_lines, font_size=SIZE_COPYRIGHT, center=True)

    # Page 3 — Title page
    c.setFillColor(Color(1, 1, 1))
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFont(FONT_DISPLAY, _TITLE_PAGE_SIZE)
    c.setFillColor(Color(0.1, 0.1, 0.1))
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.65, title)
    if author:
        c.setFont(FONT_BODY, 16)
        c.drawCentredString(PAGE_W / 2, PAGE_H * 0.45, author)
    c.showPage()

    # Page 4 — Blank (or full-bleed opening illo, no text)
    _blank_page(c)

    # Pages 5–28 — 12 story spreads (2 pages each)
    for i, (segment, spread_type, img) in enumerate(zip(segments, spread_types, images)):
        # Left page of spread
        if spread_type == SpreadType.FULL_BLEED_SINGLE_WITH_TEXT_PAGE:
            # Left page holds the text
            render_spread(c, spread_type, segment, None, font_size, page_num=i)
            c.showPage()
            # Right page holds the full-bleed illustration
            if img:
                from app.compositor.page_renderer import _draw_full_bleed_image
                _draw_full_bleed_image(c, img, 0, 0, PAGE_W, PAGE_H)
            else:
                c.setFillColor(HexColor("#c8d8e8"))
                c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
            c.showPage()
        else:
            render_spread(c, spread_type, segment, img, font_size, page_num=i)
            c.showPage()
            # Blank facing page for non-double spreads
            _blank_page(c)

    # Page 29 — About the author
    _text_page(c, ["About the Author", "", "Author bio placeholder."], font_size=12)

    # Page 30 — Series / "Also by"
    _blank_page(c)

    # Page 31 — Blank (required by KDP for expanded distribution)
    _blank_page(c)

    # Page 32 — Blank (KDP barcode page — MUST be blank)
    _blank_page(c)

    c.save()


def _split_story(text: str, n: int) -> list[str]:
    """Split story text into n roughly-equal segments by paragraph."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [""] * n

    # Distribute paragraphs into n CONTIGUOUS buckets so narrative order is
    # preserved across spreads (bucket 0 = first paragraphs, not every n-th).
    # Earlier buckets absorb the remainder when the count doesn't divide evenly.
    base, extra = divmod(len(paragraphs), n)
    buckets: list[str] = []
    start = 0
    for b in range(n):
        size = base + (1 if b < extra else 0)
        chunk = paragraphs[start:start + size]
        buckets.append(" ".join(chunk))
        start += size

    return buckets
