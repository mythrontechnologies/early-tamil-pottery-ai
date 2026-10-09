"""Language / reading results: one explicit block per analysis.

    inscription or mark status · transcription · transliteration · translation · reading completeness

Each field carries its value, its state, who asserts it (the tier), a confidence, the supporting evidence and,
when it cannot be established, a fixed explanation of why. Nothing here composes a reading, a transliteration
or a translation: values are copied from the reasoning result (human evidence only, one basis annotation) or
from the research record's promoted ground truth (expert consensus, ``src.annotation.promote``). An AI draft
(an OCR candidate or an AI-prediction annotation) is listed apart and never fills a field, and a model
probability is never a reading confidence. A translation is shown only when a human recorded it with a cited
source (``src.translation.interpret``); classifier output and OCR candidates can never produce one.

The synthetic counterpart is ``src.synthetic.reading`` (same shape, every field marked synthetic).
"""

from __future__ import annotations

from typing import Any

from src.annotation.model import is_real

FIELDS: tuple[tuple[str, str], ...] = (
    ("inscription_status", "Inscription / mark"), ("transcription", "Transcription"),
    ("transliteration", "Transliteration"), ("translation", "Translation"),
    ("completeness", "Reading completeness"))
STATES = ("established", "not_established", "not_applicable", "not_available")

#: Who asserts a value, strongest first. The tiers are never merged.
TIERS: dict[str, str] = {
    "promoted_ground_truth": "Promoted ground truth (expert consensus)",
    "adjudicated": "Expert adjudication",
    "expert_reviewed": "Expert-reviewed annotation",
    "expert_annotation": "Expert annotation (not reviewed)",
    "source_information": "Published source statement (transcribed, not verified)",
    "project_annotation": "Project annotation (not expert-reviewed)",
    "ai_draft": "AI draft (not a reading)",
    "synthetic_model": "Synthetic model output (not evidence)",
    "synthetic_rule_decoder": "Synthetic rule-based decoder (fictional language, not evidence)",
    "none": "No source",
}

HUMAN_ONLY = "Human evidence only. AI drafts are listed apart and never fill a field."
UNREGISTERED = ("This image is not a registered research photograph, so no human reading, transliteration or "
                "translation applies to it.")
NOT_ESTABLISHED = "Not established"
NO_INSCRIPTION = "Not applicable — no inscription or mark is recorded."
NO_READING_TO_TRANSLITERATE = "Not available — no reading has been established, so there is nothing to transliterate."
NO_READING_TO_TRANSLATE = "Not available — no reading has been established, so nothing can be translated."
NO_TRANSLATION = "Not established — no human translation with a cited source has been recorded."
PROPER_NAME = "Not applicable — a proper name has no literal translation."
AI_DRAFT_NOTE = "AI draft — not a reading. It is never copied into a field, an annotation or a translation."
PROMOTED = "research record: promoted from expert consensus (label_source expert_annotation)"

PRESENCE = {"yes": "Inscription or mark present", "no": "No inscription or mark",
            "uncertain": "Uncertain whether an inscription or mark is present"}
COMPLETENESS = {"complete": "Complete — every sign is read",
                "partial": "Partial — some signs are lost or doubtful",
                "fragmentary": "Fragmentary — only isolated signs are read",
                "illegible": "Illegible — no sign can be read"}


def entry(field: str, display: str, *, state: str, value: Any = None, tier: str = "none",
          confidence: str = "not_applicable", evidence: list[str] | None = None, explanation: str = "",
          caveats: list[str] | None = None, synthetic: bool = False) -> dict[str, Any]:
    """One field of the block. ``display`` is what is shown; ``value`` is the recorded value, if any."""
    if state not in STATES or tier not in TIERS:
        raise ValueError(f"unknown state {state!r} or tier {tier!r}")
    return {"field": field, "label": dict(FIELDS)[field], "state": state, "value": value, "display": display,
            "tier": tier, "tier_label": TIERS[tier], "confidence": confidence, "evidence": list(evidence or []),
            "explanation": explanation, "caveats": list(caveats or []), "synthetic": synthetic}


def _tier(provenance: str, basis: dict[str, Any] | None, annotation_status: str) -> str:
    if provenance in ("none", "ai_prediction") or basis is None:
        return "none"
    if annotation_status == "adjudicated":
        return "adjudicated"
    if provenance == "expert_annotation":
        return "expert_reviewed" if basis.get("review_state") == "expert_reviewed" else "expert_annotation"
    return provenance if provenance in TIERS else "none"


def _source(ref_id: str, references: dict[str, dict[str, Any]]) -> str:
    if ref_id in ("annotator_observation", "this_annotator"):
        return "source: the annotator's own observation"
    ref = references.get(ref_id)
    status = ref["verification_status"] if ref else "unknown reference"
    return f"source: {ref_id} ({status.replace('_', ' ')})"


def ai_drafts(ai_predictions: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    """OCR candidates and AI-prediction readings, labelled as drafts. Never a field value."""
    out = []
    for p in ai_predictions:
        if p.get("stage") == "ocr" and is_real(p.get("candidate_text")):
            out.append({"kind": "ocr_candidate", "text": p["candidate_text"], "engine": p.get("engine"),
                        "engine_score": p.get("engine_score"), "note": AI_DRAFT_NOTE})
        elif "annotation_id" in p and is_real(p.get("reading")):
            out.append({"kind": "ai_prediction_annotation", "text": p["reading"], "engine": p.get("annotator"),
                        "engine_score": None, "note": AI_DRAFT_NOTE})
    return out


def reading_results(*, dataset_type: str, reading: dict[str, Any], interpretation: dict[str, Any],
                    basis: dict[str, Any] | None, annotation_status: str = "unannotated",
                    record: dict[str, Any] | None = None, references: dict[str, dict[str, Any]] | None = None,
                    ai_predictions: list[dict[str, Any]] | tuple[dict[str, Any], ...] = ()) -> dict[str, Any]:
    """The block for a real (research or unregistered) image.

    ``reading`` / ``interpretation``: ``AnalysisResult.reading`` / ``.interpretation`` (human evidence only);
    ``basis``: the annotation they come from (or None); ``record``: the research record (promoted ground truth).
    """
    references = references or {}
    record = record or {}
    drafts = ai_drafts(ai_predictions)
    registered = dataset_type == "research"
    promoted_rec = registered and record.get("label_source") == "expert_annotation"     # written by promotion only
    prov = reading.get("provenance", "none")
    tier = _tier(prov, basis, annotation_status)
    b_ins = (basis or {}).get("inscription", {})
    who = f"annotation {basis['annotation_id']}" if basis else ""
    no_human = UNREGISTERED if not registered else "No human annotation of this artifact has been recorded."

    # -- inscription or mark status ----------------------------------------------------------------
    pres = reading.get("inscription_present") or {}
    pres_value = pres.get("value", "unknown")
    promoted_pres = record.get("inscription_present")
    if promoted_rec and promoted_pres in PRESENCE:
        status = entry("inscription_status", PRESENCE[promoted_pres], state="established", value=promoted_pres,
                       tier="promoted_ground_truth", evidence=[PROMOTED],
                       caveats=([f"The current annotation records {pres_value!r}."]
                                if pres_value in PRESENCE and pres_value != promoted_pres else []))
    elif pres_value in PRESENCE:
        ev = [who] + ([f"{len(b_ins.get('regions', []))} region(s) marked by the annotator"]
                      if b_ins.get("regions") else [])
        status = entry("inscription_status", PRESENCE[pres_value], state="established", value=pres_value,
                       tier=_tier(pres.get("provenance", "none"), basis, annotation_status),
                       confidence=pres.get("confidence", "unknown"), evidence=ev,
                       explanation=("The annotator could not tell; nothing is read from the marks."
                                    if pres_value == "uncertain" else ""))
    else:
        status = entry("inscription_status", NOT_ESTABLISHED, state="not_established",
                       explanation=no_human if basis is None else
                       "The annotation does not record whether an inscription or mark is present.")
    absent = status["value"] == "no" or reading.get("value") == "not_applicable"

    # -- transcription -----------------------------------------------------------------------------
    value, completeness = reading.get("value"), reading.get("completeness") or "unknown"
    promoted = record.get("transcription")
    known = is_real(value)
    caveats: list[str] = []
    if known and completeness in ("partial", "fragmentary"):
        caveats.append(COMPLETENESS[completeness] + ": lost or doubtful signs are not supplied.")
    conf = reading.get("confidence", "unknown")
    if known and conf in ("unknown", "very_low", "low"):
        caveats.append(f"Uncertain reading: the annotator's confidence is {conf.replace('_', ' ')}.")
    alts = reading.get("alternative_readings") or []
    if alts:
        caveats.append("Alternative reading(s) recorded: " + "; ".join(
            f"{a.get('reading')} ({a.get('source')})" for a in alts) + ".")
    if promoted_rec and is_real(promoted):
        ev = [PROMOTED] + ([str(record["reading_source"])] if is_real(record.get("reading_source")) else [])
        if known and value != promoted:
            caveats.append(f"The current annotation reads {value!r}, which differs from the promoted value.")
        transcription = entry("transcription", str(promoted), state="established", value=promoted,
                              tier="promoted_ground_truth", confidence=conf if known else "not_recorded",
                              evidence=ev, caveats=caveats)
    elif known:
        transcription = entry("transcription", str(value), state="established", value=value, tier=tier,
                              confidence=conf, evidence=[who, _source(reading.get("source", "not_available"),
                                                                       references)], caveats=caveats)
    elif absent:
        transcription = entry("transcription", NO_INSCRIPTION, state="not_applicable")
    elif completeness == "illegible":
        transcription = entry("transcription", "Illegible — no transcription", state="not_established", tier=tier,
                              evidence=[who], explanation="The annotator examined the marks and recorded them as "
                              "illegible; no sign is supplied by inference.")
    else:
        transcription = entry("transcription", NOT_ESTABLISHED, state="not_established",
                              explanation=(no_human if basis is None else "The annotation records no reading.")
                              + (" An AI draft exists (listed below); it is never a reading." if drafts else ""))
    read = transcription["state"] == "established"

    # -- transliteration ---------------------------------------------------------------------------
    tl, promoted_tl = reading.get("transliteration"), record.get("transliteration")
    scheme = b_ins.get("transliteration_scheme", "not_available")
    if absent:
        transliteration = entry("transliteration", NO_INSCRIPTION, state="not_applicable")
    elif not read:
        transliteration = entry("transliteration", NO_READING_TO_TRANSLITERATE, state="not_available")
    elif promoted_rec and is_real(promoted_tl) and transcription["tier"] == "promoted_ground_truth":
        s = record.get("transliteration_scheme")
        transliteration = entry("transliteration", str(promoted_tl), state="established", value=promoted_tl,
                                tier="promoted_ground_truth", evidence=[PROMOTED] + ([f"scheme: {s}"] if is_real(s) else []))
    elif is_real(tl):
        transliteration = entry("transliteration", str(tl), state="established", value=tl, tier=tier,
                                confidence=conf, evidence=[who] + ([f"scheme: {scheme}"] if is_real(scheme) else
                                                                   ["scheme: not recorded"]),
                                caveats=[c for c in caveats if c.startswith(("Partial", "Fragmentary"))])
    else:
        transliteration = entry("transliteration", NOT_ESTABLISHED, state="not_established",
                                explanation="No transliteration has been recorded with this reading.")

    # -- translation -------------------------------------------------------------------------------
    st, promoted_tr = interpretation.get("state", "no_reading"), record.get("translation_en")
    if absent:
        translation = entry("translation", NO_INSCRIPTION, state="not_applicable")
    elif not read:
        translation = entry("translation", NO_READING_TO_TRANSLATE, state="not_available")
    elif promoted_rec and is_real(promoted_tr) and transcription["tier"] == "promoted_ground_truth":
        translation = entry("translation", str(promoted_tr), state="established", value=promoted_tr,
                            tier="promoted_ground_truth", evidence=[PROMOTED],
                            caveats=[c for c in caveats if not c.startswith("Alternative")])
    elif st == "translated":
        translation = entry("translation", str(interpretation["translation"]), state="established",
                            value=interpretation["translation"],
                            tier=_tier(interpretation.get("provenance", "none"), basis, annotation_status),
                            confidence=interpretation.get("confidence", "unknown"),
                            evidence=[who, _source(interpretation.get("source", "not_available"), references)],
                            caveats=([f"Limited to what is read: the reading is {completeness}."]
                                     if completeness in ("partial", "fragmentary") else [])
                            + ([f"Based on an uncertain reading (confidence {conf.replace('_', ' ')})."]
                               if conf in ("unknown", "very_low", "low") else []))
    elif st == "personal_name":
        translation = entry("translation", PROPER_NAME, state="not_applicable",
                            tier=_tier(interpretation.get("provenance", "none"), basis, annotation_status),
                            evidence=[who], explanation=str(interpretation.get("meaning", "")))
    elif st == "not_translatable":
        translation = entry("translation", "Not applicable — " + str(interpretation.get("meaning", "no translation.")),
                            state="not_applicable", evidence=[who])
    else:
        translation = entry("translation", NO_TRANSLATION, state="not_established",
                            explanation="A translation is shown only when a human records one with a cited source; "
                                        "it is never derived from a classifier or an OCR draft.")

    # -- reading completeness ----------------------------------------------------------------------
    if absent:
        comp = entry("completeness", NO_INSCRIPTION, state="not_applicable", value="not_applicable")
    elif completeness in COMPLETENESS:
        comp = entry("completeness", COMPLETENESS[completeness], state="established", value=completeness,
                     tier=tier, evidence=[who])
    else:
        comp = entry("completeness", "Unknown", state="not_established", value="unknown",
                     explanation=("The annotator did not record how complete the reading is." if read else
                                  "No reading has been recorded, so its completeness is unknown."))

    fields = [status, transcription, transliteration, translation, comp]
    for f in fields:
        f["evidence"] = [x for x in f["evidence"] if x]
    return {"label": "Language / reading results", "dataset_type": dataset_type, "synthetic": False,
            "statement": HUMAN_ONLY if registered else UNREGISTERED, "annotation_status": annotation_status,
            "fields": fields, "ai_drafts": drafts}


__all__ = ["AI_DRAFT_NOTE", "COMPLETENESS", "FIELDS", "HUMAN_ONLY", "NOT_ESTABLISHED", "NO_INSCRIPTION",
           "NO_READING_TO_TRANSLATE", "NO_READING_TO_TRANSLITERATE", "NO_TRANSLATION", "PRESENCE", "PROMOTED", "PROPER_NAME",
           "STATES", "TIERS", "UNREGISTERED", "ai_drafts", "entry", "reading_results"]
