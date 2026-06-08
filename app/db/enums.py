"""BookStatus pipeline stages and the single-source legal transition table."""
import enum


class BookStatus(str, enum.Enum):
    DRAFT_BRIEF = "DRAFT_BRIEF"
    OUTLINING = "OUTLINING"
    WRITING = "WRITING"
    JUDGING = "JUDGING"
    REVISION = "REVISION"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    GENERATING_IMAGES = "GENERATING_IMAGES"
    GENERATING_COVER = "GENERATING_COVER"
    DRAFTING_METADATA = "DRAFTING_METADATA"
    EXPORTING = "EXPORTING"
    EXPORT_READY = "EXPORT_READY"
    DONE = "DONE"
    RETIRED = "RETIRED"


# Single source of truth for legal pipeline transitions.
# The orchestrator is the ONLY caller of assert_legal_transition.
LEGAL_TRANSITIONS: dict[BookStatus, frozenset[BookStatus]] = {
    BookStatus.DRAFT_BRIEF: frozenset({BookStatus.OUTLINING}),
    BookStatus.OUTLINING: frozenset({BookStatus.WRITING}),
    BookStatus.WRITING: frozenset({BookStatus.JUDGING}),
    BookStatus.JUDGING: frozenset({BookStatus.REVISION, BookStatus.AWAITING_APPROVAL, BookStatus.RETIRED}),
    BookStatus.REVISION: frozenset({BookStatus.WRITING}),
    BookStatus.AWAITING_APPROVAL: frozenset({BookStatus.APPROVED, BookStatus.RETIRED}),
    BookStatus.APPROVED: frozenset({BookStatus.GENERATING_IMAGES}),
    BookStatus.GENERATING_IMAGES: frozenset({BookStatus.GENERATING_COVER}),
    BookStatus.GENERATING_COVER: frozenset({BookStatus.DRAFTING_METADATA}),
    BookStatus.DRAFTING_METADATA: frozenset({BookStatus.EXPORTING}),
    BookStatus.EXPORTING: frozenset({BookStatus.EXPORT_READY}),
    BookStatus.EXPORT_READY: frozenset({BookStatus.DONE}),
    BookStatus.DONE: frozenset(),
    BookStatus.RETIRED: frozenset(),
}

assert set(LEGAL_TRANSITIONS) == set(BookStatus), "LEGAL_TRANSITIONS must cover every BookStatus"


def assert_legal_transition(from_status: BookStatus, to_status: BookStatus) -> None:
    """Raise ValueError if the transition is not in the legal table."""
    if to_status not in LEGAL_TRANSITIONS[from_status]:
        raise ValueError(
            f"Illegal transition {from_status} → {to_status}. "
            f"Legal targets: {sorted(s.value for s in LEGAL_TRANSITIONS[from_status])}"
        )
