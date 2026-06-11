"""Unit 5 tests: FastAPI endpoints + WebSocket progress.

All offline — repos and Celery tasks are patched; no DB, Redis, or worker needed.

Strategy:
  - Override the FastAPI `get_session` dependency with a MagicMock session so
    the HTTP layer runs without a real DB.
  - Patch `BookRepo` and task `.delay()` calls per-test to control exact behavior.
  - The orchestrator approve/reject logic is a thin orchestration of
    `BookRepo.transition`, so we verify the transition call arguments directly.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi.testclient import TestClient

from app.db.enums import BookStatus, LEGAL_TRANSITIONS, assert_legal_transition
from app.db.session import get_session
from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_book(status: BookStatus = BookStatus.DRAFT_BRIEF) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        title="Test Book",
        brief={"title": "Test", "age_range": "4-6"},
        status=status,
        max_rounds=5,
        current_round=1,
        score_threshold=7.5,
        approved_version_id=None,
        cancel_requested=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _fake_version(book_id: uuid.UUID, round_: int = 1, method: str = "three-act") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        book_id=book_id,
        round=round_,
        method=method,
        content="Once upon a time...",
        shortlisted=False,
        judgements=[],
        created_at=datetime.now(timezone.utc),
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
# Enum: all new statuses present with correct transitions
# ---------------------------------------------------------------------------


class TestEnumUpdate:
    def test_awaiting_shortlist_exists(self):
        assert BookStatus.AWAITING_SHORTLIST in BookStatus

    def test_shortlist_judging_exists(self):
        assert BookStatus.SHORTLIST_JUDGING in BookStatus

    def test_awaiting_final_approval_exists(self):
        assert BookStatus.AWAITING_FINAL_APPROVAL in BookStatus

    def test_judging_can_go_to_awaiting_shortlist(self):
        assert BookStatus.AWAITING_SHORTLIST in LEGAL_TRANSITIONS[BookStatus.JUDGING]

    def test_judging_can_still_go_to_revision(self):
        assert BookStatus.REVISION in LEGAL_TRANSITIONS[BookStatus.JUDGING]

    def test_judging_no_longer_goes_directly_to_awaiting_approval(self):
        assert BookStatus.AWAITING_APPROVAL not in LEGAL_TRANSITIONS[BookStatus.JUDGING]

    def test_awaiting_shortlist_to_shortlist_judging(self):
        assert_legal_transition(BookStatus.AWAITING_SHORTLIST, BookStatus.SHORTLIST_JUDGING)

    def test_shortlist_judging_to_awaiting_final_approval(self):
        assert_legal_transition(BookStatus.SHORTLIST_JUDGING, BookStatus.AWAITING_FINAL_APPROVAL)

    def test_awaiting_final_approval_to_approved(self):
        assert_legal_transition(BookStatus.AWAITING_FINAL_APPROVAL, BookStatus.APPROVED)

    def test_awaiting_approval_still_has_legal_targets_for_compat(self):
        targets = LEGAL_TRANSITIONS[BookStatus.AWAITING_APPROVAL]
        assert BookStatus.APPROVED in targets
        assert BookStatus.REVISION in targets

    def test_all_statuses_covered(self):
        assert set(LEGAL_TRANSITIONS) == set(BookStatus)

    def test_cancelled_status_exists(self):
        assert BookStatus.CANCELLED in BookStatus

    def test_running_stage_can_be_cancelled(self):
        assert BookStatus.CANCELLED in LEGAL_TRANSITIONS[BookStatus.WRITING]
        assert BookStatus.CANCELLED in LEGAL_TRANSITIONS[BookStatus.GENERATING_IMAGES]

    def test_gate_can_be_cancelled(self):
        assert BookStatus.CANCELLED in LEGAL_TRANSITIONS[BookStatus.AWAITING_FINAL_APPROVAL]

    def test_cancelled_is_terminal(self):
        assert LEGAL_TRANSITIONS[BookStatus.CANCELLED] == frozenset()

    def test_finished_book_cannot_be_cancelled(self):
        assert BookStatus.CANCELLED not in LEGAL_TRANSITIONS[BookStatus.EXPORT_READY]
        assert BookStatus.CANCELLED not in LEGAL_TRANSITIONS[BookStatus.DONE]


# ---------------------------------------------------------------------------
# POST /books/{id}/cancel
# ---------------------------------------------------------------------------


class TestCancelBook:
    def test_running_stage_flags_and_does_not_transition(self, client):
        book = _fake_book(BookStatus.WRITING)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            resp = client.post(f"/books/{book.id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["cancelling"] is True
        MockRepo.return_value.request_cancel.assert_called_once_with(book)
        MockRepo.return_value.cancel.assert_not_called()

    def test_gate_cancels_immediately(self, client):
        book = _fake_book(BookStatus.AWAITING_FINAL_APPROVAL)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            resp = client.post(f"/books/{book.id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "CANCELLED"
        MockRepo.return_value.cancel.assert_called_once()

    def test_terminal_book_rejected(self, client):
        book = _fake_book(BookStatus.DONE)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            resp = client.post(f"/books/{book.id}/cancel")
        assert resp.status_code == 400

    def test_missing_book_404(self, client):
        bid = uuid.uuid4()
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.side_effect = ValueError("nope")
            resp = client.post(f"/books/{bid}/cancel")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /books/{id}
# ---------------------------------------------------------------------------


class TestDeleteBook:
    def test_deletes_and_returns_204(self, client):
        book = _fake_book(BookStatus.RETIRED)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.LocalStorage") as MockStorage,
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            MockRepo.return_value.delete.return_value = []
            resp = client.delete(f"/books/{book.id}")
        assert resp.status_code == 204
        MockRepo.return_value.delete.assert_called_once_with(book)

    def test_purges_returned_storage_keys(self, client):
        book = _fake_book(BookStatus.CANCELLED)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.LocalStorage") as MockStorage,
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            MockRepo.return_value.delete.return_value = ["img/a.png", "export/b.pdf"]
            resp = client.delete(f"/books/{book.id}")
        assert resp.status_code == 204
        storage = MockStorage.return_value
        assert storage.delete.call_count == 2
        storage.delete.assert_any_call("img/a.png")
        storage.delete.assert_any_call("export/b.pdf")

    def test_allows_delete_from_running_state(self, client):
        book = _fake_book(BookStatus.WRITING)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.LocalStorage"),
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            MockRepo.return_value.delete.return_value = []
            resp = client.delete(f"/books/{book.id}")
        assert resp.status_code == 204

    def test_missing_book_404(self, client):
        bid = uuid.uuid4()
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.side_effect = ValueError("nope")
            resp = client.delete(f"/books/{bid}")
        assert resp.status_code == 404
        MockRepo.return_value.delete.assert_not_called()


# ---------------------------------------------------------------------------
# POST /books
# ---------------------------------------------------------------------------


class TestCreateBook:
    def test_returns_201(self, client):
        book = _fake_book()
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_start") as mock_task,
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.create.return_value = book
            resp = client.post("/books", json={"brief": {"title": "Brave Snail", "age_range": "4-6"}})
        assert resp.status_code == 201

    def test_response_contains_book_id(self, client):
        book = _fake_book()
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_start"),
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.create.return_value = book
            resp = client.post("/books", json={"brief": {"title": "x"}})
        assert resp.json()["id"] == str(book.id)

    def test_pipeline_start_enqueued(self, client):
        book = _fake_book()
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_start") as mock_task,
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.create.return_value = book
            client.post("/books", json={"brief": {"title": "x"}})
        mock_task.delay.assert_called_once_with(str(book.id))

    def test_book_created_with_brief(self, client):
        book = _fake_book()
        brief = {"title": "The Brave Snail", "age_range": "4-6", "theme": "courage"}
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_start"),
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.create.return_value = book
            client.post("/books", json={"brief": brief, "max_rounds": 3, "score_threshold": 8.0})
        MockRepo.return_value.create.assert_called_once_with(
            brief, title=None, max_rounds=3, score_threshold=8.0
        )

    def test_status_is_string_in_response(self, client):
        book = _fake_book()
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_start"),
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.create.return_value = book
            resp = client.post("/books", json={"brief": {}})
        assert isinstance(resp.json()["status"], str)


# ---------------------------------------------------------------------------
# GET /books
# ---------------------------------------------------------------------------


class TestListBooks:
    def test_returns_200(self, client):
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.list_all.return_value = []
            resp = client.get("/books")
        assert resp.status_code == 200

    def test_returns_list(self, client):
        books = [_fake_book(), _fake_book()]
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.list_all.return_value = books
            resp = client.get("/books")
        assert len(resp.json()) == 2

    def test_empty_list(self, client):
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.list_all.return_value = []
            resp = client.get("/books")
        assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /books/{id}
# ---------------------------------------------------------------------------


class TestGetBook:
    def test_returns_200(self, client):
        book = _fake_book()
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            resp = client.get(f"/books/{book.id}")
        assert resp.status_code == 200

    def test_returns_book_data(self, client):
        book = _fake_book(BookStatus.WRITING)
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            resp = client.get(f"/books/{book.id}")
        data = resp.json()
        assert data["id"] == str(book.id)
        assert data["status"] == "WRITING"

    def test_returns_404_for_unknown_book(self, client):
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.side_effect = ValueError("not found")
            resp = client.get(f"/books/{uuid.uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /books/{id}/versions
# ---------------------------------------------------------------------------


class TestGetVersions:
    def test_returns_200(self, client):
        book = _fake_book()
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            _mock_session_inst = app.dependency_overrides[get_session]()
            resp = client.get(f"/books/{book.id}/versions")
        assert resp.status_code == 200

    def test_returns_404_for_unknown_book(self, client):
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.side_effect = ValueError("not found")
            resp = client.get(f"/books/{uuid.uuid4()}/versions")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /books/{id}/shortlist
# ---------------------------------------------------------------------------


class TestShortlistBook:
    def test_shortlist_from_awaiting_shortlist_returns_200(self, client):
        book = _fake_book(BookStatus.AWAITING_SHORTLIST)
        version_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_rejudge_shortlist") as mock_task,
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            resp = client.post(
                f"/books/{book.id}/shortlist",
                json={"story_version_ids": version_ids},
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "status": "SHORTLIST_JUDGING"}

    def test_shortlist_enqueues_rejudge_task(self, client):
        book = _fake_book(BookStatus.AWAITING_SHORTLIST)
        version_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_rejudge_shortlist") as mock_task,
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            client.post(
                f"/books/{book.id}/shortlist",
                json={"story_version_ids": version_ids},
            )
        mock_task.delay.assert_called_once_with(str(book.id), version_ids)

    def test_shortlist_from_wrong_state_returns_400(self, client):
        book = _fake_book(BookStatus.WRITING)
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            resp = client.post(
                f"/books/{book.id}/shortlist",
                json={"story_version_ids": [str(uuid.uuid4())]},
            )
        assert resp.status_code == 400

    def test_shortlist_empty_list_returns_400(self, client):
        book = _fake_book(BookStatus.AWAITING_SHORTLIST)
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            resp = client.post(
                f"/books/{book.id}/shortlist",
                json={"story_version_ids": []},
            )
        assert resp.status_code == 400

    def test_shortlist_unknown_book_returns_404(self, client):
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.side_effect = ValueError("not found")
            resp = client.post(
                f"/books/{uuid.uuid4()}/shortlist",
                json={"story_version_ids": [str(uuid.uuid4())]},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /books/{id}/approve — new AWAITING_FINAL_APPROVAL flow
# ---------------------------------------------------------------------------


class TestApproveBookNewFlow:
    def test_approve_from_awaiting_final_approval_returns_200(self, client):
        book = _fake_book(BookStatus.AWAITING_FINAL_APPROVAL)
        version_id = str(uuid.uuid4())
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_generate_images"),
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            resp = client.post(
                f"/books/{book.id}/approve",
                json={"story_version_id": version_id},
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "status": "APPROVED"}

    def test_approve_new_flow_sets_approved_version(self, client):
        book = _fake_book(BookStatus.AWAITING_FINAL_APPROVAL)
        version_id = str(uuid.uuid4())
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_generate_images"),
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            client.post(
                f"/books/{book.id}/approve",
                json={"story_version_id": version_id},
            )
        MockRepo.return_value.set_approved_version.assert_called_once_with(
            book, uuid.UUID(version_id)
        )

    def test_approve_new_flow_calls_transition(self, client):
        book = _fake_book(BookStatus.AWAITING_FINAL_APPROVAL)
        version_id = str(uuid.uuid4())
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_generate_images"),
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            client.post(
                f"/books/{book.id}/approve",
                json={"story_version_id": version_id},
            )
        MockRepo.return_value.transition.assert_called_once_with(
            book, BookStatus.APPROVED, actor="human"
        )

    def test_approve_new_flow_requires_story_version_id(self, client):
        book = _fake_book(BookStatus.AWAITING_FINAL_APPROVAL)
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            resp = client.post(f"/books/{book.id}/approve", json={})
        assert resp.status_code == 400

    def test_approve_from_wrong_state_returns_400(self, client):
        book = _fake_book(BookStatus.WRITING)
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            resp = client.post(
                f"/books/{book.id}/approve",
                json={"story_version_id": str(uuid.uuid4())},
            )
        assert resp.status_code == 400

    def test_approve_enqueues_generate_images(self, client):
        book = _fake_book(BookStatus.AWAITING_FINAL_APPROVAL)
        version_id = str(uuid.uuid4())
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_generate_images") as mock_task,
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            client.post(
                f"/books/{book.id}/approve",
                json={"story_version_id": version_id},
            )
        mock_task.delay.assert_called_once_with(str(book.id))


# ---------------------------------------------------------------------------
# POST /books/{id}/approve — legacy AWAITING_APPROVAL backward compat
# ---------------------------------------------------------------------------


class TestApproveBookLegacy:
    def test_approve_from_awaiting_returns_200(self, client):
        book = _fake_book(BookStatus.AWAITING_APPROVAL)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_generate_images"),
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            resp = client.post(f"/books/{book.id}/approve")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "status": "APPROVED"}

    def test_approve_legacy_calls_transition(self, client):
        book = _fake_book(BookStatus.AWAITING_APPROVAL)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_generate_images"),
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            client.post(f"/books/{book.id}/approve")
        MockRepo.return_value.transition.assert_called_once_with(
            book, BookStatus.APPROVED, actor="human"
        )

    def test_approve_legacy_does_not_set_approved_version(self, client):
        book = _fake_book(BookStatus.AWAITING_APPROVAL)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_generate_images"),
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            client.post(f"/books/{book.id}/approve")
        MockRepo.return_value.set_approved_version.assert_not_called()

    def test_approve_unknown_book_returns_404(self, client):
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.side_effect = ValueError("not found")
            resp = client.post(f"/books/{uuid.uuid4()}/approve")
        assert resp.status_code == 404

    def test_approve_publishes_event(self, client):
        book = _fake_book(BookStatus.AWAITING_APPROVAL)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_generate_images"),
            patch("app.api.books.publish_event") as mock_pub,
        ):
            MockRepo.return_value.get.return_value = book
            client.post(f"/books/{book.id}/approve")
        mock_pub.assert_called_once()
        event = mock_pub.call_args[0][1]
        assert event["status"] == "APPROVED"
        assert event["actor"] == "human"


# ---------------------------------------------------------------------------
# POST /books/{id}/reject
# ---------------------------------------------------------------------------


class TestRejectBook:
    def test_reject_from_awaiting_returns_200(self, client):
        book = _fake_book(BookStatus.AWAITING_APPROVAL)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_handle_revision"),
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            resp = client.post(f"/books/{book.id}/reject")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "status": "REVISION"}

    def test_reject_calls_transition_to_revision(self, client):
        book = _fake_book(BookStatus.AWAITING_APPROVAL)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_handle_revision"),
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            client.post(f"/books/{book.id}/reject")
        MockRepo.return_value.transition.assert_called_once_with(
            book, BookStatus.REVISION, actor="human", note=None
        )

    def test_reject_enqueues_handle_revision(self, client):
        book = _fake_book(BookStatus.AWAITING_APPROVAL)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_handle_revision") as mock_task,
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            client.post(f"/books/{book.id}/reject")
        mock_task.delay.assert_called_once_with(str(book.id))

    def test_reject_with_note(self, client):
        book = _fake_book(BookStatus.AWAITING_APPROVAL)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_handle_revision"),
            patch("app.api.books.publish_event"),
        ):
            MockRepo.return_value.get.return_value = book
            client.post(f"/books/{book.id}/reject", json={"note": "needs more humor"})
        MockRepo.return_value.transition.assert_called_once_with(
            book, BookStatus.REVISION, actor="human", note="needs more humor"
        )

    def test_reject_from_wrong_state_returns_400(self, client):
        book = _fake_book(BookStatus.APPROVED)
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.return_value = book
            resp = client.post(f"/books/{book.id}/reject")
        assert resp.status_code == 400

    def test_reject_unknown_book_returns_404(self, client):
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.side_effect = ValueError("not found")
            resp = client.post(f"/books/{uuid.uuid4()}/reject")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /books/{id}/retry
# ---------------------------------------------------------------------------


class TestRetryBook:
    def test_retry_from_judging_enqueues_run_judging(self, client):
        book = _fake_book(BookStatus.JUDGING)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_run_judging") as mock_task,
        ):
            MockRepo.return_value.get.return_value = book
            resp = client.post(f"/books/{book.id}/retry")
        assert resp.status_code == 200
        assert resp.json()["task"] == "pipeline_run_judging"
        mock_task.delay.assert_called_once_with(str(book.id))

    def test_retry_from_revision_enqueues_handle_revision(self, client):
        book = _fake_book(BookStatus.REVISION)
        with (
            patch("app.api.books.BookRepo") as MockRepo,
            patch("app.api.books.pipeline_handle_revision") as mock_task,
        ):
            MockRepo.return_value.get.return_value = book
            resp = client.post(f"/books/{book.id}/retry")
        assert resp.status_code == 200
        assert resp.json()["task"] == "pipeline_handle_revision"
        mock_task.delay.assert_called_once_with(str(book.id))

    def test_retry_from_non_retryable_state_returns_400(self, client):
        for status in (BookStatus.APPROVED, BookStatus.AWAITING_APPROVAL, BookStatus.RETIRED):
            book = _fake_book(status)
            with patch("app.api.books.BookRepo") as MockRepo:
                MockRepo.return_value.get.return_value = book
                resp = client.post(f"/books/{book.id}/retry")
            assert resp.status_code == 400, f"Expected 400 for status {status}"

    def test_retry_unknown_book_returns_404(self, client):
        with patch("app.api.books.BookRepo") as MockRepo:
            MockRepo.return_value.get.side_effect = ValueError("not found")
            resp = client.post(f"/books/{uuid.uuid4()}/retry")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Health endpoints still work
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    def test_health_still_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
