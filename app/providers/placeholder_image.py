"""PlaceholderImageProvider — generates labeled rectangles at correct spread dimensions.

Intended for use before a real image API key is available. Drop-in replacement:
set IMAGE_PROVIDER to the real provider name and re-run the GENERATING_IMAGES
pipeline stage — all placeholders are replaced with real illustrations, no code
changes required.
"""
import io
import textwrap
import uuid

from PIL import Image, ImageDraw, ImageFont

from app.providers.base import CharacterRef, ImageProvider, ImageResult
from app.storage.local import LocalStorage

_DPI = 300

# Pixel dimensions at 300 DPI. Source: book-design-spec.md.
# Full single page with bleed: 8.75" × 8.75" = 2625 × 2625 px.
# Double spread with bleed: 17.25" × 8.75" = 5175 × 2625 px.
_SPREAD_DIMS: dict[str, tuple[int, int]] = {
    "FULL_BLEED_DOUBLE":                (5175, 2625),
    "FULL_BLEED_SINGLE_WITH_TEXT_PAGE": (2625, 2625),
    "FULL_BLEED_SINGLE_OVERLAY":        (2625, 2625),
    "PORTRAIT_WITH_CAPTION_BELOW":      (2625, 1838),  # illustration area = top 70% of page
    "VIGNETTE":                         (1838, 1838),  # floating ~70% of page width/height
    "COVER":                            (2625, 2625),
}
_DEFAULT_DIMS = (2625, 2625)

_BG        = (215, 223, 232)
_BORDER    = (90,  110, 130)
_HEADER_BG = (50,  100, 160)
_HEADER_FG = (255, 255, 255)
_BODY_FG   = (25,  35,  45)
_BORDER_W  = 18
_HEADER_H  = 130


def _font(size: int):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


class PlaceholderImageProvider(ImageProvider):
    """Renders gray rectangle placeholders at correct spread dimensions.

    Swap to a real provider by changing IMAGE_PROVIDER in .env and re-running
    the GENERATING_IMAGES stage — no code changes required.
    """

    def __init__(self, storage: LocalStorage) -> None:
        self._storage = storage

    def generate_scene(
        self, scene_prompt: str, character_ref: CharacterRef, params: dict
    ) -> ImageResult:
        spread_type = params.get("spread_type", "")
        w, h = _SPREAD_DIMS.get(spread_type, _DEFAULT_DIMS)

        img = _render(w, h, spread_type, scene_prompt, character_ref)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, dpi=(_DPI, _DPI))

        key = f"placeholders/{uuid.uuid4().hex}.jpg"
        self._storage.put(key, buf.getvalue())

        return ImageResult(storage_key=key, seed=None, provider_params=params)


def _render(
    w: int,
    h: int,
    spread_type: str,
    scene_prompt: str,
    character_ref: CharacterRef,
) -> Image.Image:
    img = Image.new("RGB", (w, h), _BG)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, w - 1, h - 1], outline=_BORDER, width=_BORDER_W)

    hdr_y1 = _BORDER_W
    hdr_y2 = _BORDER_W + _HEADER_H
    draw.rectangle([_BORDER_W, hdr_y1, w - _BORDER_W, hdr_y2], fill=_HEADER_BG)

    hdr_font = _font(52)
    label = f"PLACEHOLDER  ·  {spread_type or 'UNKNOWN'}  ·  {w} × {h} px @ 300 dpi"
    draw.text((_BORDER_W + 24, hdr_y1 + 28), label, font=hdr_font, fill=_HEADER_FG)

    body_font = _font(44)
    tx = _BORDER_W + 40
    ty = hdr_y2 + 40
    usable_w = w - tx - _BORDER_W - 40
    try:
        char_w = (draw.textbbox((0, 0), "x" * 10, font=body_font)[2]) / 10
    except Exception:
        char_w = 26
    wrapped = textwrap.fill(scene_prompt, width=max(20, int(usable_w / char_w)))
    draw.multiline_text((tx, ty), wrapped, font=body_font, fill=_BODY_FG, spacing=18)

    if character_ref.data:
        ref_font = _font(36)
        ref_text = f"character_ref · kind={character_ref.kind!r} · {character_ref.data}"
        draw.text((_BORDER_W + 24, h - _BORDER_W - 60), ref_text, font=ref_font, fill=_BORDER)

    return img
