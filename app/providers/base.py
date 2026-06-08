"""Abstract provider interfaces and shared data types.

No vendor SDK is ever imported here or in any caller. Swap implementations via config.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int


@dataclass
class CharacterRef:
    """Abstracts over reference images (v1) and trained model handles (future).

    kind="reference_images": data={"storage_keys": [...]}
    kind="trained_model":    data={"model_id": "..."}
    """
    kind: str
    data: dict = field(default_factory=dict)


@dataclass
class ImageResult:
    storage_key: str
    seed: str | None
    provider_params: dict = field(default_factory=dict)


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system: str, messages: list, *, json_schema: dict | None = None) -> LLMResponse:
        """Call the LLM and return its response.

        Pass json_schema to request structured JSON output (vendor-specific enforcement).
        """
        ...


class ImageProvider(ABC):
    @abstractmethod
    def generate_scene(self, scene_prompt: str, character_ref: CharacterRef, params: dict) -> ImageResult:
        """Generate a scene illustration and return its stored location."""
        ...
