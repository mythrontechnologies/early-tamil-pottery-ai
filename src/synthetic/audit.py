"""Statistics and verification of the synthetic dataset.   SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE

    python -m src.synthetic stats  [--json]
    python -m src.synthetic verify [--regenerate N] [--json]

``verify`` checks the dataset itself (schema, ids, files, hashes, duplicates, counts, lock,
split leakage), that it can be reproduced (re-renders a sample from seed + generator version +
configuration and compares SHA-256), and that it has not crossed into the research data
(no synthetic file under data/raw, data/external, data/interim or data/processed; no synthetic
record in the research records; no synthetic annotation in the annotation store).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.dataset.convert import read_jsonl
from src.dataset.schema import RESEARCH_RECORDS_PATH, ROOT
from src.dataset.splits import HOLDOUT_PARTITIONS, partition_records

from . import MARKER, PROTECTED_DATA_DIRS, PURPOSE, is_synthetic_id, synthetic_reasons
from .config import SyntheticDatasetConfig
from .dataset import (
    SyntheticDatasetError,
    SyntheticPaths,
    build_lock,
    find_manifest,
    load_synthetic_dataset,
    validate_synthetic_records,
)
from .generator import GENERATOR_VERSION, build_artifact, generate_view


def _size(paths: SyntheticPaths) -> dict[str, int]:
    files = [p for p in paths.root.rglob("*") if p.is_file()] if paths.root.is_dir() else []
    images = [p for p in files if p.parent == paths.images]
    return {"total_bytes": sum(p.stat().st_size for p in files), "image_bytes": sum(p.stat().st_size for p in images),
            "image_files": len(images)}


def dataset_stats(root: Path | str | None = None) -> dict[str, Any]:
    paths = SyntheticPaths.at(root)
    if not paths.records.exists():
        return {"exists": False, "marker": MARKER, "message": "No synthetic dataset. Run `python -m src.synthetic generate`."}
    records = read_jsonl(paths.records)
    lock = json.loads(paths.lock.read_text(encoding="utf-8")) if paths.lock.exists() else {}
    by_art = {r["artifact_id"]: r["script_type"] for r in records}
    hashes = Counter(r["image_sha256"] for r in records)
    ids = Counter(r["image_id"] for r in records)
    stats: dict[str, Any] = {
        "exists": True, "marker": MARKER, "purpose": PURPOSE, "dataset_type": "synthetic",
        "artifacts": len(by_art), "images": len(records),
        "artifacts_by_class": dict(sorted(Counter(by_art.values()).items())),
        "images_by_class": dict(sorted(Counter(r["script_type"] for r in records).items())),
        "views_per_artifact": dict(sorted(Counter(Counter(r["artifact_id"] for r in records).values()).items())),
        "uncertain_modes": dict(sorted(Counter(r["synthetic_uncertain_mode"] for r in records
                                               if r["script_type"] == "synthetic_uncertain").items())),
        "surfaces": dict(sorted(Counter(r["synthetic_surface"] for r in records).items())),
        "duplicate_image_ids": sum(n - 1 for n in ids.values() if n > 1),
        "hash_collisions": sum(n - 1 for n in hashes.values() if n > 1),
        "generator_versions": sorted({r["synthetic_generator_version"] for r in records}),
        "generation_seeds": sorted({r["generation_seed"] for r in records}),
        "config_digest": lock.get("config_digest"),
        "records_fingerprint": lock.get("records_fingerprint"),
        "synthetic_fingerprint": lock.get("synthetic_fingerprint"),
        "split_digest": lock.get("split_digest"),
        "storage": _size(paths),
        "split": None,
    }
    try:
        ds = load_synthetic_dataset(paths.root, verify_hashes=False)
        m = find_manifest(ds, paths.root)
        stats["split"] = {"strategy": m.strategy, "digest": m.digest, "seed": m.seed,
                          **{p: {"artifacts": m.summary[p]["artifacts"], "images": m.summary[p]["images"],
                                 "artifacts_by_class": m.summary[p]["artifacts_by_class"]} for p in m.partitions}}
    except SyntheticDatasetError as exc:
        stats["split"] = {"status": str(exc)}
    return stats


def render_stats(s: dict[str, Any]) -> str:
    bar = "=" * 72
    if not s.get("exists"):
        return f"{bar}\n{MARKER}\n{s['message']}\n{bar}"
    L = [bar, f"SYNTHETIC DATASET STATISTICS   ({MARKER})", bar,
         f"Artifacts            : {s['artifacts']}", f"Images               : {s['images']}",
         "Class distribution (artifacts / images):"]
    for c, n in s["artifacts_by_class"].items():
        L.append(f"    {c:<30} {n:>5} / {s['images_by_class'].get(c, 0)}")
    L.append(f"Views per artifact   : {s['views_per_artifact']}")
    L.append(f"Uncertain modes      : {s['uncertain_modes']}")
    L.append(f"Surfaces             : {s['surfaces']}")
    sp = s.get("split") or {}
    if "strategy" in sp:
        L.append(f"Split ({sp['strategy']}, digest {sp['digest'][:16]}):")
        for p in HOLDOUT_PARTITIONS:
            if p in sp:
                L.append(f"    {p:<6} {sp[p]['artifacts']:>5} artifacts  {sp[p]['images']:>5} images  {sp[p]['artifacts_by_class']}")
    else:
        L.append(f"Split                : {sp.get('status', 'none')}")
    st = s["storage"]
    L += [f"Duplicate image ids  : {s['duplicate_image_ids']}", f"Hash collisions      : {s['hash_collisions']}",
          f"Generator version    : {', '.join(s['generator_versions'])}", f"Seeds                : {s['generation_seeds']}",
          f"Config digest        : {s['config_digest']}", f"Records fingerprint  : {s['records_fingerprint']}",
          f"Synthetic fingerprint: {s['synthetic_fingerprint']}",
          f"Storage              : {st['total_bytes'] / 2**20:.1f} MiB ({st['image_files']} images, "
          f"{st['image_bytes'] / 2**20:.1f} MiB)", "", PURPOSE, bar]
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #


@dataclass
class Check:
    id: str
    title: str
    passed: bool
    detail: str = ""


@dataclass
class VerifyReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, cid: str, title: str, passed: bool, detail: str = "") -> None:
        self.checks.append(Check(cid, title, bool(passed), detail))

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "marker": MARKER, "checks": [asdict(c) for c in self.checks]}

    def render(self) -> str:
        L = ["=" * 72, f"SYNTHETIC DATASET VERIFICATION   ({MARKER})", "=" * 72]
        for c in self.checks:
            L.append(f"  {c.id:<4} {'PASS' if c.passed else 'FAIL':<5} {c.title}" + (f"  - {c.detail}" if c.detail else ""))
        L += ["", f"RESULT: {'PASS' if self.ok else 'FAIL'}", "=" * 72]
        return "\n".join(L)


def _research_contamination() -> tuple[list[str], list[str], list[str]]:
    """Synthetic traces inside the research data: files, records, annotations."""
    files = []
    for d in PROTECTED_DATA_DIRS:
        if d.name == "metadata" or not d.is_dir():
            continue
        files += [p.relative_to(ROOT).as_posix() for p in d.rglob("*") if p.is_file() and is_synthetic_id(p.name)]
    records = []
    if RESEARCH_RECORDS_PATH.exists():
        records = [str(r.get("image_id")) for r in read_jsonl(RESEARCH_RECORDS_PATH) if synthetic_reasons(r)]
    from src.annotation.model import ANNOTATIONS_PATH

    anns = []
    if ANNOTATIONS_PATH.exists():
        anns = [str(a.get("annotation_id")) for a in read_jsonl(ANNOTATIONS_PATH) if synthetic_reasons(a)]
    return files, records, anns


def verify_dataset(root: Path | str | None = None, *, regenerate: int = 8,
                   config: SyntheticDatasetConfig | None = None) -> VerifyReport:
    paths = SyntheticPaths.at(root)
    rep = VerifyReport()
    files, recs, anns = _research_contamination()
    rep.add("V1", "no synthetic file under data/raw, data/external, data/interim, data/processed", not files,
            f"{len(files)} found: {files[:3]}" if files else "none")
    rep.add("V2", "no synthetic record in data/metadata/records.jsonl", not recs, f"{len(recs)} found" if recs else "none")
    rep.add("V3", "no synthetic annotation in the annotation store", not anns, f"{len(anns)} found" if anns else "none")
    if not paths.records.exists():
        rep.add("V4", "synthetic records present", False, "run `python -m src.synthetic generate`")
        return rep
    cfg = config or SyntheticDatasetConfig.load()
    raw = read_jsonl(paths.records)
    findings = validate_synthetic_records(raw, paths.root, verify_hashes=True)
    by_rule = Counter(f.rule for f in findings)
    rep.add("V4", "every record passes the synthetic schema (dataset_type, marker, sentinels, ids)", not by_rule.get("S1"),
            f"{by_rule.get('S1', 0)} problem(s)")
    rep.add("V5", "image ids unique and grouped under their artifact", not by_rule.get("S2"), f"{by_rule.get('S2', 0)} problem(s)")
    rep.add("V6", "every image file exists and matches its SHA-256", not by_rule.get("S3"),
            f"{len(raw)} checked, {by_rule.get('S3', 0)} problem(s)")
    rep.add("V7", "no duplicate image (hash collision)", not by_rule.get("S4"), f"{by_rule.get('S4', 0)} collision(s)")
    rep.add("V8", "one label per artifact; labels consistent", not (by_rule.get("S5") or by_rule.get("S6")),
            f"{by_rule.get('S5', 0) + by_rule.get('S6', 0)} problem(s)")
    per_class = Counter({r["artifact_id"]: r["script_type"] for r in raw}.values())
    expected = dict.fromkeys(per_class, cfg.artifacts_per_class) if per_class else {}
    rep.add("V9", f"{cfg.artifacts_per_class} artifacts per class, as configured",
            dict(per_class) == expected and len(per_class) == 4, str(dict(sorted(per_class.items()))))
    on_disk = {p.name for p in paths.images.glob("*.jpg")}
    listed = {Path(r["image_path"]).name for r in raw}
    rep.add("V10", "image folder holds exactly the recorded images", on_disk == listed,
            f"{len(on_disk - listed)} unrecorded, {len(listed - on_disk)} missing")

    lock = json.loads(paths.lock.read_text(encoding="utf-8")) if paths.lock.exists() else None
    ds = load_synthetic_dataset(paths.root, verify_hashes=False)
    manifest = None
    try:
        manifest = find_manifest(ds, paths.root)
    except SyntheticDatasetError as exc:
        rep.add("V11", "verified artifact-level split manifest", False, str(exc))
    if manifest is not None:
        parts = partition_records(manifest, ds)
        arts = [{r.artifact_id for r in v} for v in parts.values()]
        hashes = [{r.image_sha256 for r in v} for v in parts.values()]
        overlap_a = sum(len(a & b) for i, a in enumerate(arts) for b in arts[i + 1:])
        overlap_h = sum(len(a & b) for i, a in enumerate(hashes) for b in hashes[i + 1:])
        assigned = sum(len(a) for a in arts)
        rep.add("V11", "split: no artifact or image hash in two partitions; every artifact assigned",
                overlap_a == 0 and overlap_h == 0 and assigned == len(ds.by_artifact()),
                f"{manifest.strategy} {manifest.digest[:12]}; artifact overlaps {overlap_a}, hash overlaps {overlap_h}")
    fresh = build_lock(cfg, raw, manifest)
    if lock is None:
        rep.add("V12", "dataset lock matches the records", False, "manifests/dataset_lock.json missing")
    else:
        keys = ("records_fingerprint", "image_set_fingerprint", "metadata_fingerprint", "config_digest",
                "split_digest", "synthetic_fingerprint")
        diff = [k for k in keys if lock.get(k) != fresh.get(k)]
        rep.add("V12", "dataset lock matches the records, configuration and split", not diff,
                f"differs: {diff}" if diff else f"synthetic fingerprint {fresh['synthetic_fingerprint'][:16]}")
    rep.add("V13", "records were made by this generator version and seed",
            {r["synthetic_generator_version"] for r in raw} == {GENERATOR_VERSION} and {r["generation_seed"] for r in raw} == {cfg.seed},
            f"generator {GENERATOR_VERSION}, seed {cfg.seed}")
    if regenerate > 0:
        by_img = {r["image_id"]: r for r in raw}
        sample = sorted(by_img)[:: max(1, len(by_img) // regenerate)][:regenerate]
        mismatched = []
        for iid in sample:
            r = by_img[iid]
            state = build_artifact(cfg, r["artifact_index"], r["script_type"])
            gv = generate_view(cfg, state, r["view_index"])
            if gv.sha256 != r["image_sha256"] or gv.params_digest != r["generation_params_sha256"]:
                mismatched.append(iid)
        rep.add("V14", f"reproducible: {len(sample)} image(s) re-rendered from seed + version + config are byte-identical",
                not mismatched, f"mismatched: {mismatched[:3]}" if mismatched else "identical SHA-256 and parameters")
    return rep


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = ["Check", "VerifyReport", "dataset_stats", "render_stats", "verify_dataset"]
