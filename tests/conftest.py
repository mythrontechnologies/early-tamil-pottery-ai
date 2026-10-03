"""Shared test fixtures.

All record data originates from ``tests/fixtures/`` and is synthetic. See
``tests/fixtures/README.md``. Nothing here touches ``data/``.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def _base_record_raw() -> dict[str, Any]:
    return json.loads((FIXTURES / "valid" / "base_record.json").read_text(encoding="utf-8"))


@pytest.fixture
def base_record(_base_record_raw: dict[str, Any]) -> dict[str, Any]:
    """A complete, valid record. Mutating it does not affect other tests."""
    return deepcopy(_base_record_raw)


@pytest.fixture
def make_record(_base_record_raw: dict[str, Any]) -> Callable[..., dict[str, Any]]:
    """Build a variant of the base record.

    Passing ``...`` as a value deletes that field, which is how tests exercise
    missing-field behaviour.
    """

    def _make(**overrides: Any) -> dict[str, Any]:
        record = deepcopy(_base_record_raw)
        for key, value in overrides.items():
            if value is ...:
                record.pop(key, None)
            else:
                record[key] = value
        return record

    return _make


def _script_fields(label: str) -> dict[str, Any]:
    """Field values that keep a synthetic record consistent with rules R5/R6."""
    if label == "none":
        return {"inscription_present": "no", "transcription": "not_applicable",
                "transliteration": "not_applicable", "translation_en": "not_applicable",
                "translation_ta": "not_applicable", "inscription_regions": []}
    if label == "uncertain":
        return {"inscription_present": "uncertain", "inscription_regions": []}
    if label == "other_script":
        return {"inscription_present": "yes", "inscription_regions": [],
                "script_type_other_detail": "FIXTURE_OTHER_SCRIPT_PLACEHOLDER"}
    return {"inscription_present": "yes", "inscription_regions": []}


@pytest.fixture
def synthetic_corpus(_base_record_raw: dict[str, Any]) -> Callable[..., dict[str, Any]]:
    """Write a SYNTHETIC records.jsonl + tiny generated images into a temp directory.

    Everything produced is marked FIXTURE/SYNTHETIC and lives under pytest's tmp_path,
    never under data/. Images are flat-colour squares with a pixel pattern that makes
    every file unique (so hashes differ). They are not photographs of anything.

    Returns ``{"records_path", "data_root", "records"}``.
    """
    import hashlib

    from PIL import Image

    def _build(
        root: Path,
        per_class: dict[str, int],
        *,
        images_per_artifact: int = 1,
        sites: tuple[str, ...] = ("FIXTURE_SITE_A", "FIXTURE_SITE_B"),
        overrides: dict[str, Any] | None = None,
        size: int = 40,
    ) -> dict[str, Any]:
        data_root = root / "raw"
        (data_root / "fixture").mkdir(parents=True, exist_ok=True)
        records: list[dict[str, Any]] = []
        n = 0
        for label, count in per_class.items():
            for a in range(count):
                aid = f"FIXTURE_{label.upper()}_{a:03d}"
                for v in range(images_per_artifact):
                    n += 1
                    iid = f"{aid}__exterior__{v + 1}"
                    rel = f"fixture/{iid}.png"
                    img = Image.new("RGB", (size, size), (40 * (n % 6), 90, 140))
                    img.putpixel((n % size, (n // size) % size), (255, 255, 255))
                    img.putpixel((0, 0), (n % 256, (n // 256) % 256, 7))
                    img.save(data_root / rel)
                    rec = deepcopy(_base_record_raw)
                    rec.update(_script_fields(label))
                    rec.update({
                        "image_id": iid, "artifact_id": aid, "image_path": rel,
                        "image_sha256": hashlib.sha256((data_root / rel).read_bytes()).hexdigest(),
                        "image_width_px": size, "image_height_px": size,
                        "script_type": label, "site": sites[a % len(sites)],
                        "split": "unassigned",
                        "notes": "SYNTHETIC TEST FIXTURE generated in tmp_path. Not data.",
                    })
                    if overrides:
                        rec.update(overrides)
                    records.append(rec)
        records_path = root / "records.jsonl"
        records_path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
        return {"records_path": records_path, "data_root": data_root, "records": records}

    return _build


@pytest.fixture(scope="session")
def live_research() -> dict[str, Any]:
    """The REAL research dataset as it currently stands (read-only).

    Tests that describe the live project state use this instead of assuming the dataset is
    empty, so they stay true as authorised data arrives (Milestone 6 onward).
    """
    from src.acquisition.provenance import read_registry
    from src.dataset.convert import read_jsonl
    from src.dataset.schema import RESEARCH_DATA_ROOT, RESEARCH_RECORDS_PATH

    records = read_jsonl(RESEARCH_RECORDS_PATH) if RESEARCH_RECORDS_PATH.exists() else []
    registry = read_registry()
    return {
        "records": records,
        "artifacts": {r["artifact_id"] for r in records},
        "provenance": {p["image_id"]: p for p in registry},
        "raw_root": RESEARCH_DATA_ROOT,
    }


@pytest.fixture
def load_fixture() -> Callable[[str], list[dict[str, Any]]]:
    """Load a fixture file under ``tests/fixtures/`` by relative path."""

    def _load(relative: str) -> list[dict[str, Any]]:
        path = FIXTURES / relative
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        data = json.loads(text)
        return data if isinstance(data, list) else [data]

    return _load


# --------------------------------------------------------------------------- #
# Synthetic world: unlabelled records (like the real 30) + real image files + a store
# --------------------------------------------------------------------------- #


def _unlabelled(base: dict, aid: str, iid: str, rel: str, sha: str, size: int) -> dict:
    r = deepcopy(base)
    r.update({
        "image_id": iid, "artifact_id": aid, "image_path": rel, "image_sha256": sha,
        "image_width_px": size, "image_height_px": size, "split": "unassigned",
        "context_reliability": "unknown", "stratigraphic_context": "not_available",
        "inscription_present": "unknown", "script_type": "unknown", "label_source": "unknown",
        "label_confidence": "unknown", "inscription_regions": [], "character_count_visible": None,
        "transcription": "not_available", "transcription_encoding": "not_available",
        "transliteration": "not_available", "transliteration_scheme": "not_available",
        "translation_en": "not_available", "translation_ta": "not_available",
        "reading_status": "unknown", "alternative_readings": [], "reading_source": "not_available",
        "dating_text": "not_available", "dating_lower_year": None, "dating_upper_year": None,
        "dating_basis": ["not_available"], "dating_reliability": "unknown",
        "dating_source": "not_available", "annotator": "not_applicable",
        "annotation_date": "not_applicable", "inscription_technique": "unknown",
        "notes": "SYNTHETIC TEST FIXTURE generated in tmp_path. Not data.",
    })
    return r


@pytest.fixture
def world(tmp_path, base_record):
    """Six unlabelled synthetic artifacts (one photo each), images on disk, empty store."""
    raw = tmp_path / "raw"
    (raw / "fixture").mkdir(parents=True)
    records = []
    for n in range(1, 7):
        aid, iid = f"FIXTURE_PILOT_{n}", f"FIXTURE_PILOT_{n}__1"
        rel = f"fixture/{iid}.png"
        img = Image.new("RGB", (100, 100), (30 * n, 90, 140))
        img.putpixel((n, n), (255, 255, 255))
        img.save(raw / rel)
        sha = hashlib.sha256((raw / rel).read_bytes()).hexdigest()
        records.append(_unlabelled(base_record, aid, iid, rel, sha, 100))
    from src.annotation.store import AnnotationStore
    from src.dataset.convert import write_jsonl

    rp = tmp_path / "records.jsonl"
    write_jsonl(rp, records)
    store = AnnotationStore(tmp_path / "annotations.jsonl", rp)
    return {"records_path": rp, "raw": raw, "store": store, "log": tmp_path / "promotion_log.jsonl",
            "arts": [r["artifact_id"] for r in records], "records": records, "tmp": tmp_path}


# --------------------------------------------------------------------------- #
# Milestone 9: a tiny SYNTHETIC engineering dataset (and a tiny CPU model), session-scoped.
# Generated under pytest's temporary directory, never under data/. SYNTHETIC — NOT
# ARCHAEOLOGICAL EVIDENCE: these exist only to exercise the synthetic pipeline.
# --------------------------------------------------------------------------- #


def tiny_synthetic_config(**overrides: Any):
    from src.synthetic.config import SyntheticDatasetConfig

    data = SyntheticDatasetConfig.load().to_dict()
    data.update(artifacts_per_class=5, object_px=192)
    data["canvas"] = {"min_px": 160, "max_px": 200}
    data["split"]["min_artifacts_per_class_for_holdout"] = 3
    data.update(overrides)
    return SyntheticDatasetConfig.from_dict(data)


@pytest.fixture(scope="session")
def tiny_synthetic(tmp_path_factory) -> dict[str, Any]:
    """A generated and split tiny synthetic dataset: {"root", "cfg", "config_path", "records"}."""
    import yaml

    from src.dataset.convert import read_jsonl
    from src.synthetic.dataset import generate_dataset, make_synthetic_split

    base = tmp_path_factory.mktemp("synthetic")
    cfg = tiny_synthetic_config()
    config_path = base / "synthetic_dataset.yaml"
    config_path.write_text(yaml.safe_dump(cfg.to_dict()), encoding="utf-8")
    root = base / "data_synthetic"
    generate_dataset(cfg, root)
    make_synthetic_split(cfg, root)
    return {"root": root, "cfg": cfg, "config_path": config_path, "base": base,
            "records": read_jsonl(root / "metadata" / "records.jsonl")}


@pytest.fixture(scope="session")
def tiny_synthetic_model(tiny_synthetic) -> dict[str, Any]:
    """One CPU epoch of resnet18 (no pretrained download) on the tiny synthetic dataset."""
    import yaml

    from src.synthetic.train import run_synthetic_training

    base = tiny_synthetic["base"]
    data = yaml.safe_load((ROOT / "configs" / "synthetic_training.yaml").read_text(encoding="utf-8"))
    data["dataset_config"] = str(tiny_synthetic["config_path"])
    data["reports_directory"] = str(base / "models" / "reports")
    t = data["training"]
    t["model"].update(pretrained=False, freeze_backbone=False)
    t["data"].update(batch_size=8, num_workers=0, pin_memory=False)
    t["optimization"]["epochs"] = 1
    t["runtime"].update(device="cpu", mixed_precision=False)
    t["checkpoint"]["directory"] = str(base / "models" / "checkpoints")
    t["experiments"]["directory"] = str(base / "models" / "experiments")
    config_path = base / "synthetic_training.yaml"
    config_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    outcome = run_synthetic_training(config_path, root=tiny_synthetic["root"])
    assert outcome.status == "completed", outcome.message
    return {"outcome": outcome, "config_path": config_path, "checkpoint": Path(outcome.best_checkpoint),
            "experiment": Path(outcome.experiment)}
