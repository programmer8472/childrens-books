"""BookStatus pipeline stages and the single-source legal transition table."""
import enum


class BookStatus(str, enum.Enum):
    DRAFT_BRIEF = "DRAFT_BRIEF"
    OUTLINING = "OUTLINING"
    WRITING = "WRITING"
    JUDGING = "JUDGING"
    REVISION = "REVISION"
    AWAITING_SHORTLIST = "AWAITING_SHORTLIST"
    SHORTLIST_JUDGING = "SHORTLIST_JUDGING"
    AWAITING_FINAL_APPROVAL = "AWAITING_FINAL_APPROVAL"
    # Kept for backward-compatibility with books created before the three-phase redesign
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    GENERATING_IMAGES = "GENERATING_IMAGES"
    GENERATING_COVER = "GENERATING_COVER"
    DRAFTING_METADATA = "DRAFTING_METADATA"
    EXPORTING = "EXPORTING"
    EXPORT_READY = "EXPORT_READY"
    DONE = "DONE"
    RETIRED = "RETIRED"
    # Human-requested stop. Distinct from RETIRED (failure) so the board can
    # tell "I cancelled this" apart from "this broke."
    CANCELLED = "CANCELLED"


# Single source of truth for legal pipeline transitions.
# The orchestrator is the ONLY caller of assert_legal_transition.
# Every automated, in-progress stage may also fail to RETIRED. A task that
# exhausts its retries marks the book RETIRED with the error in the audit note,
# so a failure surfaces as red on the board instead of silently freezing.
# Every non-terminal status may also be CANCELLED by a human stop request.
# C is appended below so the per-row sets stay readable.
_C = BookStatus.CANCELLED

LEGAL_TRANSITIONS: dict[BookStatus, frozenset[BookStatus]] = {
    BookStatus.DRAFT_BRIEF: frozenset({BookStatus.OUTLINING, BookStatus.RETIRED, _C}),
    BookStatus.OUTLINING: frozenset({BookStatus.WRITING, BookStatus.RETIRED, _C}),
    BookStatus.WRITING: frozenset({BookStatus.JUDGING, BookStatus.RETIRED, _C}),
    # New flow: always iterate all rounds; no early exit on score pass.
    # JUDGING → REVISION (more rounds remain) or AWAITING_SHORTLIST (max rounds hit).
    BookStatus.JUDGING: frozenset({BookStatus.REVISION, BookStatus.AWAITING_SHORTLIST, BookStatus.RETIRED, _C}),
    BookStatus.REVISION: frozenset({BookStatus.WRITING, BookStatus.RETIRED, _C}),
    BookStatus.AWAITING_SHORTLIST: frozenset({BookStatus.SHORTLIST_JUDGING, BookStatus.RETIRED, _C}),
    BookStatus.SHORTLIST_JUDGING: frozenset({BookStatus.AWAITING_FINAL_APPROVAL, BookStatus.RETIRED, _C}),
    BookStatus.AWAITING_FINAL_APPROVAL: frozenset({BookStatus.APPROVED, BookStatus.RETIRED, _C}),
    # Legacy gate kept for backward-compat; no new books enter this state.
    BookStatus.AWAITING_APPROVAL: frozenset({BookStatus.APPROVED, BookStatus.REVISION, BookStatus.RETIRED, _C}),
    BookStatus.APPROVED: frozenset({BookStatus.GENERATING_IMAGES, BookStatus.RETIRED, _C}),
    BookStatus.GENERATING_IMAGES: frozenset({BookStatus.GENERATING_COVER, BookStatus.RETIRED, _C}),
    BookStatus.GENERATING_COVER: frozenset({BookStatus.DRAFTING_METADATA, BookStatus.RETIRED, _C}),
    BookStatus.DRAFTING_METADATA: frozenset({BookStatus.EXPORTING, BookStatus.RETIRED, _C}),
    BookStatus.EXPORTING: frozenset({BookStatus.EXPORT_READY, BookStatus.RETIRED, _C}),
    BookStatus.EXPORT_READY: frozenset({BookStatus.DONE}),
    BookStatus.DONE: frozenset(),
    BookStatus.RETIRED: frozenset(),
    BookStatus.CANCELLED: frozenset(),
}

assert set(LEGAL_TRANSITIONS) == set(BookStatus), "LEGAL_TRANSITIONS must cover every BookStatus"


def assert_legal_transition(from_status: BookStatus, to_status: BookStatus) -> None:
    """Raise ValueError if the transition is not in the legal table."""
    if to_status not in LEGAL_TRANSITIONS[from_status]:
        raise ValueError(
            f"Illegal transition {from_status} → {to_status}. "
            f"Legal targets: {sorted(s.value for s in LEGAL_TRANSITIONS[from_status])}"
        )
