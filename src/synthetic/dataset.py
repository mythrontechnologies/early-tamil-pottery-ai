"""The synthetic dataset on disk: generation, records, provenance, fingerprint, loading, split.

    SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE

Layout (``data/synthetic/``; images and per-image JSONL are git-ignored and regenerable)::

    images/SYNTH-A0001-V1.jpg            generated JPEGs
    metadata/records.jsonl               one record per image (synthetic_record.schema.json)
    manifests/provenance.jsonl           per-image generator parameters, seeds and streams
    manifests/generation_run.json        when, which commit, which environment (not fingerprinted)
    manifests/dataset_lock.json          deterministic summary: counts + every fingerprint (committed)
    splits/split_holdout_<fp>_seed<s>.json  artifact-level split manifest (committed)

Records reuse :class:`src.dataset.loader.DatasetRecord` and the research split code
(:func:`src.dataset.splits.make_split`), so the synthetic dataset exercises the SAME grouping,
leakage and fingerprint machinery as the research dataset, but through a separate loader, a
separate schema and a separate root. The research loader, validator and readiness gate never
read anything here.
"""

from __future__ import annotations

import hashlib
import json
import platform
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

from jsonschema import Draft202012Validator

from src.dataset.classes import ClassSpec
from src.dataset.convert import read_jsonl, write_jsonl
from src.dataset.fingerprint import dataset_fingerprint, image_set_fingerprint
from src.dataset.loader import DatasetRecord, LoadedDataset, Rejection
from src.dataset.schema import ROOT
from src.dataset.splits import SplitManifest, SplitSettings, latest_manifest, make_split, verify_manifest

from . import (
    DATASET_TYPE,
    LABEL_SOURCE,
    LABEL_WARNING,
    MARKER,
    PURPOSE,
    SCHEMA_PATH,
    SOURCE,
    SYNTHETIC_LABELS,
    SYNTHETIC_ROOT,
    assert_synthetic_destination,
)
from .config import SyntheticDatasetConfig
from .generator import (
    GENERATOR_VERSION,
    INSCRIPTION_PRESENT,
    STREAM_DISTRACT,
    STREAM_MARKS,
    STREAM_OBJECT,
    STREAM_VIEWS,
    VIEW_BASE,
    ArtifactState,
    GeneratedView,
    build_artifact,
    class_assignment,
    generate_view,
)

SCHEMA_VERSION = "synthetic-1.0.0"
FINGERPRINT_VERSION = "synthetic-fingerprint-v1"


class SyntheticDatasetError(RuntimeError):
    """The synthetic dataset is missing, invalid, or would be overwritten without --force."""


@lru_cache(maxsize=1)
def load_synthetic_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def synthetic_class_spec() -> ClassSpec:
    """The synthetic label vocabulary as a ClassSpec (all four trainable, none held out)."""
    spec = ClassSpec(SYNTHETIC_LABELS, (), SYNTHETIC_LABELS)
    spec.check()
    return spec


@dataclass(frozen=True)
class SyntheticPaths:
    root: Path

    @classmethod
    def at(cls, root: Path | str | None = None) -> SyntheticPaths:
        return cls(Path(root) if root else SYNTHETIC_ROOT)

    images = property(lambda self: self.root / "images")
    metadata = property(lambda self: self.root / "metadata")
    splits = property(lambda self: self.root / "splits")
    manifests = property(lambda self: self.root / "manifests")
    records = property(lambda self: self.root / "metadata" / "records.jsonl")
    provenance = property(lambda self: self.root / "manifests" / "provenance.jsonl")
    lock = property(lambda self: self.root / "manifests" / "dataset_lock.json")
    run = property(lambda self: self.root / "manifests" / "generation_run.json")


def split_settings(cfg: SyntheticDatasetConfig, paths: SyntheticPaths | None = None) -> SplitSettings:
    s = cfg.split
    return SplitSettings(seed=s.seed, ratios=(s.train, s.val, s.test),
                         min_artifacts_per_class_for_holdout=s.min_artifacts_per_class_for_holdout,
                         k_folds=s.k_folds, stratify_by="script_type", balance_secondary=tuple(s.balance_secondary),
                         manifest_dir=(paths or SyntheticPaths.at()).splits)


# --------------------------------------------------------------------------- #
# Records and provenance
# --------------------------------------------------------------------------- #


def make_record(cfg: SyntheticDatasetConfig, state: ArtifactState, gv: GeneratedView) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_type": DATASET_TYPE,
        "synthetic_marker": MARKER,
        "label_warning": LABEL_WARNING,
        "image_id": gv.image_id,
        "artifact_id": state.artifact_id,
        "catalogue_number": f"SYNTH-ONLY-{state.index + 1:04d}",
        "image_path": f"images/{gv.image_id}.jpg",
        "image_sha256": gv.sha256,
        "image_width_px": gv.width,
        "image_height_px": gv.height,
        "view": f"synthetic_view_{gv.view + 1}",
        "source": SOURCE,
        "synthetic_generator_version": GENERATOR_VERSION,
        "generation_seed": cfg.seed,
        "artifact_index": state.index,
        "view_index": gv.view,
        "site": "not_applicable",
        "context": "not_applicable",
        "period": "not_applicable",
        "dating_basis": "not_applicable",
        "script_type": state.label,
        "inscription_present": INSCRIPTION_PRESENT[state.label],
        "inscription_type": state.marks["inscription_type"],
        "transcription": "not_applicable",
        "translation": "not_applicable",
        "label_source": LABEL_SOURCE,
        "label_confidence": "high",
        "synthetic_surface": state.params["surface"]["surface"],
        "synthetic_uncertain_mode": state.marks["uncertain_mode"],
        "synthetic_glyph_sequence": state.marks["glyph_sequence"],
        "synthetic_regions": gv.regions,
        "generation_params_sha256": gv.params_digest,
    }


def provenance_entry(cfg: SyntheticDatasetConfig, state: ArtifactState, gv: GeneratedView) -> dict[str, Any]:
    seed, i, v = cfg.seed, state.index, gv.view
    return {
        "dataset_type": DATASET_TYPE,
        "synthetic_marker": MARKER,
        "image_id": gv.image_id,
        "artifact_id": state.artifact_id,
        "image_sha256": gv.sha256,
        "class": state.label,
        "generator_version": GENERATOR_VERSION,
        "generation_seed": seed,
        "config_digest": cfg.digest,
        "random_streams": {"object": [seed, i, STREAM_OBJECT], "marks": [seed, i, STREAM_MARKS],
                           "distractors": [seed, i, STREAM_DISTRACT], "view_count": [seed, i, STREAM_VIEWS],
                           "view": [seed, i, VIEW_BASE + v]},
        "artifact_params": state.params,
        "view_params": gv.view_params,
        "view_params_sha256": gv.params_digest,
    }


# --------------------------------------------------------------------------- #
# Fingerprint
# --------------------------------------------------------------------------- #


def _sha_json(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def metadata_fingerprint(records: list[dict[str, Any]]) -> str:
    """Records WITHOUT their image hashes: identical wherever the generator runs (no JPEG codec involved)."""
    return dataset_fingerprint([{k: v for k, v in r.items() if k != "image_sha256"} for r in records])


def synthetic_fingerprint(records: list[dict[str, Any]], *, generator_version: str, config_digest: str,
                          split_digest: str | None) -> str:
    """One string for the whole synthetic dataset: image hashes, record metadata, generator version,
    configuration and split. Changing any of them changes it."""
    return _sha_json({
        "version": FINGERPRINT_VERSION,
        "dataset_type": DATASET_TYPE,
        "generator_version": generator_version,
        "config_digest": config_digest,
        "records_fingerprint": dataset_fingerprint(records),
        "metadata_fingerprint": metadata_fingerprint(records),
        "image_hashes_sha256": _sha_json(sorted(r.get("image_sha256", "") for r in records)),
        "split_digest": split_digest or "unsplit",
    })


def build_lock(cfg: SyntheticDatasetConfig, records: list[dict[str, Any]], split: SplitManifest | None) -> dict[str, Any]:
    """Deterministic summary of a generated dataset (no timestamps, no machine facts)."""
    by_art: dict[str, str] = {r["artifact_id"]: r["script_type"] for r in records}
    return {
        "dataset_type": DATASET_TYPE,
        "synthetic_marker": MARKER,
        "purpose": PURPOSE,
        "generator_version": GENERATOR_VERSION,
        "generation_seed": cfg.seed,
        "config_digest": cfg.digest,
        "config": cfg.to_dict(),
        "artifacts": len(by_art),
        "images": len(records),
        "artifacts_by_class": dict(sorted(Counter(by_art.values()).items())),
        "images_by_class": dict(sorted(Counter(r["script_type"] for r in records).items())),
        "records_fingerprint": dataset_fingerprint(records),
        "image_set_fingerprint": image_set_fingerprint(records),
        "metadata_fingerprint": metadata_fingerprint(records),
        "split_digest": split.digest if split else None,
        "split_manifest": split.default_filename() if split else None,
        "synthetic_fingerprint": synthetic_fingerprint(records, generator_version=GENERATOR_VERSION,
                                                       config_digest=cfg.digest,
                                                       split_digest=split.digest if split else None),
    }


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #


@dataclass
class GenerationResult:
    root: str
    artifacts: int
    images: int
    bytes_written: int
    seconds: float
    lock: dict[str, Any]


def _clean(paths: SyntheticPaths) -> None:
    """Remove a previous synthetic dataset: generated files only, matched by name, under the synthetic root."""
    for p in paths.images.glob("SYNTH-A*-V*.jpg") if paths.images.is_dir() else []:
        p.unlink()
    for p in (paths.records, paths.provenance, paths.lock, paths.run):
        if p.exists():
            p.unlink()
    for p in paths.splits.glob("split_*.json") if paths.splits.is_dir() else []:
        p.unlink()


def generate_dataset(cfg: SyntheticDatasetConfig, root: Path | str | None = None, *, force: bool = False,
                     progress: Callable[[int, int], None] | None = None) -> GenerationResult:
    """Generate every artifact and view, write records, provenance and the lock. Deterministic."""
    paths = SyntheticPaths.at(assert_synthetic_destination(root or SYNTHETIC_ROOT))
    if paths.records.exists() and not force:
        raise SyntheticDatasetError(f"a synthetic dataset already exists at {paths.root}; pass --force to regenerate it")
    _clean(paths)
    paths.images.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    labels = class_assignment(cfg.seed, cfg.artifacts_per_class)
    records: list[dict[str, Any]] = []
    prov: list[dict[str, Any]] = []
    written = 0
    for idx, label in enumerate(labels):
        state = build_artifact(cfg, idx, label)
        for v in range(state.n_views):
            gv = generate_view(cfg, state, v)
            (paths.images / f"{gv.image_id}.jpg").write_bytes(gv.jpeg)
            written += len(gv.jpeg)
            records.append(make_record(cfg, state, gv))
            prov.append(provenance_entry(cfg, state, gv))
        if progress:
            progress(idx + 1, len(labels))
    records.sort(key=lambda r: r["image_id"])
    prov.sort(key=lambda r: r["image_id"])
    schema = load_synthetic_schema()
    write_jsonl(paths.records, records, schema)
    paths.provenance.parent.mkdir(parents=True, exist_ok=True)
    with paths.provenance.open("w", encoding="utf-8", newline="\n") as fh:
        for row in prov:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    lock = build_lock(cfg, records, None)
    _write_json(paths.lock, lock)
    seconds = time.perf_counter() - start
    _write_json(paths.run, _run_facts(cfg, len(records), written, seconds))
    return GenerationResult(str(paths.root), lock["artifacts"], lock["images"], written, seconds, lock)


def _run_facts(cfg: SyntheticDatasetConfig, images: int, written: int, seconds: float) -> dict[str, Any]:
    import cv2
    import numpy
    import PIL

    from src.training.runtime import git_commit

    return {"dataset_type": DATASET_TYPE, "synthetic_marker": MARKER,
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "git": git_commit(),
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "numpy": numpy.__version__, "opencv": cv2.__version__, "pillow": PIL.__version__},
            "generator_version": GENERATOR_VERSION, "generation_seed": cfg.seed, "config_digest": cfg.digest,
            "images": images, "bytes_written": written, "seconds": round(seconds, 2),
            "note": "Facts about this run. Not part of any fingerprint: the dataset itself is deterministic."}


# --------------------------------------------------------------------------- #
# Validation and loading
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SyntheticFinding:
    rule: str
    message: str
    image_id: str | None = None

    def __str__(self) -> str:
        return f"{self.rule} {self.image_id or '<dataset>'}: {self.message}"


SYNTHETIC_RULES: dict[str, str] = {
    "S1": "record conforms to synthetic_record.schema.json (dataset_type, marker, sentinels, ids)",
    "S2": "image_id is unique and belongs to its artifact",
    "S3": "image file exists inside the synthetic root and its SHA-256 matches",
    "S4": "no photograph (SHA-256) appears twice",
    "S5": "one artifact has one synthetic label",
    "S6": "inscription_present agrees with the synthetic label",
}


def validate_synthetic_records(records: list[dict[str, Any]], root: Path | None = None, *,
                               verify_hashes: bool = True) -> list[SyntheticFinding]:
    validator = Draft202012Validator(load_synthetic_schema())
    out: list[SyntheticFinding] = []
    seen_ids: set[str] = set()
    seen_hash: dict[str, str] = {}
    labels: dict[str, set[str]] = {}
    for r in records:
        iid = r.get("image_id") if isinstance(r, dict) else None
        if not isinstance(r, dict):
            out.append(SyntheticFinding("S1", "record is not a JSON object"))
            continue
        for err in validator.iter_errors(r):
            out.append(SyntheticFinding("S1", f"{'.'.join(map(str, err.path)) or '<root>'}: {err.message}", iid))
        if iid in seen_ids:
            out.append(SyntheticFinding("S2", "duplicate image_id", iid))
        seen_ids.add(str(iid))
        if isinstance(iid, str) and not iid.startswith(f"{r.get('artifact_id')}-V"):
            out.append(SyntheticFinding("S2", f"image_id does not belong to artifact {r.get('artifact_id')!r}", iid))
        labels.setdefault(str(r.get("artifact_id")), set()).add(str(r.get("script_type")))
        sha = r.get("image_sha256")
        if isinstance(sha, str):
            if sha in seen_hash:
                out.append(SyntheticFinding("S4", f"identical image to {seen_hash[sha]}", iid))
            seen_hash.setdefault(sha, str(iid))
        if r.get("script_type") in INSCRIPTION_PRESENT and r.get("inscription_present") != INSCRIPTION_PRESENT[r["script_type"]]:
            out.append(SyntheticFinding("S6", f"inscription_present={r.get('inscription_present')!r} disagrees with "
                                              f"{r['script_type']}", iid))
        if root is not None and isinstance(r.get("image_path"), str):
            path = (root / r["image_path"]).resolve()
            try:
                path.relative_to(root.resolve())
            except ValueError:
                out.append(SyntheticFinding("S3", "image_path escapes the synthetic root", iid))
                continue
            if not path.is_file():
                out.append(SyntheticFinding("S3", f"image file missing: {r['image_path']}", iid))
            elif verify_hashes and isinstance(sha, str) and hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                out.append(SyntheticFinding("S3", "file SHA-256 differs from the record", iid))
    for aid, labs in sorted(labels.items()):
        if len(labs) > 1:
            out.append(SyntheticFinding("S5", f"artifact {aid} has labels {sorted(labs)}"))
    return out


def load_synthetic_dataset(root: Path | str | None = None, *, verify_hashes: bool = True) -> LoadedDataset:
    """The synthetic records as a LoadedDataset (``is_research_dataset`` is always False)."""
    paths = SyntheticPaths.at(root)
    base = dict(source=_rel(paths.records), data_root=_rel(paths.root), is_research_dataset=False)
    if not paths.records.exists():
        return LoadedDataset(**base, exists=False, fingerprint=dataset_fingerprint([]),
                             image_fingerprint=image_set_fingerprint([]))
    raw = read_jsonl(paths.records)
    findings = validate_synthetic_records(raw, paths.root, verify_hashes=verify_hashes)
    reasons: dict[str, list[str]] = {}
    for f in findings:
        reasons.setdefault(f.image_id or "<dataset>", []).append(f"{f.rule}: {f.message}")
    accepted, rejected = [], []
    for idx, r in enumerate(raw):
        iid = r.get("image_id")
        if reasons.get(iid):
            rejected.append(Rejection(idx, iid, tuple(reasons[iid])))
            continue
        accepted.append(DatasetRecord(index=idx, image_id=iid, artifact_id=r["artifact_id"],
                                      image_path=(paths.root / r["image_path"]).resolve(),
                                      image_sha256=r["image_sha256"], script_type=r["script_type"],
                                      record=MappingProxyType(dict(r))))
    if reasons.get("<dataset>"):
        rejected.append(Rejection(-1, None, tuple(reasons["<dataset>"])))
    return LoadedDataset(**base, records=tuple(accepted), rejections=tuple(rejected), validation=None,
                         raw_record_count=len(raw), fingerprint=dataset_fingerprint(raw),
                         image_fingerprint=image_set_fingerprint(raw), hashes_verified=verify_hashes)


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------- #
# Split
# --------------------------------------------------------------------------- #


def make_synthetic_split(cfg: SyntheticDatasetConfig, root: Path | str | None = None, *,
                         dataset: LoadedDataset | None = None) -> tuple[SplitManifest, Path]:
    """Artifact-level hold-out split with the research splitter; writes the manifest and updates the lock."""
    paths = SyntheticPaths.at(assert_synthetic_destination(root or SYNTHETIC_ROOT))
    dataset = dataset or load_synthetic_dataset(paths.root)
    if dataset.is_empty:
        raise SyntheticDatasetError("no synthetic dataset; run `python -m src.synthetic generate` first")
    if not dataset.ok:
        raise SyntheticDatasetError(f"synthetic dataset invalid: {[str(r) for r in dataset.rejections[:3]]}")
    manifest = make_split(dataset, synthetic_class_spec(), split_settings(cfg, paths), strategy="holdout")
    manifest.warnings.append(f"{MARKER}: synthetic split; it never stands in for a research split.")
    out = manifest.save(paths.splits / manifest.default_filename())
    raw = read_jsonl(paths.records)
    _write_json(paths.lock, build_lock(cfg, raw, manifest))
    return manifest, out


def find_manifest(dataset: LoadedDataset, root: Path | str | None = None, *, digest: str | None = None,
                  path: Path | str | None = None) -> SplitManifest:
    """The split manifest for this dataset (a given path, a given digest, or the newest), verified."""
    paths = SyntheticPaths.at(root)
    if path is not None:
        candidates = [Path(path)]
    elif digest is not None:
        candidates = sorted(paths.splits.glob("split_*.json"))
    else:
        latest = latest_manifest(paths.splits, dataset.fingerprint)
        candidates = [latest] if latest else []
    for c in candidates:
        m = SplitManifest.load(c)
        if digest is not None and m.digest != digest:
            continue
        errors = verify_manifest(m, dataset)
        if errors:
            raise SyntheticDatasetError(f"{c.name} does not verify against the synthetic dataset: {errors[:3]}")
        return m
    raise SyntheticDatasetError("no verified synthetic split manifest for this dataset; run `python -m src.synthetic split`")


__all__ = [
    "FINGERPRINT_VERSION",
    "SCHEMA_VERSION",
    "SYNTHETIC_RULES",
    "GenerationResult",
    "SyntheticDatasetError",
    "SyntheticFinding",
    "SyntheticPaths",
    "build_lock",
    "find_manifest",
    "generate_dataset",
    "load_synthetic_dataset",
    "load_synthetic_schema",
    "make_record",
    "make_synthetic_split",
    "metadata_fingerprint",
    "provenance_entry",
    "split_settings",
    "synthetic_class_spec",
    "synthetic_fingerprint",
    "validate_synthetic_records",
]
