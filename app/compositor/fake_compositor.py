"""FakeComposer — valid-structure outputs with placeholder content for tests.

Same interface as BookComposer. Every compositor test uses this; real and
fake share the same method signatures so they can be swapped in config.
"""
from __future__ import annotations

import io
import uuid

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas

from app.storage.local import LocalStorage

_PAGE_W = 8.75 * inch
_PAGE_H = 8.75 * inch


def _minimal_pdf(label: str) -> bytes:
    """Produce a structurally valid single-page PDF with a colored placeholder."""
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=(_PAGE_W, _PAGE_H))
    c.setFillColor(HexColor("#d4e8f0"))
    c.rect(0, 0, _PAGE_W, _PAGE_H, fill=1, stroke=0)
    c.setFillColor(Color(0.1, 0.1, 0.1))
    c.setFont("Helvetica", 18)
    c.drawCentredString(_PAGE_W / 2, _PAGE_H / 2, f"[FAKE] {label}")
    c.showPage()
    c.save()
    return buf.getvalue()


def _minimal_wide_pdf(label: str, width: float) -> bytes:
    """Produce a wide (cover) placeholder PDF."""
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=(width, _PAGE_H))
    c.setFillColor(HexColor("#f0d4d4"))
    c.rect(0, 0, width, _PAGE_H, fill=1, stroke=0)
    c.setFillColor(Color(0.1, 0.1, 0.1))
    c.setFont("Helvetica", 18)
    c.drawCentredString(width / 2, _PAGE_H / 2, f"[FAKE] {label}")
    c.showPage()
    c.save()
    return buf.getvalue()


class FakeComposer:
    """Generates structurally valid placeholder exports — no ReportLab layout logic."""

    def __init__(self, storage: LocalStorage) -> None:
        self._storage = storage
        self.calls: list[str] = []

    def compose_interior(
        self,
        book_id: uuid.UUID,
        story_text: str,
        images: list[bytes | None],
        metadata: dict,
    ) -> str:
        self.calls.append("compose_interior")
        key = f"exports/{book_id}/interior.pdf"
        self._storage.put(key, _minimal_pdf("INTERIOR"))
        return key

    def compose_cover(
        self,
        book_id: uuid.UUID,
        front_image_bytes: bytes | None,
        metadata: dict,
        page_count: int = 32,
    ) -> str:
        self.calls.append("compose_cover")
        cover_w = 2 * _PAGE_W + page_count * 0.002252 * inch
        key = f"exports/{book_id}/cover.pdf"
        self._storage.put(key, _minimal_wide_pdf("COVER", cover_w))
        return key

    def export_word(self, book_id: uuid.UUID, story_text: str, metadata: dict) -> str:
        self.calls.append("export_word")
        key = f"exports/{book_id}/book.docx"
        self._storage.put(key, b"PK\x03\x04FAKE_DOCX")
        return key

    def export_markdown(self, book_id: uuid.UUID, story_text: str, metadata: dict) -> str:
        self.calls.append("export_markdown")
        title = metadata.get("title", "Untitled")
        key = f"exports/{book_id}/book.md"
        self._storage.put(key, f"# {title}\n\n[placeholder]\n".encode())
        return key

    def export_text(self, book_id: uuid.UUID, story_text: str, metadata: dict) -> str:
        self.calls.append("export_text")
        key = f"exports/{book_id}/book.txt"
        self._storage.put(key, story_text.encode() if story_text else b"[placeholder]")
        return key

    def export_images(self, book_id: uuid.UUID, images: list[bytes | None], cover: bytes | None) -> str:
        self.calls.append("export_images")
        folder = f"exports/{book_id}/images"
        if cover:
            self._storage.put(f"{folder}/cover.jpg", cover)
        for i, img in enumerate(images):
            if img:
                self._storage.put(f"{folder}/spread_{i + 1:02d}.jpg", img)
        return folder

    def compose_all(
        self,
        book_id: uuid.UUID,
        story_text: str,
        interior_images: list[bytes | None],
        cover_image: bytes | None,
        metadata: dict,
    ) -> dict:
        self.calls.append("compose_all")
        interior_key = self.compose_interior(book_id, story_text, interior_images, metadata)
        cover_key = self.compose_cover(book_id, cover_image, metadata)
        word_key = self.export_word(book_id, story_text, metadata)
        md_key = self.export_markdown(book_id, story_text, metadata)
        txt_key = self.export_text(book_id, story_text, metadata)
        images_folder = self.export_images(book_id, interior_images, cover_image)
        return {
            "interior_pdf": interior_key,
            "cover_pdf": cover_key,
            "word": word_key,
            "markdown": md_key,
            "text": txt_key,
            "images_folder": images_folder,
        }
