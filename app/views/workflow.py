"""Workflow timeline: the existing src.workflow stages, rendered. No status is computed here."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.boot import boot

boot("Workflow")

import streamlit as st
from ui import data
from ui.components import badge, e, footer, grid, note, page_header, section, stat

page_header("Workflow", "From photograph to model",
            "The eleven stages every photograph passes through, checked in order by the project's own validators "
            "(python -m src.workflow status). The first stage that is not complete is where work continues.")

wf = data.workflow()
stages, cur = wf["stages"], wf["current_stage"]
done = sum(s["status"] == "PASS" for s in stages)
grid([
    stat(f"{done}/{len(stages)}", "stages complete"),
    stat(cur["name"] if cur else "all complete", "current stage", word=True),
    stat("yes" if cur and cur["human_action"] else "no", "human action required", word=True),
    stat(sum(s["status"] == "BLOCKED" for s in stages), "stages with a problem", "BLOCKED means something is wrong"),
], "cols-4")
if cur:
    note(f'<b>Next:</b> {e(cur["next_action"])}')

section("Stages", "PASS · WAITING (needs people or data) · BLOCKED (fix first)")
items = []
for s in stages:
    st_cls = s["status"].lower()
    is_cur = cur is not None and s["number"] == cur["number"]
    glyph = {"pass": "✓", "waiting": "…", "blocked": "!"}[st_cls]
    extra = badge("human") if s["human_action"] and s["status"] != "PASS" else ""
    nxt = (f'<div class="next">Next: <code>{e(s["next_action"])}</code></div>'
           if s["status"] != "PASS" and s["next_action"] else "")
    items.append(
        f'<li class="etp-stage {st_cls}{" current" if is_cur else ""}" style="list-style:none">'
        f'<span class="dot" aria-hidden="true">{glyph}</span>'
        f'<div class="row"><span class="num">{s["number"]:02d}</span><span class="name">{e(s["name"])}</span>'
        f'{badge(st_cls, s["status"])}{extra}'
        + ('<span class="etp-badge b-neutral">current</span>' if is_cur else "")
        + f'</div><div class="detail">{e(s["detail"])}</div>{nxt}</li>')
st.html(f'<ol class="etp-timeline" aria-label="Workflow stages">{"".join(items)}</ol>')

section("Append-only stores", "tamper evidence")
from src.annotation.promote import _settings as promotion_settings
from src.integrity import verify
from src.knowledge.verification import registry_path

rows = []
for name, path in (("Annotation store", data.store().path), ("Verification registry", registry_path()),
                   ("Promotion log", promotion_settings(None)[0])):
    rep = verify(path)
    state = {"INTACT": "pass", "EMPTY": "neutral"}.get(rep.status, "blocked")
    rows.append(f'<div class="etp-card" style="padding:.9rem 1rem"><div style="display:flex;justify-content:space-between;'
                f'align-items:center"><b>{e(name)}</b>{badge(state, rep.status.replace("_", " ").lower())}</div>'
                f'<div class="etp-mono" style="color:var(--muted);font-size:.8rem;margin-top:.45rem">{rep.lines} line(s) · '
                f'ledger head {e(rep.head[:16])}…</div></div>')
grid(rows, "cols-3")
footer()
