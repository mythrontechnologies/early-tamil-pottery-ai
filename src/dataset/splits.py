"""Artifact-level, deterministic, leakage-checked dataset splitting.

The unit of splitting is the **physical artifact** (``artifact_id``), never the
photograph. See ``docs/DATASET_SPLIT.md`` for the algorithm and its justification, and
``docs/SPLIT_METHODOLOGY.md`` for the methodology it implements.

Two strategies:

* ``holdout`` - train / val / test by artifact, in the proportions from
  ``configs/project.yaml``. Requires at least ``min_artifacts_per_class_for_holdout``
  artifacts in every trainable class.
* ``grouped_kfold`` - ``k`` folds by artifact. Requires at least ``k`` artifacts in every
  trainable class, so each class can appear in each fold.

``auto`` picks holdout when the threshold is met, else k-fold when possible, else
refuses. **The splitter refuses rather than produce a misleading split.** It never
fabricates, duplicates or relabels an artifact to make the numbers work.

Balancing:

* primary: ``script_type`` (the label), enforced per class;
* secondary: configurable fields (default ``inscription_present`` and ``site``), balanced
  approximately by interleaving within each class. Secondary balancing can never break
  artifact grouping, because it only changes the *order* in which whole artifacts are
  dealt out.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from dataclasses import field as dc_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .classes import ClassSpec, eligibility
from .loader import DatasetRecord, LoadedDataset
from .schema import ROOT, load_config

MANIFEST_VERSION = "1.0.0"
HOLDOUT_PARTITIONS = ("train", "val", "test")
DEFAULT_MANIFEST_DIR = ROOT / "data" / "metadata" / "splits"

Strategy = Literal["holdout", "grouped_kfold", "auto", "adopted"]


class SplitError(RuntimeError):
    """A split was refused. ``problems`` lists every reason."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(problems)
        super().__init__("split refused:\n  - " + "\n  - ".join(self.problems))


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SplitSettings:
    seed: int
    ratios: tuple[float, float, float]
    min_artifacts_per_class_for_holdout: int
    k_folds: int
    stratify_by: str
    balance_secondary: tuple[str, ...]
    manifest_dir: Path

    @classmethod
    def from_config(cls, config: dict[str, Any] | None = None) -> SplitSettings:
        section = (config or load_config()).get("split", {})
        ratios = (float(section.get("train", 0.7)), float(section.get("val", 0.15)),
                  float(section.get("test", 0.15)))
        if abs(sum(ratios) - 1.0) > 1e-9 or min(ratios) <= 0:
            raise SplitError([f"split proportions must be positive and sum to 1, got {ratios}"])
        manifest_dir = Path(section.get("manifest_dir", "data/metadata/splits"))
        return cls(
            seed=int(section.get("seed", 0)),
            ratios=ratios,
            min_artifacts_per_class_for_holdout=int(
                section.get("min_artifacts_per_class_for_holdout", 20)),
            k_folds=int(section.get("k_folds", 5)),
            stratify_by=str(section.get("stratify_by", "script_type")),
            balance_secondary=tuple(section.get("balance_secondary", ())),
            manifest_dir=manifest_dir if manifest_dir.is_absolute() else ROOT / manifest_dir,
        )


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #


@dataclass
class SplitManifest:
    strategy: str
    seed: int
    group_key: str
    stratify_by: str
    balance_secondary: list[str]
    classes: list[str]
    dataset_fingerprint: str
    image_set_fingerprint: str
    source: str
    assignments: dict[str, str]                 # artifact_id -> partition
    images: dict[str, list[str]]                # artifact_id -> image_ids
    excluded: dict[str, str] = dc_field(default_factory=dict)  # artifact_id -> reason
    ratios: list[float] | None = None
    k: int | None = None
    summary: dict[str, Any] = dc_field(default_factory=dict)
    warnings: list[str] = dc_field(default_factory=list)
    created_utc: str = ""
    manifest_version: str = MANIFEST_VERSION

    # -- queries ------------------------------------------------------------

    @property
    def partitions(self) -> list[str]:
        if self.strategy == "grouped_kfold":
            return [f"fold_{i}" for i in range(int(self.k or 0))]
        return list(HOLDOUT_PARTITIONS)

    def artifacts_in(self, partition: str) -> set[str]:
        return {a for a, p in self.assignments.items() if p == partition}

    def images_in(self, partition: str) -> set[str]:
        return {i for a in self.artifacts_in(partition) for i in self.images.get(a, [])}

    def fold_partitions(self, fold: int) -> dict[str, set[str]]:
        """For k-fold: artifacts for training and validation when ``fold`` is held out."""
        if self.strategy != "grouped_kfold":
            raise SplitError([f"fold_partitions() needs a grouped_kfold manifest, not {self.strategy}"])
        held = f"fold_{fold}"
        if held not in self.partitions:
            raise SplitError([f"fold {fold} out of range for k={self.k}"])
        return {
            "train": {a for a, p in self.assignments.items() if p != held},
            "val": self.artifacts_in(held),
        }

    @property
    def digest(self) -> str:
        """Identity of the split itself. Excludes the creation time, so two runs of the
        same inputs give the same digest (the determinism tests rely on this)."""
        core = {
            "strategy": self.strategy, "seed": self.seed, "k": self.k, "ratios": self.ratios,
            "dataset_fingerprint": self.dataset_fingerprint,
            "assignments": dict(sorted(self.assignments.items())),
            "excluded": dict(sorted(self.excluded.items())),
        }
        blob = json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(blob).hexdigest()

    # -- io -----------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["digest"] = self.digest
        return data

    def save(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path | str) -> SplitManifest:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        stored_digest = data.pop("digest", None)
        manifest = cls(**data)
        if stored_digest is not None and stored_digest != manifest.digest:
            raise SplitError([f"{path}: manifest digest mismatch; the file was edited by hand"])
        return manifest

    def default_filename(self) -> str:
        return f"split_{self.strategy}_{self.dataset_fingerprint[:12]}_seed{self.seed}.json"


# --------------------------------------------------------------------------- #
# Preconditions
# --------------------------------------------------------------------------- #


def _eligible_artifacts(
    dataset: LoadedDataset, spec: ClassSpec
) -> tuple[dict[str, list[DatasetRecord]], dict[str, str], list[str]]:
    """Group eligible records by artifact. Returns (eligible, excluded, problems)."""
    eligible: dict[str, list[DatasetRecord]] = defaultdict(list)
    excluded: dict[str, str] = {}
    problems: list[str] = []

    for aid, recs in dataset.by_artifact().items():
        verdicts = {eligibility(r, spec) for r in recs}
        ok_flags = {ok for ok, _ in verdicts}
        if ok_flags == {False}:
            excluded[aid] = min(reason for _, reason in verdicts)
            continue
        if ok_flags == {True, False}:
            problems.append(
                f"artifact '{aid}' has some photographs eligible and some not "
                f"({sorted(reason for _, reason in verdicts)}); an artifact is eligible "
                "or excluded as a whole"
            )
            continue
        labels = {r.script_type for r in recs}
        if len(labels) > 1:
            problems.append(
                f"artifact '{aid}' has inconsistent script_type across photographs "
                f"{sorted(labels)}; script_type describes the sherd, not the photograph"
            )
            continue
        eligible[aid] = sorted(recs, key=lambda r: r.image_id)
    return dict(sorted(eligible.items())), excluded, problems


def check_splittable(
    dataset: LoadedDataset,
    spec: ClassSpec,
    settings: SplitSettings,
    strategy: Strategy = "auto",
) -> tuple[str, list[str]]:
    """Decide the concrete strategy, or list why no split can be made.

    Returns ``(resolved_strategy, problems)``; a non-empty ``problems`` means refuse.
    """
    problems: list[str] = []
    if dataset.is_empty:
        return strategy, [("no records: there is nothing to split, and a split will not be "
                           "fabricated for an empty dataset")]
    if not dataset.ok:
        problems.append(
            f"dataset is invalid ({len(dataset.rejections)} rejected record(s)); "
            "fix validation errors before splitting"
        )
        return strategy, problems

    preassigned = sorted({r.split for r in dataset.records} & set(HOLDOUT_PARTITIONS))
    if preassigned:
        problems.append(
            f"records already carry split assignments ({', '.join(preassigned)}). Re-splitting "
            "after a test set exists would invalidate any result measured on it. Use "
            "adopt_existing_split() to build a manifest from the existing assignment."
        )

    eligible, _, grouping = _eligible_artifacts(dataset, spec)
    problems.extend(grouping)

    per_class = Counter(recs[0].script_type for recs in eligible.values())
    missing = [c for c in spec.trainable if per_class.get(c, 0) == 0]
    if missing:
        problems.append(
            f"no artifacts at all for trainable class(es): {', '.join(missing)}. A classifier "
            "cannot be split, trained or evaluated for a class with no examples"
        )

    t, k = settings.min_artifacts_per_class_for_holdout, settings.k_folds
    holdout_ok = all(per_class.get(c, 0) >= t for c in spec.trainable)
    kfold_ok = all(per_class.get(c, 0) >= k for c in spec.trainable)
    counts = ", ".join(f"{c}={per_class.get(c, 0)}" for c in spec.trainable)

    resolved = strategy
    if strategy == "auto":
        resolved = "holdout" if holdout_ok else "grouped_kfold"
    if resolved == "holdout" and not holdout_ok:
        problems.append(
            f"holdout needs >= {t} artifacts per class (configs/project.yaml "
            f"split.min_artifacts_per_class_for_holdout); have {counts}"
        )
    if resolved == "grouped_kfold" and not kfold_ok:
        problems.append(
            f"grouped k-fold (k={k}) needs >= {k} artifacts per class so every class can "
            f"appear in every fold; have {counts}"
        )
    return resolved, list(dict.fromkeys(problems))


# --------------------------------------------------------------------------- #
# Assignment
# --------------------------------------------------------------------------- #


def _stable_int(*parts: Any) -> int:
    blob = "\x1f".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(blob).digest()[:8], "big")


def _secondary_key(recs: list[DatasetRecord], fields: Sequence[str]) -> tuple[str, ...]:
    """Secondary stratification key of an artifact: its (first photograph's) values."""
    first = recs[0]
    return tuple(str(first.get(f)) for f in fields)


def _interleave(
    artifacts: dict[str, list[DatasetRecord]], fields: Sequence[str], seed: int, label: str
) -> list[str]:
    """Order one class's artifacts so secondary groups are spread evenly.

    Each secondary group is shuffled with a seed derived from (seed, label, group); the
    groups are then drawn round-robin, largest first. Dealing this order out to the
    partitions by proportional deficit spreads each group across partitions in
    proportion to its size.
    """
    groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for aid, recs in artifacts.items():
        groups[_secondary_key(recs, fields)].append(aid)
    shuffled: list[list[str]] = []
    for key in sorted(groups):
        members = sorted(groups[key])
        random.Random(_stable_int(seed, label, *key)).shuffle(members)
        shuffled.append(members)
    shuffled.sort(key=lambda g: (-len(g), g[0]))
    order: list[str] = []
    while any(shuffled):
        for g in shuffled:
            if g:
                order.append(g.pop(0))
    return order


def _deal(order: list[str], names: Sequence[str], ratios: Sequence[float]) -> dict[str, str]:
    """Assign items to partitions, always to the one furthest below its target share.

    Deterministic (ties go to the earlier partition). Every partition receives at least
    one item when ``len(order) >= len(names)``: the first pass seeds each partition in
    order of largest ratio, which is what guarantees every class appears in every split.
    """
    out: dict[str, str] = {}
    counts = dict.fromkeys(names, 0)
    items = list(order)
    if len(items) >= len(names):
        for name in sorted(names, key=lambda n: -ratios[list(names).index(n)]):
            out[items.pop(0)] = name
            counts[name] += 1
    for item in items:
        total = sum(counts.values()) + 1
        deficits = [(ratios[i] * total - counts[n], -i) for i, n in enumerate(names)]
        _, neg_i = max(deficits)
        name = names[-neg_i]
        out[item] = name
        counts[name] += 1
    return out


def _summarise(
    manifest_assignments: dict[str, str],
    eligible: dict[str, list[DatasetRecord]],
    partitions: Sequence[str],
    secondary: Sequence[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for part in partitions:
        aids = [a for a, p in manifest_assignments.items() if p == part]
        by_class_art = Counter(eligible[a][0].script_type for a in aids)
        by_class_img = Counter()
        for a in aids:
            by_class_img[eligible[a][0].script_type] += len(eligible[a])
        entry: dict[str, Any] = {
            "artifacts": len(aids),
            "images": sum(len(eligible[a]) for a in aids),
            "artifacts_by_class": dict(sorted(by_class_art.items())),
            "images_by_class": dict(sorted(by_class_img.items())),
        }
        for f in secondary:
            entry[f"artifacts_by_{f}"] = dict(sorted(
                Counter(str(eligible[a][0].get(f)) for a in aids).items()))
        summary[part] = entry
    return summary


def make_split(
    dataset: LoadedDataset,
    spec: ClassSpec | None = None,
    settings: SplitSettings | None = None,
    *,
    strategy: Strategy = "auto",
    seed: int | None = None,
) -> SplitManifest:
    """Create a split manifest, or raise :class:`SplitError` with every reason.

    Pure: reads the dataset, writes nothing. Identical inputs and seed give an
    identical manifest digest.
    """
    spec = spec or ClassSpec.from_config()
    settings = settings or SplitSettings.from_config()
    seed = settings.seed if seed is None else int(seed)

    resolved, problems = check_splittable(dataset, spec, settings, strategy)
    if problems:
        raise SplitError(problems)

    eligible, excluded, _ = _eligible_artifacts(dataset, spec)
    if resolved == "holdout":
        names: list[str] = list(HOLDOUT_PARTITIONS)
        ratios: list[float] = list(settings.ratios)
    else:
        names = [f"fold_{i}" for i in range(settings.k_folds)]
        ratios = [1.0 / settings.k_folds] * settings.k_folds

    assignments: dict[str, str] = {}
    for label in spec.trainable:
        members = {a: r for a, r in eligible.items() if r[0].script_type == label}
        order = _interleave(members, settings.balance_secondary, seed, label)
        assignments.update(_deal(order, names, ratios))

    warnings: list[str] = []
    if resolved == "grouped_kfold":
        warnings.append(
            "grouped k-fold selected: too few artifacts per class for a single held-out test "
            "set. Report cross-validated results as such; there is no untouched test set."
        )
    held = sorted({r for r in excluded.values() if r.startswith("held_out_label")})
    if held:
        warnings.append(f"held-out labels present and excluded from this split: {held}")

    manifest = SplitManifest(
        strategy=resolved,
        seed=seed,
        group_key="artifact_id",
        stratify_by=settings.stratify_by,
        balance_secondary=list(settings.balance_secondary),
        classes=list(spec.trainable),
        dataset_fingerprint=dataset.fingerprint,
        image_set_fingerprint=dataset.image_fingerprint,
        source=dataset.source,
        assignments=dict(sorted(assignments.items())),
        images={a: [r.image_id for r in recs] for a, recs in eligible.items()},
        excluded=dict(sorted(excluded.items())),
        ratios=ratios if resolved == "holdout" else None,
        k=settings.k_folds if resolved == "grouped_kfold" else None,
        summary=_summarise(assignments, eligible, names, settings.balance_secondary),
        warnings=warnings,
        created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    errors = verify_manifest(manifest, dataset)
    if errors:  # pragma: no cover - defensive; the algorithm cannot produce these
        raise SplitError(["internal error, generated split failed verification:", *errors])
    return manifest


def adopt_existing_split(
    dataset: LoadedDataset, spec: ClassSpec | None = None, *, seed: int | None = None
) -> SplitManifest:
    """Build a manifest from ``split`` values already in the records, after verifying them.

    For datasets whose partition was fixed earlier (e.g. a published benchmark split).
    Every eligible artifact must already be in train, val or test.
    """
    spec = spec or ClassSpec.from_config()
    settings = SplitSettings.from_config()
    if dataset.is_empty:
        raise SplitError(["no records to adopt a split from"])
    if not dataset.ok:
        raise SplitError(["dataset is invalid; fix validation errors first"])
    eligible, excluded, problems = _eligible_artifacts(dataset, spec)
    assignments: dict[str, str] = {}
    for aid, recs in eligible.items():
        splits = {r.split for r in recs}
        if len(splits) != 1 or next(iter(splits)) not in HOLDOUT_PARTITIONS:
            problems.append(f"artifact '{aid}' has no single train/val/test assignment: {sorted(splits)}")
            continue
        assignments[aid] = next(iter(splits))
    if problems:
        raise SplitError(problems)
    manifest = SplitManifest(
        strategy="adopted", seed=settings.seed if seed is None else seed,
        group_key="artifact_id", stratify_by=settings.stratify_by,
        balance_secondary=list(settings.balance_secondary), classes=list(spec.trainable),
        dataset_fingerprint=dataset.fingerprint, image_set_fingerprint=dataset.image_fingerprint,
        source=dataset.source, assignments=dict(sorted(assignments.items())),
        images={a: [r.image_id for r in recs] for a, recs in eligible.items()},
        excluded=dict(sorted(excluded.items())),
        summary=_summarise(assignments, eligible, HOLDOUT_PARTITIONS, settings.balance_secondary),
        warnings=["split adopted from existing record assignments, not generated"],
        created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    errors = verify_manifest(manifest, dataset)
    if errors:
        raise SplitError(errors)
    return manifest


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #


def verify_partitions(
    partitions: dict[str, Iterable[DatasetRecord]],
) -> list[str]:
    """Check pairwise disjointness of artifacts, image ids and image hashes.

    This is the leakage check, applied to whatever sets a trainer actually uses:
    ``train ∩ val = train ∩ test = val ∩ test = ∅`` for artifacts, and no identical
    photograph (by SHA-256) in two partitions.
    """
    errors: list[str] = []
    owner_art: dict[str, str] = {}
    owner_img: dict[str, str] = {}
    owner_hash: dict[str, str] = {}
    for name, recs in partitions.items():
        for r in recs:
            for table, key, what in ((owner_art, r.artifact_id, "artifact"),
                                     (owner_img, r.image_id, "image_id"),
                                     (owner_hash, r.image_sha256, "image hash")):
                prev = table.setdefault(key, name)
                if prev != name:
                    errors.append(f"{what} {key[:16]}{'...' if len(key) > 16 else ''} is in "
                                  f"both '{prev}' and '{name}'")
    return sorted(set(errors))


def verify_manifest(manifest: SplitManifest, dataset: LoadedDataset) -> list[str]:
    """Check a manifest against the dataset it claims to describe."""
    errors: list[str] = []
    if manifest.dataset_fingerprint != dataset.fingerprint:
        errors.append(
            "manifest was made for a different dataset (fingerprint "
            f"{manifest.dataset_fingerprint[:12]} != {dataset.fingerprint[:12]}); "
            "the records changed since the split was made"
        )
        return errors
    if manifest.group_key != "artifact_id":
        errors.append(f"group_key is {manifest.group_key!r}; only artifact_id is permitted")

    by_art = dataset.by_artifact()
    valid_parts = set(manifest.partitions)
    for aid, part in manifest.assignments.items():
        if part not in valid_parts:
            errors.append(f"artifact '{aid}' assigned to unknown partition {part!r}")
        if aid not in by_art:
            errors.append(f"manifest lists artifact '{aid}' that is not in the dataset")
        elif sorted(manifest.images.get(aid, [])) != sorted(r.image_id for r in by_art[aid]):
            errors.append(f"artifact '{aid}': manifest images differ from dataset images")
    overlap = set(manifest.assignments) & set(manifest.excluded)
    if overlap:
        errors.append(f"artifacts both assigned and excluded: {sorted(overlap)}")
    unaccounted = set(by_art) - set(manifest.assignments) - set(manifest.excluded)
    if unaccounted:
        errors.append(f"artifacts neither assigned nor excluded: {sorted(unaccounted)}")

    for aid, part in manifest.assignments.items():
        if manifest.strategy in ("holdout", "adopted"):
            for r in by_art.get(aid, []):
                if r.split in HOLDOUT_PARTITIONS and r.split != part:
                    errors.append(f"record '{r.image_id}' says split={r.split} but the "
                                  f"manifest puts artifact '{aid}' in {part}")

    groups: dict[str, list[DatasetRecord]] = defaultdict(list)
    for aid, part in manifest.assignments.items():
        groups[part].extend(by_art.get(aid, []))
    errors.extend(verify_partitions(groups))
    return errors


def partition_records(
    manifest: SplitManifest, dataset: LoadedDataset, *, fold: int | None = None
) -> dict[str, list[DatasetRecord]]:
    """Materialise partitions as record lists, verifying leakage on the way out.

    Holdout/adopted manifests give ``train``/``val``/``test``. K-fold manifests need
    ``fold`` and give ``train``/``val`` for that fold.
    """
    errors = verify_manifest(manifest, dataset)
    if errors:
        raise SplitError(errors)
    by_art = dataset.by_artifact()
    if manifest.strategy == "grouped_kfold":
        if fold is None:
            raise SplitError(["a grouped_kfold manifest needs a fold index"])
        parts = manifest.fold_partitions(fold)
    else:
        parts = {p: manifest.artifacts_in(p) for p in HOLDOUT_PARTITIONS}
    out = {name: [r for a in sorted(aids) for r in by_art[a]] for name, aids in parts.items()}
    errors = verify_partitions(out)
    if errors:  # pragma: no cover - verify_manifest already covers this
        raise SplitError(errors)
    return out


def latest_manifest(manifest_dir: Path | None = None, fingerprint: str | None = None) -> Path | None:
    """Newest manifest in ``manifest_dir`` (optionally for one dataset fingerprint)."""
    manifest_dir = manifest_dir or SplitSettings.from_config().manifest_dir
    if not manifest_dir.is_dir():
        return None
    pattern = f"split_*_{fingerprint[:12]}_seed*.json" if fingerprint else "split_*.json"
    found = sorted(manifest_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
    return found[-1] if found else None


__all__ = [
    "DEFAULT_MANIFEST_DIR",
    "HOLDOUT_PARTITIONS",
    "MANIFEST_VERSION",
    "SplitError",
    "SplitManifest",
    "SplitSettings",
    "adopt_existing_split",
    "check_splittable",
    "latest_manifest",
    "make_split",
    "partition_records",
    "verify_manifest",
    "verify_partitions",
]
