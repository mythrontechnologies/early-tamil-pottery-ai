"""Inter-annotator agreement (Milestone 8).

Agreement is MEASUREMENT, never resolution. Nothing here changes an annotation, a
resolution status or a record: two annotators who disagree still disagree after this module
has counted them, and the disagreement is listed item by item so an expert can resolve it.

Two raters are compared on the artifacts both have annotated (current, non-superseded
annotations only; AI predictions are never a rater). A rater is either a provenance tier
(``project_annotation``, ``expert_annotation``, ``source_information``) or an annotator id.
When a tier has more than one current annotation on an artifact the pair is ambiguous and
the artifact is skipped with that reason; name the annotator ids instead.

Fields, each reported separately with its own metric:

    object_status            categorical   original / reproduction / uncertain (schema 1.1.0)
    inscription_present      categorical   raw agreement, confusion matrix, Cohen's kappa
    script_type              categorical   raw agreement, confusion matrix, Cohen's kappa
    inscription_type         categorical   raw agreement, confusion matrix, Cohen's kappa
    interpretation_type      categorical   raw agreement, confusion matrix, Cohen's kappa
    regions                  geometric     per-image best-match IoU; matched-region counts
    reading                  textual       exact (normalised) match; character similarity
    dating_evidence_types    set-valued    exact set match; mean Jaccard
    dating_range             interval      identical range / overlapping / disjoint / one-sided

``item_summary`` lists, per paired artifact, every field on which the raters differ and every
field one or both left undetermined. With a pilot of six items this list, not a statistic, is
the result: the text report withholds kappa whenever it is not interpretable.

Items where either rater recorded ``unknown`` (not examined / not determined) are excluded
from a categorical comparison and counted as such: agreeing that nobody looked is not
agreement about the object.

Kappa is always shown beside the raw counts. Below ``agreement.min_items_for_kappa``
(configs/project.yaml) it is marked NOT interpretable, and when chance agreement is 1 (both
raters used one identical category throughout) it is undefined, not 1.0.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from dataclasses import field as dc_field
from typing import Any, cast

from src.dataset.schema import load_config

from .model import PROVENANCE_ROLE

CATEGORICAL = {
    "object_status": ("object", "object_status"),
    "inscription_present": ("inscription", "inscription_present"),
    "script_type": ("inscription", "script_type"),
    "inscription_type": ("inscription", "inscription_type"),
    "interpretation_type": ("interpretation", "interpretation_type"),
}
#: Values that mean "not determined"; an item with one of these is not compared.
NOT_DETERMINED = frozenset({"unknown", "not_available"})
#: Region labels that mark writing or marks (compared); damage / decoration are not.
MARK_LABELS = frozenset({"inscription", "graffiti", "possible_inscription"})
TIERS = tuple(t for t in PROVENANCE_ROLE if t != "ai_prediction")


def _settings(config: dict[str, Any] | None) -> tuple[int, float]:
    a = (config or load_config()).get("agreement", {})
    return int(a.get("min_items_for_kappa", 30)), float(a.get("region_iou_match", 0.5))


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #


def cohens_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa for paired categorical judgements; ``None`` when undefined
    (no items, or expected chance agreement of 1)."""
    n = len(pairs)
    if n == 0:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if pe >= 1.0:
        return None
    return (po - pe) / (1.0 - pe)


def iou(a: dict[str, float], b: dict[str, float]) -> float:
    """Intersection over union of two normalised rectangles on the same image."""
    ix = max(0.0, min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"]))
    iy = max(0.0, min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"]))
    inter = ix * iy
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union > 0 else 0.0


def normalise_reading(text: str) -> str:
    """NFC, whitespace collapsed, case-folded. Editorial marks are kept: they are content."""
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


def char_similarity(a: str, b: str) -> float:
    """1 - Levenshtein distance / length of the longer string, on normalised readings."""
    a, b = normalise_reading(a), normalise_reading(b)
    if not a and not b:
        return 1.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return 1.0 - prev[-1] / max(len(a), len(b))


# --------------------------------------------------------------------------- #
# Report structures
# --------------------------------------------------------------------------- #


@dataclass
class FieldAgreement:
    field: str
    metric: str
    items_compared: int
    items_agreeing: int
    raw_agreement: float | None
    statistic_name: str = ""
    statistic: float | None = None
    interpretable: bool = False
    status: str = ""
    note: str = ""
    excluded: dict[str, int] = dc_field(default_factory=dict)          # reason -> count
    confusion: dict[str, dict[str, int]] = dc_field(default_factory=dict)
    per_artifact: dict[str, Any] = dc_field(default_factory=dict)
    disagreements: list[dict[str, Any]] = dc_field(default_factory=list)


@dataclass
class AgreementReport:
    rater_a: str
    rater_b: str
    artifacts_requested: int
    artifacts_paired: list[str]
    skipped: dict[str, str]                                         # artifact -> reason
    fields: dict[str, FieldAgreement]
    min_items_for_kappa: int
    resolves_disagreement: bool = False                             # always False, by design
    notes: list[str] = dc_field(default_factory=list)
    items: dict[str, dict[str, list[str]]] = dc_field(default_factory=dict)     # item-level review

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Pairing
# --------------------------------------------------------------------------- #


def _matches(a: dict[str, Any], rater: str) -> bool:
    if rater in TIERS:
        return a["provenance_type"] == rater
    return a["annotator"]["annotator_id"] == rater


def pair_annotations(current: Iterable[dict[str, Any]], artifact_ids: Iterable[str],
                     rater_a: str, rater_b: str
                     ) -> tuple[dict[str, tuple[dict[str, Any], dict[str, Any]]], dict[str, str]]:
    """artifact -> (annotation by A, annotation by B), and artifact -> reason skipped."""
    if rater_a == rater_b:
        raise ValueError("the two raters must differ")
    humans = [a for a in current if a["provenance_type"] != "ai_prediction"]
    pairs, skipped = {}, {}
    for art in sorted(set(artifact_ids)):
        mine = [a for a in humans if a["artifact_id"] == art]
        sa = [a for a in mine if _matches(a, rater_a)]
        sb = [a for a in mine if _matches(a, rater_b) and a not in sa]
        if not sa or not sb:
            missing = [r for r, s in ((rater_a, sa), (rater_b, sb)) if not s]
            skipped[art] = "no current annotation by " + " or ".join(missing)
        elif len(sa) > 1 or len(sb) > 1:
            skipped[art] = ("more than one current annotation for a rater "
                            f"({rater_a}: {len(sa)}, {rater_b}: {len(sb)}); name annotator ids")
        else:
            pairs[art] = (sa[0], sb[0])
    return pairs, skipped


# --------------------------------------------------------------------------- #
# Per-field comparison
# --------------------------------------------------------------------------- #


def _categorical(name: str, pairs: dict[str, tuple[dict, dict]], min_items: int) -> FieldAgreement:
    section, key = CATEGORICAL[name]
    compared: list[tuple[str, str]] = []
    excluded: Counter[str] = Counter()
    fa = FieldAgreement(name, "categorical", 0, 0, None, "cohens_kappa")
    for art, (a, b) in pairs.items():
        va, vb = a[section].get(key, "unknown"), b[section].get(key, "unknown")
        fa.per_artifact[art] = {"a": va, "b": vb}
        if va in NOT_DETERMINED or vb in NOT_DETERMINED:
            excluded["not determined by one or both raters"] += 1
            continue
        compared.append((va, vb))
        if va != vb:
            fa.disagreements.append({"artifact_id": art, "a": va, "b": vb})
    for va, vb in compared:
        fa.confusion.setdefault(va, {}).setdefault(vb, 0)
        fa.confusion[va][vb] += 1
    fa.items_compared = len(compared)
    fa.items_agreeing = sum(x == y for x, y in compared)
    fa.excluded = dict(excluded)
    if not compared:
        fa.status, fa.note = "no_data", "No item was determined by both raters."
        return fa
    fa.raw_agreement = fa.items_agreeing / fa.items_compared
    fa.statistic = cohens_kappa(compared)
    if fa.statistic is None:
        fa.status = "undefined"
        fa.note = ("Kappa is undefined: expected chance agreement is 1 (both raters used a single "
                   "identical category). Only the raw counts are meaningful.")
    elif fa.items_compared < min_items:
        fa.status = "insufficient_sample"
        fa.note = (f"n={fa.items_compared} < {min_items}: kappa is shown for completeness but is NOT "
                   "interpretable at this sample size; rely on the raw counts and the item list.")
    else:
        fa.status, fa.interpretable = "ok", True
    return fa


def _mark_regions(a: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in a["inscription"].get("regions", []) if r["label"] in MARK_LABELS]


def _regions(pairs: dict[str, tuple[dict, dict]], iou_match: float) -> FieldAgreement:
    fa = FieldAgreement("regions", "geometric", 0, 0, None, "mean_best_match_iou")
    excluded: Counter[str] = Counter()
    ious: list[float] = []
    for art, (a, b) in pairs.items():
        ra, rb = _mark_regions(a), _mark_regions(b)
        if not ra and not rb:
            excluded["neither rater marked an inscription/graffiti region"] += 1
            continue
        if not ra or not rb:
            excluded["only one rater marked regions"] += 1
            fa.disagreements.append({"artifact_id": art, "a_regions": len(ra), "b_regions": len(rb)})
            continue
        # Best match for each of A's regions among B's regions on the same image.
        best = [max((iou(x, y) for y in rb if y["image_id"] == x["image_id"]), default=0.0) for x in ra]
        matched = sum(v >= iou_match for v in best)
        fa.per_artifact[art] = {"a_regions": len(ra), "b_regions": len(rb),
                                "best_iou": [round(v, 4) for v in best], "matched": matched}
        ious += best
        fa.items_compared += len(ra)
        fa.items_agreeing += matched
        if matched < max(len(ra), len(rb)):
            fa.disagreements.append({"artifact_id": art, **fa.per_artifact[art]})
    fa.excluded = dict(excluded)
    if not ious:
        fa.status, fa.note = "no_data", "No artifact where both raters marked regions."
        return fa
    fa.raw_agreement = fa.items_agreeing / fa.items_compared
    fa.statistic = sum(ious) / len(ious)
    fa.status = "descriptive"
    fa.note = (f"Descriptive only. A region 'matches' at IoU >= {iou_match}. Counts are regions of "
               "rater A; regions only B marked appear as unmatched in the per-artifact detail.")
    return fa


def _has_reading(a: dict[str, Any]) -> bool:
    r = a["inscription"]["reading"]
    return isinstance(r, str) and r not in ("not_available", "not_applicable", "unknown")


def _readings(pairs: dict[str, tuple[dict, dict]]) -> FieldAgreement:
    fa = FieldAgreement("reading", "textual", 0, 0, None, "mean_character_similarity")
    excluded: Counter[str] = Counter()
    sims = []
    for art, (a, b) in pairs.items():
        ha, hb = _has_reading(a), _has_reading(b)
        if not ha and not hb:
            excluded["neither rater gave a reading"] += 1
            continue
        if ha != hb:
            excluded["only one rater gave a reading"] += 1
            fa.disagreements.append({"artifact_id": art, "a": a["inscription"]["reading"],
                                     "b": b["inscription"]["reading"]})
            continue
        ra, rb = a["inscription"]["reading"], b["inscription"]["reading"]
        same = normalise_reading(ra) == normalise_reading(rb)
        sim = char_similarity(ra, rb)
        sims.append(sim)
        fa.items_compared += 1
        fa.items_agreeing += same
        fa.per_artifact[art] = {"a": ra, "b": rb, "exact": same, "similarity": round(sim, 4)}
        if not same:
            fa.disagreements.append({"artifact_id": art, "a": ra, "b": rb})
    fa.excluded = dict(excluded)
    if not sims:
        fa.status, fa.note = "no_data", "No artifact where both raters gave a reading."
        return fa
    fa.raw_agreement = fa.items_agreeing / fa.items_compared
    fa.statistic = sum(sims) / len(sims)
    fa.status = "descriptive"
    fa.note = ("Descriptive only. A similar string is not an agreed reading: every non-identical "
               "pair is listed as a disagreement for expert resolution.")
    return fa


def _evidence_types(a: dict[str, Any]) -> set[str]:
    return {e["evidence_type"] for e in a["dating"]["dating_evidence"]}


def _dating(pairs: dict[str, tuple[dict, dict]]) -> FieldAgreement:
    fa = FieldAgreement("dating_evidence_types", "set", 0, 0, None, "mean_jaccard")
    excluded: Counter[str] = Counter()
    jac = []
    for art, (a, b) in pairs.items():
        sa, sb = _evidence_types(a), _evidence_types(b)
        if not sa and not sb:
            excluded["neither rater recorded dating evidence"] += 1
            continue
        j = len(sa & sb) / len(sa | sb)
        jac.append(j)
        fa.items_compared += 1
        fa.items_agreeing += sa == sb
        fa.per_artifact[art] = {"a": sorted(sa), "b": sorted(sb), "jaccard": round(j, 4)}
        if sa != sb:
            fa.disagreements.append({"artifact_id": art, "a": sorted(sa), "b": sorted(sb)})
    fa.excluded = dict(excluded)
    if not jac:
        fa.status, fa.note = "no_data", "No artifact where either rater recorded dating evidence."
        return fa
    fa.raw_agreement = fa.items_agreeing / fa.items_compared
    fa.statistic = sum(jac) / len(jac)
    fa.status = "descriptive"
    fa.note = ("Compares which KINDS of dating evidence each rater recorded, not the dates. "
               "Kappa is not computed for set-valued judgements.")
    return fa


def _range(a: dict[str, Any]) -> tuple[int | None, int | None]:
    d = a["dating"]
    return d["estimated_start_year"], d["estimated_end_year"]


def _dating_range(pairs: dict[str, tuple[dict, dict]]) -> FieldAgreement:
    """Proposed date ranges: identical, overlapping, disjoint, or proposed by one rater only.
    Ranges are compared, never merged or averaged."""
    fa = FieldAgreement("dating_range", "interval", 0, 0, None, "")
    excluded: Counter[str] = Counter()
    for art, (a, b) in pairs.items():
        ra, rb = _range(a), _range(b)
        has_a, has_b = ra != (None, None), rb != (None, None)
        if not has_a and not has_b:
            excluded["neither rater proposed a date range"] += 1
            continue
        fa.items_compared += 1
        if has_a != has_b:
            relation = "one rater only"
        elif ra == rb:
            relation = "identical"
        elif None in ra or None in rb:
            relation = "open-ended; not comparable"
        else:
            a0, a1, b0, b1 = (cast(int, v) for v in (*ra, *rb))      # None excluded just above
            relation = "overlapping" if max(a0, b0) <= min(a1, b1) else "disjoint"
        fa.per_artifact[art] = {"a": list(ra), "b": list(rb), "relation": relation}
        if relation == "identical":
            fa.items_agreeing += 1
        else:
            fa.disagreements.append({"artifact_id": art, **fa.per_artifact[art]})
    fa.excluded = dict(excluded)
    if not fa.items_compared:
        fa.status, fa.note = "no_data", "No artifact where either rater proposed a date range."
        return fa
    fa.raw_agreement = fa.items_agreeing / fa.items_compared
    fa.status = "descriptive"
    fa.note = ("Only identical ranges agree. Overlap is reported, not treated as agreement, and "
               "no range is averaged or combined.")
    return fa


def item_summary(fields: dict[str, FieldAgreement], paired: Iterable[str]) -> dict[str, dict[str, list[str]]]:
    """artifact -> {"disagree": [fields], "undetermined": [fields]} for the item-level review."""
    out: dict[str, dict[str, list[str]]] = {art: {"disagree": [], "undetermined": []} for art in paired}
    for name, f in fields.items():
        for d in f.disagreements:
            out[d["artifact_id"]]["disagree"].append(name)
        if name in CATEGORICAL:
            for art, v in f.per_artifact.items():
                if v["a"] in NOT_DETERMINED or v["b"] in NOT_DETERMINED:
                    out[art]["undetermined"].append(name)
    return out


def compute_agreement(current: Iterable[dict[str, Any]], artifact_ids: Iterable[str],
                      rater_a: str = "project_annotation", rater_b: str = "expert_annotation",
                      *, config: dict[str, Any] | None = None) -> AgreementReport:
    """Agreement between two raters over the given artifacts. Pure: reads, never writes."""
    artifact_ids = sorted(set(artifact_ids))
    min_items, iou_match = _settings(config)
    pairs, skipped = pair_annotations(list(current), artifact_ids, rater_a, rater_b)
    fields = {name: _categorical(name, pairs, min_items) for name in CATEGORICAL}
    fields["regions"] = _regions(pairs, iou_match)
    fields["reading"] = _readings(pairs)
    fields["dating_evidence_types"] = _dating(pairs)
    fields["dating_range"] = _dating_range(pairs)
    notes = [("Agreement statistics describe the annotators, not the objects. They never resolve a "
              "disagreement: see `python -m src.annotation summary` for each artifact's status.")]
    if len(pairs) < min_items:
        notes.append(f"Only {len(pairs)} artifact(s) are paired; no chance-corrected statistic is "
                     f"interpretable below {min_items} items.")
    return AgreementReport(rater_a, rater_b, len(artifact_ids), sorted(pairs), skipped, fields,
                           min_items, False, notes, item_summary(fields, pairs))


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def render_agreement(r: AgreementReport) -> str:
    L = [f"AGREEMENT  {r.rater_a}  vs  {r.rater_b}",
         (f"  artifacts requested {r.artifacts_requested}, paired {len(r.artifacts_paired)}, "
          f"skipped {len(r.skipped)}")]
    for art, why in sorted(r.skipped.items()):
        L.append(f"    skipped {art}: {why}")
    for f in r.fields.values():
        L.append("")
        L.append(f"{f.field}  [{f.metric}]  status: {f.status}")
        stat = ""
        if f.statistic_name == "cohens_kappa" and not f.interpretable:
            stat = (f"; cohens_kappa withheld: not interpretable (n={f.items_compared} < {r.min_items_for_kappa})"
                    if f.status == "insufficient_sample" else f"; cohens_kappa not interpretable ({f.status})")
        elif f.statistic_name:
            stat = f"; {f.statistic_name} {_fmt(f.statistic)}" + ("" if f.interpretable else " (not interpretable)")
        L.append(f"  compared {f.items_compared}, agreeing {f.items_agreeing}, raw agreement "
                 f"{_fmt(f.raw_agreement)}{stat}")
        for why, n in sorted(f.excluded.items()):
            L.append(f"  excluded {n}: {why}")
        if f.confusion:
            L.append(f"  confusion (rows {r.rater_a}, columns {r.rater_b}): {f.confusion}")
        for d in f.disagreements:
            L.append(f"  DISAGREE {d}")
        if f.note:
            L.append(f"  note: {f.note}")
    if r.items:
        L += ["", "ITEM-LEVEL REVIEW (the result that matters at this sample size)"]
        for art, v in sorted(r.items.items()):
            dis = ", ".join(v["disagree"]) or "none"
            und = ", ".join(v["undetermined"]) or "none"
            L.append(f"  {art}: DISAGREE [{dis}]  UNDETERMINED/UNRESOLVED [{und}]")
    L += [""] + [f"NOTE: {n}" for n in r.notes]
    return "\n".join(L)


__all__ = ["CATEGORICAL", "MARK_LABELS", "NOT_DETERMINED", "AgreementReport", "FieldAgreement",
           "char_similarity", "cohens_kappa", "compute_agreement", "iou", "item_summary", "normalise_reading",
           "pair_annotations", "render_agreement"]
