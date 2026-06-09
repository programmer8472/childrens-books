"""Unit 8 tests: compositor, MetadataAgent, Orchestrator post-approval pipeline, API.

All offline — fake repos (in-memory), FakeLLMProvider/FakeImageProvider, no DB, no Celery.
Real BookComposer tests use actual ReportLab + Pillow to verify PDF output structure.
FakeComposer tests verify interface and storage I/O without layout overhead.
"""
import io
import json
import tempfile
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.compositor.fake_compositor import FakeComposer
from app.compositor.spread_types import (
    NUM_STORY_SPREADS,
    SpreadType,
    assign_spread_types,
    spread_type_for_index,
)
from app.compositor.typography import (
    body_font_size,
    contrast_ratio,
    needs_contrast_pill,
    pick_text_color,
    wrap_text,
)
from app.compositor.color import to_cmyk
from app.db.enums import BookStatus, assert_legal_transition
from app.main import app
from app.providers.base import CharacterRef, ImageResult
from app.providers.fake_llm import FakeLLMProvider
from app.providers.fake_image import FakeImageProvider
from app.storage.local import LocalStorage
from app.db.session import get_session

# Re-use the in-memory fakes from test_unit4 (they live at module level, safe to import)
from tests.test_unit4 import (
    _FakeBook,
    _FakeBookRepo,
    _FakeJudgementRepo,
    _FakeImageRepo,
    _FakeStorage,
    _FakeStoryVersionRepo,
    BRIEF,
    _judge_json,
    _passing_responses,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _storage(tmpdir: str) -> LocalStorage:
    return LocalStorage(tmpdir)


def _fake_image_bytes(w: int = 100, h: int = 100) -> bytes:
    """Return minimal valid JPEG bytes."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (100, 150, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def _fake_story() -> str:
    return "\n\n".join(f"Paragraph {i} of the story." for i in range(1, 25))


def _fake_metadata() -> dict:
    return {
        "title": "The Brave Little Cloud",
        "subtitle": "",
        "author": "A. Author",
        "description": "A warm story about courage.",
        "keywords": ["picture book", "courage", "children", "ages 3-5", "brave", "cloud", "friendship"],
        "age_range": "3-5",
        "series_name": "",
    }


def _make_book_with_approved_version():
    """Return (book, book_repo, version_repo, judgement_repo, image_repo, storage) at APPROVED state."""
    book = _FakeBook(BRIEF, max_rounds=3)
    book_repo = _FakeBookRepo(book)
    version_repo = _FakeStoryVersionRepo()
    judgement_repo = _FakeJudgementRepo()
    image_repo = _FakeImageRepo()
    storage = _FakeStorage()

    # Simulate a book that has an approved version
    book.status = BookStatus.APPROVED
    version = version_repo.create(
        book_id=book.id, round=1, method="three-act",
        content=_fake_story(),
    )
    judgement_repo.create(
        book_id=book.id, story_version_id=version.id, round=1,
        judge_prompt_version="v1",
        emotional_authenticity=8.0, representation_quality=8.0,
        pacing=8.0, age_fit=8.0, uniqueness=8.0,
        weighted_total=8.0, passed=True,
        critique={"emotional_authenticity": "Good"},
    )
    book.current_round = 1
    book.book_metadata = None
    book.export_manifest = None

    def _save_metadata(b, meta):
        b.book_metadata = meta
        return b
    def _save_export_manifest(b, manifest):
        b.export_manifest = manifest
        return b
    def _transition(b, to_status, *, actor, note=None):
        assert_legal_transition(b.status, to_status)
        b.status = to_status
        return b

    book_repo.save_metadata = _save_metadata
    book_repo.save_export_manifest = _save_export_manifest
    book_repo.transition = _transition

    return book, book_repo, version_repo, judgement_repo, image_repo, storage


def _make_orchestrator(book_repo, version_repo, judgement_repo, image_repo, storage, llm=None, image=None):
    from app.orchestrator import Orchestrator
    return Orchestrator(
        book_repo=book_repo,
        version_repo=version_repo,
        judgement_repo=judgement_repo,
        image_repo=image_repo,
        llm=llm or FakeLLMProvider(),
        image=image or FakeImageProvider(),
        storage=storage,
    )


def _mock_session():
    session = MagicMock()
    session.commit.return_value = None
    session.close.return_value = None
    yield session


@pytest.fixture(autouse=True)
def _override_session():
    app.dependency_overrides[get_session] = _mock_session
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _fake_api_book(status: BookStatus = BookStatus.AWAITING_APPROVAL):
    from datetime import datetime, timezone
    return SimpleNamespace(
        id=uuid.uuid4(),
        title="Test Book",
        brief={"title": "Test", "age_range": "4-6"},
        status=status,
        max_rounds=5,
        current_round=1,
        score_threshold=7.5,
        book_metadata=None,
        export_manifest=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# spread_types.py
# ---------------------------------------------------------------------------


class TestSpreadTypes:
    def test_assign_returns_twelve(self):
        result = assign_spread_types()
        assert len(result) == NUM_STORY_SPREADS

    def test_all_valid_spread_types(self):
        valid = set(SpreadType)
        for st in assign_spread_types():
            assert st in valid

    def test_first_spread_is_full_bleed_double(self):
        assert assign_spread_types()[0] == SpreadType.FULL_BLEED_DOUBLE

    def test_climax_spreads_are_full_bleed_double(self):
        spreads = assign_spread_types()
        assert spreads[8] == SpreadType.FULL_BLEED_DOUBLE
        assert spreads[9] == SpreadType.FULL_BLEED_DOUBLE

    def test_resolution_spread(self):
        assert assign_spread_types()[10] == SpreadType.FULL_BLEED_SINGLE_WITH_TEXT_PAGE

    def test_spread_type_for_index_clamps(self):
        assert spread_type_for_index(99) == spread_type_for_index(11)

    def test_spread_type_for_index_zero(self):
        assert spread_type_for_index(0) == SpreadType.FULL_BLEED_DOUBLE


# ---------------------------------------------------------------------------
# typography.py
# ---------------------------------------------------------------------------


class TestTypography:
    def test_body_font_size_young(self):
        assert body_font_size("3-5") == 20

    def test_body_font_size_older(self):
        assert body_font_size("5-8") == 18

    def test_wrap_text_max_chars(self):
        long_line = "word " * 20
        lines = wrap_text(long_line.strip(), max_chars=40)
        for line in lines:
            assert len(line) <= 45  # allow slight overage for long single words

    def test_wrap_text_preserves_content(self):
        text = "First paragraph.\n\nSecond paragraph."
        lines = wrap_text(text)
        joined = " ".join(l for l in lines if l)
        assert "First paragraph" in joined
        assert "Second paragraph" in joined

    def test_contrast_ratio_black_on_white(self):
        assert contrast_ratio((0, 0, 0), (255, 255, 255)) > 20

    def test_contrast_ratio_passes_wcag_aa(self):
        assert contrast_ratio((26, 26, 26), (255, 255, 255)) >= 4.5

    def test_pick_text_color_dark_bg_returns_white(self):
        assert pick_text_color((20, 20, 20)) == (255, 255, 255)

    def test_pick_text_color_light_bg_returns_dark(self):
        assert pick_text_color((240, 240, 240)) == (26, 26, 26)

    def test_needs_contrast_pill_low_contrast(self):
        assert needs_contrast_pill((26, 26, 26), (30, 30, 30)) is True

    def test_needs_contrast_pill_high_contrast(self):
        assert needs_contrast_pill((255, 255, 255), (20, 20, 20)) is False


# ---------------------------------------------------------------------------
# color.py
# ---------------------------------------------------------------------------


class TestColor:
    def test_rgb_to_cmyk_mode(self):
        from PIL import Image
        img = Image.new("RGB", (10, 10), (255, 0, 0))
        assert to_cmyk(img).mode == "CMYK"

    def test_rgba_to_cmyk_flattens_alpha(self):
        from PIL import Image
        img = Image.new("RGBA", (10, 10), (0, 255, 0, 128))
        assert to_cmyk(img).mode == "CMYK"

    def test_cmyk_same_size(self):
        from PIL import Image
        img = Image.new("RGB", (50, 80), (100, 150, 200))
        assert to_cmyk(img).size == (50, 80)


# ---------------------------------------------------------------------------
# FakeComposer
# ---------------------------------------------------------------------------


class TestFakeComposer:
    def _composer(self, tmpdir: str) -> FakeComposer:
        return FakeComposer(_storage(tmpdir))

    def test_compose_all_returns_manifest_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._composer(tmp).compose_all(
                uuid.uuid4(), _fake_story(), [None] * 12, None, _fake_metadata()
            )
        assert {"interior_pdf", "cover_pdf", "word", "markdown", "text", "images_folder"}.issubset(manifest)

    def test_compose_interior_writes_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            book_id = uuid.uuid4()
            key = self._composer(tmp).compose_interior(book_id, _fake_story(), [None] * 12, _fake_metadata())
            assert _storage(tmp).exists(key)
            assert key.endswith(".pdf")

    def test_compose_cover_writes_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = self._composer(tmp).compose_cover(uuid.uuid4(), None, _fake_metadata())
            assert _storage(tmp).exists(key) and key.endswith(".pdf")

    def test_export_word_writes_docx(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = self._composer(tmp).export_word(uuid.uuid4(), _fake_story(), _fake_metadata())
            assert _storage(tmp).exists(key) and key.endswith(".docx")

    def test_export_markdown_contains_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            book_id = uuid.uuid4()
            key = self._composer(tmp).export_markdown(book_id, _fake_story(), _fake_metadata())
            assert b"The Brave Little Cloud" in _storage(tmp).get(key)

    def test_export_text_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = self._composer(tmp).export_text(uuid.uuid4(), _fake_story(), _fake_metadata())
            assert _storage(tmp).exists(key)

    def test_export_images_with_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            book_id = uuid.uuid4()
            imgs = [_fake_image_bytes() if i % 2 == 0 else None for i in range(12)]
            folder = self._composer(tmp).export_images(book_id, imgs, _fake_image_bytes())
            st = _storage(tmp)
            assert st.exists(f"{folder}/cover.jpg")
            assert st.exists(f"{folder}/spread_01.jpg")

    def test_calls_list_tracks_compose_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = self._composer(tmp)
            c.compose_all(uuid.uuid4(), "", [None] * 12, None, _fake_metadata())
        assert "compose_all" in c.calls
        assert "compose_interior" in c.calls


# ---------------------------------------------------------------------------
# Real BookComposer — structural output checks
# ---------------------------------------------------------------------------


class TestBookComposer:
    def test_interior_pdf_is_valid_pdf(self):
        from app.compositor.composer import BookComposer
        with tempfile.TemporaryDirectory() as tmp:
            key = BookComposer(_storage(tmp)).compose_interior(
                uuid.uuid4(), _fake_story(), [_fake_image_bytes()] * 12, _fake_metadata()
            )
            assert _storage(tmp).get(key)[:4] == b"%PDF"

    def test_cover_pdf_is_valid_pdf(self):
        from app.compositor.composer import BookComposer
        with tempfile.TemporaryDirectory() as tmp:
            key = BookComposer(_storage(tmp)).compose_cover(
                uuid.uuid4(), _fake_image_bytes(), _fake_metadata()
            )
            assert _storage(tmp).get(key)[:4] == b"%PDF"

    def test_word_docx_has_zip_magic(self):
        from app.compositor.composer import BookComposer
        with tempfile.TemporaryDirectory() as tmp:
            key = BookComposer(_storage(tmp)).export_word(
                uuid.uuid4(), _fake_story(), _fake_metadata()
            )
            assert _storage(tmp).get(key)[:2] == b"PK"

    def test_markdown_starts_with_title_heading(self):
        from app.compositor.composer import BookComposer
        with tempfile.TemporaryDirectory() as tmp:
            key = BookComposer(_storage(tmp)).export_markdown(
                uuid.uuid4(), _fake_story(), _fake_metadata()
            )
            assert _storage(tmp).get(key).decode().startswith("# The Brave Little Cloud")

    def test_text_export_contains_story(self):
        from app.compositor.composer import BookComposer
        with tempfile.TemporaryDirectory() as tmp:
            key = BookComposer(_storage(tmp)).export_text(
                uuid.uuid4(), "Once upon a time.", _fake_metadata()
            )
            assert "Once upon a time." in _storage(tmp).get(key).decode()

    def test_compose_all_returns_all_keys(self):
        from app.compositor.composer import BookComposer
        with tempfile.TemporaryDirectory() as tmp:
            manifest = BookComposer(_storage(tmp)).compose_all(
                uuid.uuid4(), _fake_story(),
                [_fake_image_bytes()] * 12, _fake_image_bytes(), _fake_metadata()
            )
        for key in ("interior_pdf", "cover_pdf", "word", "markdown", "text", "images_folder"):
            assert key in manifest

    def test_interior_pdf_handles_none_images(self):
        """Compositor must not crash when image slots are None."""
        from app.compositor.composer import BookComposer
        with tempfile.TemporaryDirectory() as tmp:
            key = BookComposer(_storage(tmp)).compose_interior(
                uuid.uuid4(), _fake_story(), [None] * 12, _fake_metadata()
            )
            assert _storage(tmp).get(key)[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# MetadataAgent
# ---------------------------------------------------------------------------


class TestMetadataAgent:
    def _agent_with_response(self, content: str):
        from app.agents.metadata import MetadataAgent
        llm = FakeLLMProvider()
        llm.push(content)
        return MetadataAgent(llm)

    def test_returns_dict_with_required_keys(self):
        from app.agents.metadata import MetadataAgent, _METADATA_SCHEMA
        agent = self._agent_with_response(json.dumps(_fake_metadata()))
        result = agent.draft("Story text", {"age_range": "3-5"})
        for key in _METADATA_SCHEMA["required"]:
            assert key in result

    def test_keywords_is_list(self):
        agent = self._agent_with_response(json.dumps(_fake_metadata()))
        result = agent.draft("Story", {})
        assert isinstance(result["keywords"], list)

    def test_retries_on_bad_json(self):
        """Two bad responses followed by one good → succeeds on third attempt."""
        from app.agents.metadata import MetadataAgent
        llm = FakeLLMProvider()
        llm.push("not json")
        llm.push("{bad}")
        llm.push(json.dumps(_fake_metadata()))
        result = MetadataAgent(llm).draft("Story", {})
        assert result["title"] == "The Brave Little Cloud"

    def test_raises_after_three_failures(self):
        from app.agents.metadata import MetadataAgent
        llm = FakeLLMProvider()
        for _ in range(3):
            llm.push("not json")
        with pytest.raises(RuntimeError, match="3 attempts"):
            MetadataAgent(llm).draft("Story", {})


# ---------------------------------------------------------------------------
# Orchestrator post-approval pipeline (all in-memory fakes)
# ---------------------------------------------------------------------------


class TestOrchestratorPostApproval:
    def _env(self, llm=None, image=None):
        book, book_repo, version_repo, judgement_repo, image_repo, storage = \
            _make_book_with_approved_version()
        orch = _make_orchestrator(
            book_repo, version_repo, judgement_repo, image_repo, storage,
            llm=llm, image=image,
        )
        return orch, book, book_repo, version_repo, judgement_repo, image_repo, storage

    def test_generate_images_transitions_to_generating_cover(self):
        orch, book, *_ = self._env()
        orch.generate_images(book.id)
        assert book.status == BookStatus.GENERATING_COVER

    def test_generate_images_creates_twelve_scene_records(self):
        orch, book, _, _, _, image_repo, _ = self._env()
        orch.generate_images(book.id)
        scenes = image_repo.list_for_book(book.id, kind="scene")
        assert len(scenes) == 12

    def test_generate_images_calls_event_callback(self):
        orch, book, *_ = self._env()
        events = []
        orch.generate_images(book.id, event_cb=lambda c, t: events.append((c, t)))
        assert len(events) == 12
        assert events[-1] == (12, 12)

    def test_generate_cover_transitions_to_drafting_metadata(self):
        orch, book, *_ = self._env()
        orch.generate_images(book.id)
        orch.generate_cover(book.id)
        assert book.status == BookStatus.DRAFTING_METADATA

    def test_generate_cover_creates_cover_image_record(self):
        orch, book, _, _, _, image_repo, _ = self._env()
        orch.generate_images(book.id)
        orch.generate_cover(book.id)
        covers = image_repo.list_for_book(book.id, kind="cover")
        assert len(covers) == 1

    def test_draft_metadata_saves_to_book(self):
        llm = FakeLLMProvider()
        llm.push(json.dumps(_fake_metadata()))
        orch, book, *_ = self._env(llm=llm)
        orch.generate_images(book.id)
        orch.generate_cover(book.id)
        orch.draft_metadata(book.id)
        assert book.book_metadata is not None
        assert book.book_metadata["title"] == "The Brave Little Cloud"

    def test_draft_metadata_transitions_to_exporting(self):
        llm = FakeLLMProvider()
        llm.push(json.dumps(_fake_metadata()))
        orch, book, *_ = self._env(llm=llm)
        orch.generate_images(book.id)
        orch.generate_cover(book.id)
        orch.draft_metadata(book.id)
        assert book.status == BookStatus.EXPORTING

    def test_export_book_transitions_to_export_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            book, book_repo, version_repo, judgement_repo, image_repo, _ = \
                _make_book_with_approved_version()
            storage_real = LocalStorage(tmp)
            orch = _make_orchestrator(
                book_repo, version_repo, judgement_repo, image_repo, storage_real
            )
            llm = FakeLLMProvider()
            llm.push(json.dumps(_fake_metadata()))
            orch._llm = llm
            orch.generate_images(book.id)
            orch.generate_cover(book.id)
            orch.draft_metadata(book.id)
            orch.export_book(book.id)
        assert book.status == BookStatus.EXPORT_READY
        assert book.export_manifest is not None
        assert "interior_pdf" in book.export_manifest

    def test_export_manifest_files_written_to_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            book, book_repo, version_repo, judgement_repo, image_repo, _ = \
                _make_book_with_approved_version()
            storage_real = LocalStorage(tmp)
            orch = _make_orchestrator(
                book_repo, version_repo, judgement_repo, image_repo, storage_real
            )
            llm = FakeLLMProvider()
            llm.push(json.dumps(_fake_metadata()))
            orch._llm = llm
            orch.generate_images(book.id)
            orch.generate_cover(book.id)
            orch.draft_metadata(book.id)
            orch.export_book(book.id)
            for key in ("interior_pdf", "cover_pdf", "word", "markdown", "text"):
                assert storage_real.exists(book.export_manifest[key]), f"Missing: {key}"


# ---------------------------------------------------------------------------
# API: approve now triggers pipeline_generate_images
# ---------------------------------------------------------------------------


class TestApproveWiresGenImages:
    def test_approve_enqueues_generate_images(self, client):
        book = _fake_api_book(BookStatus.AWAITING_APPROVAL)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_generate_images") as mock_task,
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            client.post(f"/books/{book.id}/approve")
        mock_task.delay.assert_called_once_with(str(book.id))

    def test_approve_returns_approved_status(self, client):
        book = _fake_api_book(BookStatus.AWAITING_APPROVAL)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_generate_images"),
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            resp = client.post(f"/books/{book.id}/approve")
        assert resp.json()["status"] == "APPROVED"


# ---------------------------------------------------------------------------
# API: metadata endpoints
# ---------------------------------------------------------------------------


class TestMetadataAPI:
    def test_get_metadata_returns_empty_dict_when_none(self, client):
        book = _fake_api_book()
        book.book_metadata = None
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            resp = client.get(f"/books/{book.id}/metadata")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_get_metadata_returns_stored_value(self, client):
        book = _fake_api_book()
        book.book_metadata = {"title": "My Book", "author": "Author"}
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            resp = client.get(f"/books/{book.id}/metadata")
        assert resp.json()["title"] == "My Book"

    def test_put_metadata_calls_save(self, client):
        book = _fake_api_book()
        book.book_metadata = {}
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            resp = client.put(
                f"/books/{book.id}/metadata",
                json={"title": "Updated Title"},
            )
        assert resp.status_code == 200
        MockRepo.return_value.save_metadata.assert_called_once()

    def test_put_metadata_merges_with_existing(self, client):
        book = _fake_api_book()
        book.book_metadata = {"title": "Original", "author": "A"}
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            resp = client.put(
                f"/books/{book.id}/metadata",
                json={"author": "B"},
            )
        saved = MockRepo.return_value.save_metadata.call_args[0][1]
        assert saved["title"] == "Original"
        assert saved["author"] == "B"

    def test_get_metadata_404_for_missing_book(self, client):
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.side_effect = ValueError("Not found")
            resp = client.get(f"/books/{uuid.uuid4()}/metadata")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API: export endpoints
# ---------------------------------------------------------------------------


class TestExportAPI:
    def test_export_returns_400_when_not_export_ready(self, client):
        book = _fake_api_book(BookStatus.EXPORTING)
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            resp = client.get(f"/books/{book.id}/export")
        assert resp.status_code == 400

    def test_export_returns_manifest_when_ready(self, client):
        book = _fake_api_book(BookStatus.EXPORT_READY)
        book.export_manifest = {"interior_pdf": "exports/x/interior.pdf", "cover_pdf": "exports/x/cover.pdf"}
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            resp = client.get(f"/books/{book.id}/export")
        assert resp.status_code == 200
        assert "interior_pdf" in resp.json()

    def test_download_artifact_returns_pdf_bytes(self, client):
        book = _fake_api_book(BookStatus.EXPORT_READY)
        book.export_manifest = {"interior_pdf": "exports/x/interior.pdf"}
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.LocalStorage") as MockStorage,
            patch("app.api.books.get_settings"),
        ):
            MockRepo.return_value.get.return_value = book
            MockStorage.return_value.get.return_value = b"%PDF-1.4 fake"
            resp = client.get(f"/books/{book.id}/export/interior_pdf")
        assert resp.status_code == 200
        assert resp.content == b"%PDF-1.4 fake"
        assert resp.headers["content-type"] == "application/pdf"

    def test_download_unknown_artifact_returns_404(self, client):
        book = _fake_api_book(BookStatus.EXPORT_READY)
        book.export_manifest = {"interior_pdf": "exports/x/interior.pdf"}
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            resp = client.get(f"/books/{book.id}/export/nonexistent")
        assert resp.status_code == 404
