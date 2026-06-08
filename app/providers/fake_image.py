"""FakeImageProvider — deterministic, offline image provider for tests and local dev."""
import uuid
from collections import deque

from app.providers.base import CharacterRef, ImageProvider, ImageResult


class FakeImageProvider(ImageProvider):
    """Returns queued results in order; generates a deterministic fake key otherwise.

    Usage in tests:
        provider = FakeImageProvider()
        provider.push(ImageResult(storage_key="fake/scene_0.png", seed="42"))
    """

    def __init__(self, results: list[ImageResult] | None = None) -> None:
        self._queue: deque[ImageResult] = deque(results or [])
        self.calls: list[dict] = []

    def push(self, result: ImageResult) -> None:
        self._queue.append(result)

    def generate_scene(self, scene_prompt: str, character_ref: CharacterRef, params: dict) -> ImageResult:
        self.calls.append({"scene_prompt": scene_prompt, "character_ref": character_ref, "params": params})
        if self._queue:
            return self._queue.popleft()
        return ImageResult(
            storage_key=f"fake/scene_{uuid.uuid4().hex[:8]}.png",
            seed=None,
            provider_params=params,
        )
