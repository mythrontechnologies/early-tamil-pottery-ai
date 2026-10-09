"""Synthetic chronology and reasoning (Milestone 10).

    Synthetic demonstration — not archaeological dating.

This exercises the evidence-combination machinery with invented categories (``SYNTH_CAT_01`` ...
``SYNTH_CAT_04``), never years, periods, BCE or CE. It is deliberately separate from
``src.reasoning`` (which reasons only from human evidence and verified references), so no real
reference, period or date can ever appear to support a synthetic result.

Evidence sources (each yields a SET of allowed synthetic categories, or nothing):

* glyph-form evidence    - an invented table: each recognised glyph supports some categories;
                           the categories supported by the most glyphs win;
* mark-type evidence     - from the synthetic task class (graffiti-like constrains nothing);
* recorded synthetic context - the generator's surface family, known only for dataset images.

Combination: the intersection of all non-empty sets. An empty intersection is reported as a
CONFLICT (each source's position listed, nothing averaged); no source at all is INSUFFICIENT
SYNTHETIC EVIDENCE. Confidence is a word derived from agreement and model scores.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

CHRONOLOGY_STATEMENT = "Synthetic demonstration — not archaeological dating."
RULES_VERSION = "synthetic-chronology-1"
CATEGORIES = ("SYNTH_CAT_01", "SYNTH_CAT_02", "SYNTH_CAT_03", "SYNTH_CAT_04")

#: invented: glyph code -> synthetic categories it "supports"
GLYPH_FORM: dict[str, frozenset[str]] = {
    **{f"SG{i:02d}": frozenset({"SYNTH_CAT_01", "SYNTH_CAT_02"}) for i in range(0, 4)},
    **{f"SG{i:02d}": frozenset({"SYNTH_CAT_02", "SYNTH_CAT_03"}) for i in range(4, 8)},
    **{f"SG{i:02d}": frozenset({"SYNTH_CAT_03", "SYNTH_CAT_04"}) for i in range(8, 12)},
    **{f"SG{i:02d}": frozenset({"SYNTH_CAT_01", "SYNTH_CAT_04"}) for i in range(12, 16)},
}
#: invented: synthetic task class -> categories (None = the class says nothing about chronology)
MARK_TYPE: dict[str, frozenset[str] | None] = {
    "synthetic_tamil_brahmi_like": frozenset({"SYNTH_CAT_02", "SYNTH_CAT_03"}),
    "synthetic_graffiti_like": None,
    "synthetic_none": None,
    "synthetic_uncertain": None,
}
#: invented: generator surface family -> categories
SURFACE: dict[str, frozenset[str]] = {
    "reddish": frozenset({"SYNTH_CAT_02", "SYNTH_CAT_03"}),
    "buff": frozenset({"SYNTH_CAT_03", "SYNTH_CAT_04"}),
    "grey": frozenset({"SYNTH_CAT_01", "SYNTH_CAT_02"}),
    "dark": frozenset({"SYNTH_CAT_01"}),
    "two_tone": frozenset({"SYNTH_CAT_02"}),
}


@dataclass
class EvidenceItem:
    source: str
    supports: list[str]
    detail: str


@dataclass
class SyntheticChronology:
    state: str                     # estimated | conflict | insufficient
    categories: list[str]
    display: str
    confidence: str                # high | moderate | low | none (synthetic confidence words)
    evidence: list[EvidenceItem] = field(default_factory=list)
    conflict: list[str] = field(default_factory=list)
    statement: str = CHRONOLOGY_STATEMENT
    rules: str = RULES_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _span(cats: set[str] | frozenset[str]) -> str:
    s = sorted(cats)
    return s[0] if len(s) == 1 else f"{s[0]} – {s[-1]}" if _contiguous(s) else ", ".join(s)


def _contiguous(s: list[str]) -> bool:
    idx = [CATEGORIES.index(c) for c in s]
    return idx == list(range(idx[0], idx[0] + len(idx)))


def glyph_form_evidence(words: list[list[str]]) -> EvidenceItem | None:
    codes = [c for w in words for c in w if c in GLYPH_FORM]
    if not codes:
        return None
    votes = Counter(cat for c in codes for cat in GLYPH_FORM[c])
    top = max(votes.values())
    best = sorted(c for c, v in votes.items() if v == top)
    return EvidenceItem("synthetic glyph-form evidence", best,
                        f"{top} of {len(codes)} recognised glyph(s) support {_span(set(best))} (invented table {RULES_VERSION})")


def chronology(*, words: list[list[str]], synthetic_class: str | None, class_confidence: float | None,
               ocr_score: float | None, surface: str | None) -> SyntheticChronology:
    evidence: list[EvidenceItem] = []
    g = glyph_form_evidence(words)
    if g is not None:
        evidence.append(g)
    mt = MARK_TYPE.get(synthetic_class or "")
    if mt is not None:
        evidence.append(EvidenceItem("synthetic mark-type evidence", sorted(mt),
                                     f"synthetic task class {synthetic_class} supports {_span(mt)}"))
    if surface in SURFACE:
        evidence.append(EvidenceItem("recorded synthetic context", sorted(SURFACE[surface]),
                                     f"generator surface family '{surface}' supports {_span(SURFACE[surface])}"))
    if not evidence:
        return SyntheticChronology("insufficient", [], "Insufficient synthetic evidence", "none", evidence)
    common = set(evidence[0].supports)
    for e in evidence[1:]:
        common &= set(e.supports)
    if not common:
        return SyntheticChronology(
            "conflict", [], "Conflicting synthetic evidence — no synthetic category assigned (positions not averaged)",
            "none", evidence, [f"{e.source}: {_span(set(e.supports))}" for e in evidence])
    sources = len(evidence)
    strong = (class_confidence or 0) >= 0.7 and (ocr_score is None or ocr_score >= 0.8)
    if len(common) == 1 and sources >= 2 and strong:
        conf = "high"
    elif len(common) == 1:
        conf = "moderate"
    else:
        conf = "low"
    return SyntheticChronology("estimated", sorted(common), _span(common), conf, evidence)


# --------------------------------------------------------------------------- #
# Reasoning report and the synthetic evidence chain
# --------------------------------------------------------------------------- #


def reasoning_lines(a: dict[str, Any]) -> list[str]:
    """Every line traces to a recorded pipeline output. All are synthetic task evidence only."""
    c, ins, ocr, interp, chron = a["classification"], a["inscription"], a["ocr"], a["interpretation"], a["chronology"]
    kind = "calibrated" if c.get("calibrated") else "uncalibrated"
    lines = [f"SYNTHETIC: the synthetic task classifier assigned '{c['label']}' with {kind} model probability "
             f"{c['confidence']:.2f} ({c['confidence_words']})."]
    lines.append(f"SYNTHETIC: the region detector proposed {len(ins['regions'])} synthetic inscription region(s) and "
                 f"{len(ins['rows'])} glyph row(s).")
    if ocr["status"] == "read":
        lines.append(f"SYNTHETIC: {ocr['glyph_count']} glyph(s) segmented ({ocr['segmentation']}) and recognised: "
                     f"'{ocr['transcription']}' (mean glyph score {ocr['mean_glyph_score']:.2f}).")
    else:
        lines.append(f"SYNTHETIC: no synthetic glyph transcription ({ocr['reason']}).")
    lines.append(f"SYNTHETIC: grammatical interpretation under the invented synthetic language ({interp['spec']}): "
                 f"{interp['summary']}.")
    for e in chron["evidence"]:
        lines.append(f"SYNTHETIC: {e['source']}: {e['detail']}.")
    if chron["state"] == "conflict":
        lines.append("SYNTHETIC: the chronology sources disagree; no synthetic category is assigned and nothing is averaged.")
    elif chron["state"] == "insufficient":
        lines.append("SYNTHETIC: no synthetic chronology evidence; insufficient synthetic evidence.")
    else:
        lines.append(f"SYNTHETIC: combined synthetic chronology {chron['display']} (synthetic confidence {chron['confidence']}).")
    for note in a.get("consistency", []):
        lines.append(f"SYNTHETIC: {note}")
    lines.append("This result has no archaeological significance and has not been validated on real material.")
    return lines


def evidence_chain(a: dict[str, Any]) -> list[dict[str, Any]]:
    """The 8-step chain in synthetic form; every node is marked SYNTHETIC."""
    c, ins, ocr, interp, chron, img = (a["classification"], a["inscription"], a["ocr"], a["interpretation"],
                                       a["chronology"], a["input"])
    insufficient = ("insufficient", "Insufficient synthetic evidence")

    def node(key: str, title: str, value: str, status: tuple[str, str], confidence: str = "—", source: str = "—",
             uncertainty: str = "") -> dict[str, Any]:
        return {"key": key, "title": title, "value": value, "status": status, "confidence": confidence,
                "source": source, "provenance": "SYNTHETIC — generated image, synthetic models", "uncertainty": uncertainty,
                "synthetic": True}

    regions = ins["regions"]
    nodes = [
        node("observation", "Observation", f"{img['width_px']}×{img['height_px']} px synthetic image {img.get('image_id') or ''}".strip(),
             ("synthetic", "Synthetic image"), source="synthetic generator v" + str(img.get("generator_version", "?")),
             uncertainty="A generated image, not a photograph of any object."),
        node("inscription", "Synthetic inscription",
             f"{len(regions)} synthetic inscription region(s)" + (f", best score {regions[0]['confidence']:.2f}" if regions else ""),
             ("synthetic", "Synthetic detector") if regions else insufficient,
             confidence=f"{regions[0]['confidence']:.2f}" if regions else "—", source="RegionNet (synthetic)",
             uncertainty="A region score is a heat-map peak, not evidence that a mark exists."),
        node("script", "Synthetic script task", f"{c['display_label']} (synthetic task class)",
             ("synthetic", "Synthetic classifier"), confidence=f"{c['confidence']:.2f} · {c['calibration_status']}",
             source=c["model"], uncertainty="A synthetic task category, not a script identification."),
        node("reading", "Synthetic reading",
             ocr["transcription"] if ocr["status"] == "read" else "No synthetic glyph transcription",
             ("synthetic", "Synthetic glyph transcription") if ocr["status"] == "read" else insufficient,
             confidence=f"{ocr['mean_glyph_score']:.2f}" if ocr["status"] == "read" else "—",
             source=f"GlyphNet + {ocr.get('segmentation', '—')} segmentation",
             uncertainty="Synthetic glyph codes have no sound and no reading."),
        node("linguistic", "Synthetic linguistic features",
             " · ".join(f"{g['glyph']} {g['reading'] or '?'} ({g['class']}, {g['role']})"
                        for g in a.get("synthetic_language", {}).get("gloss", [])) or "No glyph read",
             ("synthetic", "Synthetic lexicon") if ocr["status"] == "read" else insufficient,
             source=interp["spec"], uncertainty="Word classes and roles of an invented language (not Tamil-Brahmi)."),
        node("chronology", "Synthetic chronology", chron["display"],
             ("synthetic", f"Synthetic · {chron['confidence']}") if chron["state"] == "estimated"
             else ("unresolved", "Conflicting synthetic evidence") if chron["state"] == "conflict" else insufficient,
             confidence=chron["confidence"], source=chron["rules"], uncertainty=CHRONOLOGY_STATEMENT),
        node("interpretation", "Synthetic grammatical interpretation", interp["summary"],
             ("synthetic", "Synthetic grammar") if interp["clauses"] else insufficient,
             source=interp["spec"], uncertainty=interp["statement"]),
        node("result", "Synthetic result", a["summary"], ("synthetic", "Synthetic result"),
             confidence=chron["confidence"], source="this pipeline run",
             uncertainty="No archaeological significance; not validated on real material."),
    ]
    return nodes


__all__ = ["CATEGORIES", "CHRONOLOGY_STATEMENT", "RULES_VERSION", "EvidenceItem", "SyntheticChronology", "chronology",
           "evidence_chain", "glyph_form_evidence", "reasoning_lines"]
