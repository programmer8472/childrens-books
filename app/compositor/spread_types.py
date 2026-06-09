"""Spread type enum and narrative-position assignment.

Spec: book-design-spec.md §Spread layout system.
Assignment is deterministic from spread index (0-based) so it can be stored
in the DB and reproduced exactly on re-export.
"""
from enum import Enum


class SpreadType(str, Enum):
    FULL_BLEED_DOUBLE = "FULL_BLEED_DOUBLE"
    FULL_BLEED_SINGLE_WITH_TEXT_PAGE = "FULL_BLEED_SINGLE_WITH_TEXT_PAGE"
    FULL_BLEED_SINGLE_OVERLAY = "FULL_BLEED_SINGLE_OVERLAY"
    PORTRAIT_WITH_CAPTION_BELOW = "PORTRAIT_WITH_CAPTION_BELOW"
    VIGNETTE = "VIGNETTE"


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
