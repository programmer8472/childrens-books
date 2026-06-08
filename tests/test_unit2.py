"""Unit 2 tests: provider interfaces and fake implementations.

All offline — no DB, no network, no API keys.
"""
import pytest

from app.providers import (
    CharacterRef,
    FakeImageProvider,
    FakeLLMProvider,
    ImageProvider,
    ImageResult,
    LLMProvider,
    LLMResponse,
)


class TestInterfaces:
    def test_llm_provider_is_abstract(self):
        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore[abstract]

    def test_image_provider_is_abstract(self):
        with pytest.raises(TypeError):
            ImageProvider()  # type: ignore[abstract]

    def test_fakes_are_subclasses(self):
        assert issubclass(FakeLLMProvider, LLMProvider)
        assert issubclass(FakeImageProvider, ImageProvider)


class TestCharacterRef:
    def test_reference_images_kind(self):
        ref = CharacterRef(kind="reference_images", data={"storage_keys": ["fake/img.png"]})
        assert ref.kind == "reference_images"
        assert ref.data["storage_keys"] == ["fake/img.png"]

    def test_trained_model_kind(self):
        ref = CharacterRef(kind="trained_model", data={"model_id": "lora-abc123"})
        assert ref.kind == "trained_model"

    def test_default_data_is_empty_dict(self):
        ref = CharacterRef(kind="reference_images")
        assert ref.data == {}


class TestFakeLLMProvider:
    def test_returns_llm_response(self):
        provider = FakeLLMProvider()
        result = provider.generate("sys", [{"role": "user", "content": "hi"}])
        assert isinstance(result, LLMResponse)

    def test_default_text_response(self):
        provider = FakeLLMProvider()
        result = provider.generate("sys", [])
        assert result.model == "fake"
        assert isinstance(result.content, str)
        assert len(result.content) > 0

    def test_default_json_response_when_schema_provided(self):
        provider = FakeLLMProvider()
        result = provider.generate("sys", [], json_schema={"type": "object"})
        # Should return valid JSON-ish string, not the plain-text default
        assert result.content == "{}"

    def test_queued_responses_returned_in_order(self):
        provider = FakeLLMProvider(responses=["first", "second", "third"])
        assert provider.generate("s", []).content == "first"
        assert provider.generate("s", []).content == "second"
        assert provider.generate("s", []).content == "third"

    def test_falls_back_to_default_after_queue_exhausted(self):
        provider = FakeLLMProvider(responses=["only one"])
        provider.generate("s", [])  # consume it
        result = provider.generate("s", [])
        assert result.content != "only one"

    def test_push_enqueues_response(self):
        provider = FakeLLMProvider()
        provider.push("pushed response")
        assert provider.generate("s", []).content == "pushed response"

    def test_records_calls(self):
        provider = FakeLLMProvider()
        provider.generate("my system", [{"role": "user", "content": "hello"}])
        assert len(provider.calls) == 1
        assert provider.calls[0]["system"] == "my system"
        assert provider.calls[0]["json_schema"] is None

    def test_records_json_schema_in_call(self):
        provider = FakeLLMProvider()
        schema = {"type": "object", "properties": {"score": {"type": "number"}}}
        provider.generate("s", [], json_schema=schema)
        assert provider.calls[0]["json_schema"] == schema

    def test_multiple_calls_accumulated(self):
        provider = FakeLLMProvider()
        provider.generate("s", [])
        provider.generate("s", [])
        assert len(provider.calls) == 2


class TestFakeImageProvider:
    def _make_ref(self) -> CharacterRef:
        return CharacterRef(kind="reference_images", data={"storage_keys": []})

    def test_returns_image_result(self):
        provider = FakeImageProvider()
        result = provider.generate_scene("a sunny meadow", self._make_ref(), {})
        assert isinstance(result, ImageResult)

    def test_default_storage_key_is_fake_path(self):
        provider = FakeImageProvider()
        result = provider.generate_scene("scene", self._make_ref(), {})
        assert result.storage_key.startswith("fake/")
        assert result.storage_key.endswith(".png")

    def test_default_results_are_unique(self):
        provider = FakeImageProvider()
        ref = self._make_ref()
        keys = {provider.generate_scene("s", ref, {}).storage_key for _ in range(5)}
        assert len(keys) == 5

    def test_queued_result_returned(self):
        provider = FakeImageProvider()
        expected = ImageResult(storage_key="custom/scene.png", seed="999", provider_params={})
        provider.push(expected)
        result = provider.generate_scene("s", self._make_ref(), {})
        assert result.storage_key == "custom/scene.png"
        assert result.seed == "999"

    def test_provider_params_echoed_in_default(self):
        provider = FakeImageProvider()
        params = {"width": 1024, "height": 1024}
        result = provider.generate_scene("s", self._make_ref(), params)
        assert result.provider_params == params

    def test_records_calls(self):
        provider = FakeImageProvider()
        ref = self._make_ref()
        provider.generate_scene("a dark forest", ref, {"style": "watercolor"})
        assert len(provider.calls) == 1
        assert provider.calls[0]["scene_prompt"] == "a dark forest"
        assert provider.calls[0]["character_ref"] is ref
        assert provider.calls[0]["params"] == {"style": "watercolor"}
