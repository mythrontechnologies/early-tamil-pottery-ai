"""Reversible label promotion (Milestone 8): expert annotations -> training records.

Annotations never edit ``records.jsonl`` directly. The ONLY path from an annotation to a
training label is this explicit, audited, reversible process:

    annotation store
      -> validation            the whole store passes N1-N14, or nothing is planned
      -> agreement / review    resolve_artifact: only status ``expert_label`` (current expert
                               annotations, all ``expert_reviewed``, agreeing) is eligible
      -> promotion candidate   per-artifact checks P1-P10 (below)
      -> dry-run report        field-by-field before/after, dataset validation of the result,
                               and a ``plan_digest`` over all of it
      -> human approval        ``--execute --approve <plan_digest> --approver <id>``
      -> training record       atomic rewrite of records.jsonl + append-only promotion log

Candidate checks (a failure rejects the artifact, with the reason, and never blocks others):

``P1`` resolution status is ``expert_label``. Disputed, provisional (project-only),
       project-disagreement and unannotated artifacts are rejected; AI predictions never count
``P2`` every source annotation is a current, ``expert_reviewed`` ``expert_annotation`` with a
       stated qualification
``P3`` the experts also agree on ``inscription_present``
``P4`` the label is representable in the record (``other_script`` needs the script's name,
       which the annotation schema does not record)
``P5`` the artifact and every annotated photograph exist in the records; regions can be
       converted to pixels
``P6`` no silent overwrite: a record whose label came from anywhere else is left alone
``P7`` the photograph's SHA-256 on disk equals the record's (when the image is present)
``P8`` only ``promotion.writable_fields`` change; provenance, rights, path, SHA-256, site and
       split are verified unchanged
``P9`` the promoted records pass the dataset validator (E*/R* rules)
``P10`` the object is an original: no expert records it as a ``reproduction`` or leaves it
       ``uncertain``, and an artifact carrying a ``possible_reproduction`` review flag
       (``annotation_pilot.review_flags``) is refused until every expert states ``original``.
       A reproduction duplicates another artifact's inscription under a different id, which
       the split protection cannot see.

What is promoted, and how uncertainty survives it:

* ``label_source = expert_annotation``; ``label_confidence`` is the LOWEST expert confidence.
* Regions are converted to pixel ``xywh`` and name the annotator and annotation id.
* A reading is promoted only if every expert gave the same one. Otherwise ``transcription``
  stays ``not_available``, ``reading_status = disputed`` and every reading is preserved in
  ``alternative_readings`` with its attribution.
* A personal name receives no translation (``not_applicable``); a translation is promoted
  only when it names its source.
* A date range is promoted only if every expert gave the same range; differing ranges are
  recorded as ``dating_reliability = disputed`` with no numeric bounds and each position in
  ``dating_text``. An expert estimate is ``project_estimate``, never ``published_secure``.
  ``dating_source`` names every cited reference with its EFFECTIVE verification status.
* ``verification_status`` of the record is not touched: an expert label is not a check of the
  record against its cited source.

Reversal: ``revert`` restores each changed record's exact pre-promotion state, provided the
record has not changed since (otherwise it refuses). It is dry-run by default too. The
promotion log is append-only; a reversal is a new entry, not an erasure.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.dataset.convert import read_jsonl, write_jsonl
from src.dataset.schema import (
    RESEARCH_DATA_ROOT,
    RESEARCH_RECORDS_PATH,
    ROOT,
    load_config,
)
from src.dataset.validation import sha256_file, validate_records
from src.integrity import append_line, verify

from .model import is_real, region_to_pixels, utc_now
from .pilot import load_review_flags
from .resolve import resolve_artifact
from .store import AnnotationStore

LOG_SCHEMA_VERSION = "1.0.0"
CONFIDENCE_MAP = {"high": "high", "moderate": "medium", "low": "low", "very_low": "low"}
CONFIDENCE_RANK = ("unknown", "low", "medium", "high")
REJECTION_BY_STATUS = {
    "disputed": "P1 disputed: annotations disagree or are marked disputed; disputed annotations are "
                "never promoted (requires expert resolution)",
    "provisional": "P1 project annotations only: a project label never becomes an expert label",
    "project_disagreement": "P1 project annotators disagree and no expert has annotated",
    "unannotated": "P1 no human annotation (AI predictions are never labels)",
}


class PromotionError(RuntimeError):
    """A promotion or reversal was refused. Nothing has been written."""


def _settings(config: dict[str, Any] | None) -> tuple[Path, tuple[str, ...]]:
    p = (config or load_config()).get("promotion", {})
    log = ROOT / p.get("log", "data/metadata/promotions/promotion_log.jsonl")
    return log, tuple(p.get("writable_fields", ()))


def _rel(path: Path) -> str:
    """Repository-relative POSIX path when inside the repository (portable audit log)."""
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(Path(path).resolve())


def _abs(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def _sha_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "absent"


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _encoding(text: str) -> str:
    """Script of a reading from its Unicode block: a property of the string, not a judgement."""
    kinds = set()
    for ch in text:
        cp = ord(ch)
        if 0x11000 <= cp <= 0x1107F:
            kinds.add("brahmi_unicode")
        elif 0x0B80 <= cp <= 0x0BFF:
            kinds.add("tamil_unicode")
        elif ch.isalpha():
            kinds.add("romanized")
    return kinds.pop() if len(kinds) == 1 else ("mixed" if kinds else "not_available")


# --------------------------------------------------------------------------- #
# Plan structures
# --------------------------------------------------------------------------- #


@dataclass
class RecordChange:
    image_id: str
    artifact_id: str
    image_sha256: str
    changed_fields: list[str]
    before: dict[str, Any]
    after: dict[str, Any]


@dataclass
class Candidate:
    artifact_id: str
    label: str
    source_annotation_ids: list[str]
    changes: list[RecordChange] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Rejection:
    artifact_id: str
    status: str
    reasons: list[str]


@dataclass
class PromotionPlan:
    records_path: str
    records_sha256: str
    annotations_sha256: str
    registry_sha256: str
    candidates: list[Candidate]
    rejections: list[Rejection]
    unchanged: list[str]
    validation_status: str
    validation_errors: list[str]
    plan_digest: str = ""
    dry_run: bool = True
    annotations_ledger_head: str = ""   # src.integrity chain head of the annotation store

    @property
    def executable(self) -> bool:
        return bool(self.candidates) and self.validation_status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"executable": self.executable}


# --------------------------------------------------------------------------- #
# Building the promoted record
# --------------------------------------------------------------------------- #


def _ref_status_text(ref_ids: set[str], statuses: dict[str, str]) -> str:
    return ", ".join(f"{r} ({statuses.get(r, 'not in knowledge base')})" for r in sorted(ref_ids)) or "none"


def _promoted(rec: dict[str, Any], label: str, experts: list[dict[str, Any]],
              statuses: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    """The record after promotion, and notes for the report. Pure."""
    new, notes = deepcopy(rec), []
    ids = [a["annotation_id"] for a in experts]
    via = ", ".join(ids)
    ins0 = experts[0]["inscription"]
    new["inscription_present"] = ins0["inscription_present"]
    new["script_type"] = label
    new["label_source"] = "expert_annotation"
    confs = [CONFIDENCE_MAP.get(a["inscription"]["script_confidence"], "unknown") for a in experts]
    new["label_confidence"] = min(confs, key=CONFIDENCE_RANK.index)

    w, h = rec.get("image_width_px"), rec.get("image_height_px")
    regions = []
    for a in experts:
        for r in a["inscription"].get("regions", []):
            if r["image_id"] != rec["image_id"]:
                continue
            px = region_to_pixels(r, w, h)
            regions.append({**px, "region_label": r["label"], "annotator": a["annotator"]["annotator_id"],
                            "notes": f"expert annotation {a['annotation_id']}"
                                     + (f"; {r['note']}" if r.get("note") else "")})
    new["inscription_regions"] = regions
    counts = {a["inscription"].get("characters_visible") for a in experts}
    new["character_count_visible"] = counts.pop() if len(counts) == 1 else None

    if label == "none":
        for f in ("transcription", "transliteration", "translation_en", "translation_ta"):
            new[f] = "not_applicable"
        new.update(transcription_encoding="not_applicable", transliteration_scheme="not_applicable",
                   reading_status="not_applicable", alternative_readings=[], reading_source="not_applicable")
    else:
        readings = {a["annotation_id"]: a["inscription"]["reading"] for a in experts
                    if is_real(a["inscription"]["reading"]) and a["inscription"]["reading"] != "not_applicable"}
        alts = []
        for a in experts:
            for r in a["inscription"].get("alternative_readings", []):
                alts.append(f"{r['reading']} ({r['source']}; via {a['annotation_id']})")
        distinct = {" ".join(r.split()) for r in readings.values()}
        if readings and len(distinct) == 1 and len(readings) == len(experts):
            reading = next(iter(readings.values()))
            src = {a["inscription"]["reading_source"] for a in experts}
            new["transcription"] = reading
            new["transcription_encoding"] = _encoding(reading)
            tls = {a["inscription"].get("transliteration", "not_available") for a in experts}
            tl = tls.pop() if len(tls) == 1 else "not_available"
            new["transliteration"] = tl
            schemes = {a["inscription"].get("transliteration_scheme", "not_available") for a in experts}
            new["transliteration_scheme"] = schemes.pop() if len(schemes) == 1 and is_real(tl) else "not_available"
            new["reading_status"] = "unknown"
            new["reading_source"] = (f"expert annotation(s) {via}; reading source: "
                                     f"{', '.join(sorted(src))}; not a published reading")
        elif readings:
            new["transcription"] = "not_available"
            new["transcription_encoding"] = "not_available"
            new["transliteration"] = "not_available"
            new["transliteration_scheme"] = "not_available"
            new["reading_status"] = "disputed"
            new["reading_source"] = f"expert annotations {via} give different readings"
            alts = [f"{r} (expert annotation {aid})" for aid, r in sorted(readings.items())] + alts
            notes.append("Experts disagree on the reading: no transcription promoted; every reading "
                         "kept in alternative_readings.")
        else:
            new["reading_status"] = "unread"
        new["alternative_readings"] = alts
        # Translation: only a sourced translation all experts share; never for a name.
        interps = {(a["interpretation"]["interpretation_type"], a["interpretation"]["translation"],
                    a["interpretation"]["translation_source"]) for a in experts}
        if len(interps) == 1:
            itype, tr, tsrc = interps.pop()
            if itype == "personal_name":
                new["translation_en"] = "not_applicable"
            elif is_real(tr) and is_real(tsrc) and new["transcription"] != "not_available":
                new["translation_en"] = tr
            else:
                new["translation_en"] = "not_available"
        else:
            new["translation_en"] = "not_available"
            notes.append("Experts differ on interpretation/translation: none promoted.")

    # Dating: identical expert ranges only; otherwise the disagreement is recorded, not resolved.
    ranges = {(a["dating"]["estimated_start_year"], a["dating"]["estimated_end_year"]) for a in experts}
    dated = [a for a in experts if a["dating"]["estimated_start_year"] is not None
             or a["dating"]["estimated_end_year"] is not None]
    if dated:
        cited = {e["source_reference"] for a in dated for e in a["dating"]["dating_evidence"]
                 if e["source_reference"] not in ("annotator_observation", "this_annotator")}
        basis = sorted({b for a in dated for b in a["dating"]["dating_basis"]
                        if b not in ("not_available", "unknown")})
        refs_text = _ref_status_text(cited, statuses)
        if len(ranges) == 1 and len(dated) == len(experts):
            lo, hi = next(iter(ranges))
            new["dating_lower_year"], new["dating_upper_year"] = lo, hi
            new["dating_basis"] = basis or ["not_available"]
            new["dating_reliability"] = "project_estimate"
            from src.dating.chronology import format_range

            new["dating_text"] = f"{format_range(lo, hi)} (expert estimate; not a published date)"
            new["dating_source"] = f"expert annotation(s) {via}; references cited: {refs_text}"
        else:
            from src.dating.chronology import format_range

            positions = "; ".join(
                f"{a['annotation_id']}: "
                + (format_range(a['dating']['estimated_start_year'], a['dating']['estimated_end_year'])
                   if a in dated else "no range")
                for a in experts)
            new["dating_lower_year"] = new["dating_upper_year"] = None
            new["dating_basis"] = ["not_available"]
            new["dating_reliability"] = "disputed"
            new["dating_text"] = f"Experts disagree (not averaged): {positions}"
            new["dating_source"] = f"expert annotations {via}; references cited: {refs_text}"
            notes.append("Experts give different date ranges: no numeric bounds promoted.")
        if any(statuses.get(r) != "verified_against_source" for r in cited):
            notes.append(f"Dating cites unverified reference(s): {refs_text}; marked as such.")

    quals = "; ".join(f"{a['annotator']['annotator_id']} ({a['annotator'].get('qualification', '')})"
                      for a in experts)
    new["annotator"] = quals
    new["annotation_date"] = max(a["created_utc"][:10] for a in experts)
    tag = (f"Milestone 8 label promotion from expert annotation(s) {via}; audit trail: "
           "data/metadata/promotions/promotion_log.jsonl.")
    base = rec.get("notes", "not_available")
    new["notes"] = tag if not is_real(base) else base if tag in base else f"{base} | {tag}"
    return new, notes


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #


def plan_promotion(
    *,
    store: AnnotationStore | None = None,
    records_path: Path | None = None,
    data_root: Path | None = None,
    artifact_ids: list[str] | None = None,
    config: dict[str, Any] | None = None,
    ref_statuses: dict[str, str] | None = None,
    registry_path: Path | None = None,
    knowledge_ref_ids: set[str] | None = None,
    verified_ref_ids: set[str] | None = None,
) -> PromotionPlan:
    """Build the promotion plan. Reads only; writes nothing."""
    records_path = Path(records_path or RESEARCH_RECORDS_PATH)
    data_root = Path(data_root) if data_root else (RESEARCH_DATA_ROOT if records_path == RESEARCH_RECORDS_PATH else None)
    store = store or AnnotationStore(records_path=records_path)
    _, writable = _settings(config)
    if ref_statuses is None or knowledge_ref_ids is None or verified_ref_ids is None:
        from src.knowledge.verification import effective_statuses
        from src.knowledge.verification import registry_path as _rp

        eff = effective_statuses()
        ref_statuses = ref_statuses if ref_statuses is not None else {k: v.effective_status for k, v in eff.items()}
        knowledge_ref_ids = knowledge_ref_ids if knowledge_ref_ids is not None else set(eff)
        verified_ref_ids = verified_ref_ids if verified_ref_ids is not None else {k for k, v in eff.items() if v.verified}
        registry_path = registry_path or _rp(config)

    records = read_jsonl(records_path) if records_path.exists() else []
    by_art: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_art.setdefault(r["artifact_id"], []).append(r)
    plan = PromotionPlan(
        records_path=_rel(records_path), records_sha256=_sha_text(records_path),
        annotations_sha256=_sha_text(store.path), annotations_ledger_head=verify(store.path).head,
        registry_sha256=_sha_text(Path(registry_path)) if registry_path else "absent",
        candidates=[], rejections=[], unchanged=[], validation_status="FAIL", validation_errors=[])

    validation = store.validate(knowledge_ref_ids=knowledge_ref_ids, verified_ref_ids=verified_ref_ids)
    if not validation.ok:
        plan.validation_errors = [f"annotation store invalid: {p}" for p in validation.problems]
        plan.plan_digest = _digest(_digest_body(plan))
        return plan

    flags = load_review_flags(config)
    current = store.current()
    wanted = sorted(set(artifact_ids) if artifact_ids else {a["artifact_id"] for a in current})
    for art in wanted:
        res = resolve_artifact(art, current)
        if res.status != "expert_label" or not res.ground_truth_eligible:
            reason = REJECTION_BY_STATUS.get(res.status, f"P1 status {res.status}")
            if res.ai_predictions and res.status == "unannotated":
                reason += f" ({len(res.ai_predictions)} AI prediction(s) ignored)"
            plan.rejections.append(Rejection(art, res.status, [reason]))
            continue
        experts = sorted((a for a in current if a["artifact_id"] == art
                          and a["provenance_type"] == "expert_annotation"
                          and a["review_state"] == "expert_reviewed"), key=lambda a: a["annotation_id"])
        reasons = []
        if not experts or any(a["provenance_type"] != "expert_annotation" for a in experts):
            reasons.append("P2 no expert-reviewed expert annotation")
        if any(not is_real(a["annotator"].get("qualification")) for a in experts):
            reasons.append("P2 an expert annotation states no qualification")
        if len({a["inscription"]["inscription_present"] for a in experts}) > 1:
            reasons.append("P3 experts disagree on inscription_present (disputed)")
        if res.label == "other_script":
            reasons.append("P4 'other_script' needs the script's name (script_type_other_detail), which "
                           "the annotation does not record; resolve by hand")
        statuses = {a["object"].get("object_status", "unknown") for a in experts}
        if "reproduction" in statuses:
            reasons.append("P10 an expert records the object as a reproduction: not an archaeological "
                           "object, never a training label")
        elif "uncertain" in statuses:
            reasons.append("P10 an expert records original/reproduction status as uncertain")
        for f in flags.get(art, []):
            if f.kind == "possible_reproduction" and statuses != {"original"}:
                reasons.append(f"P10 {f.label}: every expert must state object_status='original' "
                               f"(related: {f.related_artifact or '-'})")
        recs = sorted(by_art.get(art, []), key=lambda r: r["image_id"])
        if not recs:
            reasons.append("P5 artifact is not in the records")
        rec_ids = {r["image_id"] for r in recs}
        for a in experts:
            for rg in a["inscription"].get("regions", []):
                if rg["image_id"] not in rec_ids:
                    reasons.append(f"P5 region on {rg['image_id']!r}, which is not a record of this artifact")
        if reasons:
            plan.rejections.append(Rejection(art, res.status, reasons))
            continue

        cand = Candidate(art, res.label, [a["annotation_id"] for a in experts])
        if res.disagreements:
            cand.notes.append("Recorded disagreement with other annotators (not resolved by promotion): "
                              + json.dumps(res.disagreements, ensure_ascii=False, sort_keys=True))
        for rec in recs:
            if not isinstance(rec.get("image_width_px"), int) or not isinstance(rec.get("image_height_px"), int):
                reasons.append(f"P5 {rec['image_id']}: image dimensions unknown; regions cannot be converted")
                continue
            if rec.get("script_type") != "unknown" and rec.get("label_source") != "expert_annotation":
                reasons.append(f"P6 {rec['image_id']} already has script_type={rec.get('script_type')!r} "
                               f"from label_source={rec.get('label_source')!r}; no silent overwrite")
                continue
            if data_root is not None and is_real(rec.get("image_sha256")):
                img = data_root / rec["image_path"]
                if img.is_file() and sha256_file(img) != rec["image_sha256"]:
                    reasons.append(f"P7 {rec['image_id']}: file SHA-256 differs from the record")
                    continue
            after, notes = _promoted(rec, res.label, experts, ref_statuses)
            changed = sorted(k for k in set(rec) | set(after) if rec.get(k, ...) != after.get(k, ...))
            illegal = [k for k in changed if k not in writable]
            if illegal:
                reasons.append(f"P8 {rec['image_id']}: would change protected field(s) {illegal}")
                continue
            if not changed:
                continue
            cand.changes.append(RecordChange(rec["image_id"], art, rec.get("image_sha256", "unknown"),
                                             changed, deepcopy(rec), after))
            cand.notes += [n for n in notes if n not in cand.notes]
        if reasons:
            plan.rejections.append(Rejection(art, res.status, reasons))
        elif not cand.changes:
            plan.unchanged.append(art)
        else:
            plan.candidates.append(cand)

    # P9: validate the dataset as it would be after promotion; reject candidates with findings.
    # Each pass removes at least one candidate, so this terminates.
    while True:
        after_records = _apply(records, plan.candidates)
        result = validate_records(after_records, data_root=data_root,
                                  verify_hashes=data_root is not None)
        bad: dict[str, list[str]] = {}
        for f in result.errors:
            owner = next((c for c in plan.candidates if any(ch.image_id == f.image_id for ch in c.changes)), None)
            if owner is not None:
                bad.setdefault(owner.artifact_id, []).append(f"P9 {f.rule} {f.image_id}: {f.message}")
        if not bad:
            plan.validation_status = "FAIL" if result.errors else "PASS"
            plan.validation_errors = [str(f) for f in result.errors]
            break
        for c in [c for c in plan.candidates if c.artifact_id in bad]:
            plan.candidates.remove(c)
            plan.rejections.append(Rejection(c.artifact_id, "expert_label", bad[c.artifact_id]))
    plan.rejections.sort(key=lambda r: r.artifact_id)
    plan.plan_digest = _digest(_digest_body(plan))
    return plan


def _digest_body(plan: PromotionPlan) -> dict[str, Any]:
    d = asdict(plan)
    d.pop("plan_digest", None)
    d.pop("dry_run", None)
    return d


def _apply(records: list[dict[str, Any]], candidates: list[Candidate]) -> list[dict[str, Any]]:
    after = {ch.image_id: ch.after for c in candidates for ch in c.changes}
    return [deepcopy(after.get(r["image_id"], r)) for r in records]


# --------------------------------------------------------------------------- #
# Writing (only on explicit approval)
# --------------------------------------------------------------------------- #


def _write_records_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    tmp = path.with_name(path.name + f".tmp-{uuid.uuid4().hex[:8]}")
    try:
        write_jsonl(tmp, records)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _append_log(log: Path, entry: dict[str, Any]) -> None:
    """Append-only, ledger-chained (src.integrity): a tampered log refuses further entries."""
    append_line(log, json.dumps(entry, ensure_ascii=False, sort_keys=True))


def read_log(log: Path | None = None, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    log = Path(log) if log else _settings(config)[0]
    if not log.exists():
        return []
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]


def _check_approval(approver: str | None, approve: str | None, digest: str) -> None:
    if not approver or not approver.strip():
        raise PromotionError("an approver id is required: a human must approve every write")
    if approve != digest:
        raise PromotionError("approval does not match the current plan digest; re-run the dry run, "
                             "review it, and approve the digest it prints")


def execute_promotion(plan_fn: Callable[[], PromotionPlan], *, approver: str | None, approve: str | None,
                      log: Path | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Re-plan, check the approval matches, write the records, append the audit entry."""
    plan = plan_fn()
    _check_approval(approver, approve, plan.plan_digest)
    if not plan.executable:
        raise PromotionError("nothing to promote, or the promoted dataset would not validate: "
                             + "; ".join(plan.validation_errors[:5]))
    log = Path(log) if log else _settings(config)[0]
    path = _abs(plan.records_path)
    records = read_jsonl(path)
    if _sha_text(path) != plan.records_sha256:
        raise PromotionError("records.jsonl changed while planning; re-run the dry run")
    after = _apply(records, plan.candidates)
    entry = {
        "log_schema_version": LOG_SCHEMA_VERSION,
        "promotion_id": "prm_" + uuid.uuid4().hex[:16],
        "action": "promote",
        "approver": approver.strip(),                                   # type: ignore[union-attr]
        "executed_utc": utc_now(),
        "plan_digest": plan.plan_digest,
        "records_path": _rel(path),
        "records_sha256_before": plan.records_sha256,
        "annotations_sha256": plan.annotations_sha256,
        "annotations_ledger_head": plan.annotations_ledger_head,
        "registry_sha256": plan.registry_sha256,
        "artifacts": [c.artifact_id for c in plan.candidates],
        "source_annotation_ids": {c.artifact_id: c.source_annotation_ids for c in plan.candidates},
        "changes": [asdict(ch) for c in plan.candidates for ch in c.changes],
        "notes": {c.artifact_id: c.notes for c in plan.candidates if c.notes},
    }
    _write_records_atomic(path, after)
    entry["records_sha256_after"] = _sha_text(path)
    _append_log(log, entry)
    return entry


# --------------------------------------------------------------------------- #
# Reversal
# --------------------------------------------------------------------------- #


@dataclass
class RevertPlan:
    promotion_id: str
    records_path: str
    records_sha256: str
    restorable: list[str]
    conflicts: list[str]
    plan_digest: str = ""

    @property
    def executable(self) -> bool:
        return bool(self.restorable) and not self.conflicts

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"executable": self.executable}


def _promotion_entry(promotion_id: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    entry = next((e for e in entries if e.get("action") == "promote"
                  and e.get("promotion_id") == promotion_id), None)
    if entry is None:
        raise PromotionError(f"no promotion {promotion_id!r} in the log")
    if any(e.get("action") == "revert" and e.get("reverts") == promotion_id for e in entries):
        raise PromotionError(f"promotion {promotion_id} has already been reverted")
    return entry


def plan_revert(promotion_id: str, *, records_path: Path | None = None, log: Path | None = None,
                config: dict[str, Any] | None = None) -> RevertPlan:
    """Which records can be restored. Reads only."""
    entry = _promotion_entry(promotion_id, read_log(log, config))
    path = Path(records_path) if records_path else _abs(entry["records_path"])
    current = {r["image_id"]: r for r in read_jsonl(path)}
    rp = RevertPlan(promotion_id, _rel(path), _sha_text(path), [], [])
    for ch in entry["changes"]:
        now = current.get(ch["image_id"])
        if now is None:
            rp.conflicts.append(f"{ch['image_id']}: record no longer exists")
        elif now != ch["after"]:
            rp.conflicts.append(f"{ch['image_id']}: record changed since the promotion; refusing to "
                                "overwrite the newer state")
        else:
            rp.restorable.append(ch["image_id"])
    rp.plan_digest = _digest({k: v for k, v in asdict(rp).items() if k != "plan_digest"})
    return rp


def execute_revert(promotion_id: str, *, approver: str | None, approve: str | None,
                   records_path: Path | None = None, log: Path | None = None,
                   config: dict[str, Any] | None = None) -> dict[str, Any]:
    rp = plan_revert(promotion_id, records_path=records_path, log=log, config=config)
    _check_approval(approver, approve, rp.plan_digest)
    if not rp.executable:
        raise PromotionError("revert refused: " + "; ".join(rp.conflicts or ["nothing to restore"]))
    log = Path(log) if log else _settings(config)[0]
    entry = _promotion_entry(promotion_id, read_log(log))
    before = {ch["image_id"]: ch["before"] for ch in entry["changes"]}
    path = _abs(rp.records_path)
    restored = [deepcopy(before.get(r["image_id"], r)) for r in read_jsonl(path)]
    rev = {
        "log_schema_version": LOG_SCHEMA_VERSION,
        "promotion_id": "prm_" + uuid.uuid4().hex[:16],
        "action": "revert",
        "reverts": promotion_id,
        "approver": approver.strip(),                                   # type: ignore[union-attr]
        "executed_utc": utc_now(),
        "plan_digest": rp.plan_digest,
        "records_path": _rel(path),
        "records_sha256_before": rp.records_sha256,
        "restored_image_ids": rp.restorable,
    }
    _write_records_atomic(path, restored)
    rev["records_sha256_after"] = _sha_text(path)
    _append_log(log, rev)
    return rev


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def render_plan(plan: PromotionPlan) -> str:
    L = ["PROMOTION PLAN (DRY RUN: nothing has been written)",
         f"  records      {plan.records_path}  sha256 {plan.records_sha256[:16]}",
         f"  annotations  sha256 {plan.annotations_sha256[:16]}   registry sha256 {plan.registry_sha256[:16]}",
         (f"  candidates {len(plan.candidates)}, rejected {len(plan.rejections)}, already promoted "
          f"{len(plan.unchanged)}"), ""]
    for c in plan.candidates:
        L.append(f"CANDIDATE {c.artifact_id}: script_type -> {c.label}  from {', '.join(c.source_annotation_ids)}")
        for ch in c.changes:
            L.append(f"  {ch.image_id} (sha256 {ch.image_sha256[:12]}, unchanged)")
            for f in ch.changed_fields:
                L.append(f"    {f}: {json.dumps(ch.before.get(f), ensure_ascii=False)} -> "
                         f"{json.dumps(ch.after.get(f), ensure_ascii=False)}")
        for n in c.notes:
            L.append(f"  NOTE {n}")
    for r in plan.rejections:
        L.append(f"REJECTED {r.artifact_id} [{r.status}]")
        L += [f"  - {x}" for x in r.reasons]
    for a in plan.unchanged:
        L.append(f"UNCHANGED {a}: records already carry this promotion")
    L += ["", f"Dataset validation after promotion: {plan.validation_status}"]
    L += [f"  {e}" for e in plan.validation_errors[:20]]
    L.append(f"Plan digest: {plan.plan_digest}")
    if plan.executable:
        L.append("To execute, a human reviewer runs:  python -m src.annotation promote --execute "
                 f"--approve {plan.plan_digest} --approver <id>")
    else:
        L.append("Nothing can be executed from this plan.")
    return "\n".join(L)


__all__ = ["Candidate", "PromotionError", "PromotionPlan", "RecordChange", "Rejection", "RevertPlan",
           "execute_promotion", "execute_revert", "plan_promotion", "plan_revert", "read_log",
           "render_plan"]
