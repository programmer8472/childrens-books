"""WriterAgent: generates story content from a brief using a named writing method.

The writer authors the book as the exact 12 spreads it will become, each within
the spec word budget (book-design-spec.md §Typography). Structured output keeps
text density correct at the source rather than relying on downstream pagination.
"""
import json
from dataclasses import dataclass, field

from app.agents.base import NUM_STORY_SPREADS, word_budget
from app.providers.base import LLMProvider

_METHOD_GUIDANCE: dict[str, str] = {
    "three-act": (
        "Structure the story in three acts: Setup (introduce the world and protagonist), "
        "Confrontation (the central challenge or conflict), Resolution (how it is resolved "
        "and what the character learns)."
    ),
    "sensory-first": (
        "Open with rich sensory details that immediately immerse the reader in the world. "
        "Lead with what the protagonist sees, hears, smells, or feels before introducing the plot."
    ),
    "problem-solution": (
        "Present a clear, relatable problem early. Show the protagonist's attempts and struggles "
        "before arriving at a satisfying solution. The solution should feel earned, not lucky."
    ),
    "hero's-journey": (
        "Follow the hero's journey arc: the ordinary world, the call to adventure, crossing the "
        "threshold, trials, the climax, and the return transformed."
    ),
}

# The body of every spread string is what gets typeset on one page-turn, so the
# word cap is a hard print-layout constraint, not a style preference.
_SYSTEM_PROMPT = """\
You are a skilled children's book author. Write a complete, engaging picture-book story.

Output rules (these are layout constraints — breaking them makes the book unprintable):
- Return ONLY a JSON object of the form {{"spreads": ["...", "..."]}} — no prose, no titles, no markdown.
- "spreads" must contain EXACTLY {n} strings, in reading order, one per page-turn.
- Each spread MUST be at most {budget} words. Fewer is fine. Never exceed it.
- Keep sentences short and language age-appropriate; make every page turn meaningful.\
"""

_SYSTEM_PROMPT_REVISION = """\
You are a skilled children's book author revising a draft based on editorial feedback.
Address every point in the critique specifically. Do not rewrite from scratch; improve the draft.

Output rules (these are layout constraints — breaking them makes the book unprintable):
- Return ONLY a JSON object of the form {{"spreads": ["...", "..."]}} — no prose, no titles, no markdown.
- "spreads" must contain EXACTLY {n} strings, in reading order, one per page-turn.
- Each spread MUST be at most {budget} words. Fewer is fine. Never exceed it.\
"""

_SPREADS_SCHEMA: dict = {
    "type": "object",
    "required": ["spreads"],
    "properties": {
        "spreads": {"type": "array", "items": {"type": "string"}},
    },
}


@dataclass
class StoryDraft:
    """A writer's output: the joined prose plus the 12 per-spread strings."""
    content: str
    spreads: list[str] = field(default_factory=list)


class WriterAgent:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def write(self, brief: dict, method: str, prior_critique: str | None = None) -> StoryDraft:
        """Return a StoryDraft (joined prose + 12 spreads) for the brief and method.

        When prior_critique is provided it contains the previous draft + judge feedback;
        the writer revises rather than starting fresh.
        """
        if method not in _METHOD_GUIDANCE:
            raise ValueError(
                f"Unknown writing method '{method}'. "
                f"Valid methods: {sorted(_METHOD_GUIDANCE)}"
            )

        budget = word_budget(brief.get("age_range", "3-8"))
        template = _SYSTEM_PROMPT_REVISION if prior_critique else _SYSTEM_PROMPT
        system = template.format(n=NUM_STORY_SPREADS, budget=budget)
        user_content = self._build_user_prompt(brief, method, prior_critique, budget)
        response = self._llm.generate(
            system, [{"role": "user", "content": user_content}], json_schema=_SPREADS_SCHEMA
        )
        spreads = self._parse_spreads(response.content)
        content = "\n\n".join(spreads)
        return StoryDraft(content=content, spreads=spreads)

    def _parse_spreads(self, raw: str) -> list[str]:
        """Parse the model output into exactly NUM_STORY_SPREADS spread strings.

        Tolerant by design: accepts a {"spreads": [...]} object or a bare array,
        and falls back to paginating free prose so a non-conforming response
        (or the offline fake) still yields a usable, non-clipping book. The hard
        word-budget guarantee is enforced downstream by the judge gate and the
        compositor preflight, so this parser never needs to reject.
        """
        spreads: list[str] | None = None
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and isinstance(data.get("spreads"), list):
                spreads = [str(x).strip() for x in data["spreads"] if str(x).strip()]
            elif isinstance(data, list):
                spreads = [str(x).strip() for x in data if str(x).strip()]
        except (json.JSONDecodeError, TypeError):
            spreads = None

        if spreads and len(spreads) == NUM_STORY_SPREADS:
            return spreads

        # Either prose, a malformed shape, or the wrong count: re-paginate the
        # joined text into exactly NUM_STORY_SPREADS contiguous segments.
        from app.compositor.pdf_writer import _split_story
        prose = " ".join(spreads) if spreads else raw
        return _split_story(prose, NUM_STORY_SPREADS)

    def _build_user_prompt(
        self, brief: dict, method: str, prior_critique: str | None, budget: int
    ) -> str:
        brief_block = json.dumps(brief, indent=2)
        method_block = _METHOD_GUIDANCE[method]
        budget_line = (
            f"Write exactly {NUM_STORY_SPREADS} spreads; each at most {budget} words."
        )

        if prior_critique:
            return (
                f"STORY BRIEF:\n{brief_block}\n\n"
                f"WRITING METHOD ({method}):\n{method_block}\n\n"
                f"PREVIOUS DRAFT AND CRITIQUE:\n{prior_critique}\n\n"
                f"{budget_line}\n"
                "Write the revised story as the JSON spreads object."
            )

        return (
            f"STORY BRIEF:\n{brief_block}\n\n"
            f"WRITING METHOD ({method}):\n{method_block}\n\n"
            f"{budget_line}\n"
            "Write the story as the JSON spreads object."
        )
