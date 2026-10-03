"""The collection: artifacts on museum plinths, an Artifact Inspector, and training readiness.

Every value shown comes from the records, the annotation store, the review flags and the
readiness gate. Nothing is invented; an empty field says so.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.boot import boot, research

boot("Dataset")

import streamlit as st
from ui import data
from ui.components import badge, blocked_state, dataset_badge, e, footer, grid, note, page_header, section, stat
from ui.inspector import artifact_facts, render_inspector

page_header("Collection", "The research collection",
            "Every artifact with its photograph, licence and state. Counts are live and honest: a zero means nothing has "
            "been established yet, not that something is broken.")

st.html(f'<div class="etp-dataset-line">{dataset_badge("research")}<span>Every count on this page is the research '
        "dataset only. The synthetic engineering dataset (data/synthetic, Milestone 9) is kept separate, is never "
        "counted here, and can never satisfy the training gate.</span></div>")
o = data.overview()
ready = o["training_ready"]
grid([
    stat(o["artifacts"], "research artifacts"),
    stat(o["images"], "photographs"),
    stat(o["labelled_images"], "expert-labelled images", "labels come only from promoted expert annotations"),
    stat(o["expert_annotations"], "expert annotations"),
    stat(o["verified_references"], "verified references", f'of {o["references"]} in the knowledge base'),
    stat("READY" if ready else "BLOCKED", "training",
         badge("pass", "gate passed") if ready else badge("blocked", "gate G1–G11"), word=True),
], "cols-6")


@st.dialog("Artifact inspector", width="large")
def inspect(artifact_id: str) -> None:
    facts = artifact_facts(artifact_id)
    if facts is None:
        st.error(f"No artifact {artifact_id!r} in the records.")
        return
    st.html(render_inspector(facts, research=research()))


requested = st.query_params.get("inspect")
if requested and st.session_state.get("_inspected_qp") != requested:
    st.session_state["_inspected_qp"] = requested
    inspect(str(requested))

section("Artifacts", "click Inspect for provenance, annotation and training state")
arts = data.artifacts()
f1, f2 = st.columns([1.2, 2])
scope = f1.segmented_control("Show", ["All", "Pilot six", "Review flags"], default="All", key="ds_scope")
query = f2.text_input("Filter by artifact or image id", placeholder="e.g. SHERD_106", key="ds_q")
if scope == "Pilot six":
    arts = [a for a in arts if a["pilot"]]
elif scope == "Review flags":
    arts = [a for a in arts if a["flags"]]
if query:
    q = query.strip().lower()
    arts = [a for a in arts if q in a["artifact_id"].lower() or any(q in i["image_id"].lower() for i in a["images"])]

if not arts:
    note("No artifact matches this filter.")
per_row = 4
for start in range(0, len(arts), per_row):
    cols = st.columns(per_row, gap="medium")
    for col, a in zip(cols, arts[start:start + per_row]):
        im = a["images"][0]
        uri = data.thumbnail_b64(im["path"])
        tiers = a["annotations"]
        ann = ("awaiting human annotation" if not tiers else
               ", ".join(f"{v} {k.replace('_annotation', '').replace('_', ' ')}" for k, v in sorted(tiers.items())))
        labelled = im["label_source"] == "expert_annotation"
        chips = (badge("expert", "expert-labelled") if labelled else badge("insufficient", "no label")) \
            + (badge("neutral", "pilot six") if a["pilot"] else "") + (badge("unresolved", "review flag") if a["flags"] else "")
        vit = (f'<img src="{uri}" loading="lazy" alt="Photograph {e(im["image_id"])} of artifact {e(a["artifact_id"])}">' if uri
               else '<div style="aspect-ratio:4/3;display:grid;place-items:center;color:var(--muted);font-size:.8rem">image file not present</div>')
        site = a["site"] if a["site"] not in (None, "not_available", "unknown") else "site not stated by source"
        with col:
            st.html(f'<article class="etp-plinth"><div class="plate"><div class="vit">{vit}</div><div class="base">'
                    f'<div class="id">{e(a["artifact_id"])}</div><div class="meta">{len(a["images"])} photograph(s) · {e(site)}<br>'
                    f'{e(im["license"])} · {e(ann)}</div><div class="chips">{chips}</div></div></div></article>')
            if st.button("Inspect", key=f"insp_{a['artifact_id']}", use_container_width=True,
                         help=f"Open the Artifact Inspector for {a['artifact_id']}"):
                inspect(a["artifact_id"])

section("Training readiness", "the unchanged gate")
cls = o["artifacts_by_class"] or dict.fromkeys(("tamil_brahmi", "graffiti", "none", "uncertain"), 0)
counts = ", ".join(f"{k} {v}" for k, v in cls.items())
need = int(o["min_per_class"] or 20)
if not ready:
    failing = [f'{g["id"]} {g.get("title", "")}: {g.get("detail", "")}' for g in o["gates"] if not g.get("passed")]
    st.html(blocked_state("blocked", "Awaiting expert-labelled archaeological data",
                          "Training becomes available only after sufficient expert-labelled archaeological data is available. "
                          f"Each class needs at least 5 artifacts for grouped cross-validation and {need} for the hold-out "
                          f"split. Artifacts per class today: {counts}. This is the expected state before expert review, "
                          "not a fault.", failing))
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
st.html('<div style="margin-top:.8rem"></div>')
grid(rows, "cols-4")

if research():
    section("Provenance table", "research mode")
    st.dataframe([{"artifact": a["artifact_id"], "image": i["image_id"], "licence": i["license"],
                   "label": i["script_type"] if i["label_source"] == "expert_annotation" else "none (unlabelled)",
                   "sha256": i["sha256"], "source": i["source"]} for a in data.artifacts() for i in a["images"]],
                 hide_index=True, column_config={"source": st.column_config.LinkColumn("source")})
    with st.expander("Gate detail (G1–G11)"):
        for g in o["gates"]:
            st.html(f'<div style="display:flex;gap:.7rem;align-items:flex-start;padding:.35rem 0;border-top:1px solid var(--line)">'
                    f'{badge("pass", "pass") if g.get("passed") else badge("blocked", "fail")}<div><b class="etp-mono">{e(g["id"])}</b> '
                    f'{e(g.get("title"))}<div style="color:var(--muted);font-size:.85rem">{e(g.get("detail"))}</div></div></div>')
footer()
