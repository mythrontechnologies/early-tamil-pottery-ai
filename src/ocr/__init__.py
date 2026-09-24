"""Inscription reading pipeline: enhancement -> mark analysis -> OCR / transcription.

OCR output is an **AI observation**. It is kept apart from epigraphic interpretation: an
expert's reading lives in the annotation store (``inscription.reading``) and reaches the
reasoning layer from there; an OCR string never does. Every result here carries
``provenance = "ai_prediction"`` and is reported under "AI observation" only.

No validated Tamil-Brahmi or graffiti OCR model exists in this project (there is no
expert-labelled character data to train or test one on). The defaults are therefore honest
null stages:

* ``NullMarkAnalyzer`` - no validated mark/character segmenter; reports nothing;
* ``NullTranscriber``  - returns ``"No reliable transcription established."``

A real engine plugs in through the ``Transcriber`` / ``MarkAnalyzer`` protocols. Even then its
text is a candidate for a human to check, never a reading. ``character_error_rate`` in
``src.evaluation.metrics`` is the hook for evaluating one against expert readings.

``enhance`` is deterministic image processing (grayscale + CLAHE + optional inversion) to
help a PERSON see incisions. It changes nothing on disk and is not evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

import cv2
import numpy as np
from PIL import Image, ImageOps

NO_TRANSCRIPTION = "No reliable transcription established."
NO_OCR_ENGINE = ("No validated OCR model for Tamil-Brahmi or pottery graffiti exists in this project; "
                 "no characters were read automatically.")
NO_MARK_ANALYZER = "No validated mark/character segmentation model exists in this project."


@dataclass
class MarkAnalysis:
    status: str                            # no_analyzer | analysed
    statement: str
    marks: list[dict[str, Any]] = field(default_factory=list)
    provenance: str = "ai_prediction"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OCRResult:
    status: str                            # no_engine | no_reliable_transcription | candidate
    statement: str
    text: str | None = None                # a CANDIDATE string only when status == candidate
    confidence: float | None = None        # the engine's own score; not archaeological confidence
    engine: str = "none"
    provenance: str = "ai_prediction"
    is_reading: bool = False               # always False: OCR output is never a reading

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MarkAnalyzer(Protocol):
    name: str

    def analyze(self, crop: Image.Image) -> MarkAnalysis: ...


class Transcriber(Protocol):
    name: str

    def transcribe(self, crop: Image.Image) -> OCRResult: ...


class NullMarkAnalyzer:
    name = "none"

    def analyze(self, crop: Image.Image) -> MarkAnalysis:
        return MarkAnalysis("no_analyzer", NO_MARK_ANALYZER)


class NullTranscriber:
    name = "none"

    def transcribe(self, crop: Image.Image) -> OCRResult:
        return OCRResult("no_engine", f"{NO_TRANSCRIPTION} {NO_OCR_ENGINE}")


def screen_ocr(result: OCRResult, *, min_engine_confidence: float = 0.9) -> OCRResult:
    """Downgrade a weak or empty engine output to 'no reliable transcription'. A candidate
    survives only with non-empty text and an engine score >= ``min_engine_confidence``;
    even then it is marked a candidate for human checking, never a reading."""
    result.is_reading = False
    result.provenance = "ai_prediction"
    if result.status != "candidate":
        return result
    text = (result.text or "").strip()
    if not text or result.confidence is None or result.confidence < min_engine_confidence:
        return OCRResult("no_reliable_transcription",
                         f"{NO_TRANSCRIPTION} (engine output below the reliability threshold "
                         f"{min_engine_confidence}; discarded)", engine=result.engine)
    result.text = text
    result.statement = ("OCR CANDIDATE for human checking only: not a reading, not evidence. "
                        f"Engine {result.engine}, score {result.confidence:.2f}.")
    return result


def enhance(crop: Image.Image, *, clip_limit: float = 2.0, tile: int = 8, invert: bool = False) -> Image.Image:
    """Grayscale + CLAHE (+ optional inversion): a deterministic viewing aid for incisions."""
    gray = np.asarray(ImageOps.grayscale(crop.convert("RGB")), dtype=np.uint8)
    out = cv2.createCLAHE(clipLimit=float(clip_limit), tileGridSize=(tile, tile)).apply(gray)
    img = Image.fromarray(out, mode="L")
    return ImageOps.invert(img) if invert else img


__all__ = ["NO_MARK_ANALYZER", "NO_OCR_ENGINE", "NO_TRANSCRIPTION", "MarkAnalysis", "MarkAnalyzer",
           "NullMarkAnalyzer", "NullTranscriber", "OCRResult", "Transcriber", "enhance", "screen_ocr"]
