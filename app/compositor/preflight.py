"""Pre-export QA gate for the composed interior.

The compositor renders fit-or-flag, but the binding promise — "never ship a
clipped or out-of-spec book" — needs an independent assertion before a book is
declared EXPORT_READY. This module re-checks the print-correctness invariants
the screenshot defect proved were unenforced: per-spread text fit, the word
budget, image resolution, and the 32-page / blank-barcode page structure.

The orchestrator runs validate_interior() right before the EXPORT_READY
transition; any failure routes the book to RETIRED with the report attached.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from PIL import Image as PilImage

from app.agents.base import check_spread_budget
from app.compositor.spread_types import spread_type_for_index, text_box
from app.compositor.typography import body_font_size, text_fits

# Smallest acceptable image side in pixels. The smallest region any spread type
# places an illustration into is ~5 inches; 1500px keeps that at >=300 DPI while
# clearing every in-spec 300-DPI asset the providers produce.
_MIN_IMAGE_SIDE = 1500
_REQUIRED_PAGES = 32


@dataclass
class PreflightIssue:
    check: str
    spread_index: int | None
    detail: str

    def to_dict(self) -> dict:
        return {"check": self.check, "spread_index": self.spread_index, "detail": self.detail}


@dataclass
class PreflightReport:
    issues: list[PreflightIssue] = field(default_factory=list)
    page_count: int | None = None

    @property
    def passed(self) -> bool:
        return not self.issues

    def summary(self) -> str:
        if self.passed:
            return "preflight passed"
        return "; ".join(i.detail for i in self.issues)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "page_count": self.page_count,
            "issues": [i.to_dict() for i in self.issues],
        }


def validate_interior(
    spreads: list[str],
    images: list[bytes | None],
    metadata: dict,
    pdf_bytes: bytes | None = None,
) -> PreflightReport:
    """Validate the composed interior; return a structured pass/fail report."""
    issues: list[PreflightIssue] = []
    age_range = metadata.get("age_range", "3-8")
    font_size = body_font_size(age_range)

    # 1) Word budget — deterministic, independent of the judge.
    for violation in check_spread_budget(spreads, age_range):
        issues.append(PreflightIssue("word_budget", violation.index, violation.message()))

    # 2) Text fit — every spread must fit its reserved box at >= the floor size.
    for i, text in enumerate(spreads):
        if not text.strip():
            continue
        box = text_box(spread_type_for_index(i))
        if not text_fits(text, box.w, box.h, font_size):
            st = spread_type_for_index(i).value
            issues.append(PreflightIssue(
                "text_fit", i,
                f"Spread {i + 1} text overflows its {st} box even at the minimum size.",
            ))

    # 3) Image resolution — present illustrations must clear the print floor.
    for i, img in enumerate(images or []):
        if not img:
            continue
        try:
            with PilImage.open(io.BytesIO(img)) as im:
                w, h = im.size
        except Exception as exc:  # noqa: BLE001 — any decode failure is a defect
            issues.append(PreflightIssue("image_decode", i, f"Spread {i + 1} image unreadable: {exc}"))
            continue
        if min(w, h) < _MIN_IMAGE_SIDE:
            issues.append(PreflightIssue(
                "image_resolution", i,
                f"Spread {i + 1} image is {w}x{h}px, below the 300-DPI print floor.",
            ))

    # 4) Page structure — exactly 32 pages, last page blank (KDP barcode).
    page_count = None
    if pdf_bytes is not None:
        import fitz

        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page_count = doc.page_count
            if page_count != _REQUIRED_PAGES:
                issues.append(PreflightIssue(
                    "page_count", None,
                    f"Interior has {page_count} pages; KDP requires exactly {_REQUIRED_PAGES}.",
                ))
            if page_count:
                last = doc[-1]
                if last.get_text().strip() or last.get_images():
                    issues.append(PreflightIssue(
                        "barcode_page", page_count - 1,
                        "Final page (KDP barcode page) must be blank.",
                    ))

    return PreflightReport(issues=issues, page_count=page_count)
