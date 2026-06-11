"""Print-quality defense-in-depth: word budget, text fit, and preflight QA.

Regression anchor: a real spread (~75 words) was being typeset past the bottom
of the page and clipped mid-sentence in interior2.pdf. These tests prove the
three layers that now make that impossible:
  1. word budgets are defined and checked (app/agents/base.py)
  2. text fitting is measured, not guessed (app/compositor/typography.py)
  3. the export is gated on a preflight report (app/compositor/preflight.py),
     and a failing book is retired rather than declared EXPORT_READY.
"""
import io
import json
import tempfile

import pytest

from app.agents.base import (
    JudgementResult,
    check_spread_budget,
    word_budget,
)
from app.compositor.preflight import validate_interior
from app.compositor.spread_types import SpreadType, text_box
from app.compositor.typography import (
    SIZE_BODY_MIN,
    SIZE_BODY_YOUNG,
    fit_text_block,
    text_fits,
)

# The exact paragraph that overflowed page 5 of interior2.pdf.
SCREENSHOT_TEXT = (
    "Max sat at his desk. His feet wiggled. His pencil tapped. The classroom "
    "buzzed with twenty-six kids. Mrs. Chen wrote numbers on the board. Max "
    "tried to focus. But his brain zoomed like a rocket. Seven times eight is "
    "fifty-six, he thought. But wait—did he feed his lizard? What if lizards "
    "dreamed of flying? Could a lizard build a spaceship? Out the window, a "
    "squirrel scampered. Max wanted to scamper too."
)
IN_BUDGET_SPREAD = "Max tapped his pencil. His brain zoomed like a rocket today."


# ---------------------------------------------------------------------------
# Layer 1 — word budgets
# ---------------------------------------------------------------------------


class TestWordBudget:
    def test_young_band(self):
        assert word_budget("3-5") == 30

    def test_older_band(self):
        assert word_budget("5-8") == 75

    def test_default_mixed_range_uses_older(self):
        assert word_budget("3-8") == 75

    def test_over_budget_spread_flagged(self):
        spreads = [IN_BUDGET_SPREAD] * 11 + [SCREENSHOT_TEXT]
        violations = check_spread_budget(spreads, "3-5")
        assert len(violations) == 1
        assert violations[0].index == 11
        assert violations[0].word_count > 30

    def test_in_budget_spreads_pass(self):
        assert check_spread_budget([IN_BUDGET_SPREAD] * 12, "3-5") == []


# ---------------------------------------------------------------------------
# Layer 2 — text fitting (the actual clipping defect)
# ---------------------------------------------------------------------------


class TestTextFitting:
    def test_screenshot_text_autofits_instead_of_clipping(self):
        # At the full 20pt the screenshot paragraph overflows the box (the old
        # fixed-size renderer is exactly why it clipped off the page). The
        # fitter must shrink it to a size that fits — never draw past the box.
        box = text_box(SpreadType.FULL_BLEED_DOUBLE)
        from app.compositor.typography import wrap_text_to_width, FONT_BODY, LEADING_MULTIPLIER
        at_full = wrap_text_to_width(SCREENSHOT_TEXT, FONT_BODY, SIZE_BODY_YOUNG, box.w)
        assert len(at_full) * SIZE_BODY_YOUNG * LEADING_MULTIPLIER > box.h  # would clip

        fit = fit_text_block(SCREENSHOT_TEXT, box.w, box.h, SIZE_BODY_YOUNG)
        assert fit.fits is True
        assert SIZE_BODY_MIN <= fit.size < SIZE_BODY_YOUNG

    def test_unfittable_text_is_reported_not_clipped(self):
        box = text_box(SpreadType.FULL_BLEED_DOUBLE)
        huge = SCREENSHOT_TEXT * 3
        assert text_fits(huge, box.w, box.h, SIZE_BODY_YOUNG) is False

    def test_in_budget_text_fits_every_layout(self):
        for st in SpreadType:
            box = text_box(st)
            fit = fit_text_block(IN_BUDGET_SPREAD, box.w, box.h, SIZE_BODY_YOUNG)
            assert fit.fits, f"in-budget text should fit {st.value}"

    def test_fit_uses_full_size_when_there_is_room(self):
        box = text_box(SpreadType.FULL_BLEED_SINGLE_WITH_TEXT_PAGE)
        fit = fit_text_block("A short line.", box.w, box.h, SIZE_BODY_YOUNG)
        assert fit.size == SIZE_BODY_YOUNG

    def test_fit_never_returns_below_floor(self):
        box = text_box(SpreadType.VIGNETTE)
        fit = fit_text_block(SCREENSHOT_TEXT * 3, box.w, box.h, SIZE_BODY_YOUNG)
        assert fit.size >= SIZE_BODY_MIN

    def test_no_wrapped_line_exceeds_box_width(self):
        box = text_box(SpreadType.FULL_BLEED_DOUBLE)
        from reportlab.pdfbase import pdfmetrics

        from app.compositor.typography import FONT_BODY, ensure_fonts_registered
        ensure_fonts_registered()
        fit = fit_text_block(IN_BUDGET_SPREAD, box.w, box.h, SIZE_BODY_YOUNG)
        for line in fit.lines:
            assert pdfmetrics.stringWidth(line, FONT_BODY, fit.size) <= box.w


# ---------------------------------------------------------------------------
# Layer 3 — preflight QA gate
# ---------------------------------------------------------------------------


def _metadata(age_range: str = "3-5") -> dict:
    return {"title": "T", "author": "A", "age_range": age_range}


class TestPreflight:
    def test_flags_over_budget_spread(self):
        # SCREENSHOT_TEXT is ~75 words — over the 30-word young budget.
        spreads = [IN_BUDGET_SPREAD] * 11 + [SCREENSHOT_TEXT]
        report = validate_interior(spreads, [None] * 12, _metadata("3-5"))
        assert report.passed is False
        assert "word_budget" in {i.check for i in report.issues}

    def test_flags_unfittable_spread(self):
        # An unfittable block at spread 0 (FULL_BLEED_DOUBLE) trips text_fit.
        spreads = [SCREENSHOT_TEXT * 3] + [IN_BUDGET_SPREAD] * 11
        report = validate_interior(spreads, [None] * 12, _metadata("5-8"))
        assert report.passed is False
        assert "text_fit" in {i.check for i in report.issues}

    def test_passes_for_in_budget_book(self):
        report = validate_interior([IN_BUDGET_SPREAD] * 12, [None] * 12, _metadata("3-5"))
        assert report.passed is True

    def test_flags_low_resolution_image(self):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (200, 200), (120, 120, 120)).save(buf, format="JPEG")
        images = [buf.getvalue()] + [None] * 11
        report = validate_interior([IN_BUDGET_SPREAD] * 12, images, _metadata())
        assert report.passed is False
        assert any(i.check == "image_resolution" for i in report.issues)

    def test_validates_composed_pdf_is_32_pages(self):
        from app.compositor.pdf_writer import assemble_interior
        buf = io.BytesIO()
        spreads = [IN_BUDGET_SPREAD] * 12
        assemble_interior(buf, "\n\n".join(spreads), [None] * 12, _metadata(), spreads=spreads)
        report = validate_interior(spreads, [None] * 12, _metadata(), buf.getvalue())
        assert report.page_count == 32
        assert report.passed is True


# ---------------------------------------------------------------------------
# Orchestrator budget gate
# ---------------------------------------------------------------------------


class TestBudgetGate:
    def _orch(self):
        from app.orchestrator import Orchestrator
        return Orchestrator(None, None, None, None, None, None, None)

    def _result(self) -> JudgementResult:
        return JudgementResult(
            emotional_authenticity=8.0, representation_quality=8.0, pacing=8.0,
            age_fit=8.0, uniqueness=8.0, weighted_total=8.0, passed=True,
            critique={"age_fit": "Good."},
        )

    def test_over_budget_forces_fail_with_critique(self):
        from types import SimpleNamespace
        version = SimpleNamespace(spreads=[SCREENSHOT_TEXT] * 12, content="")
        result = self._result()
        self._orch()._apply_budget_gate(version, result, "3-5")
        assert result.passed is False
        assert "LENGTH FAIL" in result.critique["age_fit"]

    def test_in_budget_leaves_result_untouched(self):
        from types import SimpleNamespace
        version = SimpleNamespace(spreads=[IN_BUDGET_SPREAD] * 12, content="")
        result = self._result()
        self._orch()._apply_budget_gate(version, result, "3-5")
        assert result.passed is True
