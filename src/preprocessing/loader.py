"""File and image validation, and safe decoding.

This module answers one question: **can this file be trusted as an image?** It never
attempts to repair anything. A truncated JPEG is reported as truncated, not silently
padded out to full size - a partially-decoded research photograph that looks fine is
worse than one that loudly fails, because the missing region could be the inscription.

Issue codes are ``P*`` (preprocessing). They are engineering checks on files, parallel
to the ``E*`` checks in ``src/dataset/validation.py``, and equally not archaeological
claims.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageFile, UnidentifiedImageError

# Explicit and load-bearing: Pillow must refuse to decode a truncated file rather
# than return a partially-filled image. This is the "do not silently repair" rule.
ImageFile.LOAD_TRUNCATED_IMAGES = False

Severity = Literal["error", "warning", "info"]

#: Extension -> the Pillow format we expect the bytes to actually be.
EXTENSION_FORMATS: dict[str, str] = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".jpe": "JPEG",
    ".png": "PNG",
    ".tif": "TIFF",
    ".tiff": "TIFF",
    ".bmp": "BMP",
    ".webp": "WEBP",
}

#: Formats Pillow reports that are variants of a supported format (Milestone 6).
#: MPO ("multi-picture object") is a baseline JPEG, written by many cameras, with extra
#: frames (previews, stereo pairs) appended. Pillow decodes the primary frame by default,
#: which is the photograph; the extra frames are ignored and an info issue records that.
FORMAT_ALIASES: dict[str, str] = {"MPO": "JPEG"}

ISSUE_TITLES: dict[str, str] = {
    "P1": "file exists, is a regular file, and is non-empty",
    "P2": "image format is supported",
    "P3": "image decodes without error",
    "P4": "image is not oversized beyond the decompression-bomb limit",
    "P5": "image meets the minimum dimension",
    "P6": "colour mode is convertible to RGB",
    "P7": "extension matches the actual file format",
    "P8": "output never overwrites a raw research image",
}


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Severity
    message: str
    detail: str | None = None

    def __str__(self) -> str:
        tail = f" ({self.detail})" if self.detail else ""
        return f"[{self.severity.upper():7}] {self.code}: {self.message}{tail}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "detail": self.detail,
        }


@dataclass
class LoadedImage:
    """A decoded image plus the facts about the file it came from."""

    path: Path
    image: Image.Image | None
    ok: bool
    issues: list[Issue] = dc_field(default_factory=list)
    file_size_bytes: int = 0
    sha256: str | None = None
    detected_format: str | None = None
    original_mode: str | None = None
    original_size: tuple[int, int] | None = None
    exif_orientation: int | None = None
    has_alpha: bool = False

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    def source_facts(self) -> dict[str, Any]:
        """Everything about the source file, for the provenance sidecar."""
        return {
            "source_path": self.path.as_posix(),
            "source_sha256": self.sha256,
            "source_file_size_bytes": self.file_size_bytes,
            "source_format": self.detected_format,
            "source_mode": self.original_mode,
            "source_width_px": self.original_size[0] if self.original_size else None,
            "source_height_px": self.original_size[1] if self.original_size else None,
            "source_exif_orientation": self.exif_orientation,
            "source_has_alpha": self.has_alpha,
        }


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def load_image(
    path: Path | str,
    *,
    supported_formats: set[str] | None = None,
    min_dimension_px: int = 32,
    max_pixels: int | None = None,
    compute_hash: bool = True,
) -> LoadedImage:
    """Validate and decode one image file.

    Returns a :class:`LoadedImage` whose ``ok`` flag says whether the image may be
    used. Failures are reported, never worked around.
    """
    path = Path(path)
    supported = supported_formats or set(EXTENSION_FORMATS.values())
    result = LoadedImage(path=path, image=None, ok=False)

    # -- P1: the file itself ------------------------------------------------
    if not path.exists():
        result.issues.append(Issue("P1", "error", "file does not exist", str(path)))
        return result
    if not path.is_file():
        result.issues.append(Issue("P1", "error", "path is not a regular file", str(path)))
        return result

    result.file_size_bytes = path.stat().st_size
    if result.file_size_bytes == 0:
        result.issues.append(Issue("P1", "error", "file is empty (0 bytes)", str(path)))
        return result

    if compute_hash:
        result.sha256 = sha256_file(path)

    # -- P3/P4: does it decode at all? --------------------------------------
    # verify() consumes the file object, so the image must be reopened to use it.
    previous_limit = Image.MAX_IMAGE_PIXELS
    if max_pixels is not None:
        Image.MAX_IMAGE_PIXELS = max_pixels
    try:
        try:
            with Image.open(path) as probe:
                result.detected_format = probe.format
                result.original_mode = probe.mode
                result.original_size = probe.size
                probe.verify()
        except UnidentifiedImageError:
            result.issues.append(
                Issue("P2", "error", "not a recognised image format",
                      f"{path.name}: Pillow could not identify the contents")
            )
            return result
        except Image.DecompressionBombError as exc:
            result.issues.append(Issue("P4", "error", "image exceeds the pixel limit", str(exc)))
            return result
        except (OSError, SyntaxError, ValueError) as exc:
            result.issues.append(
                Issue("P3", "error", "image is corrupted or truncated", f"{type(exc).__name__}: {exc}")
            )
            return result

        # -- P2: supported format --------------------------------------------
        base_format = FORMAT_ALIASES.get(result.detected_format or "", result.detected_format)
        if base_format != result.detected_format:
            result.issues.append(
                Issue("P2", "info",
                      f"{result.detected_format} is a {base_format} variant; the primary frame "
                      "is used and any additional frames are ignored")
            )
        if base_format not in supported:
            result.issues.append(
                Issue("P2", "error",
                      f"format {result.detected_format!r} is not supported",
                      f"supported: {', '.join(sorted(supported))}")
            )
            return result

        # -- P7: extension honesty (warning, not an error) --------------------
        expected = EXTENSION_FORMATS.get(path.suffix.lower())
        if expected and expected != base_format:
            result.issues.append(
                Issue("P7", "warning",
                      f"extension says {expected} but the file is {result.detected_format}",
                      "the file was still read using its real format")
            )
        elif expected is None:
            result.issues.append(
                Issue("P7", "warning",
                      f"unrecognised extension {path.suffix!r}",
                      f"content is {result.detected_format}")
            )

        # -- actually decode --------------------------------------------------
        try:
            with Image.open(path) as opened:
                opened.load()
                image = opened.copy()
                exif_tag = None
                try:
                    exif = opened.getexif()
                    exif_tag = exif.get(0x0112)  # Orientation
                except Exception:  # noqa: BLE001 - malformed EXIF must not fail the load
                    exif_tag = None
        except Image.DecompressionBombError as exc:
            result.issues.append(Issue("P4", "error", "image exceeds the pixel limit", str(exc)))
            return result
        except (OSError, SyntaxError, ValueError) as exc:
            result.issues.append(
                Issue("P3", "error", "image could not be decoded",
                      f"{type(exc).__name__}: {exc}")
            )
            return result
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit

    result.image = image
    result.original_mode = image.mode
    result.original_size = image.size
    result.exif_orientation = int(exif_tag) if isinstance(exif_tag, int) else None
    result.has_alpha = image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info

    # -- P5: minimum dimension ---------------------------------------------
    width, height = image.size
    if min(width, height) < min_dimension_px:
        result.issues.append(
            Issue("P5", "error",
                  f"smallest dimension {min(width, height)}px is below the "
                  f"{min_dimension_px}px floor",
                  f"{width}x{height}")
        )
        return result

    # -- P6: convertible colour mode ----------------------------------------
    if image.mode not in CONVERTIBLE_MODES:
        result.issues.append(
            Issue("P6", "error", f"colour mode {image.mode!r} is not supported",
                  f"supported: {', '.join(sorted(CONVERTIBLE_MODES))}")
        )
        return result

    result.ok = True
    return result


#: Modes the transform layer knows how to turn into 8-bit RGB.
CONVERTIBLE_MODES: frozenset[str] = frozenset(
    {"1", "L", "LA", "P", "PA", "RGB", "RGBA", "CMYK", "YCbCr", "I", "I;16", "I;16B", "F"}
)


__all__ = [
    "CONVERTIBLE_MODES",
    "EXTENSION_FORMATS",
    "ISSUE_TITLES",
    "Issue",
    "LoadedImage",
    "load_image",
    "sha256_file",
]
