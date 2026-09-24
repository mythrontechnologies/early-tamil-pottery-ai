"""Dataset explorer: what exists, with provenance, and why training is (not) available."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.boot import boot

boot("Dataset")

import streamlit as st
from ui import data
from ui.components import badge, e, footer, grid, note, page_header, section, stat

page_header("Dataset", "The research dataset",
            "Every photograph, with its licence, source and hash. Counts are live and honest: a zero means "
            "nothing has been established yet, not that something is broken.")

o = data.overview()
ready = o["training_ready"]
grid([
    stat(o["artifacts"], "research artifacts"),
    stat(o["images"], "photographs"),
    stat(o["labelled_images"], "expert-labelled images", "labels come only from promoted expert annotations"),
    stat(o["expert_annotations"], "expert annotations"),
    stat(f'{o["verified_references"]}', "verified references", f'of {o["references"]} in the knowledge base'),
    stat("READY" if ready else "BLOCKED", "training",
         badge("pass" if ready else "blocked", "gate passed" if ready else "gate G1–G11"), word=True),
], "cols-6")

section("Training readiness", "the unchanged gate")
cls = o["artifacts_by_class"] or dict.fromkeys(("tamil_brahmi", "graffiti", "none", "uncertain"), 0)
counts_txt = ", ".join(f"{k} {v}" for k, v in cls.items())
if not ready:
    note("<b>Training becomes available only after sufficient expert-labelled archaeological data is available.</b> "
         f"Each class needs at least <b>5</b> artifacts for grouped cross-validation and "
         f'<b>{e(o["min_per_class"])}</b> for the hold-out split. Artifacts per class today: {e(counts_txt)}. '
         "This is the expected state of an honest dataset before expert review, not a fault.")
need = int(o["min_per_class"] or 20)
rows = []
for c, n in cls.items():
    pct = min(100, round(100 * n / need)) if need else 0
    rows.append(f'<div class="etp-card" style="padding:.9rem 1rem"><div style="display:flex;justify-content:space-between;'
                f'align-items:baseline"><span class="etp-mono" style="color:var(--sand)">{e(c)}</span>'
                f'<span class="etp-mono" style="color:var(--muted)">{e(n)} / {need}</span></div>'
                f'<div role="progressbar" aria-label="{e(c)}: {e(n)} of {need} artifacts" aria-valuemin="0" '
                f'aria-valuemax="{need}" aria-valuenow="{e(n)}" style="margin-top:.6rem;height:6px;border-radius:3px;'
                f'background:rgba(236,228,216,.07);overflow:hidden"><div style="width:{pct}%;height:100%;'
                f'background:var(--terracotta)"></div></div></div>')
grid(rows, "cols-4")
with st.expander("Gate detail (G1–G11)"):
    for g in o["gates"]:
        state = "pass" if g.get("passed") else "blocked"
        st.html(f'<div style="display:flex;gap:.7rem;align-items:flex-start;padding:.35rem 0;border-top:1px solid var(--line)">'
                f'{badge(state, "pass" if g.get("passed") else "fail")}<div><b class="etp-mono">{e(g["id"])}</b> '
                f'{e(g.get("title"))}<div style="color:var(--muted);font-size:.85rem">{e(g.get("detail"))}</div></div></div>')

section("Artifacts", "real photographs, as recorded")
arts = data.artifacts()
f1, f2 = st.columns([1, 2])
scope = f1.segmented_control("Show", ["All", "Pilot six", "Review flags"], default="All", key="ds_scope")
query = f2.text_input("Filter by artifact or image id", placeholder="e.g. SHERD_106", key="ds_q")
if scope == "Pilot six":
    arts = [a for a in arts if a["pilot"]]
elif scope == "Review flags":
    arts = [a for a in arts if a["flags"]]
if query:
    q = query.strip().lower()
    arts = [a for a in arts if q in a["artifact_id"].lower() or any(q in i["image_id"].lower() for i in a["images"])]

tiles = []
for a in arts:
    im = a["images"][0]
    uri = data.thumbnail_b64(im["path"])
    anns = a["annotations"]
    ann_txt = ", ".join(f"{v} {k.replace('_annotation', '').replace('_', ' ')}" for k, v in sorted(anns.items())) or "no annotations"
    label = im["script_type"] if im["label_source"] == "expert_annotation" else "no label"
    badges = (badge("neutral", "pilot six") if a["pilot"] else "") + "".join(badge("unresolved", "review flag") for _ in a["flags"][:1])
    img_html = (f'<img src="{uri}" loading="lazy" alt="Photograph {e(im["image_id"])} of {e(a["artifact_id"])}">' if uri
                else '<div style="aspect-ratio:4/3;display:grid;place-items:center;color:var(--muted);font-size:.8rem">image file not present</div>')
    tiles.append(
        f'<article class="etp-thumb">{img_html}<div class="cap"><b>{e(a["artifact_id"])}</b>'
        f'<span>{len(a["images"])} photograph(s) · {e(label)} · {e(ann_txt)}</span>'
        f'<span>{e(im["license"])} · sha256 <span class="etp-mono">{e((im["sha256"] or "")[:12])}…</span></span>'
        f'<div style="display:flex;gap:.35rem;flex-wrap:wrap;margin-top:.45rem">{badges}</div></div></article>')
if tiles:
    grid(tiles, "cols-4")
else:
    note("No artifact matches this filter.")

section("Provenance table")
st.dataframe([{"artifact": a["artifact_id"], "image": i["image_id"], "licence": i["license"],
               "label": i["script_type"] if i["label_source"] == "expert_annotation" else "none (unlabelled)",
               "sha256": i["sha256"], "source": i["source"]} for a in data.artifacts() for i in a["images"]],
             hide_index=True, column_config={"source": st.column_config.LinkColumn("source")})
footer()
