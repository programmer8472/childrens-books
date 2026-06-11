"""BookComposer: top-level export interface.

Produces the full KDP export bundle from an approved book:
  - interior.pdf  — 32-page print-ready PDF/X-1a interior
  - cover.pdf     — flat cover PDF (back + spine + front)
  - book.docx     — Word document for manual editing
  - book.md       — Markdown
  - book.txt      — raw text (Canva import)
  - images/       — organized image asset folder

All artifacts are written to LocalStorage under exports/{book_id}/.
"""
from __future__ import annotations

import io
import uuid
from pathlib import PurePosixPath

from docx import Document
from docx.shared import Pt

from app.compositor import color as colormod  # noqa: F401 (ensure color module loads ICC)
from app.compositor.cover_renderer import render_cover
from app.compositor.pdf_writer import assemble_interior
from app.compositor.typography import (
    FONT_BODY,
    LEADING_MULTIPLIER,
    ensure_fonts_registered,
)
from app.storage.local import LocalStorage


class BookComposer:
    def __init__(self, storage: LocalStorage) -> None:
        self._storage = storage

    def compose_interior(
        self,
        book_id: uuid.UUID,
        story_text: str,
        images: list[bytes | None],
        metadata: dict,
        spreads: list[str] | None = None,
    ) -> str:
        """Generate interior PDF; return storage key."""
        ensure_fonts_registered()
        buf = io.BytesIO()
        assemble_interior(buf, story_text, images, metadata, spreads=spreads)
        key = f"exports/{book_id}/interior.pdf"
        self._storage.put(key, buf.getvalue())
        return key

    def render_previews(self, book_id: uuid.UUID, interior_pdf: bytes, dpi: int = 96) -> list[str]:
        """Rasterize each interior page to a PNG preview; return ordered keys.

        These are the in-app visual-QA images shown before final sign-off, so a
        human sees the real composed pages — not just metadata. Low DPI keeps
        them light; the print PDF remains the source of truth.
        """
        import fitz  # PyMuPDF — pure-wheel PDF rasterizer

        keys: list[str] = []
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        with fitz.open(stream=interior_pdf, filetype="pdf") as doc:
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                key = f"exports/{book_id}/previews/page_{i + 1:02d}.png"
                self._storage.put(key, pix.tobytes("png"))
                keys.append(key)
        return keys

    def compose_cover(
        self,
        book_id: uuid.UUID,
        front_image_bytes: bytes | None,
        metadata: dict,
        page_count: int = 32,
    ) -> str:
        """Generate flat cover PDF; return storage key."""
        ensure_fonts_registered()
        buf = io.BytesIO()
        render_cover(buf, front_image_bytes, metadata, page_count)
        key = f"exports/{book_id}/cover.pdf"
        self._storage.put(key, buf.getvalue())
        return key

    def export_word(self, book_id: uuid.UUID, story_text: str, metadata: dict) -> str:
        """Generate Word .docx; return storage key."""
        doc = Document()
        title = metadata.get("title", "Untitled")
        doc.add_heading(title, level=0)
        doc.add_paragraph()
        for para in story_text.split("\n\n"):
            if para.strip():
                p = doc.add_paragraph(para.strip())
                p.style.font.name = "Andika"
                p.style.font.size = Pt(12)
        buf = io.BytesIO()
        doc.save(buf)
        key = f"exports/{book_id}/book.docx"
        self._storage.put(key, buf.getvalue())
        return key

    def export_markdown(self, book_id: uuid.UUID, story_text: str, metadata: dict) -> str:
        """Generate Markdown; return storage key."""
        title = metadata.get("title", "Untitled")
        author = metadata.get("author", "")
        lines = [f"# {title}", ""]
        if author:
            lines += [f"*by {author}*", ""]
        for para in story_text.split("\n\n"):
            if para.strip():
                lines.append(para.strip())
                lines.append("")
        content = "\n".join(lines)
        key = f"exports/{book_id}/book.md"
        self._storage.put(key, content.encode())
        return key

    def export_text(self, book_id: uuid.UUID, story_text: str, metadata: dict) -> str:
        """Generate plain text; return storage key."""
        title = metadata.get("title", "Untitled")
        content = f"{title}\n{'=' * len(title)}\n\n{story_text}"
        key = f"exports/{book_id}/book.txt"
        self._storage.put(key, content.encode())
        return key

    def export_images(self, book_id: uuid.UUID, images: list[bytes | None], cover: bytes | None) -> str:
        """Copy images into an organized folder; return folder prefix."""
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
        spreads: list[str] | None = None,
    ) -> dict:
        """Run all exports; return manifest dict of storage keys."""
        interior_key = self.compose_interior(
            book_id, story_text, interior_images, metadata, spreads=spreads
        )
        previews = self.render_previews(book_id, self._storage.get(interior_key))
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
            "previews": previews,
        }
