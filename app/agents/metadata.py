"""MetadataAgent: drafts KDP-ready book metadata from the approved story text.

Output is human-editable before export. Stored in Book.book_metadata.
"""
from __future__ import annotations

import json

from app.providers.base import LLMProvider

_METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Final book title (≤60 chars for Amazon thumbnail readability)"},
        "subtitle": {"type": "string", "description": "Optional subtitle (leave empty string if none)"},
        "author": {"type": "string", "description": "Author name as it should appear on the cover"},
        "description": {
            "type": "string",
            "description": (
                "Amazon product description, 200–300 words. "
                "Open with the child's emotional experience, not a plot summary. "
                "Use language from real 5-star children's book reviews. "
                "End with the age range and a call to action."
            ),
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 7,
            "maxItems": 10,
            "description": (
                "KDP backend keywords. Mix: theme phrases, child age ('picture book 3-5'), "
                "emotional outcome, and one long-tail search phrase."
            ),
        },
        "age_range": {"type": "string", "description": "e.g. '3-5' or '5-8'"},
        "series_name": {"type": "string", "description": "Series name if applicable, else empty string"},
    },
    "required": ["title", "subtitle", "author", "description", "keywords", "age_range", "series_name"],
    "additionalProperties": False,
}

_SYSTEM = """You are a children's book marketing specialist with deep knowledge of Amazon KDP
and what makes children's book listings convert. You write metadata that is warm, authentic,
and grounded in the emotional experience of the child reader — never clinical or summary-like.
Your keyword research is informed by real Amazon search behavior for children's books.
Output ONLY valid JSON matching the schema provided."""

PROMPT_VERSION = "v1"


class MetadataAgent:
    PROMPT_VERSION = PROMPT_VERSION

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def draft(self, story_text: str, brief: dict) -> dict:
        """Draft book metadata from the approved story text + original brief.

        Returns a dict matching _METADATA_SCHEMA. Retries up to 3× on bad JSON.
        """
        user_message = (
            f"STORY BRIEF:\n{json.dumps(brief, indent=2)}\n\n"
            f"APPROVED STORY TEXT:\n{story_text}\n\n"
            "Draft complete KDP metadata for this book. "
            "Return JSON only, no prose, matching the schema exactly."
        )
        last_err: Exception | None = None
        for attempt in range(3):
            prompt = user_message if attempt == 0 else (
                f"{user_message}\n\nYour previous attempt returned invalid JSON: {last_err}. "
                "Return ONLY the JSON object."
            )
            resp = self._llm.generate(
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                json_schema=_METADATA_SCHEMA,
            )
            try:
                data = json.loads(resp.content)
                # Ensure required keys present
                for key in _METADATA_SCHEMA["required"]:
                    if key not in data:
                        raise ValueError(f"Missing required key: {key}")
                return data
            except (json.JSONDecodeError, ValueError) as e:
                last_err = e

        # After 3 failed attempts, raise so the task retries at the Celery level.
        raise RuntimeError(f"MetadataAgent failed after 3 attempts: {last_err}")
