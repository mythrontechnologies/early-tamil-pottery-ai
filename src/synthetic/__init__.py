"""Synthetic engineering dataset (Milestone 9): constants, the label mapping, and separation guards.

    SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE

The synthetic dataset exists solely for engineering and model-pipeline validation. It must
not be interpreted as archaeological evidence or used to make claims about real Tamil Nadu
pottery. Every image is drawn by a procedural generator (``src.synthetic.generator``); no
pixel comes from a photograph, and no mark reproduces a historical inscription.

Separation is enforced in code, not by convention:

* synthetic files live only under ``data/synthetic/`` (or a temporary directory), never under
  ``data/raw``, ``data/external``, ``data/interim``, ``data/processed`` or ``data/metadata``
  (:func:`assert_synthetic_destination`);
* synthetic checkpoints, experiments and reports live only under ``models/synthetic/``
  (:func:`assert_synthetic_model_destination`);
* every synthetic identifier starts with ``SYNTH-`` and every record carries
  ``dataset_type: synthetic`` and :data:`MARKER`; :func:`synthetic_reasons` recognises a
  synthetic record wherever it turns up, and the research validator (rule ``E6``), the
  annotation validator (rule ``N17``) and label promotion refuse one;
* synthetic class labels are a separate vocabulary (:data:`SYNTHETIC_LABELS`). They share the
  classifier's four output slots through :data:`ARCHITECTURE_SLOTS`, which is a statement
  about tensor shape only; it never gives a synthetic label the meaning of a real one.

This module imports only the standard library and ``src.dataset.schema`` so that the research
validators can use the guards without pulling in the generator or torch.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.dataset.schema import ROOT

DATASET_TYPE = "synthetic"
MARKER = "SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE"
LABEL_WARNING = "Synthetic task label — not archaeological evidence."
PURPOSE = ("The synthetic dataset exists solely for engineering and model-pipeline validation. It must not be "
           "interpreted as archaeological evidence or used to make claims about real Tamil Nadu pottery.")
TRAINING_BANNER = "SYNTHETIC TRAINING — NOT ARCHAEOLOGICAL MODEL EVALUATION"
EVALUATION_BANNER = "SYNTHETIC DATA ONLY — NOT ARCHAEOLOGICAL PERFORMANCE"
ROBUSTNESS_NOTE = "Synthetic robustness is not archaeological robustness."
UI_BANNER = "Synthetic demonstration — not archaeological evidence"
OCR_BENCHMARK_NAME = "Synthetic glyph recognition benchmark"

SOURCE = "synthetic_generator"
LABEL_SOURCE = "synthetic_ground_truth"
ID_PREFIX = "SYNTH-"

#: Synthetic VISUAL TASK categories. They mean "which kind of procedural mark the generator
#: drew", nothing more: not verified Tamil-Brahmi, not verified graffiti.
SYNTHETIC_LABELS: tuple[str, ...] = (
    "synthetic_tamil_brahmi_like",
    "synthetic_graffiti_like",
    "synthetic_none",
    "synthetic_uncertain",
)

#: The controlled mapping layer. A synthetic label occupies the same classifier OUTPUT SLOT
#: (index) as the real class named here, so the unchanged 4-way architecture can be exercised.
#: This is a statement about tensor positions only. Checkpoints store the SYNTHETIC names, so a
#: synthetic model can never be loaded as a model of the real classes (the class-list check
#: refuses it), and the real labels keep exactly their schema meaning.
ARCHITECTURE_SLOTS: dict[str, str] = {
    "synthetic_tamil_brahmi_like": "tamil_brahmi",
    "synthetic_graffiti_like": "graffiti",
    "synthetic_none": "none",
    "synthetic_uncertain": "uncertain",
}

SYNTHETIC_ROOT = ROOT / "data" / "synthetic"
IMAGES_DIR = SYNTHETIC_ROOT / "images"
METADATA_DIR = SYNTHETIC_ROOT / "metadata"
SPLITS_DIR = SYNTHETIC_ROOT / "splits"
MANIFESTS_DIR = SYNTHETIC_ROOT / "manifests"
RECORDS_PATH = METADATA_DIR / "records.jsonl"
PROVENANCE_PATH = MANIFESTS_DIR / "provenance.jsonl"
LOCK_PATH = MANIFESTS_DIR / "dataset_lock.json"
SCHEMA_PATH = Path(__file__).with_name("synthetic_record.schema.json")

SYNTHETIC_MODELS_ROOT = ROOT / "models" / "synthetic"
DATASET_CONFIG_PATH = ROOT / "configs" / "synthetic_dataset.yaml"
TRAINING_CONFIG_PATH = ROOT / "configs" / "synthetic_training.yaml"

#: Real-data locations a synthetic file may never be written into.
PROTECTED_DATA_DIRS: tuple[Path, ...] = tuple(ROOT / "data" / d for d in
                                              ("raw", "external", "interim", "processed", "metadata"))
#: Real-model locations a synthetic checkpoint, experiment or report may never be written into.
PROTECTED_MODEL_DIRS: tuple[Path, ...] = (ROOT / "models" / "checkpoints", ROOT / "models" / "experiments")


class SyntheticSeparationError(RuntimeError):
    """Synthetic data would cross into the research data, the research models or the evidence stores."""


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def assert_synthetic_destination(path: Path | str) -> Path:
    """Refuse to write synthetic data anywhere the research dataset lives.

    Inside ``data/`` only ``data/synthetic/`` is allowed. Outside the project (a temporary
    directory) is allowed, so tests can generate without touching the repository."""
    p = Path(path)
    for protected in PROTECTED_DATA_DIRS:
        if _inside(p, protected):
            raise SyntheticSeparationError(
                f"refusing to write synthetic data into {protected.relative_to(ROOT).as_posix()}/: "
                f"synthetic files belong under data/synthetic/ only ({MARKER})")
    if _inside(p, ROOT / "data") and not _inside(p, SYNTHETIC_ROOT):
        raise SyntheticSeparationError(
            f"refusing to write synthetic data to {p}: inside data/ only data/synthetic/ may hold synthetic files")
    return p


def assert_synthetic_model_destination(path: Path | str) -> Path:
    """Refuse to write a synthetic checkpoint, experiment or report outside ``models/synthetic/``.

    Real-data model directories are always refused; elsewhere inside ``models/`` only
    ``models/synthetic/`` is allowed. Outside the project (a temporary directory) is allowed."""
    p = Path(path)
    for protected in PROTECTED_MODEL_DIRS:
        if _inside(p, protected):
            raise SyntheticSeparationError(
                f"refusing to write a synthetic model artefact into {protected.relative_to(ROOT).as_posix()}/, "
                "which holds archaeological models; use models/synthetic/")
    if _inside(p, ROOT / "models") and not _inside(p, SYNTHETIC_MODELS_ROOT):
        raise SyntheticSeparationError(f"refusing to write a synthetic model artefact to {p}: use models/synthetic/")
    return p


def is_synthetic_id(value: Any) -> bool:
    return isinstance(value, str) and value.upper().startswith(ID_PREFIX)


def synthetic_reasons(record: Mapping[str, Any]) -> list[str]:
    """Why a record (research record, annotation, or anything dict-like) is synthetic. Empty = not synthetic."""
    if not isinstance(record, Mapping):
        return []
    reasons = []
    if record.get("dataset_type") == DATASET_TYPE:
        reasons.append("dataset_type is 'synthetic'")
    for key in ("artifact_id", "image_id", "catalogue_number"):
        if is_synthetic_id(record.get(key)):
            reasons.append(f"{key} {record.get(key)!r} is a synthetic identifier")
    image_ids = record.get("image_ids")
    if isinstance(image_ids, (list, tuple)) and any(is_synthetic_id(i) for i in image_ids):
        reasons.append("image_ids name a synthetic image")
    if record.get("source") == SOURCE or record.get("label_source") == LABEL_SOURCE:
        reasons.append("source/label_source is the synthetic generator")
    path = record.get("image_path")
    if isinstance(path, str) and ("synthetic/" in path.replace("\\", "/").lower() or is_synthetic_id(Path(path).name)):
        reasons.append(f"image_path {path!r} is a synthetic file")
    if isinstance(record.get("script_type"), str) and record["script_type"] in SYNTHETIC_LABELS:
        reasons.append(f"script_type {record['script_type']!r} is a synthetic task label")
    if MARKER in (record.get("synthetic_marker"), record.get("notes")):
        reasons.append("carries the synthetic marker")
    return reasons


def is_synthetic_record(record: Mapping[str, Any]) -> bool:
    return bool(synthetic_reasons(record))


__all__ = [
    "ARCHITECTURE_SLOTS",
    "DATASET_CONFIG_PATH",
    "DATASET_TYPE",
    "EVALUATION_BANNER",
    "ID_PREFIX",
    "IMAGES_DIR",
    "LABEL_SOURCE",
    "LABEL_WARNING",
    "LOCK_PATH",
    "MANIFESTS_DIR",
    "MARKER",
    "METADATA_DIR",
    "OCR_BENCHMARK_NAME",
    "PROTECTED_DATA_DIRS",
    "PROTECTED_MODEL_DIRS",
    "PROVENANCE_PATH",
    "PURPOSE",
    "RECORDS_PATH",
    "ROBUSTNESS_NOTE",
    "SCHEMA_PATH",
    "SOURCE",
    "SPLITS_DIR",
    "SYNTHETIC_LABELS",
    "SYNTHETIC_MODELS_ROOT",
    "SYNTHETIC_ROOT",
    "TRAINING_BANNER",
    "TRAINING_CONFIG_PATH",
    "UI_BANNER",
    "SyntheticSeparationError",
    "assert_synthetic_destination",
    "assert_synthetic_model_destination",
    "is_synthetic_id",
    "is_synthetic_record",
    "synthetic_reasons",
]
