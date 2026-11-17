from __future__ import annotations

import io
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError

# §39: uploads/ is a top-level directory, separate from app/static.
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "backgrounds"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
_EXTENSION_FOR_FORMAT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
_MAX_DIMENSION = 2560
_MAX_UPLOAD_BYTES = 8 * 1024 * 1024


class InvalidImageError(Exception):
    pass


def save_background(raw: bytes) -> str:
    """Validate, downscale if needed, and store an uploaded background image.

    Returns the URL path to serve it from. Format is verified via Pillow
    (not just the filename extension) -- §26 requires JPG/JPEG/PNG/WEBP.
    """
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise InvalidImageError("Fajl je prevelik (maksimum 8MB)")

    try:
        probe = Image.open(io.BytesIO(raw))
        probe.verify()
        image = Image.open(io.BytesIO(raw))  # verify() consumes the parser; reopen to actually use it
    except (UnidentifiedImageError, OSError):
        raise InvalidImageError("Fajl nije validna slika") from None

    if image.format not in _ALLOWED_FORMATS:
        raise InvalidImageError(f"Nepodržan format: {image.format} (dozvoljeno: JPG, PNG, WEBP)")

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")

    if max(image.size) > _MAX_DIMENSION:
        image.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION), Image.LANCZOS)

    ext = _EXTENSION_FOR_FORMAT[image.format]
    filename = f"background-{uuid.uuid4().hex}.{ext}"
    save_kwargs = {"quality": 85, "optimize": True} if image.format == "JPEG" else {}
    image.save(UPLOAD_DIR / filename, format=image.format, **save_kwargs)

    return f"/uploads/backgrounds/{filename}"


def delete_background(url: str | None) -> None:
    if not url or not url.startswith("/uploads/backgrounds/"):
        return
    path = UPLOAD_DIR / url.rsplit("/", 1)[-1]
    if path.is_file():
        path.unlink()
