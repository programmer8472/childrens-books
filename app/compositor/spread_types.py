"""Spread type enum, narrative-position assignment, and per-layout text boxes.

Spec: book-design-spec.md §Spread layout system + §Canonical format.
Assignment is deterministic from spread index (0-based) so it can be stored
in the DB and reproduced exactly on re-export. Page geometry lives here (the
single source) and is re-exported by page_renderer.
"""
from dataclasses import dataclass
from enum import Enum

from reportlab.lib.units import inch

# Spec dimensions (all in points at 72 pt/inch).
PAGE_W = 8.75 * inch        # bleed page width  (8.5 trim + 0.125 bleed × 2)
PAGE_H = 8.75 * inch        # bleed page height
BLEED = 0.125 * inch
SAFE_INSET = 0.375 * inch   # safe content zone from trim edge = 3× bleed
GUTTER = 0.5 * inch         # spine-side margin


class SpreadType(str, Enum):
    FULL_BLEED_DOUBLE = "FULL_BLEED_DOUBLE"
    FULL_BLEED_SINGLE_WITH_TEXT_PAGE = "FULL_BLEED_SINGLE_WITH_TEXT_PAGE"
    FULL_BLEED_SINGLE_OVERLAY = "FULL_BLEED_SINGLE_OVERLAY"
    PORTRAIT_WITH_CAPTION_BELOW = "PORTRAIT_WITH_CAPTION_BELOW"
    VIGNETTE = "VIGNETTE"


@dataclass(frozen=True)
class TextBox:
    """Rectangle (bottom-left origin) reserved for body text on a spread.

    Text is top-anchored within the box: the first baseline sits near the top
    and lines descend. As long as the wrapped block height fits `h`, no glyph
    can fall outside the rectangle — which is how clipping is made impossible.
    """
    x: float
    y: float
    w: float
    h: float


# Per-layout text rectangles, sized generously enough to hold the older-age
# word budget (75 words) at the 16pt floor, so fit_text_block never has to
# fail on in-budget content. Image areas are sized around these.
def text_box(spread_type: "SpreadType") -> TextBox:
    si = SAFE_INSET
    full_w = PAGE_W - 2 * si
    if spread_type == SpreadType.FULL_BLEED_SINGLE_WITH_TEXT_PAGE:
        # Clean text page — whole safe area.
        return TextBox(x=si, y=si, w=full_w, h=PAGE_H - 2 * si)
    if spread_type == SpreadType.PORTRAIT_WITH_CAPTION_BELOW:
        # Illustration fills the top ~58%; text sits in the white below it.
        illus_h = PAGE_H * 0.58
        return TextBox(x=si, y=si, w=full_w, h=(PAGE_H - illus_h) - si - 10)
    if spread_type == SpreadType.VIGNETTE:
        # Illustration floats in the upper area; text in a lower band.
        return TextBox(x=si, y=si, w=full_w, h=PAGE_H * 0.42 - si)
    # FULL_BLEED_DOUBLE / FULL_BLEED_SINGLE_OVERLAY: text band over the
    # lower-left of a full-bleed illustration (contrast pill applied as needed).
    return TextBox(x=si, y=si, w=PAGE_W * 0.62, h=PAGE_H * 0.42 - si)


# Ordered assignments for 12 story spreads (0-based index → SpreadType).
# Source: book-design-spec.md §Spread type assignment by narrative position.
_ASSIGNMENT: list[SpreadType] = [
    SpreadType.FULL_BLEED_DOUBLE,                  # 0  — opening
    SpreadType.PORTRAIT_WITH_CAPTION_BELOW,        # 1
    SpreadType.FULL_BLEED_SINGLE_WITH_TEXT_PAGE,   # 2
    SpreadType.PORTRAIT_WITH_CAPTION_BELOW,        # 3
    SpreadType.FULL_BLEED_SINGLE_OVERLAY,          # 4  — rising action
    SpreadType.VIGNETTE,                           # 5
    SpreadType.FULL_BLEED_SINGLE_OVERLAY,          # 6
    SpreadType.VIGNETTE,                           # 7
    SpreadType.FULL_BLEED_DOUBLE,                  # 8  — climax
    SpreadType.FULL_BLEED_DOUBLE,                  # 9
    SpreadType.FULL_BLEED_SINGLE_WITH_TEXT_PAGE,   # 10 — resolution
    SpreadType.PORTRAIT_WITH_CAPTION_BELOW,        # 11 — closing
]

NUM_STORY_SPREADS = 12


def assign_spread_types() -> list[SpreadType]:
    """Return the ordered SpreadType for each of the 12 story spreads."""
    return list(_ASSIGNMENT)


def spread_type_for_index(index: int) -> SpreadType:
    """Return the SpreadType for spread at 0-based index (clamps if out of range)."""
    return _ASSIGNMENT[min(index, len(_ASSIGNMENT) - 1)]
