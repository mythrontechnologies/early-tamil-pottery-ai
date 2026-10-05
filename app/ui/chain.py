"""The evidence chain: from observation to reference, read from an analysis result.

``evidence_chain(result)`` is a PURE function over ``src.inference.analyze(...).to_dict()``. Each
node's status is read from a field of that result, never guessed:

    OBSERVATION → INSCRIPTION REGION → SCRIPT ASSESSMENT → READING → LINGUISTIC EVIDENCE
      → ARCHAEOLOGICAL CONTEXT → CHRONOLOGICAL ESTIMATE → REFERENCE

AI observations are NOT part of the chain; they are shown separately. Statuses carry a word
and a glyph (see ``ui.components.BADGES``), never colour alone.
"""

from __future__ import annotations

from typing import Any

from .components import badge, e

#: provenance -> (badge kind, badge label)
PROVENANCE_BADGE = {
    "expert_annotation": ("expert", "Expert review"),
    "project_annotation": ("project", "Project annotation"),
    "source_information": ("transcribed", "Published source · unverified"),
    "ai_prediction": ("ai", "AI observation — not evidence"),
}
INSUFFICIENT = ("insufficient", "Insufficient evidence")
EMPTY = ("not_available", "not_applicable", "unknown", None, "")


def _prov(p: str | None) -> tuple[str, str]:
    return PROVENANCE_BADGE.get(p or "", INSUFFICIENT)


def evidence_chain(r: dict[str, Any]) -> list[dict[str, Any]]:
    q, script, reading = r["image_quality"], r["script"], r["transcription"]["human_reading"]
    ident = r["evidence"]["identification"]
    age, refs = r["age"], r["evidence"]["references"]
    nodes: list[dict[str, Any]] = []

    def node(key: str, title: str, value: str, status: tuple[str, str], *, confidence: str = "—",
             source: str = "—", provenance: str = "—", uncertainty: str = "") -> None:
        nodes.append({"key": key, "title": title, "value": value, "status": status, "confidence": confidence,
                      "source": source, "provenance": provenance, "uncertainty": uncertainty})

    reg = "registered research photograph" if r["image"]["registered"] else "unregistered image (no provenance)"
    node("observation", "Observation", f"{r['image']['width_px']}×{r['image']['height_px']} px · {reg}",
         ("neutral", "Technical measurement"), source="image file (SHA-256 " + r["image"]["sha256"][:12] + "…)",
         provenance="measured by the guarded image loader",
         uncertainty="Quality flags: " + (", ".join(q["flags"]) or "none") + " (uncalibrated; they describe the photograph, not the object).")

    human = [x for x in r["regions"] if x["source"] == "human_annotation"]
    if human:
        tiers = sorted({x.get("provenance_type") or "project_annotation" for x in human})
        st = _prov("expert_annotation" if "expert_annotation" in tiers else tiers[0])
        node("region", "Inscription region", f"{len(human)} region(s) marked by people", st,
             source=", ".join(sorted({x.get("annotator") or "—" for x in human})), provenance=", ".join(tiers),
             uncertainty="Regions are where people saw marks; they are not a reading.")
    else:
        node("region", "Inscription region", "No region has been marked by a person", INSUFFICIENT,
             uncertainty="No validated automatic detector exists; user-drawn regions are viewing aids, not evidence.")

    known = script.get("value") not in EMPTY
    node("script", "Script assessment", script.get("statement", "Script not determined."),
         _prov(script.get("provenance")) if known else INSUFFICIENT,
         confidence=script.get("confidence", "—") if known else "—",
         source=script.get("source", "—") if known else "—", provenance=script.get("provenance_label", "—"),
         uncertainty="" if known else "No human annotator or published source has assessed the script.")

    has_reading = reading.get("value") not in EMPTY
    alts = reading.get("alternative_readings") or []
    node("reading", "Reading", r["transcription"]["statement"],
         _prov(reading.get("provenance")) if has_reading else INSUFFICIENT,
         confidence=reading.get("confidence", "—") if has_reading else "—",
         source=reading.get("source", "—") if has_reading else "—", provenance=reading.get("provenance_label", "—"),
         uncertainty=(f"{len(alts)} alternative reading(s) recorded." if alts else "")
         + ("" if has_reading else " OCR output is never used as a reading."))

    ling = [x for x in r["reasoning"] if x.startswith("Linguistic")]
    node("linguistic", "Linguistic evidence", "; ".join(ling) if ling else "No linguistic feature recorded",
         ("neutral", "Recorded") if ling else INSUFFICIENT,
         uncertainty="Linguistic features date nothing unless a dating-evidence item says so.")

    ctx = ident.get("context_reliability", {}) or {}
    site = ident.get("site", {}) or {}
    ctx_known = ctx.get("value") not in EMPTY + ("museum_unprovenanced", "unprovenanced")
    node("context", "Archaeological context",
         f"site: {site.get('value') if site.get('value') not in EMPTY else 'not recorded'} · context: {ctx.get('value') or 'unknown'}",
         (("transcribed", "As stated by source") if ctx_known else INSUFFICIENT),
         provenance=site.get("provenance_label", "—"),
         uncertainty="" if ctx_known else "No secure archaeological context is recorded for this object.")

    state = age.get("state")
    ds = age.get("dating_summary", {}) or {}
    status = {"estimated": ("neutral", f"Estimated · {r['confidence']['archaeological']}"),
              "outer_bound_only": ("unverified", "Outer bound only")}.get(state, INSUFFICIENT)
    node("chronology", "Chronological estimate", age.get("display", "Insufficient evidence"), status,
         confidence=r["confidence"]["archaeological"], source="; ".join(ds.get("basis", [])) or "—",
         uncertainty="; ".join(ds.get("important_uncertainty", [])))

    if refs:
        statuses = {v["verification_status"] for v in refs.values()}
        st = (("verified", "Verified") if statuses == {"verified_against_source"}
              else ("unverified", "Unverified") if "verified_against_source" not in statuses
              else ("unverified", "Partly verified"))
        node("reference", "Reference", ", ".join(sorted(refs)), st, source="; ".join(v["citation"] for v in refs.values()),
             provenance="verification registry (effective status)",
             uncertainty="A reference is verified only for the claims a named person checked.")
    else:
        node("reference", "Reference", "No reference is cited by the evidence", INSUFFICIENT,
             uncertainty="Nothing here rests on a publication yet.")
    return nodes


def render_chain(nodes: list[dict[str, Any]], *, label: str = "Evidence chain, from observation to reference",
                 note: str = "AI observations are not part of the evidence chain; they are shown separately and never "
                             "count as evidence.") -> str:
    """Interactive, keyboard-native chain: every node is a <details> element. Synthetic nodes (Milestone 10)
    carry ``synthetic: True`` and get an extra SYNTHETIC badge."""
    items = []
    for i, n in enumerate(nodes, 1):
        kind, status_label = n["status"]
        extra = badge("synthetic", "Synthetic") if n.get("synthetic") and kind != "synthetic" else ""
        items.append(
            f'<li class="etp-node"><details><summary><span class="num">{i:02d}</span>'
            f'<span class="t">{e(n["title"])}</span>{badge(kind, status_label)}{extra}'
            f'<span class="v">{e(n["value"])}</span></summary>'
            f'<dl class="etp-kv"><dt>Confidence</dt><dd>{e(n["confidence"])}</dd><dt>Source</dt><dd>{e(n["source"])}</dd>'
            f'<dt>Provenance</dt><dd>{e(n["provenance"])}</dd><dt>Uncertainty</dt><dd>{e(n["uncertainty"] or "—")}</dd></dl>'
            "</details></li>")
    return (f'<ol class="etp-chain" aria-label="{e(label)}">' + "".join(items)
            + f'</ol><p class="etp-chain-note">{e(note)}</p>')


__all__ = ["INSUFFICIENT", "PROVENANCE_BADGE", "evidence_chain", "render_chain"]
