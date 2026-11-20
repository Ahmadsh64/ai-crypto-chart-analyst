"""Screenshot upload validation — content-based, no persistent storage."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from app.core.config import Settings


ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}
FORMAT_TO_MIME = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}


class ImageValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ValidatedImage:
    content_type: str
    width: int
    height: int
    format: str
    size_bytes: int
    png_bytes: bytes  # normalized PNG for provider calls


def validate_image_bytes(data: bytes, settings: Settings) -> ValidatedImage:
    max_bytes = int(settings.max_upload_size_mb * 1024 * 1024)
    if not data:
        raise ImageValidationError("EMPTY_IMAGE", "Uploaded image is empty.")
    if len(data) > max_bytes:
        raise ImageValidationError(
            "IMAGE_TOO_LARGE",
            f"Image exceeds maximum size of {settings.max_upload_size_mb} MB.",
        )

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            fmt = (img.format or "").upper()
            if fmt not in ALLOWED_FORMATS:
                raise ImageValidationError(
                    "UNSUPPORTED_FORMAT",
                    f"Unsupported image format {fmt or 'unknown'}. Allowed: PNG, JPEG, WebP.",
                )
            # Normalize orientation via EXIF when present.
            try:
                from PIL import ImageOps

                img = ImageOps.exif_transpose(img)
            except Exception:  # noqa: BLE001
                pass

            width, height = img.size
            if width < settings.min_image_width or height < settings.min_image_height:
                raise ImageValidationError(
                    "IMAGE_TOO_SMALL",
                    f"Image dimensions {width}x{height} below minimum "
                    f"{settings.min_image_width}x{settings.min_image_height}.",
                )
            if width > settings.max_image_width or height > settings.max_image_height:
                raise ImageValidationError(
                    "IMAGE_DIMENSIONS_TOO_LARGE",
                    f"Image dimensions {width}x{height} exceed maximum "
                    f"{settings.max_image_width}x{settings.max_image_height}.",
                )

            # Re-encode to PNG (strips untrusted metadata for provider payload).
            out = io.BytesIO()
            rgb = img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img
            if rgb.mode == "RGBA":
                rgb.save(out, format="PNG", optimize=True)
            else:
                rgb.convert("RGB").save(out, format="PNG", optimize=True)
            png_bytes = out.getvalue()
            return ValidatedImage(
                content_type=FORMAT_TO_MIME[fmt],
                width=width,
                height=height,
                format=fmt,
                size_bytes=len(data),
                png_bytes=png_bytes,
            )
    except ImageValidationError:
        raise
    except UnidentifiedImageError as exc:
        raise ImageValidationError(
            "CORRUPTED_IMAGE",
            "Image could not be decoded. File may be corrupted or not an image.",
        ) from exc
    except OSError as exc:
        raise ImageValidationError(
            "CORRUPTED_IMAGE",
            "Image could not be decoded. File may be corrupted or not an image.",
        ) from exc
