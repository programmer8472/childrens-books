"""Provider factory — returns the right implementation based on config.

Add a new elif branch here (and a new class in its own file) when wiring in a real vendor.
Never let provider selection logic leak into agents or orchestrator code.
"""
from app.config import get_settings
from app.providers.base import ImageProvider, LLMProvider
from app.providers.fake_image import FakeImageProvider
from app.providers.fake_llm import FakeLLMProvider


def get_llm_provider() -> LLMProvider:
    name = get_settings().llm_provider
    if name == "fake":
        return FakeLLMProvider()
    raise ValueError(f"Unknown llm_provider '{name}'. Add it to app/providers/factory.py.")


def get_image_provider() -> ImageProvider:
    name = get_settings().image_provider
    if name == "fake":
        return FakeImageProvider()
    raise ValueError(f"Unknown image_provider '{name}'. Add it to app/providers/factory.py.")
