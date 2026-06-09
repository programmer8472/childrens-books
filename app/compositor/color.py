"""RGB → CMYK conversion using the bundled SWOP v2 ICC profile.

Spec: book-design-spec.md §Color and print quality.
All illustration images are converted at compositor time so the PDF is fully
CMYK — KDP's auto-conversion from RGB shifts saturated blues and greens.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageCms

_ICC_PATH = Path(__file__).parent / "icc" / "USWebCoatedSWOP.icc"

_srgb_profile: ImageCms.ImageCmsProfile | None = None
_cmyk_profile: ImageCms.ImageCmsProfile | None = None
_transform: ImageCms.ImageCmsTransform | None = None


def _get_transform() -> ImageCms.ImageCmsTransform:
    global _srgb_profile, _cmyk_profile, _transform
    if _transform is None:
        _srgb_profile = ImageCms.createProfile("sRGB")
        _cmyk_profile = ImageCms.getOpenProfile(str(_ICC_PATH))
        _transform = ImageCms.buildTransform(
            _srgb_profile, _cmyk_profile, "RGB", "CMYK",
            renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
        )
    return _transform


def to_cmyk(img: Image.Image) -> Image.Image:
    """Convert a PIL Image to CMYK using the SWOP v2 ICC profile.

    Input may be RGB or RGBA (alpha channel is discarded — flatten to white first
    if the image has meaningful transparency).
    """
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    return ImageCms.applyTransform(img, _get_transform())


def cmyk_profile_bytes() -> bytes:
    """Return the raw ICC profile bytes for embedding in the PDF output intent."""
    return _ICC_PATH.read_bytes()
