"""DeepSeekLLMProvider — calls the DeepSeek API via the OpenAI-compatible endpoint.

Model selection is driven by the caller's `tier`, NOT by json_schema:
  - tier="high" (default) → deepseek-v4-pro, large token budget. Creative
    authoring (writer, paragraph rewrite). These emit long structured stories;
    deepseek-v4-pro is a reasoning model, so the budget must comfortably cover
    reasoning tokens AND the visible output or the response truncates to empty.
  - tier="fast" → deepseek-v4-flash, small default budget. Evaluation and
    structured extraction (judge, metadata).

json_schema is accepted for interface compatibility but DeepSeek relies on the
agents' system prompts (which already mandate JSON) plus their retry-on-bad-JSON
logic, so it does not affect routing or the request.

Reads DEEPSEEK_API_KEY from the environment.
"""
import os

from openai import OpenAI

from app.providers.base import LLMProvider, LLMResponse

_BASE_URL = "https://api.deepseek.com"
_WRITER_MODEL = "deepseek-v4-pro"
_JUDGE_MODEL = "deepseek-v4-flash"

_MAX_TOKENS_WRITER = 8192
# deepseek-v4-flash is a reasoning model: reasoning_tokens count against this
# budget BEFORE any visible content. 1024 was routinely consumed entirely by
# reasoning, leaving zero output and a length-truncation error. Give the small
# judgement/metadata JSON ample headroom above the reasoning overhead.
_MAX_TOKENS_JUDGE = 4096


class DeepSeekLLMProvider(LLMProvider):
    """Production LLM provider backed by the DeepSeek API."""

    def __init__(
        self,
        writer_model: str = _WRITER_MODEL,
        judge_model: str = _JUDGE_MODEL,
    ) -> None:
        self._client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=_BASE_URL,
        )
        self._writer_model = writer_model
        self._judge_model = judge_model

    def generate(
        self,
        system: str,
        messages: list,
        *,
        json_schema: dict | None = None,
        max_tokens: int | None = None,
        tier: str = "high",
    ) -> LLMResponse:
        use_fast = tier == "fast"
        model = self._judge_model if use_fast else self._writer_model
        default_limit = _MAX_TOKENS_JUDGE if use_fast else _MAX_TOKENS_WRITER
        max_tokens = max_tokens if max_tokens is not None else default_limit

        api_messages = [{"role": "system", "content": system}, *messages]

        # Always stream to avoid HTTP timeout on long story outputs.
        with self._client.chat.completions.stream(
            model=model,
            messages=api_messages,
            max_tokens=max_tokens,
        ) as stream:
            completion = stream.get_final_completion()

        text = completion.choices[0].message.content or ""
        return LLMResponse(
            content=text,
            model=completion.model,
            input_tokens=completion.usage.prompt_tokens,
            output_tokens=completion.usage.completion_tokens,
        )
