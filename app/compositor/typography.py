"""Font loading, text measurement, line wrapping, and WCAG AA contrast check.

Spec: book-design-spec.md §Typography system.
All fonts are bundled in app/compositor/fonts/ — never rely on system fonts.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONTS_DIR = Path(__file__).parent / "fonts"

FONT_BODY = "Andika"
FONT_BODY_BOLD = "AndikaBold"
FONT_DISPLAY = "FredokaOne"

# Spec sizes
SIZE_BODY_YOUNG = 20       # ages 3-5
SIZE_BODY_OLDER = 18       # ages 5-8
SIZE_DISPLAY_MIN = 28
SIZE_DISPLAY_MAX = 36
SIZE_COPYRIGHT = 10
LEADING_MULTIPLIER = 1.5

# Spec colors (near-black / white — spec §Typography)
COLOR_DARK_TEXT = (26, 26, 26)      # #1A1A1A
COLOR_LIGHT_TEXT = (255, 255, 255)  # #FFFFFF

_registered = False


def ensure_fonts_registered() -> None:
    """Register Andika and Fredoka One with ReportLab (idempotent)."""
    global _registered
    if _registered:
        return
    pdfmetrics.registerFont(TTFont(FONT_BODY, str(_FONTS_DIR / "Andika-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BODY_BOLD, str(_FONTS_DIR / "Andika-Bold.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_DISPLAY, str(_FONTS_DIR / "FredokaOne-Regular.ttf")))
    _registered = True


def body_font_size(age_range: str) -> float:
    """Return the body font size in points for the given age range string."""
    if "3" in age_range or "4" in age_range or "5" in age_range:
        if "6" not in age_range and "7" not in age_range and "8" not in age_range:
            return SIZE_BODY_YOUNG
    return SIZE_BODY_OLDER


def wrap_text(text: str, max_chars: int = 40) -> list[str]:
    """Wrap text to lines of at most max_chars (spec: 35-45 chars per line)."""
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        lines.extend(textwrap.wrap(paragraph, width=max_chars) or [""])
    return lines


def _relative_luminance(r: float, g: float, b: float) -> float:
    """Compute relative luminance per WCAG 2.1."""
    def linearize(c: float) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    """Return WCAG AA contrast ratio between two RGB colors."""
    l1 = _relative_luminance(*fg)
    l2 = _relative_luminance(*bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def pick_text_color(bg_rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """Return dark or light text color that meets WCAG AA (4.5:1) against bg_rgb."""
    if contrast_ratio(COLOR_DARK_TEXT, bg_rgb) >= 4.5:
        return COLOR_DARK_TEXT
    return COLOR_LIGHT_TEXT


def needs_contrast_pill(text_color: tuple[int, int, int], bg_sample: tuple[int, int, int]) -> bool:
    """True if a soft contrast pill is needed behind text (ratio < 4.5:1)."""
    return contrast_ratio(text_color, bg_sample) < 4.5
