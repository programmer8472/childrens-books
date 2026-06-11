"""Unit 4 tests: Orchestrator + full writer/judge loop, end-to-end on fakes.

All offline — fake repos (in-memory), FakeLLMProvider, no DB, no Celery.

Key behavioral changes in the three-phase review redesign:
- No more early exit on score pass; all max_rounds are always run.
- After max_rounds, orchestrator moves to AWAITING_SHORTLIST (not AWAITING_APPROVAL).
- rejudge_shortlist() handles Phase 2 (re-judge) → AWAITING_FINAL_APPROVAL.
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
        self.approved_version_id = None
        self.cancel_requested = False


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

    def fail(self, book, note):
        return self.transition(book, BookStatus.RETIRED, actor="orchestrator", note=note)

    def refresh(self, book):
        return book

    def request_cancel(self, book):
        book.cancel_requested = True
        return book

    def cancel(self, book, note=None):
        from app.db.enums import LEGAL_TRANSITIONS
        if BookStatus.CANCELLED not in LEGAL_TRANSITIONS.get(book.status, frozenset()):
            return None
        return self.transition(book, BookStatus.CANCELLED, actor="human", note=note)


class _FakeStoryVersionRepo:
    def __init__(self) -> None:
        self._store: list = []

    def create(self, book_id, round, method, content, *, spreads=None, prior_critique=None):
        obj = SimpleNamespace(
            id=uuid.uuid4(),
            book_id=book_id,
            round=round,
            method=method,
            content=content,
            spreads=spreads,
            prior_critique=prior_critique,
            shortlisted=False,
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

    def set_shortlisted(self, version_id, shortlisted):
        version = self.get(version_id)
        version.shortlisted = shortlisted

    def list_shortlisted_for_book(self, book_id):
        return [v for v in self._store if v.book_id == book_id and v.shortlisted]


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

    def delete_for_versions(self, book_id, round, version_ids):
        ids = set(version_ids)
        self._store = [
            j for j in self._store
            if not (j.book_id == book_id and j.round == round and j.story_version_id in ids)
        ]


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
    """Writer + judge responses for `rounds` rounds (all scoring above threshold)."""
    responses = []
    for r in range(rounds):
        responses += [f"story round {r + 1}"] * 4   # 4 writers
        responses += [_judge_json(8.0, threshold)] * 4  # 4 judges passing
    return responses


def _failing_responses(rounds: int, threshold: float = 7.5) -> list[str]:
    """Writer + judge responses for `rounds` rounds where every round fails."""
    responses = []
    for r in range(rounds):
        responses += [f"story round {r + 1}"] * 4
        responses += [_judge_json(5.0, threshold)] * 4
    return responses


# ---------------------------------------------------------------------------
# _decide_outcome (pure logic) — now "shortlist" replaces "pass"/"retire"
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

    def test_shortlist_when_max_rounds_reached_and_passing(self):
        orch = self._orch()
        book = self._book(3, 3)
        j = self._judgement(8.0)
        assert orch._decide_outcome(book, j) == "shortlist"

    def test_shortlist_when_max_rounds_reached_and_failing(self):
        orch = self._orch()
        book = self._book(3, 3)
        j = self._judgement(6.0)
        assert orch._decide_outcome(book, j) == "shortlist"

    def test_shortlist_when_max_rounds_no_judgement(self):
        orch = self._orch()
        book = self._book(3, 3)
        assert orch._decide_outcome(book, None) == "shortlist"

    def test_retry_when_rounds_remain_and_failing(self):
        orch = self._orch()
        book = self._book(1, 3)
        j = self._judgement(6.0)
        assert orch._decide_outcome(book, j) == "retry"

    def test_retry_when_rounds_remain_even_if_passing(self):
        # No early exit on pass — always run all rounds.
        orch = self._orch()
        book = self._book(1, 3)
        j = self._judgement(8.0)
        assert orch._decide_outcome(book, j) == "retry"

    def test_shortlist_on_last_allowed_round(self):
        orch = self._orch()
        book = self._book(3, 3)
        j = self._judgement(9.0)
        assert orch._decide_outcome(book, j) == "shortlist"


# ---------------------------------------------------------------------------
# Happy path — max_rounds=1, reaches AWAITING_SHORTLIST in one judging step
# ---------------------------------------------------------------------------

class TestHappyPathSingleRound:
    def setup_method(self):
        self.orch, self.book, self.book_repo, self.version_repo, self.judgement_repo, self.llm = \
            _make_env(max_rounds=1, llm_responses=_passing_responses(rounds=1))

    def test_book_reaches_awaiting_shortlist(self):
        self.orch.start(self.book.id)
        self.orch.run_judging(self.book.id)
        assert self.book.status == BookStatus.AWAITING_SHORTLIST

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
            (BookStatus.JUDGING, BookStatus.AWAITING_SHORTLIST),
        ]
        assert self.book_repo.transitions == expected

    def test_round_incremented_to_one(self):
        self.orch.start(self.book.id)
        assert self.book.current_round == 1


# ---------------------------------------------------------------------------
# Retry path — two rounds (max_rounds=2); reaches AWAITING_SHORTLIST after round 2
# ---------------------------------------------------------------------------

class TestRetryPath:
    def setup_method(self):
        self.orch, self.book, self.book_repo, self.version_repo, self.judgement_repo, self.llm = \
            _make_env(max_rounds=2, llm_responses=_passing_responses(rounds=2))

    def _run_full(self):
        self.orch.start(self.book.id)          # → WRITING (round 1) → JUDGING
        self.orch.run_judging(self.book.id)    # round 1 < max 2 → REVISION
        self.orch.handle_revision(self.book.id)  # → WRITING (round 2)
        self.orch.run_judging(self.book.id)    # round 2 >= max 2 → AWAITING_SHORTLIST

    def test_reaches_awaiting_shortlist(self):
        self._run_full()
        assert self.book.status == BookStatus.AWAITING_SHORTLIST

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
# All rounds fail — still reaches AWAITING_SHORTLIST (no auto-retire)
# ---------------------------------------------------------------------------

class TestShortlistAfterMaxRounds:
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

    def test_book_reaches_awaiting_shortlist_after_max_rounds(self):
        book, _ = self._run_until_done(max_rounds=2)
        assert book.status == BookStatus.AWAITING_SHORTLIST

    def test_last_transition_is_awaiting_shortlist(self):
        book, book_repo = self._run_until_done(max_rounds=2)
        assert book_repo.transitions[-1][1] == BookStatus.AWAITING_SHORTLIST

    def test_max_rounds_respected(self):
        book, _ = self._run_until_done(max_rounds=3)
        assert book.current_round == 3
        assert book.status == BookStatus.AWAITING_SHORTLIST


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
# Best-version selection for prior critique
# ---------------------------------------------------------------------------

class TestBestVersionSelection:
    def test_each_writer_revises_own_draft(self):
        """Each round-2 writer revises its own round-1 draft, not the global best."""
        responses = (
            # Round 1 writers in _WRITING_METHODS order
            ["low story", "best story", "mid story", "other story"]
            # Round 1 judges — all below threshold (7.5); "best story" scores highest at 7.0
            + [_judge_json(5.0), _judge_json(7.0), _judge_json(6.5), _judge_json(6.0)]
            # Round 2 writers
            + ["revised"] * 4
            # Round 2 judges (not consumed in this test)
            + [_judge_json(8.0)] * 4
        )

        orch, book, _, version_repo, judgement_repo, _ = _make_env(
            max_rounds=3,
            score_threshold=7.5,
            llm_responses=responses,
        )
        orch.start(book.id)
        orch.run_judging(book.id)   # round 1 fails (1 < 3) → REVISION
        orch.handle_revision(book.id)

        round1_by_method = {v.method: v for v in version_repo.list_for_round(book.id, 1)}
        round2_versions = version_repo.list_for_round(book.id, 2)
        # Each writer's prior critique contains its own round-1 draft, not another method's
        for v in round2_versions:
            assert v.prior_critique is not None
            assert round1_by_method[v.method].content in v.prior_critique
            assert "JUDGE CRITIQUE" in v.prior_critique


# ---------------------------------------------------------------------------
# rejudge_shortlist — Phase 2 of the three-phase review
# ---------------------------------------------------------------------------

class TestRejudgeShortlist:
    def setup_method(self):
        # max_rounds=1 so one judging step reaches AWAITING_SHORTLIST.
        # Then 2 more judge responses for the shortlist re-judge.
        base = _passing_responses(rounds=1)
        shortlist_responses = [_judge_json(8.5), _judge_json(9.0)]
        self.orch, self.book, self.book_repo, self.version_repo, self.judgement_repo, self.llm = \
            _make_env(max_rounds=1, llm_responses=base + shortlist_responses)

    def _reach_shortlist(self):
        self.orch.start(self.book.id)
        self.orch.run_judging(self.book.id)
        assert self.book.status == BookStatus.AWAITING_SHORTLIST

    def test_rejudge_reaches_awaiting_final_approval(self):
        self._reach_shortlist()
        versions = self.version_repo.list_for_round(self.book.id, 1)
        self.orch.rejudge_shortlist(self.book.id, [v.id for v in versions[:2]])
        assert self.book.status == BookStatus.AWAITING_FINAL_APPROVAL

    def test_shortlisted_versions_marked(self):
        self._reach_shortlist()
        versions = self.version_repo.list_for_round(self.book.id, 1)
        selected = [v.id for v in versions[:2]]
        self.orch.rejudge_shortlist(self.book.id, selected)
        shortlisted = self.version_repo.list_shortlisted_for_book(self.book.id)
        assert len(shortlisted) == 2
        assert {v.id for v in shortlisted} == set(selected)

    def test_rejudge_replaces_scores_in_place(self):
        """Re-judging replaces a shortlisted version's score rather than stacking
        a duplicate row — each version keeps exactly one judgement per round."""
        self._reach_shortlist()
        versions = self.version_repo.list_for_round(self.book.id, 1)
        selected = [v.id for v in versions[:2]]
        old_ids = {
            j.story_version_id: j.id
            for j in self.judgement_repo.list_for_round(self.book.id, 1)
        }
        self.orch.rejudge_shortlist(self.book.id, selected)
        after = self.judgement_repo.list_for_round(self.book.id, 1)
        # No accumulation: still one judgement per version (idempotent re-judge).
        per_version = {}
        for j in after:
            per_version.setdefault(j.story_version_id, []).append(j)
        assert all(len(v) == 1 for v in per_version.values())
        # The two re-judged versions got fresh judgement rows.
        for vid in selected:
            assert per_version[vid][0].id != old_ids[vid]

    def test_rejudge_transitions_are_legal(self):
        self._reach_shortlist()
        versions = self.version_repo.list_for_round(self.book.id, 1)
        self.orch.rejudge_shortlist(self.book.id, [v.id for v in versions[:2]])
        to_statuses = [t[1] for t in self.book_repo.transitions]
        assert BookStatus.SHORTLIST_JUDGING in to_statuses
        assert BookStatus.AWAITING_FINAL_APPROVAL in to_statuses
