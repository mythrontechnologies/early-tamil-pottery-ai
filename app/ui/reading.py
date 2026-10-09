"""The LANGUAGE / READING RESULTS section (Analysis page, real and synthetic modes).

One card per field - inscription or mark status, transcription, transliteration, translation, reading
completeness - each with its state, who asserts it (tier), its confidence, why it could not be established and
any caveat (partial, uncertain, alternative readings). Every value comes from the result's ``reading_results``
block (``src.translation.reading`` / ``src.synthetic.reading``) and is escaped. Status is never colour alone: each
state and tier is a labelled badge with a glyph. Research mode adds the supporting evidence (annotation ids,
sources and their verification status); Presentation mode keeps every value, state, tier, confidence and
explanation. AI drafts are shown apart, in the AI-observation style, and never as a reading.
"""

from __future__ import annotations

from typing import Any

from ui.components import badge, e, kv

STATE_BADGE = {"established": None, "not_established": ("insufficient", "Not established"),
               "not_applicable": ("neutral", "Not applicable"), "not_available": ("insufficient", "Not available")}
TIER_BADGE = {"promoted_ground_truth": ("expert", "Promoted ground truth"), "adjudicated": ("expert", "Expert adjudication"),
              "expert_reviewed": ("expert", "Expert-reviewed"), "expert_annotation": ("expert", "Expert · not reviewed"),
              "source_information": ("bibliographic", "Published source · unverified"),
              "project_annotation": ("project", "Project · not expert-reviewed"),
              "ai_draft": ("ai", "AI draft · not a reading"), "synthetic_model": ("synthetic", "Synthetic model output"),
              "synthetic_rule_decoder": ("synthetic", "Synthetic rule-based decoder")}


def _field(f: dict[str, Any], *, research: bool) -> str:
    tags = [badge(*b) for b in (STATE_BADGE.get(f["state"]), TIER_BADGE.get(f["tier"])) if b]
    if f.get("synthetic") and f["tier"] != "synthetic_model":
        tags.append(badge("synthetic", "Synthetic demonstration"))
    mono = " mono" if f.get("synthetic") and f["field"] == "transcription" and f["state"] == "established" else ""
    lang = ' lang="zxx"' if mono else ""                 # glyph codes have no linguistic content
    conf = f["confidence"] if f["confidence"] not in ("not_applicable", "") else ""
    notes = [x for x in (f["explanation"], *f["caveats"]) if x]
    return (f'<div class="etp-card etp-reading-field" role="group" aria-label="{e(f["label"])}: {e(f["display"])}">'
            f'<div class="k">{e(f["label"])}</div><div class="v{mono}"{lang}>{e(f["display"])}</div>'
            + (f'<div class="etp-reading-tags">{"".join(tags)}</div>' if tags else "")
            + (f'<div class="who">Confidence: {e(conf.replace("_", " "))}</div>' if conf else "")
            + (f'<div class="who">Asserted by: {e(f["tier_label"])}</div>' if f["tier"] != "none" else "")
            + ("<ul>" + "".join(f"<li>{e(x)}</li>" for x in notes) + "</ul>" if notes else "")
            + (f'<div class="who">Evidence: {e("; ".join(f["evidence"]))}</div>' if research and f["evidence"] else "")
            + "</div>")


def _language(lang: dict[str, Any]) -> str:
    """The synthetic-language strip: banner, method, status and the word-by-word gloss (never for real data)."""
    rows = [("Method", f'{lang["method"]} · {lang["spec"]}', False), ("Status", lang["status_text"], False)]
    if lang.get("roles"):
        rows.append(("Grammatical roles", lang["roles"], False))
    if lang.get("reason"):
        rows.append(("Reason", lang["reason"], False))
    gloss = "".join(f'<tr><td class="mono" lang="zxx">{e(g["glyph"])}</td><td lang="zxx">{e(g["reading"])}</td>'
                    f'<td>{e(g["gloss"])}</td><td>{e(g["class"])}</td><td>{e(g["role"])}</td></tr>' for g in lang.get("gloss", []))
    table = ('<table class="etp-gloss"><caption>Word-by-word gloss (fictional synthetic lexicon)</caption><thead><tr>'
             '<th scope="col">Glyph</th><th scope="col">Reading</th><th scope="col">Gloss</th><th scope="col">Class</th>'
             f'<th scope="col">Role</th></tr></thead><tbody>{gloss}</tbody></table>') if gloss else ""
    return (f'<div class="etp-synthetic etp-language" role="note" aria-label="{e(lang["banner"])}">'
            f'{badge("synthetic", lang["banner"])}<p>{e(lang["fiction"])} {e(lang["method_note"])}</p>{kv(rows)}{table}</div>')


def reading_results_html(block: dict[str, Any] | None, *, research: bool) -> str:
    """The section body. ``block`` is ``result["reading_results"]`` (or a synthetic run's)."""
    if not block:
        return ""
    syn = block.get("synthetic", False)
    lede = badge("synthetic", "Synthetic demonstration") if syn else badge("research_data")
    drafts = block.get("ai_drafts") or []
    draft_html = ""
    if drafts:
        items = "".join(f'<li><span>{e(d["text"])}</span>'
                        + (f' · {e(d["engine"])}' + (f' · engine score {d["engine_score"]:.2f}' if d.get("engine_score") is not None else "")
                           if research else "") + "</li>" for d in drafts)
        draft_html = (f'<section class="etp-ai" aria-label="AI drafts: not readings"><div class="etp-ai-head">{badge("ai", "AI draft")}'
                      f'<span>AI drafts — not readings</span></div><ul style="margin:.2rem 0 0 1.1rem;padding:0">{items}</ul>'
                      f'<p>{e(drafts[0]["note"])}</p></section>')
    return (f'<section class="etp-reading{" etp-reading-syn" if syn else ""}" role="region" '
            f'aria-label="Language and reading results{", synthetic demonstration" if syn else ""}">'
            f'<p class="etp-reading-lede">{lede}<span>{e(block["statement"])}</span></p>'
            '<div class="etp-grid cols-3">' + "".join(_field(f, research=research) for f in block["fields"]) + "</div>"
            + (_language(block["language"]) if syn and block.get("language") else "")
            + draft_html + "</section>")


def field_map(block: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {f["field"]: f for f in (block or {}).get("fields", [])}


__all__ = ["TIER_BADGE", "field_map", "reading_results_html"]
