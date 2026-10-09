"""Language / reading results of a SYNTHETIC run (same shape as ``src.translation.reading``).

    SYNTHETIC LANGUAGE — NOT TAMIL-BRAHMI. Synthetic model output and a fictional language; not archaeological
    evidence.

The synthetic glyph transcription comes from the synthetic OCR. The transliteration and the English translation
come from the deterministic synthetic-language decoder (``src.synthetic.lexicon``) applied to those PREDICTED
codes: correct only under that invented specification, never a reading of Tamil-Brahmi. The decoder's status,
method and failure reason are carried into every field; nothing is completed or guessed, and the generator's
ground truth is never used here. The placeholder interpretation category is a separate field of the analysis.
"""

from __future__ import annotations

from typing import Any

from src.translation.reading import NOT_ESTABLISHED, entry

from . import UI_BANNER
from .lexicon import BANNER, FICTION, METHOD, METHOD_NOTE, SPEC_ID, STATUS_TEXT, grammatical_interpretation

STATEMENT = (f"{BANNER}. {UI_BANNER}: synthetic model output and a fictional language invented for engineering "
             "demonstration — not archaeological evidence and not a reading of Tamil-Brahmi.")
NOT_RUN = "Not available — the synthetic pipeline did not run on this image (the synthetic models are not loaded)."
COMPLETENESS = {"translated": ("complete", "Complete under the synthetic grammar — every glyph is part of a clause"),
                "partial": ("partial", "Partial under the synthetic grammar — trailing glyphs form no clause")}


def _language(lang: dict[str, Any] | None) -> dict[str, Any]:
    if not lang:
        return {"banner": BANNER, "spec": SPEC_ID, "method": METHOD, "method_note": METHOD_NOTE, "fiction": FICTION,
                "status": "insufficient_evidence", "status_text": STATUS_TEXT["insufficient_evidence"], "gloss": [],
                "reason": NOT_RUN}
    keys = ("banner", "spec", "method", "method_note", "fiction", "status", "status_text", "gloss", "reason",
            "unknown_glyphs", "untranslated", "confidence_note")
    return {k: lang[k] for k in keys if k in lang} | {"roles": grammatical_interpretation(lang)["summary"]}


def synthetic_reading_results(analysis: dict[str, Any] | None) -> dict[str, Any]:
    """The block for a synthetic image. ``analysis`` is a ``SyntheticPipeline.run`` result, or None."""
    def syn(field: str, display: str, **kw: Any) -> dict[str, Any]:
        return entry(field, display, synthetic=True, **kw)

    if analysis is None:
        fields = [syn("inscription_status", NOT_ESTABLISHED, state="not_established", explanation=NOT_RUN),
                  syn("transcription", NOT_RUN, state="not_available"),
                  syn("transliteration", NOT_RUN, state="not_available"),
                  syn("translation", NOT_RUN, state="not_available"),
                  syn("completeness", "Not applicable — no synthetic glyph transcription.", state="not_applicable",
                      value="not_applicable")]
        return {"label": "Language / reading results", "dataset_type": "synthetic", "synthetic": True,
                "statement": STATEMENT, "fields": fields, "ai_drafts": [], "language": _language(None)}

    c, ins, o = analysis["classification"], analysis["inscription"], analysis["ocr"]
    lang = analysis.get("synthetic_language") or {}
    status_ = lang.get("status", "insufficient_evidence")
    method = [f"method: {METHOD} ({SPEC_ID})", METHOD_NOTE]
    regions, rows = ins["regions"], ins["rows"]
    if regions:
        best = max(r["confidence"] for r in regions)
        status = syn("inscription_status",
                     f"Synthetic inscription region detected: {len(regions)} region(s), {len(rows)} glyph row(s)",
                     state="established", value="synthetic_region_detected", tier="synthetic_model",
                     confidence=f"{best:.2f} best region score (synthetic model score, not a reading confidence)",
                     evidence=["synthetic region detector", f"synthetic task class: {c['display_label']}"])
    else:
        status = syn("inscription_status", "No synthetic inscription region detected", state="established",
                     value="synthetic_no_region", tier="synthetic_model",
                     evidence=["synthetic region detector", f"synthetic task class: {c['display_label']}"])

    if o["status"] == "read":
        transcription = syn("transcription", o["transcription"], state="established", value=o["transcription"],
                            tier="synthetic_model",
                            confidence=f"{o['mean_glyph_score']:.2f} mean glyph score (synthetic model score)",
                            evidence=[f"{o['glyph_count']} glyph(s) segmented ({o['segmentation']}) and recognised by "
                                      "the synthetic glyph classifier"],
                            explanation="Synthetic glyph codes as read by the synthetic OCR; OCR errors are kept, "
                                        "never corrected from the generator's ground truth.")
    else:
        transcription = syn("transcription", f"Not available — no synthetic glyph transcription ({o['reason']}).",
                            state="not_available", tier="synthetic_model")

    why = lang.get("reason", "")
    tl = lang.get("transliteration")
    if tl:
        transliteration = syn("transliteration", tl, state="established", value=tl, tier="synthetic_rule_decoder",
                              evidence=method, explanation=f"Fictional readings from the synthetic lexicon ({BANNER})."
                              + (f" {why[:1].upper() + why[1:]}." if status_ == "unknown_glyph" else ""))
    else:
        transliteration = syn("transliteration", "Not available — no synthetic glyph was read.", state="not_available",
                              tier="synthetic_rule_decoder", evidence=method)

    tr = lang.get("translation")
    if tr:
        translation = syn("translation", tr, state="established", value=tr, tier="synthetic_rule_decoder",
                          evidence=method, explanation=f"{STATUS_TEXT[status_]}. {FICTION}",
                          caveats=([f"Partial: {why}. Untranslated: {' '.join(lang.get('untranslated', []))}."]
                                   if status_ == "partial" else [])
                          + [str(lang.get("confidence_note", ""))])
    else:
        translation = syn("translation", f"Not translated — {STATUS_TEXT[status_].split(': ', 1)[-1]}.",
                          state="not_established" if status_ != "insufficient_evidence" else "not_available",
                          tier="synthetic_rule_decoder", evidence=method,
                          explanation=(why[:1].upper() + why[1:] + ". " if why else "")
                          + "No English sentence is invented for a sequence the synthetic grammar does not accept.")

    if status_ in COMPLETENESS:
        value, text = COMPLETENESS[status_]
        completeness = syn("completeness", text, state="established", value=value, tier="synthetic_rule_decoder",
                           explanation="Judged under the fictional synthetic grammar, not from the image: a glyph the "
                                       "OCR missed cannot be seen here.")
    elif o["status"] == "read":
        completeness = syn("completeness", "Unknown — the glyphs form no complete clause", state="not_established",
                           value="unknown", tier="synthetic_rule_decoder", explanation=why)
    else:
        completeness = syn("completeness", "Not applicable — no synthetic glyph transcription.", state="not_applicable",
                           value="not_applicable")
    fields = [status, transcription, transliteration, translation, completeness]
    for f in fields:
        f["caveats"] = [x for x in f["caveats"] if x]
    return {"label": "Language / reading results", "dataset_type": "synthetic", "synthetic": True,
            "statement": STATEMENT, "fields": fields, "ai_drafts": [], "language": _language(lang)}


__all__ = ["COMPLETENESS", "NOT_RUN", "STATEMENT", "synthetic_reading_results"]
