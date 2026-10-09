"""Language / reading results of a SYNTHETIC run (same shape as ``src.translation.reading``).

    SYNTHETIC DEMONSTRATION — not archaeological evidence.

The synthetic glyphs SG00-SG15 are invented codes: no sound, no reading, no meaning. So the block shows the
synthetic glyph transcription the models produced, states that transliteration is not applicable and that no
translation is available, and says why. The synthetic interpretation category (an invented rule table,
``src.synthetic.interpretation``) is an engineering placeholder: it is named here only to say it is not a
meaning. No Tamil word, English translation, personal name or linguistic meaning is ever produced.
"""

from __future__ import annotations

from typing import Any

from src.translation.reading import NOT_ESTABLISHED, entry

from . import UI_BANNER

STATEMENT = (f"{UI_BANNER}: synthetic model output — not archaeological evidence. Synthetic glyph identifiers "
             "are codes, not a script, so they have no transliteration and no translation.")
TRANSLITERATION = ("Not applicable — synthetic glyph identifiers (SG00–SG15) are codes with no sound value, so "
                   "there is nothing to transliterate.")
TRANSLATION = "Not available — synthetic glyph identifiers have no established linguistic meaning."
NOT_RUN = "Not available — the synthetic pipeline did not run on this image (the synthetic models are not loaded)."


def synthetic_reading_results(analysis: dict[str, Any] | None) -> dict[str, Any]:
    """The block for a synthetic image. ``analysis`` is a ``SyntheticPipeline.run`` result, or None."""
    def syn(field: str, display: str, **kw: Any) -> dict[str, Any]:
        return entry(field, display, synthetic=True, **kw)

    translation_note = ("A translation is never produced for synthetic glyphs: they belong to no language, and "
                        "neither the synthetic classifier nor the synthetic OCR can supply one.")
    if analysis is None:
        fields = [syn("inscription_status", NOT_ESTABLISHED, state="not_established", explanation=NOT_RUN),
                  syn("transcription", NOT_RUN, state="not_available"),
                  syn("transliteration", TRANSLITERATION, state="not_applicable"),
                  syn("translation", TRANSLATION, state="not_available", explanation=translation_note),
                  syn("completeness", "Not applicable — no synthetic glyph transcription.", state="not_applicable",
                      value="not_applicable")]
        return {"label": "Language / reading results", "dataset_type": "synthetic", "synthetic": True,
                "statement": STATEMENT, "fields": fields, "ai_drafts": []}

    c, ins, o, it = analysis["classification"], analysis["inscription"], analysis["ocr"], analysis["interpretation"]
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

    read = o["status"] == "read"
    if read:
        transcription = syn("transcription", o["transcription"], state="established", value=o["transcription"],
                            tier="synthetic_model",
                            confidence=f"{o['mean_glyph_score']:.2f} mean glyph score (synthetic model score)",
                            evidence=[f"{o['glyph_count']} glyph(s) segmented ({o['segmentation']}) and recognised by "
                                      "the synthetic glyph classifier"],
                            explanation="Synthetic glyph transcription: invented glyph codes, not a transcription of "
                                        "any script.")
    else:
        transcription = syn("transcription", f"Not available — no synthetic glyph transcription ({o['reason']}).",
                            state="not_available", tier="synthetic_model")

    category = it.get("category", "")
    translation = syn("translation", TRANSLATION, state="not_available",
                      explanation=translation_note + (
                          f" The synthetic interpretation category {category!r} comes from an invented rule table: it "
                          "is an engineering placeholder, not a meaning or a translation."
                          if category and category != "synthetic_no_reading" else ""))
    completeness = (syn("completeness", "Unknown — not assessed by the synthetic pipeline", state="not_established",
                        value="unknown", explanation="The synthetic pipeline does not estimate how complete its glyph "
                        "transcription is. The ground-truth comparison is a benchmark check only and never changes "
                        "a result.")
                    if read else
                    syn("completeness", "Not applicable — no synthetic glyph transcription.", state="not_applicable",
                        value="not_applicable"))
    fields = [status, transcription, syn("transliteration", TRANSLITERATION, state="not_applicable"), translation,
              completeness]
    return {"label": "Language / reading results", "dataset_type": "synthetic", "synthetic": True,
            "statement": STATEMENT, "fields": fields, "ai_drafts": []}


__all__ = ["NOT_RUN", "STATEMENT", "TRANSLATION", "TRANSLITERATION", "synthetic_reading_results"]
