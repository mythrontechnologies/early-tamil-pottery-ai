"""Artifact Inspector: everything recorded about one artifact, and nothing invented.

``artifact_facts(artifact_id)`` gathers facts from the records, the annotation store
(``resolve_artifact``), the review flags and ``src.dataset.classes.eligibility``. Nothing is
derived here that the project does not already compute. ``render_inspector`` shows the facts;
implementation detail (hashes, paths, raw statuses) is collapsed by default and hidden in
Presentation mode.
"""

from __future__ import annotations

from typing import Any

from . import data
from .components import badge, e

ANNOTATION_STATE = {
    "unannotated": ("waiting", "Awaiting human annotation"),
    "provisional": ("project", "Project annotation only · provisional"),
    "project_disagreement": ("unresolved", "Project annotators disagree"),
    "disputed": ("unresolved", "Disputed · requires expert resolution"),
    "expert_label": ("expert", "Expert-labelled"),
}


def artifact_facts(artifact_id: str) -> dict[str, Any] | None:
    from src.annotation.resolve import resolve_artifact
    from src.dataset.classes import ClassSpec, eligibility

    art = next((a for a in data.artifacts() if a["artifact_id"] == artifact_id), None)
    if art is None:
        return None
    recs = [r for r in data.records() if r["artifact_id"] == artifact_id]
    current = data.store().current(artifact_id)
    res = resolve_artifact(artifact_id, current)
    experts = [a for a in current if a["provenance_type"] == "expert_annotation"]
    spec = ClassSpec.from_config()
    elig = [eligibility(r, spec) for r in recs]
    first = recs[0] if recs else {}
    return {
        "artifact_id": artifact_id, "images": art["images"], "pilot": art["pilot"], "flags": art["flags"],
        "source": "Wikimedia Commons" if "commons.wikimedia.org" in str(first.get("source_reference", "")) else
                  first.get("source_reference", "not recorded"),
        "source_url": first.get("source_reference"), "licence": first.get("license", "not recorded"),
        "attribution": data.short_attribution(first.get("rights_notes")),
        "site": first.get("site", "not_available"), "context": first.get("context_reliability", "unknown"),
        "annotation_state": ANNOTATION_STATE.get(res.status, ("neutral", res.status)),
        "annotations": {k: v for k, v in art["annotations"].items()},
        "expert_state": (("expert", f"{len(experts)} expert annotation(s): " + ", ".join(sorted({a['review_state'] for a in experts})))
                         if experts else ("waiting", "Not reviewed by an expert")),
        "eligible": all(ok for ok, _ in elig) and bool(elig),
        "eligibility_reason": sorted({why for ok, why in elig if not ok}) or ["eligible"],
    }


def render_inspector(f: dict[str, Any], *, research: bool) -> str:
    im = f["images"][0]
    thumb = data.thumbnail_b64(im["path"], 640)
    img = (f'<img src="{thumb}" alt="Photograph {e(im["image_id"])} of artifact {e(f["artifact_id"])}" class="etp-insp-img">'
           if thumb else '<div class="etp-note">Image file not present on this machine.</div>')
    site = f["site"] if f["site"] not in ("not_available", "unknown", None) else "not recorded by the source"
    rows = [("Artifact", f["artifact_id"]), ("Photographs", f"{len(f['images'])}"), ("Source", f["source"]),
            ("Licence", f["licence"]), ("Attribution", f["attribution"]), ("Site / context", f"{site} · context {f['context']}")]
    kv = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in rows)
    state = (f'<div class="etp-insp-states"><div><span class="k">Annotation</span>{badge(*f["annotation_state"])}</div>'
             f'<div><span class="k">Expert review</span>{badge(*f["expert_state"])}</div>'
             f'<div><span class="k">Training</span>{badge("pass", "Eligible") if f["eligible"] else badge("blocked", "Not eligible")}</div></div>')
    flags = "".join(f'<p class="etp-flag">{badge("unresolved", "review flag")} {e(x)}</p>' for x in f["flags"])
    tech = ""
    if research:
        imgs = "".join(f"<tr><td>{e(i['image_id'])}</td><td class='etp-mono'>{e(i['sha256'])}</td><td>{e(i['path'])}</td></tr>" for i in f["images"])
        tech = (f'<details class="etp-tech"><summary>Technical details (hashes, paths, eligibility)</summary>'
                f'<table class="etp-table"><thead><tr><th>image</th><th>SHA-256</th><th>path under data/raw</th></tr></thead><tbody>{imgs}</tbody></table>'
                f'<p>Eligibility: {e("; ".join(f["eligibility_reason"]))}</p>'
                f'<p>Annotations by tier: {e(f["annotations"] or "none")}</p></details>')
    return (f'<article class="etp-inspector" aria-label="Artifact inspector: {e(f["artifact_id"])}">{img}'
            f'<div class="etp-insp-body"><div class="etp-eyebrow">Artifact</div><h3 class="etp-insp-title">{e(f["artifact_id"])}</h3>'
            f'{state}{flags}<dl class="etp-kv">{kv}</dl>{tech}</div></article>')


__all__ = ["ANNOTATION_STATE", "artifact_facts", "render_inspector"]
