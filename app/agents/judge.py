"""JudgeAgent: scores story versions and returns structured critique.

The system prompt is a versioned artifact — PROMPT_VERSION must be bumped whenever
the prompt text changes, so judgements can be traced back to the exact prompt that
produced them.
"""
import json

from app.agents.base import JudgementResult, validate_judgement_json
from app.providers.base import LLMProvider

PROMPT_VERSION = "v1"

_JUDGEMENT_SCHEMA: dict = {
    "type": "object",
    "required": [
        "emotional_authenticity", "representation_quality", "pacing",
        "age_fit", "uniqueness", "weighted_total", "passed", "critique",
    ],
    "properties": {
        "emotional_authenticity": {"type": "number"},
        "representation_quality": {"type": "number"},
        "pacing": {"type": "number"},
        "age_fit": {"type": "number"},
        "uniqueness": {"type": "number"},
        "weighted_total": {"type": "number"},
        "passed": {"type": "boolean"},
        "critique": {
            "type": "object",
            "properties": {
                "emotional_authenticity": {"type": "string"},
                "representation_quality": {"type": "string"},
                "pacing": {"type": "string"},
                "age_fit": {"type": "string"},
                "uniqueness": {"type": "string"},
            },
        },
    },
}

_SYSTEM_PROMPT = f"""\
You are an expert children's book editor and publishing consultant. (Judge prompt {PROMPT_VERSION})

Score the provided story on five dimensions, each 0–10:
  emotional_authenticity  — does it ring true? will children feel seen?
  representation_quality  — are characters and settings portrayed with dignity and accuracy?
  pacing                  — does each page turn feel earned? no dragging or rushing?
  age_fit                 — is vocabulary, concept complexity, and length right for the target age?
  uniqueness              — does this story offer something fresh?

Compute weighted_total as the unweighted average of the five scores.
Set passed to true if weighted_total meets the threshold stated in the request.

Return ONLY a JSON object matching this schema — no prose before or after:
{{
  "emotional_authenticity": <number 0-10>,
  "representation_quality": <number 0-10>,
  "pacing": <number 0-10>,
  "age_fit": <number 0-10>,
  "uniqueness": <number 0-10>,
  "weighted_total": <number 0-10>,
  "passed": <boolean>,
  "critique": {{
    "emotional_authenticity": "<one sentence>",
    "representation_quality": "<one sentence>",
    "pacing": "<one sentence>",
    "age_fit": "<one sentence>",
    "uniqueness": "<one sentence>"
  }}
}}\
"""

_MAX_RETRIES = 3


class JudgeAgent:
    PROMPT_VERSION = PROMPT_VERSION

    def __init__(self, llm: LLMProvider, *, threshold: float = 7.5) -> None:
        self._llm = llm
        self._threshold = threshold

    def judge(self, story_versions: list[str], criteria: dict) -> list[JudgementResult]:
        """Score each story version independently. Returns one result per version."""
        return [self._judge_one(story, criteria) for story in story_versions]

    def _judge_one(self, story: str, criteria: dict) -> JudgementResult:
        user_prompt = self._build_user_prompt(story, criteria)
        messages: list[dict] = [{"role": "user", "content": user_prompt}]

        for attempt in range(_MAX_RETRIES):
            response = self._llm.generate(_SYSTEM_PROMPT, messages, json_schema=_JUDGEMENT_SCHEMA)
            try:
                data = json.loads(response.content)
                return validate_judgement_json(data, self._threshold)
            except (json.JSONDecodeError, ValueError, KeyError) as exc:
                if attempt == _MAX_RETRIES - 1:
                    raise RuntimeError(
                        f"Judge failed to return valid JSON after {_MAX_RETRIES} attempts. "
                        f"Last error: {exc}. Last response: {response.content!r}"
                    ) from exc
                # Feed the bad response back so the LLM can correct itself.
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Your response was invalid: {exc}. "
                        "Return only the JSON object — nothing else."
                    ),
                })

        raise RuntimeError("Unreachable")  # pragma: no cover

    def _build_user_prompt(self, story: str, criteria: dict) -> str:
        criteria_block = json.dumps(criteria, indent=2)
        return (
            f"SCORING CRITERIA:\n{criteria_block}\n\n"
            f"Pass threshold: {self._threshold}\n\n"
            f"STORY TO JUDGE:\n{story}"
        )
