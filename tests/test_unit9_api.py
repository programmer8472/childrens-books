"""Unit 9 tests: paragraph rewrite endpoint + CORS.

All offline — repos and LLM provider are patched; no DB needed.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db.enums import BookStatus
from app.db.session import get_session
from app.main import app
from app.providers.base import LLMResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_book(status: BookStatus = BookStatus.AWAITING_APPROVAL) -> SimpleNamespace:
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


# ---------------------------------------------------------------------------
# Paragraph rewrite
# ---------------------------------------------------------------------------


def test_rewrite_paragraph_returns_original_and_rewritten(client):
    book = _fake_book()
    rewritten_text = "The sun dipped behind the mountains as Mia waved goodbye."

    with (
        patch("app.api.books.BookRepo") as MockRepo,
        patch("app.providers.factory.get_llm_provider") as mock_get_provider,
    ):
        MockRepo.return_value.get.return_value = book
        mock_provider = MagicMock()
        mock_provider.generate.return_value = LLMResponse(
            content=f"  {rewritten_text}  ",  # extra whitespace — should be stripped
            model="fake",
            input_tokens=10,
            output_tokens=20,
        )
        mock_get_provider.return_value = mock_provider

        resp = client.post(
            f"/books/{book.id}/paragraphs/rewrite",
            json={
                "paragraph_text": "The sun went down. Mia said bye.",
                "instruction": "Make it more lyrical.",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["original"] == "The sun went down. Mia said bye."
    assert data["rewritten"] == rewritten_text
    mock_provider.generate.assert_called_once()
    call_args = mock_provider.generate.call_args
    assert "Make it more lyrical." in call_args[0][1][0]["content"]


def test_rewrite_paragraph_404_for_missing_book(client):
    with patch("app.api.books.BookRepo") as MockRepo:
        MockRepo.return_value.get.side_effect = ValueError("not found")
        resp = client.post(
            f"/books/{uuid.uuid4()}/paragraphs/rewrite",
            json={"paragraph_text": "Hello.", "instruction": "Add more detail."},
        )

    assert resp.status_code == 404


def test_rewrite_paragraph_passes_system_and_instruction_to_llm(client):
    book = _fake_book()

    with (
        patch("app.api.books.BookRepo") as MockRepo,
        patch("app.providers.factory.get_llm_provider") as mock_get_provider,
    ):
        MockRepo.return_value.get.return_value = book
        mock_provider = MagicMock()
        mock_provider.generate.return_value = LLMResponse(
            content="Rewritten paragraph.", model="fake", input_tokens=5, output_tokens=5
        )
        mock_get_provider.return_value = mock_provider

        client.post(
            f"/books/{book.id}/paragraphs/rewrite",
            json={"paragraph_text": "She ran fast.", "instruction": "Use simpler words."},
        )

    system_arg, messages_arg = mock_provider.generate.call_args[0]
    assert "children's book editor" in system_arg.lower()
    assert "She ran fast." in messages_arg[0]["content"]
    assert "Use simpler words." in messages_arg[0]["content"]


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


def test_cors_allows_localhost_3000(client):
    resp = client.options(
        "/books",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
