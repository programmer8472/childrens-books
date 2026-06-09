"""DeepSeekLLMProvider — calls the DeepSeek API via the OpenAI-compatible endpoint.

Writer calls (json_schema=None) use deepseek-v4-pro for creative quality.
Judge calls (json_schema is not None) use deepseek-v4-flash; the judge's
system prompt already enforces JSON output and the agent has retry logic for
malformed parses, so no additional schema enforcement is needed here.

Reads DEEPSEEK_API_KEY from the environment.
"""
import os

from openai import OpenAI

from app.providers.base import LLMProvider, LLMResponse

_BASE_URL = "https://api.deepseek.com"
_WRITER_MODEL = "deepseek-v4-pro"
_JUDGE_MODEL = "deepseek-v4-flash"

_MAX_TOKENS_WRITER = 8192
_MAX_TOKENS_JUDGE = 1024


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
    ) -> LLMResponse:
        is_judge = json_schema is not None
        model = self._judge_model if is_judge else self._writer_model
        max_tokens = _MAX_TOKENS_JUDGE if is_judge else _MAX_TOKENS_WRITER

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
