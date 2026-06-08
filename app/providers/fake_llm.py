"""FakeLLMProvider — deterministic, offline LLM for tests and local dev."""
from collections import deque

from app.providers.base import LLMProvider, LLMResponse

_DEFAULT_TEXT = "This is a fake LLM response."
_DEFAULT_JSON = "{}"


class FakeLLMProvider(LLMProvider):
    """Returns queued responses in order; falls back to a default when the queue is empty.

    Usage in tests:
        provider = FakeLLMProvider(responses=["first reply", "second reply"])
        # or push after construction:
        provider.push('{"key": "value"}')
    """

    def __init__(self, responses: list[str] | None = None) -> None:
        self._queue: deque[str] = deque(responses or [])
        self.calls: list[dict] = []

    def push(self, response: str) -> None:
        """Enqueue a response to be returned on the next generate() call."""
        self._queue.append(response)

    def generate(self, system: str, messages: list, *, json_schema: dict | None = None) -> LLMResponse:
        self.calls.append({"system": system, "messages": messages, "json_schema": json_schema})
        if self._queue:
            content = self._queue.popleft()
        elif json_schema is not None:
            content = _DEFAULT_JSON
        else:
            content = _DEFAULT_TEXT
        return LLMResponse(content=content, model="fake", input_tokens=0, output_tokens=0)
