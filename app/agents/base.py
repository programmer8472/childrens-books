"""Shared data types for agent outputs."""
from dataclasses import dataclass


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
