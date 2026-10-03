"""Annotation validation: JSON Schema plus cross-field rules N1-N15.

``N*`` rules encode the Milestone 7 annotation discipline: provenance never blurred,
unknown vs uncertain kept apart, no translation without a reading, no date without
evidence, no year 0, every citation resolvable. They check *consistency*; they never
judge whether an annotator's reading is right.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator

from src.synthetic import SYNTHETIC_LABELS, synthetic_reasons

from .model import (
    PROVENANCE_ROLE,
    SELF_REFERENCES,
    SENTINELS,
    is_real,
    load_annotation_schema,
)

RULES: dict[str, str] = {
    "N1": "annotation conforms to annotation.schema.json",
    "N2": "artifact and images exist in the research records",
    "N3": "regions lie inside the image and name an examined photograph",
    "N4": "provenance type, annotator role and review state agree",
    "N5": "source_information annotations cite at least one reference",
    "N6": "inscription presence, script and reading fields are consistent (unknown vs uncertain)",
    "N7": "a reading names who read it; no reading means no interpretation",
    "N8": "a translation names its source; a personal name has no translation",
    "N9": "a dating range needs evidence, a real basis and a stated confidence; no year 0",
    "N10": "every cited reference id resolves",
    "N11": "a revision supersedes an existing annotation by the same annotator of the same artifact",
    "N12": "annotation ids are unique",
    "N13": "image usability entries name examined photographs",
    "N14": "a cited reference claims verified_against_source only if the verification registry "
           "verified it (Milestone 8)",
    "N15": "an AI-marked record (annotator id 'ai_...' or an AI-draft marker) is only ever an ai_prediction",
    "N16": "the store matches its append-only ledger (no line edited, removed or added by hand)",
    "N17": "the annotation is not about synthetic engineering data (Milestone 9: synthetic images are never "
           "annotated as archaeological evidence)",
}


@dataclass(frozen=True)
class Problem:
    rule: str
    message: str
    annotation_id: str | None = None

    def __str__(self) -> str:
        return f"{self.rule} {self.annotation_id or '<annotation>'}: {self.message}"


@dataclass
class AnnotationValidation:
    problems: list[Problem] = field(default_factory=list)
    count: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def status(self) -> str:
        return "PASS" if self.ok else "FAIL"


_validator: Draft202012Validator | None = None


def _schema_validator() -> Draft202012Validator:
    global _validator
    if _validator is None:
        _validator = Draft202012Validator(load_annotation_schema())
    return _validator


def _ref_ids(a: dict[str, Any]) -> set[str]:
    return {r.get("ref_id") for r in a.get("references", []) if isinstance(r, dict)}


def _cited(value: Any) -> bool:
    return isinstance(value, str) and value not in SENTINELS and value not in SELF_REFERENCES


def validate_annotation(
    a: dict[str, Any],
    *,
    artifact_images: dict[str, set[str]] | None = None,
    knowledge_ref_ids: set[str] | None = None,
    verified_ref_ids: set[str] | None = None,
) -> list[Problem]:
    """Problems with one annotation (N1-N10, N13-N15, N17). Empty list = valid.

    ``verified_ref_ids`` (from ``src.knowledge.verification``) enables N14; ``None`` skips it."""
    aid = a.get("annotation_id") if isinstance(a, dict) else None
    out: list[Problem] = []

    def add(rule: str, msg: str) -> None:
        out.append(Problem(rule, msg, aid))

    if isinstance(a, dict):         # N17 first: reported even when the record is malformed
        reasons = synthetic_reasons(a)
        nested = (a.get("inscription") or {}).get("script_type") if isinstance(a.get("inscription"), dict) else None
        if nested in SYNTHETIC_LABELS:
            reasons.append(f"inscription.script_type {nested!r} is a synthetic task label")
        if reasons:
            add("N17", "synthetic engineering data cannot enter the annotation store: " + "; ".join(reasons))
    for err in sorted(_schema_validator().iter_errors(a), key=lambda e: list(e.path)):
        add("N1", f"{'.'.join(map(str, err.path)) or '<root>'}: {err.message}")
    if out:
        return out          # cross-field rules assume a structurally valid record

    images = set(a["image_ids"])
    ins, interp, dating = a["inscription"], a["interpretation"], a["dating"]

    # N2 - artifact and images exist.
    if artifact_images is not None:
        known = artifact_images.get(a["artifact_id"])
        if known is None:
            add("N2", f"artifact {a['artifact_id']!r} is not in the research records")
        else:
            for img in sorted(images - known):
                add("N2", f"image {img!r} does not belong to artifact {a['artifact_id']!r}")

    # N3 - regions.
    for i, r in enumerate(ins.get("regions", [])):
        if r["image_id"] not in images:
            add("N3", f"region {i} is on image {r['image_id']!r}, which is not in image_ids")
        if r["x"] + r["width"] > 1.0 + 1e-9 or r["y"] + r["height"] > 1.0 + 1e-9:
            add("N3", f"region {i} extends beyond the image (normalised coordinates exceed 1)")

    # N4 - provenance, role and review state.
    pt, role, state = a["provenance_type"], a["annotator"]["role"], a["review_state"]
    if PROVENANCE_ROLE[pt] != role:
        add("N4", f"provenance_type {pt!r} requires annotator role {PROVENANCE_ROLE[pt]!r}, got {role!r}")
    if state == "expert_reviewed" and pt != "expert_annotation":
        add("N4", "review_state 'expert_reviewed' is reserved for expert annotations; a project "
                  "annotation cannot be made equivalent to an expert label")
    if pt == "ai_prediction" and state != "unreviewed":
        add("N4", "an AI prediction is always 'unreviewed'; an expert who agrees records their own annotation")

    # N5 - transcribed source information must cite the source.
    if pt == "source_information" and not a.get("references"):
        add("N5", "source_information must cite the source in references")

    # N6 - unknown vs uncertain, presence vs script.
    present, script = ins["inscription_present"], ins["script_type"]
    if present == "no":
        if script != "none":
            add("N6", f"inscription_present='no' requires script_type='none', got {script!r}")
        if ins["inscription_type"] != "not_applicable":
            add("N6", "inscription_present='no' requires inscription_type='not_applicable'")
        if ins["reading"] != "not_applicable":
            add("N6", "inscription_present='no' requires reading='not_applicable'")
        if ins.get("regions"):
            add("N6", "inscription_present='no' but inscription regions are marked")
    if script == "none" and present != "no":
        add("N6", f"script_type='none' requires inscription_present='no', got {present!r}")
    if present == "unknown" and script != "unknown":
        add("N6", "inscription_present='unknown' (not examined) cannot carry a script_type; "
                  "use 'uncertain' if it was examined and cannot be decided")
    if script != "unknown" and ins["script_confidence"] in ("unknown", "not_applicable"):
        add("N6", f"script_type={script!r} is asserted but script_confidence is not stated")

    # N7 - readings.
    reading = ins["reading"]
    if is_real(reading):
        if present not in ("yes", "uncertain"):
            add("N7", f"a reading is given but inscription_present={present!r}")
        if not is_real(ins["reading_source"]):
            add("N7", "a reading requires reading_source (a reference id or 'this_annotator')")
        if ins["reading_confidence"] in ("unknown", "not_applicable"):
            add("N7", "a reading requires reading_confidence")
    else:
        if interp["interpretation_type"] not in ("unknown", "not_applicable", "uncertain"):
            add("N7", f"no reading, but interpretation_type={interp['interpretation_type']!r}; "
                      "nothing can be interpreted before it is read")
        if is_real(interp["translation"]):
            add("N7", "a translation is given but there is no reading")

    # N8 - translations.
    itype, translation = interp["interpretation_type"], interp["translation"]
    if itype == "personal_name" and translation != "not_applicable":
        add("N8", "a personal name has no literal translation: translation must be 'not_applicable' "
                  "(explain in 'meaning')")
    if itype in ("symbol", "not_translatable") and is_real(translation):
        add("N8", f"interpretation_type={itype!r} cannot carry a translation")
    if is_real(translation):
        if not is_real(interp["translation_source"]):
            add("N8", "a translation requires translation_source")
        if interp["translation_confidence"] in ("unknown", "not_applicable"):
            add("N8", "a translation requires translation_confidence")

    # N9 - dating.
    lo, hi = dating["estimated_start_year"], dating["estimated_end_year"]
    evidence = dating["dating_evidence"]
    basis = [b for b in dating["dating_basis"] if b not in SENTINELS]
    if isinstance(lo, int) and isinstance(hi, int) and lo > hi:
        add("N9", f"estimated_start_year {lo} is later than estimated_end_year {hi}")
    if lo is not None or hi is not None:
        if not evidence:
            add("N9", "a dating range requires at least one dating_evidence item")
        if not basis:
            add("N9", "a dating range requires a real dating_basis, not a sentinel")
        if dating["dating_confidence"] in ("unknown", "not_applicable"):
            add("N9", "a dating range requires dating_confidence")
    elif not evidence and dating["dating_confidence"] not in ("unknown", "not_applicable"):
        add("N9", "dating_confidence is stated but there is no range and no evidence")
    if not evidence and basis:
        add("N9", f"dating_basis {basis} names evidence types but dating_evidence is empty")
    ev_types = {e["evidence_type"] for e in evidence}
    for b in basis:
        if b not in ev_types:
            add("N9", f"dating_basis {b!r} has no matching dating_evidence item")
    seen_ids: set[str] = set()
    for e in evidence:
        if e["evidence_id"] in seen_ids:
            add("N9", f"duplicate evidence_id {e['evidence_id']}")
        seen_ids.add(e["evidence_id"])
        s, t = e.get("supports_start_year"), e.get("supports_end_year")
        if isinstance(s, int) and isinstance(t, int) and s > t:
            add("N9", f"{e['evidence_id']}: supports_start_year {s} later than supports_end_year {t}")
        if e["evidence_type"] in ("stratigraphy", "absolute_dating") and "association" not in e:
            add("N9", f"{e['evidence_id']}: {e['evidence_type']} evidence must state its association "
                      "with this object (docs/CHRONOLOGICAL_SCOPE.md, Position D)")

    # N10 - citations resolve.
    known_refs = _ref_ids(a) | (knowledge_ref_ids or set())
    if len(_ref_ids(a)) != len(a.get("references", [])):
        add("N10", "duplicate ref_id in references")
    cited = [("reading_source", ins["reading_source"]),
             ("translation_source", interp["translation_source"])]
    cited += [(f"alternative_readings[{i}]", r["source"]) for i, r in enumerate(ins.get("alternative_readings", []))]
    cited += [(f"linguistic_features[{i}]", f["source_reference"]) for i, f in enumerate(a.get("linguistic_features", []))]
    cited += [(e["evidence_id"], e["source_reference"]) for e in evidence]
    for where, ref in cited:
        if _cited(ref) and ref not in known_refs:
            add("N10", f"{where} cites {ref!r}, which is not in references or the knowledge base")

    # N13 - usability entries.
    for u in a.get("image_usability", []):
        if u["image_id"] not in images:
            add("N13", f"image_usability names {u['image_id']!r}, which is not in image_ids")

    # N15 - AI output cannot enter a human provenance tier by copying.
    if pt != "ai_prediction":
        from .ai_draft import is_ai_marked

        if is_ai_marked(a):
            add("N15", "this record is marked as AI-prepared (annotator id or AI-draft marker) but its "
                       f"provenance_type is {pt!r}; AI output is only ever an ai_prediction")

    # N14 - an annotator cannot self-certify a reference as verified.
    if verified_ref_ids is not None:
        for r in a.get("references", []):
            if r["verification_status"] == "verified_against_source" and r["ref_id"] not in verified_ref_ids:
                add("N14", f"reference {r['ref_id']!r} is marked verified_against_source, but the "
                           "verification registry holds no verified claim for it "
                           "(python -m src.knowledge status)")
    return out


def validate_annotations(
    annotations: Iterable[dict[str, Any]],
    *,
    artifact_images: dict[str, set[str]] | None = None,
    knowledge_ref_ids: set[str] | None = None,
    verified_ref_ids: set[str] | None = None,
) -> AnnotationValidation:
    anns = list(annotations)
    result = AnnotationValidation(count=len(anns))
    by_id: dict[str, dict[str, Any]] = {}
    for a in anns:
        result.problems += validate_annotation(a, artifact_images=artifact_images,
                                               knowledge_ref_ids=knowledge_ref_ids,
                                               verified_ref_ids=verified_ref_ids)
        aid = a.get("annotation_id") if isinstance(a, dict) else None
        if isinstance(aid, str):
            if aid in by_id:
                result.problems.append(Problem("N12", "duplicate annotation_id", aid))
            by_id[aid] = a
    superseded_by: dict[str, list[str]] = defaultdict(list)
    for a in anns:
        if not isinstance(a, dict) or not a.get("supersedes"):
            continue
        prev = by_id.get(a["supersedes"])
        aid = a.get("annotation_id")
        if prev is None:
            result.problems.append(Problem("N11", f"supersedes unknown annotation {a['supersedes']!r}", aid))
            continue
        if prev.get("artifact_id") != a.get("artifact_id"):
            result.problems.append(Problem("N11", "supersedes an annotation of a different artifact", aid))
        if prev.get("annotator", {}).get("annotator_id") != a.get("annotator", {}).get("annotator_id"):
            result.problems.append(Problem(
                "N11", "an annotator may revise only their own annotation; other annotators add "
                       "their own record so disagreement is preserved", aid))
        superseded_by[a["supersedes"]].append(aid)
    for old, new in superseded_by.items():
        if len(new) > 1:
            result.problems.append(Problem("N11", f"annotation {old} is superseded more than once: {new}", old))
    return result


__all__ = ["RULES", "AnnotationValidation", "Problem", "validate_annotation", "validate_annotations"]
