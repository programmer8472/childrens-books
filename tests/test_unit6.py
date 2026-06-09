"""Unit 6 tests: DeepSeekLLMProvider + factory wiring.

All offline — the OpenAI client is mocked; no DEEPSEEK_API_KEY required.

Strategy:
  - Patch `app.providers.deepseek_llm.OpenAI` so no real HTTP calls are made.
  - Configure the mock stream to support the `with ... as stream:` context
    manager pattern used by the openai SDK's `.stream()` helper.
  - Verify model routing (writer → deepseek-v4-pro, judge → deepseek-v4-flash),
    token limits, and LLMResponse field population.
  - Verify factory instantiates DeepSeekLLMProvider for name "deepseek" and
    raises ValueError for unknown names.
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.providers.deepseek_llm import (
    _JUDGE_MODEL,
    _MAX_TOKENS_JUDGE,
    _MAX_TOKENS_WRITER,
    _WRITER_MODEL,
    DeepSeekLLMProvider,
)
from app.providers.base import LLMResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(text: str = "story text", model: str = "deepseek-v4-pro"):
    """Return (mock_client, mock_stream, mock_completion) wired for one call."""
    mock_completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        model=model,
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
    )
    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.get_final_completion.return_value = mock_completion

    mock_client = MagicMock()
    mock_client.chat.completions.stream.return_value = mock_stream

    return mock_client, mock_stream, mock_completion


def _patched_provider(**kwargs):
    """Instantiate DeepSeekLLMProvider with DEEPSEEK_API_KEY set and OpenAI mocked."""
    mock_client, mock_stream, mock_completion = _make_mock_client(**kwargs)
    patch_openai = patch("app.providers.deepseek_llm.OpenAI", return_value=mock_client)
    patch_env = patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"})
    return mock_client, mock_stream, mock_completion, patch_openai, patch_env


# ---------------------------------------------------------------------------
# DeepSeekLLMProvider: model routing
# ---------------------------------------------------------------------------


class TestModelRouting:
    def test_writer_call_uses_writer_model(self):
        mock_client, _, _, po, pe = _patched_provider(model=_WRITER_MODEL)
        with po, pe:
            provider = DeepSeekLLMProvider()
            provider.generate("sys", [{"role": "user", "content": "write a story"}])
        _, kwargs = mock_client.chat.completions.stream.call_args
        assert kwargs["model"] == _WRITER_MODEL

    def test_judge_call_uses_judge_model(self):
        mock_client, _, _, po, pe = _patched_provider(model=_JUDGE_MODEL)
        with po, pe:
            provider = DeepSeekLLMProvider()
            provider.generate(
                "sys",
                [{"role": "user", "content": "judge this"}],
                json_schema={"type": "object"},
            )
        _, kwargs = mock_client.chat.completions.stream.call_args
        assert kwargs["model"] == _JUDGE_MODEL

    def test_system_prepended_as_first_message(self):
        mock_client, _, _, po, pe = _patched_provider()
        with po, pe:
            provider = DeepSeekLLMProvider()
            provider.generate("be creative", [{"role": "user", "content": "write"}])
        _, kwargs = mock_client.chat.completions.stream.call_args
        assert kwargs["messages"][0] == {"role": "system", "content": "be creative"}

    def test_user_messages_follow_system(self):
        mock_client, _, _, po, pe = _patched_provider()
        user_msgs = [{"role": "user", "content": "tell me a story"}]
        with po, pe:
            provider = DeepSeekLLMProvider()
            provider.generate("sys", user_msgs)
        _, kwargs = mock_client.chat.completions.stream.call_args
        assert kwargs["messages"][1:] == user_msgs


# ---------------------------------------------------------------------------
# DeepSeekLLMProvider: token limits
# ---------------------------------------------------------------------------


class TestTokenLimits:
    def test_writer_max_tokens_greater_than_judge(self):
        assert _MAX_TOKENS_WRITER > _MAX_TOKENS_JUDGE

    def test_writer_call_uses_writer_max_tokens(self):
        mock_client, _, _, po, pe = _patched_provider()
        with po, pe:
            provider = DeepSeekLLMProvider()
            provider.generate("sys", [{"role": "user", "content": "write"}])
        _, kwargs = mock_client.chat.completions.stream.call_args
        assert kwargs["max_tokens"] == _MAX_TOKENS_WRITER

    def test_judge_call_uses_judge_max_tokens(self):
        mock_client, _, _, po, pe = _patched_provider(model=_JUDGE_MODEL)
        with po, pe:
            provider = DeepSeekLLMProvider()
            provider.generate(
                "sys",
                [{"role": "user", "content": "judge"}],
                json_schema={"type": "object"},
            )
        _, kwargs = mock_client.chat.completions.stream.call_args
        assert kwargs["max_tokens"] == _MAX_TOKENS_JUDGE


# ---------------------------------------------------------------------------
# DeepSeekLLMProvider: LLMResponse population
# ---------------------------------------------------------------------------


class TestResponsePopulation:
    def test_returns_llm_response(self):
        mock_client, _, _, po, pe = _patched_provider(text="hello world")
        with po, pe:
            provider = DeepSeekLLMProvider()
            result = provider.generate("sys", [{"role": "user", "content": "hi"}])
        assert isinstance(result, LLMResponse)

    def test_content_from_completion(self):
        mock_client, _, _, po, pe = _patched_provider(text="Once upon a time")
        with po, pe:
            provider = DeepSeekLLMProvider()
            result = provider.generate("sys", [{"role": "user", "content": "write"}])
        assert result.content == "Once upon a time"

    def test_model_field_comes_from_response(self):
        mock_client, _, _, po, pe = _patched_provider(model="deepseek-v4-pro-some-hash")
        with po, pe:
            provider = DeepSeekLLMProvider()
            result = provider.generate("sys", [{"role": "user", "content": "write"}])
        assert result.model == "deepseek-v4-pro-some-hash"

    def test_input_tokens_from_prompt_tokens(self):
        mock_client, _, _, po, pe = _patched_provider()
        with po, pe:
            provider = DeepSeekLLMProvider()
            result = provider.generate("sys", [{"role": "user", "content": "write"}])
        assert result.input_tokens == 100

    def test_output_tokens_from_completion_tokens(self):
        mock_client, _, _, po, pe = _patched_provider()
        with po, pe:
            provider = DeepSeekLLMProvider()
            result = provider.generate("sys", [{"role": "user", "content": "write"}])
        assert result.output_tokens == 50

    def test_none_content_becomes_empty_string(self):
        mock_client, mock_stream, mock_completion, po, pe = _patched_provider()
        mock_completion.choices[0].message.content = None
        with po, pe:
            provider = DeepSeekLLMProvider()
            result = provider.generate("sys", [{"role": "user", "content": "write"}])
        assert result.content == ""


# ---------------------------------------------------------------------------
# DeepSeekLLMProvider: custom model injection
# ---------------------------------------------------------------------------


class TestCustomModels:
    def test_custom_writer_model_used(self):
        mock_client, _, _, po, pe = _patched_provider(model="custom-writer")
        with po, pe:
            provider = DeepSeekLLMProvider(writer_model="custom-writer")
            provider.generate("sys", [{"role": "user", "content": "write"}])
        _, kwargs = mock_client.chat.completions.stream.call_args
        assert kwargs["model"] == "custom-writer"

    def test_custom_judge_model_used(self):
        mock_client, _, _, po, pe = _patched_provider(model="custom-judge")
        with po, pe:
            provider = DeepSeekLLMProvider(judge_model="custom-judge")
            provider.generate(
                "sys",
                [{"role": "user", "content": "judge"}],
                json_schema={"type": "object"},
            )
        _, kwargs = mock_client.chat.completions.stream.call_args
        assert kwargs["model"] == "custom-judge"


# ---------------------------------------------------------------------------
# Factory wiring
# ---------------------------------------------------------------------------


class TestFactory:
    def test_deepseek_name_returns_deepseek_provider(self):
        mock_settings = MagicMock()
        mock_settings.llm_provider = "deepseek"
        mock_client, _, _, po, pe = _patched_provider()
        with (
            patch("app.providers.factory.get_settings", return_value=mock_settings),
            po,
            pe,
        ):
            from app.providers.factory import get_llm_provider
            provider = get_llm_provider()
        assert isinstance(provider, DeepSeekLLMProvider)

    def test_fake_name_returns_fake_provider(self):
        from app.providers.fake_llm import FakeLLMProvider
        mock_settings = MagicMock()
        mock_settings.llm_provider = "fake"
        with patch("app.providers.factory.get_settings", return_value=mock_settings):
            from app.providers.factory import get_llm_provider
            provider = get_llm_provider()
        assert isinstance(provider, FakeLLMProvider)

    def test_unknown_name_raises_value_error(self):
        mock_settings = MagicMock()
        mock_settings.llm_provider = "anthropic"
        with (
            patch("app.providers.factory.get_settings", return_value=mock_settings),
            pytest.raises(ValueError, match="anthropic"),
        ):
            from app.providers.factory import get_llm_provider
            get_llm_provider()

    def test_error_message_mentions_factory_file(self):
        mock_settings = MagicMock()
        mock_settings.llm_provider = "bogus"
        with (
            patch("app.providers.factory.get_settings", return_value=mock_settings),
            pytest.raises(ValueError, match="factory.py"),
        ):
            from app.providers.factory import get_llm_provider
            get_llm_provider()
