"""Shared test fixtures.

All record data originates from ``tests/fixtures/`` and is synthetic. See
``tests/fixtures/README.md``. Nothing here touches ``data/``.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import pytest

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
