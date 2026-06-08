"""WriterAgent: generates story content from a brief using a named writing method."""
import json

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

_SYSTEM_PROMPT = """\
You are a skilled children's book author. Write complete, engaging children's book stories.
Keep language age-appropriate, sentences short, and every page turn meaningful.
Return only the story text — no titles, no commentary, no formatting headers.\
"""

_SYSTEM_PROMPT_REVISION = """\
You are a skilled children's book author revising a draft based on editorial feedback.
Address every point in the critique specifically. Do not rewrite from scratch; improve the draft.
Return only the revised story text — no titles, no commentary, no formatting headers.\
"""


class WriterAgent:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def write(self, brief: dict, method: str, prior_critique: str | None = None) -> str:
        """Return story content for the given brief and writing method.

        When prior_critique is provided it contains the previous draft + judge feedback;
        the writer revises rather than starting fresh.
        """
        if method not in _METHOD_GUIDANCE:
            raise ValueError(
                f"Unknown writing method '{method}'. "
                f"Valid methods: {sorted(_METHOD_GUIDANCE)}"
            )

        system = _SYSTEM_PROMPT_REVISION if prior_critique else _SYSTEM_PROMPT
        user_content = self._build_user_prompt(brief, method, prior_critique)
        response = self._llm.generate(system, [{"role": "user", "content": user_content}])
        return response.content

    def _build_user_prompt(self, brief: dict, method: str, prior_critique: str | None) -> str:
        brief_block = json.dumps(brief, indent=2)
        method_block = _METHOD_GUIDANCE[method]

        if prior_critique:
            return (
                f"STORY BRIEF:\n{brief_block}\n\n"
                f"WRITING METHOD ({method}):\n{method_block}\n\n"
                f"PREVIOUS DRAFT AND CRITIQUE:\n{prior_critique}\n\n"
                "Write the revised story."
            )

        return (
            f"STORY BRIEF:\n{brief_block}\n\n"
            f"WRITING METHOD ({method}):\n{method_block}\n\n"
            "Write the story."
        )
