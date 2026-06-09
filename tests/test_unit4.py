"""Unit 4 tests: Orchestrator + full writer/judge loop, end-to-end on fakes.

All offline — fake repos (in-memory), FakeLLMProvider, no DB, no Celery.
"""
import json
import uuid
from types import SimpleNamespace

import pytest

from app.db.enums import BookStatus, assert_legal_transition
from app.orchestrator import Orchestrator
from app.providers import FakeImageProvider, FakeLLMProvider

# ---------------------------------------------------------------------------
# In-memory fake repos
# ---------------------------------------------------------------------------

class _FakeBook:
    def __init__(self, brief, *, max_rounds=3, score_threshold=7.5):
        self.id = uuid.uuid4()
        self.brief = brief
        self.status = BookStatus.DRAFT_BRIEF
        self.max_rounds = max_rounds
        self.current_round = 0
        self.score_threshold = score_threshold


class _FakeBookRepo:
    def __init__(self, book: _FakeBook) -> None:
        self._book = book
        self.transitions: list[tuple[BookStatus, BookStatus]] = []

    def get(self, book_id):
        return self._book

    def transition(self, book, to_status, *, actor, note=None):
        assert_legal_transition(book.status, to_status)
        self.transitions.append((book.status, to_status))
        book.status = to_status
        return book

    def increment_round(self, book):
        book.current_round += 1
        return book


class _FakeStoryVersionRepo:
    def __init__(self) -> None:
        self._store: list = []

    def create(self, book_id, round, method, content, *, prior_critique=None):
        obj = SimpleNamespace(
            id=uuid.uuid4(),
            book_id=book_id,
            round=round,
            method=method,
            content=content,
            prior_critique=prior_critique,
        )
        self._store.append(obj)
        return obj

    def get(self, version_id):
        for v in self._store:
            if v.id == version_id:
                return v
        raise ValueError(f"StoryVersion {version_id} not found")

    def list_for_round(self, book_id, round):
        return [v for v in self._store if v.book_id == book_id and v.round == round]


class _FakeJudgementRepo:
    def __init__(self) -> None:
        self._store: list = []

    def create(
        self, book_id, story_version_id, round, judge_prompt_version, *,
        emotional_authenticity, representation_quality, pacing, age_fit, uniqueness,
        weighted_total, passed, critique,
    ):
        obj = SimpleNamespace(
            id=uuid.uuid4(),
            book_id=book_id,
            story_version_id=story_version_id,
            round=round,
            judge_prompt_version=judge_prompt_version,
            emotional_authenticity=emotional_authenticity,
            representation_quality=representation_quality,
            pacing=pacing,
            age_fit=age_fit,
            uniqueness=uniqueness,
            weighted_total=weighted_total,
            passed=passed,
            critique=critique,
        )
        self._store.append(obj)
        return obj

    def list_for_round(self, book_id, round):
        results = [j for j in self._store if j.book_id == book_id and j.round == round]
        return sorted(results, key=lambda j: j.weighted_total, reverse=True)

    def best_for_round(self, book_id, round):
        results = self.list_for_round(book_id, round)
        return results[0] if results else None


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

BRIEF = {"title": "The Brave Little Snail", "age_range": "4-6", "theme": "courage"}
_METHODS = ("three-act", "sensory-first", "problem-solution", "hero's-journey")


def _judge_json(weighted_total: float, threshold: float = 7.5) -> str:
    return json.dumps({
        "emotional_authenticity": weighted_total,
        "representation_quality": weighted_total,
        "pacing": weighted_total,
        "age_fit": weighted_total,
        "uniqueness": weighted_total,
        "weighted_total": weighted_total,
        "passed": weighted_total >= threshold,
        "critique": {dim: "Looks good." for dim in
                     ("emotional_authenticity", "representation_quality",
                      "pacing", "age_fit", "uniqueness")},
    })


class _FakeImageRepo:
    def __init__(self) -> None:
        self._store: list = []

    def create(self, book_id, kind, prompt, provider, provider_params, storage_key, *,
               story_version_id=None, scene_index=None, seed=None):
        obj = SimpleNamespace(
            id=uuid.uuid4(), book_id=book_id, kind=kind, prompt=prompt,
            provider=provider, provider_params=provider_params, storage_key=storage_key,
            story_version_id=story_version_id, scene_index=scene_index, seed=seed,
        )
        self._store.append(obj)
        return obj

    def list_for_book(self, book_id, *, kind=None):
        return [i for i in self._store if i.book_id == book_id and (kind is None or i.kind == kind)]


class _FakeStorage:
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self._data[key] = data

    def get(self, key: str) -> bytes:
        return self._data[key]

    def exists(self, key: str) -> bool:
        return key in self._data


def _make_env(brief=None, *, max_rounds=3, score_threshold=7.5, llm_responses=None):
    book = _FakeBook(brief or BRIEF, max_rounds=max_rounds, score_threshold=score_threshold)
    book_repo = _FakeBookRepo(book)
    version_repo = _FakeStoryVersionRepo()
    judgement_repo = _FakeJudgementRepo()
    image_repo = _FakeImageRepo()
    llm = FakeLLMProvider(responses=llm_responses or [])
    image = FakeImageProvider()
    storage = _FakeStorage()
    orch = Orchestrator(book_repo, version_repo, judgement_repo, image_repo, llm, image, storage)
    return orch, book, book_repo, version_repo, judgement_repo, llm


def _passing_responses(rounds: int = 1, threshold: float = 7.5) -> list[str]:
    """Writer + judge responses for `rounds` rounds where the last round passes."""
    responses = []
    for r in range(rounds):
        responses += [f"story round {r + 1}"] * 4              # 4 writers
        score = 8.0 if r == rounds - 1 else 6.0               # last round passes
        responses += [_judge_json(score, threshold)] * 4       # 4 judges
    return responses


def _failing_responses(rounds: int, threshold: float = 7.5) -> list[str]:
    """Writer + judge responses for `rounds` rounds where every round fails."""
    responses = []
    for r in range(rounds):
        responses += [f"story round {r + 1}"] * 4
        responses += [_judge_json(5.0, threshold)] * 4
    return responses


# ---------------------------------------------------------------------------
# _decide_outcome (pure logic)
# ---------------------------------------------------------------------------

class TestDecideOutcome:
    def _orch(self):
        orch, *_ = _make_env()
        return orch

    def _book(self, current_round, max_rounds, score_threshold=7.5):
        b = _FakeBook({}, max_rounds=max_rounds, score_threshold=score_threshold)
        b.current_round = current_round
        return b

    def _judgement(self, weighted_total, threshold=7.5):
        return SimpleNamespace(weighted_total=weighted_total, passed=weighted_total >= threshold)

    def test_pass_when_above_threshold(self):
        orch = self._orch()
        book = self._book(1, 3)
        j = self._judgement(8.0)
        assert orch._decide_outcome(book, j) == "pass"

    def test_retry_when_below_threshold_and_rounds_remain(self):
        orch = self._orch()
        book = self._book(1, 3)
        j = self._judgement(6.0)
        assert orch._decide_outcome(book, j) == "retry"

    def test_retire_when_max_rounds_reached(self):
        orch = self._orch()
        book = self._book(3, 3)
        j = self._judgement(6.0)
        assert orch._decide_outcome(book, j) == "retire"

    def test_retire_when_no_judgement(self):
        orch = self._orch()
        book = self._book(3, 3)
        assert orch._decide_outcome(book, None) == "retire"

    def test_pass_on_last_allowed_round(self):
        orch = self._orch()
        book = self._book(3, 3)
        j = self._judgement(9.0)
        assert orch._decide_outcome(book, j) == "pass"


# ---------------------------------------------------------------------------
# Happy path — single round
# ---------------------------------------------------------------------------

class TestHappyPathSingleRound:
    def setup_method(self):
        self.orch, self.book, self.book_repo, self.version_repo, self.judgement_repo, self.llm = \
            _make_env(llm_responses=_passing_responses(rounds=1))

    def test_book_reaches_awaiting_approval(self):
        self.orch.start(self.book.id)
        self.orch.run_judging(self.book.id)
        assert self.book.status == BookStatus.AWAITING_APPROVAL

    def test_four_story_versions_written(self):
        self.orch.start(self.book.id)
        versions = self.version_repo.list_for_round(self.book.id, 1)
        assert len(versions) == 4

    def test_all_four_methods_covered(self):
        self.orch.start(self.book.id)
        methods = {v.method for v in self.version_repo.list_for_round(self.book.id, 1)}
        assert methods == set(_METHODS)

    def test_four_judgements_saved(self):
        self.orch.start(self.book.id)
        self.orch.run_judging(self.book.id)
        assert len(self.judgement_repo.list_for_round(self.book.id, 1)) == 4

    def test_judge_prompt_version_recorded(self):
        from app.agents.judge import PROMPT_VERSION
        self.orch.start(self.book.id)
        self.orch.run_judging(self.book.id)
        judgements = self.judgement_repo.list_for_round(self.book.id, 1)
        assert all(j.judge_prompt_version == PROMPT_VERSION for j in judgements)

    def test_state_transitions_are_legal(self):
        self.orch.start(self.book.id)
        self.orch.run_judging(self.book.id)
        expected = [
            (BookStatus.DRAFT_BRIEF, BookStatus.OUTLINING),
            (BookStatus.OUTLINING, BookStatus.WRITING),
            (BookStatus.WRITING, BookStatus.JUDGING),
            (BookStatus.JUDGING, BookStatus.AWAITING_APPROVAL),
        ]
        assert self.book_repo.transitions == expected

    def test_round_incremented_to_one(self):
        self.orch.start(self.book.id)
        assert self.book.current_round == 1


# ---------------------------------------------------------------------------
# Retry path — fails round 1, passes round 2
# ---------------------------------------------------------------------------

class TestRetryPath:
    def setup_method(self):
        self.orch, self.book, self.book_repo, self.version_repo, self.judgement_repo, self.llm = \
            _make_env(llm_responses=_passing_responses(rounds=2))

    def _run_full(self):
        self.orch.start(self.book.id)        # → JUDGING
        self.orch.run_judging(self.book.id)  # → REVISION
        self.orch.handle_revision(self.book.id)  # → JUDGING (round 2)
        self.orch.run_judging(self.book.id)  # → AWAITING_APPROVAL

    def test_reaches_awaiting_approval(self):
        self._run_full()
        assert self.book.status == BookStatus.AWAITING_APPROVAL

    def test_two_rounds_of_versions(self):
        self._run_full()
        assert len(self.version_repo.list_for_round(self.book.id, 1)) == 4
        assert len(self.version_repo.list_for_round(self.book.id, 2)) == 4

    def test_round_incremented_correctly(self):
        self._run_full()
        assert self.book.current_round == 2

    def test_revision_transition_sequence(self):
        self._run_full()
        statuses = [t[1] for t in self.book_repo.transitions]
        assert BookStatus.REVISION in statuses
        assert BookStatus.WRITING in statuses[statuses.index(BookStatus.REVISION):]

    def test_prior_critique_passed_in_round_2(self):
        self._run_full()
        round2_versions = self.version_repo.list_for_round(self.book.id, 2)
        assert all(v.prior_critique is not None for v in round2_versions)

    def test_prior_critique_contains_previous_draft(self):
        self._run_full()
        round2_versions = self.version_repo.list_for_round(self.book.id, 2)
        assert all("PREVIOUS DRAFT" in v.prior_critique for v in round2_versions)

    def test_prior_critique_contains_judge_feedback(self):
        self._run_full()
        round2_versions = self.version_repo.list_for_round(self.book.id, 2)
        assert all("JUDGE CRITIQUE" in v.prior_critique for v in round2_versions)

    def test_no_prior_critique_in_round_1(self):
        self.orch.start(self.book.id)
        round1_versions = self.version_repo.list_for_round(self.book.id, 1)
        assert all(v.prior_critique is None for v in round1_versions)


# ---------------------------------------------------------------------------
# Retire path — all rounds fail
# ---------------------------------------------------------------------------

class TestRetirePath:
    def _run_until_done(self, max_rounds=2):
        orch, book, book_repo, version_repo, judgement_repo, llm = _make_env(
            max_rounds=max_rounds,
            llm_responses=_failing_responses(rounds=max_rounds),
        )
        orch.start(book.id)
        orch.run_judging(book.id)
        for _ in range(max_rounds - 1):
            if book.status == BookStatus.REVISION:
                orch.handle_revision(book.id)
                orch.run_judging(book.id)
        return book, book_repo

    def test_book_retired_after_max_rounds(self):
        book, _ = self._run_until_done(max_rounds=2)
        assert book.status == BookStatus.RETIRED

    def test_retired_transition_is_final(self):
        book, book_repo = self._run_until_done(max_rounds=2)
        final = book_repo.transitions[-1]
        assert final[1] == BookStatus.RETIRED

    def test_max_rounds_respected(self):
        book, _ = self._run_until_done(max_rounds=3)
        assert book.current_round == 3
        assert book.status == BookStatus.RETIRED


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_rerunning_writing_round_does_not_duplicate(self):
        orch, book, _, version_repo, _, llm = _make_env(
            llm_responses=["story"] * 8  # plenty of responses
        )
        orch.start(book.id)
        # Manually reset status to WRITING to simulate a re-run
        book.status = BookStatus.WRITING
        orch._run_writing_round(book)  # second call — should skip all 4 methods
        versions = version_repo.list_for_round(book.id, 1)
        assert len(versions) == 4  # still 4, not 8

    def test_partial_round_completes_remaining_methods(self):
        orch, book, book_repo, version_repo, _, llm = _make_env(
            llm_responses=["story"] * 8
        )
        # Simulate a partial round: only 2 methods already written
        book.status = BookStatus.WRITING
        book.current_round = 1
        version_repo.create(book.id, 1, "three-act", "existing content")
        version_repo.create(book.id, 1, "sensory-first", "existing content")

        orch._run_writing_round(book)
        versions = version_repo.list_for_round(book.id, 1)
        assert len(versions) == 4
        methods = {v.method for v in versions}
        assert methods == set(_METHODS)


# ---------------------------------------------------------------------------
# Best-version selection
# ---------------------------------------------------------------------------

class TestBestVersionSelection:
    def test_best_judgement_wins(self):
        """The version with the highest weighted_total should be used for prior critique."""
        responses = (
            # Round 1 writers — "best story" gets the highest failing score
            ["low story", "best story", "mid story", "other story"]
            # Round 1 judges — all below threshold (7.5); "best story" scores highest at 7.0
            + [_judge_json(5.0), _judge_json(7.0), _judge_json(6.5), _judge_json(6.0)]
            # Round 2 writers
            + ["revised"] * 4
            # Round 2 judges — all pass
            + [_judge_json(8.0)] * 4
        )

        orch, book, _, version_repo, judgement_repo, _ = _make_env(
            max_rounds=3,
            score_threshold=7.5,
            llm_responses=responses,
        )
        orch.start(book.id)
        orch.run_judging(book.id)   # round 1: best is 7.0 (sensory-first → "best story"); fails → REVISION
        orch.handle_revision(book.id)

        # Prior critique for round 2 should reference the round-1 winner
        round2_versions = version_repo.list_for_round(book.id, 2)
        assert all("best story" in v.prior_critique for v in round2_versions)
