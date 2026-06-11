"""Shared data types for agent outputs."""
from dataclasses import dataclass

# Spec: book-design-spec.md §Typography — words per spread.
# Ages 3-5: <= 30 words; ages 5-8: <= 75 words. These are the binding caps
# enforced at judging time and re-asserted by the compositor preflight.
NUM_STORY_SPREADS = 12
WORD_BUDGET_YOUNG = 30
WORD_BUDGET_OLDER = 75


def word_budget(age_range: str) -> int:
    """Return the per-spread word cap for an age-range string.

    Mirrors typography.body_font_size: ages 3-5 (with no 6/7/8) read as the
    "young" band; everything else uses the older band.
    """
    ar = age_range or ""
    young = ("3" in ar or "4" in ar or "5" in ar) and not any(d in ar for d in ("6", "7", "8"))
    return WORD_BUDGET_YOUNG if young else WORD_BUDGET_OLDER


def count_words(text: str) -> int:
    return len((text or "").split())


@dataclass
class SpreadBudgetViolation:
    index: int          # 0-based spread index
    word_count: int
    budget: int

    def message(self) -> str:
        return (
            f"Spread {self.index + 1} has {self.word_count} words; "
            f"cap is {self.budget}. Tighten to one beat per spread."
        )


def check_spread_budget(spreads: list[str], age_range: str) -> list[SpreadBudgetViolation]:
    """Return a violation for every spread whose word count exceeds the age cap."""
    budget = word_budget(age_range)
    violations: list[SpreadBudgetViolation] = []
    for i, spread in enumerate(spreads):
        wc = count_words(spread)
        if wc > budget:
            violations.append(SpreadBudgetViolation(index=i, word_count=wc, budget=budget))
    return violations


_SCORE_DIMENSIONS = (
    "emotional_authenticity",
    "representation_quality",
    "pacing",
    "age_fit",
    "uniqueness",
)


@dataclass
class JudgementResult:
    emotional_authenticity: float
    representation_quality: float
    pacing: float
    age_fit: float
    uniqueness: float
    weighted_total: float
    passed: bool
    critique: dict  # keys: dimension names, values: critique strings


def validate_judgement_json(data: dict, threshold: float) -> JudgementResult:
    """Parse and validate a raw judge JSON dict; raise ValueError on bad data."""
    for dim in _SCORE_DIMENSIONS:
        if dim not in data:
            raise ValueError(f"Missing dimension: {dim}")
        val = float(data[dim])
        if not (0.0 <= val <= 10.0):
            raise ValueError(f"{dim}={val} out of range [0, 10]")

    if "weighted_total" not in data:
        raise ValueError("Missing weighted_total")
    weighted_total = float(data["weighted_total"])

    critique = data.get("critique", {})
    if not isinstance(critique, dict):
        raise ValueError("critique must be an object")

    return JudgementResult(
        emotional_authenticity=float(data["emotional_authenticity"]),
        representation_quality=float(data["representation_quality"]),
        pacing=float(data["pacing"]),
        age_fit=float(data["age_fit"]),
        uniqueness=float(data["uniqueness"]),
        weighted_total=weighted_total,
        passed=weighted_total >= threshold,
        critique=critique,
    )
