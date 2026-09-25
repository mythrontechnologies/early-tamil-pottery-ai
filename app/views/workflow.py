"""Workflow journey: the existing src.workflow stages, rendered. No status is computed here.

The journey across the top shows each stage's state from ``python -m src.workflow status``;
stages after the current one are shown as not yet reached. Each stage then expands to its
detail and the exact next action. Blocked and waiting stages explain why.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.boot import boot, research

boot("Workflow")

import streamlit as st
from ui import data
from ui.components import badge, blocked_state, e, footer, grid, page_header, section, stat

page_header("Workflow", "From photograph to model",
            "Eleven stages every photograph passes through, checked in order by the project's own validators "
            "(python -m src.workflow status). The first stage that is not complete is where work continues.")

wf = data.workflow()
stages, cur = wf["stages"], wf["current_stage"]
cur_n = cur["number"] if cur else len(stages) + 1
done = sum(s["status"] == "PASS" for s in stages)
grid([
    stat(f"{done}/{len(stages)}", "stages complete"),
    stat(cur["name"] if cur else "all complete", "current stage", word=True),
    stat("yes" if cur and cur["human_action"] else "no", "human action required", word=True),
    stat(sum(s["status"] == "BLOCKED" for s in stages), "stages with a problem", "BLOCKED means something is wrong"),
], "cols-4")

GLYPH = {"pass": "✓", "waiting": "…", "blocked": "!"}
journey = []
for s in stages:
    cls = s["status"].lower()
    reached = s["number"] <= cur_n
    state = s["status"] if reached else "NOT YET REACHED"
    journey.append(f'<li class="{cls}{" current" if cur and s["number"] == cur_n else ""}">'
                   f'<span class="dot" aria-hidden="true">{GLYPH[cls] if reached else "◌"}</span>'
                   f'<a href="#stage-{s["number"]}">{s["number"]:02d} {e(s["name"])}<span class="st">{e(state)}</span></a></li>')
st.html(f'<ol class="etp-journey" aria-label="Workflow journey: {done} of {len(stages)} stages complete">{"".join(journey)}</ol>')

if cur:
    reason = [cur["detail"]] + ([cur["next_action"]] if cur["next_action"] else [])
    st.html(blocked_state("human" if cur["human_action"] else cur["status"].lower(),
                          f'Current stage {cur["number"]:02d} · {cur["name"]}', cur["next_action"] or cur["detail"], reason,
                          why="Why is this stage waiting?" if cur["status"] == "WAITING" else "Why is this blocked?"))

section("Stages", "select a stage for its detail and next action")
items = []
for s in stages:
    cls = s["status"].lower()
    reached = s["number"] <= cur_n
    b = badge(cls, s["status"]) if reached else badge("future", "not yet reached")
    human = badge("human") if s["human_action"] and s["status"] != "PASS" else ""
    nxt = (f'<dt>Next action</dt><dd><code>{e(s["next_action"])}</code></dd>' if s["status"] != "PASS" and s["next_action"] else "")
    items.append(f'<li class="etp-node" id="stage-{s["number"]}"><details{" open" if cur and s["number"] == cur_n else ""}>'
                 f'<summary><span class="num">{s["number"]:02d}</span><span class="t">{e(s["name"])}</span>'
                 f'<span style="display:flex;gap:.35rem;flex-wrap:wrap">{b}{human}</span><span class="v">{e(s["detail"])}</span></summary>'
                 f'<dl class="etp-kv"><dt>Status</dt><dd>{e(s["status"])}{"" if reached else " (after the current stage)"}</dd>'
                 f'<dt>Detail</dt><dd>{e(s["detail"])}</dd>{nxt}</dl></details></li>')
st.html(f'<ol class="etp-chain" aria-label="Workflow stages">{"".join(items)}</ol>')

if research():
    section("Append-only stores", "tamper evidence · research mode")
    from src.annotation.promote import _settings as promotion_settings
    from src.integrity import verify
    from src.knowledge.verification import registry_path

    rows = []
    for name, path in (("Annotation store", data.store().path), ("Verification registry", registry_path()),
                       ("Promotion log", promotion_settings(None)[0])):
        rep = verify(path)
        state = {"INTACT": "pass", "EMPTY": "neutral"}.get(rep.status, "blocked")
        rows.append(f'<div class="etp-card" style="padding:.9rem 1rem"><div style="display:flex;justify-content:space-between;'
                    f'align-items:center;gap:.6rem;flex-wrap:wrap"><b>{e(name)}</b>{badge(state, rep.status.replace("_", " ").lower())}</div>'
                    f'<div class="etp-mono" style="color:var(--muted);font-size:.8rem;margin-top:.45rem">{rep.lines} line(s) · '
                    f'ledger head {e(rep.head[:16])}…</div></div>')
    grid(rows, "cols-3")
footer()
