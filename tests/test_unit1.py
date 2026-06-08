"""Unit 1 tests: status enum, transition table, and model imports.

These tests run offline — no DB connection required.
Integration tests (repo layer against a real DB) live in the docker-compose
test environment and are verified via `make test` with a running stack.
"""
import pytest

from app.db.enums import BookStatus, LEGAL_TRANSITIONS, assert_legal_transition
from app.db.models import AuditLog, Book, CharacterAsset, Image, Judgement, StoryVersion
from app.db.repos import (
    AuditLogRepo,
    BookRepo,
    CharacterAssetRepo,
    ImageRepo,
    JudgementRepo,
    StoryVersionRepo,
)


class TestBookStatus:
    def test_all_statuses_in_transition_table(self):
        assert set(LEGAL_TRANSITIONS) == set(BookStatus)

    def test_transition_table_values_are_valid_statuses(self):
        for targets in LEGAL_TRANSITIONS.values():
            for t in targets:
                assert isinstance(t, BookStatus)

    def test_terminal_states_have_no_targets(self):
        assert LEGAL_TRANSITIONS[BookStatus.DONE] == frozenset()
        assert LEGAL_TRANSITIONS[BookStatus.RETIRED] == frozenset()

    def test_legal_transition_passes(self):
        assert_legal_transition(BookStatus.DRAFT_BRIEF, BookStatus.OUTLINING)

    def test_illegal_transition_raises(self):
        with pytest.raises(ValueError, match="Illegal transition"):
            assert_legal_transition(BookStatus.DONE, BookStatus.WRITING)

    def test_illegal_skip_raises(self):
        with pytest.raises(ValueError):
            assert_legal_transition(BookStatus.DRAFT_BRIEF, BookStatus.WRITING)

    def test_judging_can_go_to_revision_approval_or_retired(self):
        targets = LEGAL_TRANSITIONS[BookStatus.JUDGING]
        assert BookStatus.REVISION in targets
        assert BookStatus.AWAITING_APPROVAL in targets
        assert BookStatus.RETIRED in targets

    def test_awaiting_approval_can_be_retired_by_human(self):
        assert BookStatus.RETIRED in LEGAL_TRANSITIONS[BookStatus.AWAITING_APPROVAL]

    def test_full_happy_path_is_legal(self):
        path = [
            BookStatus.DRAFT_BRIEF,
            BookStatus.OUTLINING,
            BookStatus.WRITING,
            BookStatus.JUDGING,
            BookStatus.AWAITING_APPROVAL,
            BookStatus.APPROVED,
            BookStatus.GENERATING_IMAGES,
            BookStatus.GENERATING_COVER,
            BookStatus.DRAFTING_METADATA,
            BookStatus.EXPORTING,
            BookStatus.EXPORT_READY,
            BookStatus.DONE,
        ]
        for from_s, to_s in zip(path, path[1:]):
            assert_legal_transition(from_s, to_s)

    def test_revision_loop_is_legal(self):
        assert_legal_transition(BookStatus.JUDGING, BookStatus.REVISION)
        assert_legal_transition(BookStatus.REVISION, BookStatus.WRITING)


class TestModelImports:
    """Smoke-test that all models can be imported and instantiated without a DB."""

    def test_book_model_fields(self):
        cols = {c.name for c in Book.__table__.columns}
        assert {"id", "title", "brief", "status", "max_rounds", "current_round", "score_threshold"} <= cols

    def test_story_version_model_fields(self):
        cols = {c.name for c in StoryVersion.__table__.columns}
        assert {"id", "book_id", "round", "method", "content", "prior_critique"} <= cols

    def test_judgement_model_fields(self):
        cols = {c.name for c in Judgement.__table__.columns}
        assert {"emotional_authenticity", "representation_quality", "pacing", "age_fit", "uniqueness", "weighted_total", "passed", "critique"} <= cols

    def test_image_model_fields(self):
        cols = {c.name for c in Image.__table__.columns}
        assert {"kind", "scene_index", "prompt", "provider", "provider_params", "seed", "storage_key"} <= cols

    def test_character_asset_model_fields(self):
        cols = {c.name for c in CharacterAsset.__table__.columns}
        assert {"book_id", "kind", "data"} <= cols

    def test_audit_log_model_fields(self):
        cols = {c.name for c in AuditLog.__table__.columns}
        assert {"book_id", "from_status", "to_status", "actor", "note"} <= cols


class TestRepoImports:
    def test_all_repos_importable(self):
        assert BookRepo
        assert StoryVersionRepo
        assert JudgementRepo
        assert ImageRepo
        assert CharacterAssetRepo
        assert AuditLogRepo
