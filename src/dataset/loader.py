"""Load validated records into an in-memory dataset for training and evaluation.

The loader is the only way research records become training inputs. It is strict: a
record is either accepted whole or rejected with every reason attached. Nothing is
repaired, defaulted or guessed.

    from src.dataset.loader import load_dataset
    ds = load_dataset()                 # data/metadata/records.jsonl + data/raw/
    ds.ok, len(ds.records), ds.rejections

What the loader checks, on top of ``src.dataset.validation`` (``E*``/``R*``):

* ``L1`` the resolved image path stays inside the data root (defeats symlink escape);
* ``L2`` ``image_sha256`` is a real hash, not a sentinel. Training needs every hash,
  because the hash is how a duplicate photograph under two ids is caught;
* hashes are recomputed from the files (``E2``) unless explicitly disabled.

``L*`` checks are engineering checks. None of them says anything about archaeology.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .audit import is_research_source
from .convert import read_jsonl
from .fingerprint import dataset_fingerprint, image_set_fingerprint
from .schema import (
    RESEARCH_DATA_ROOT,
    RESEARCH_RECORDS_PATH,
    has_real_value,
    is_sentinel,
)
from .validation import ValidationResult, validate_records

LOADER_RULES: dict[str, str] = {
    "L1": "resolved image path stays inside the data root",
    "L2": "image_sha256 is a real hash (required for leakage checks)",
}

#: Names used in the Milestone 5 brief that differ from schema field names.
#: The schema is authoritative; these are read-only aliases, never stored.
FIELD_ALIASES: dict[str, str] = {
    "dating_start": "dating_lower_year",
    "dating_end": "dating_upper_year",
    "translation": "translation_en",
    "inscription_type": "inscription_technique",
}

#: Concepts the brief names that the schema does not record. Asking for one is an error,
#: not a silent ``None``, so nobody mistakes "not recorded" for "no value".
NOT_IN_SCHEMA: dict[str, str] = {
    "period": (
        "the schema has no 'period' field. Dating is recorded as dating_text, "
        "dating_lower_year/dating_upper_year, dating_basis and dating_reliability. "
        "A periodisation is an archaeological decision that has not been made; "
        "see docs/DATASET_SPLIT.md §5."
    ),
}


class DatasetLoadError(RuntimeError):
    """The records file could not be read at all."""


@dataclass(frozen=True)
class Rejection:
    """A record that was not accepted, with every reason found."""

    record_index: int
    image_id: str | None
    reasons: tuple[str, ...]

    def __str__(self) -> str:
        who = self.image_id or f"record[{self.record_index}]"
        return f"{who}: " + "; ".join(self.reasons)


@dataclass(frozen=True)
class DatasetRecord:
    """One accepted photograph. The underlying record is read-only."""

    index: int
    image_id: str
    artifact_id: str
    image_path: Path
    image_sha256: str
    script_type: str
    record: Mapping[str, Any]

    def get(self, name: str, default: Any = "unknown") -> Any:
        """Read a field by schema name or brief alias.

        Absent fields return ``default`` (``'unknown'``), which keeps the project's
        sentinel semantics: absence is never turned into ``None`` or ``''``.
        """
        if name in NOT_IN_SCHEMA:
            raise KeyError(f"'{name}': {NOT_IN_SCHEMA[name]}")
        return self.record.get(FIELD_ALIASES.get(name, name), default)

    def has(self, name: str) -> bool:
        """True when the field carries real information, not a sentinel."""
        if name in NOT_IN_SCHEMA:
            return False
        return has_real_value(dict(self.record), FIELD_ALIASES.get(name, name))

    @property
    def split(self) -> str:
        return str(self.record.get("split", "unassigned"))

    def label_view(self) -> dict[str, Any]:
        """The fields a trainer or evaluator needs, by the brief's names."""
        keys = (
            "artifact_id", "image_id", "image_sha256", "source", "site", "dating_text",
            "dating_start", "dating_end", "dating_basis", "script_type",
            "inscription_present", "inscription_type", "transcription", "translation",
            "pottery_type", "view", "label_source", "label_confidence",
        )
        return {k: self.get(k) for k in keys}


@dataclass
class LoadedDataset:
    source: str
    data_root: str
    is_research_dataset: bool
    records: tuple[DatasetRecord, ...] = ()
    rejections: tuple[Rejection, ...] = ()
    validation: ValidationResult | None = None
    raw_record_count: int = 0
    fingerprint: str = ""
    image_fingerprint: str = ""
    hashes_verified: bool = False
    exists: bool = True

    @property
    def ok(self) -> bool:
        """Every record accepted and the dataset-level validation clean."""
        return not self.rejections and (self.validation is None or self.validation.ok)

    @property
    def is_empty(self) -> bool:
        return self.raw_record_count == 0

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self) -> Iterator[DatasetRecord]:
        return iter(self.records)

    def by_artifact(self) -> dict[str, list[DatasetRecord]]:
        groups: dict[str, list[DatasetRecord]] = defaultdict(list)
        for rec in self.records:
            groups[rec.artifact_id].append(rec)
        return dict(sorted(groups.items()))

    def by_image_id(self) -> dict[str, DatasetRecord]:
        return {r.image_id: r for r in self.records}


def _safe_resolve(data_root: Path, relative: str) -> Path | None:
    """Resolve ``relative`` under ``data_root``; ``None`` if it escapes the root."""
    root = data_root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _relative(path: Path) -> str:
    from .schema import ROOT

    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def load_dataset(
    records_path: Path | str | None = None,
    data_root: Path | str | None = None,
    *,
    verify_hashes: bool = True,
    require_sha256: bool = True,
) -> LoadedDataset:
    """Load and check records. Never raises for bad *records*; they are rejected.

    Raises :class:`DatasetLoadError` only when the file itself cannot be parsed.
    A missing records file is a normal state (no data yet) and yields an empty dataset.
    """
    records_path = Path(records_path) if records_path else RESEARCH_RECORDS_PATH
    data_root = Path(data_root) if data_root else RESEARCH_DATA_ROOT
    base: dict[str, Any] = dict(
        source=_relative(records_path),
        data_root=_relative(data_root),
        is_research_dataset=is_research_source(records_path),
    )

    if not records_path.exists():
        return LoadedDataset(**base, exists=False, validation=None,
                             fingerprint=dataset_fingerprint([]),
                             image_fingerprint=image_set_fingerprint([]))

    try:
        raw = read_jsonl(records_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise DatasetLoadError(f"cannot read {records_path}: {exc}") from exc

    root_exists = data_root.is_dir()
    validation = validate_records(
        raw,
        data_root=data_root if root_exists else None,
        verify_hashes=verify_hashes and root_exists,
    )

    reasons: dict[int, list[str]] = defaultdict(list)
    for finding in validation.errors:
        if finding.record_index is not None:
            reasons[finding.record_index].append(f"{finding.rule}: {finding.message}")

    accepted: list[DatasetRecord] = []
    for idx, rec in enumerate(raw):
        if not isinstance(rec, dict):
            reasons[idx].append("E1: record is not a JSON object")
            continue
        if not root_exists:
            reasons[idx].append(f"R2: data root {data_root} does not exist; image cannot be found")
        path_value = rec.get("image_path")
        resolved = None
        if isinstance(path_value, str) and path_value and root_exists:
            resolved = _safe_resolve(data_root, path_value)
            if resolved is None:
                reasons[idx].append(f"L1: image_path {path_value!r} resolves outside the data root")
        sha = rec.get("image_sha256")
        if require_sha256 and (not isinstance(sha, str) or is_sentinel(sha)):
            reasons[idx].append(
                f"L2: image_sha256 is {sha!r}; a real hash is required so duplicate "
                "photographs can be detected across partitions"
            )
        if reasons.get(idx):
            continue
        accepted.append(DatasetRecord(
            index=idx,
            image_id=rec["image_id"],
            artifact_id=rec["artifact_id"],
            image_path=resolved if resolved is not None else data_root / rec["image_path"],
            image_sha256=str(sha),
            script_type=rec["script_type"],
            record=MappingProxyType(dict(rec)),
        ))

    rejections = tuple(
        Rejection(
            record_index=idx,
            image_id=raw[idx].get("image_id") if isinstance(raw[idx], dict) else None,
            reasons=tuple(dict.fromkeys(msgs)),
        )
        for idx, msgs in sorted(reasons.items())
    )

    return LoadedDataset(
        **base,
        records=tuple(accepted),
        rejections=rejections,
        validation=validation,
        raw_record_count=len(raw),
        fingerprint=dataset_fingerprint(raw),
        image_fingerprint=image_set_fingerprint(raw),
        hashes_verified=bool(verify_hashes and root_exists),
    )


__all__ = [
    "FIELD_ALIASES",
    "LOADER_RULES",
    "NOT_IN_SCHEMA",
    "DatasetLoadError",
    "DatasetRecord",
    "LoadedDataset",
    "Rejection",
    "load_dataset",
]
