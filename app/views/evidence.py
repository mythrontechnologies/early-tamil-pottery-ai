"""Evidence explorer: references, claims, verification state, provenance and uncertainty.

Status comes from the verification registry (EFFECTIVE status), never from a declaration.
Unresolved placeholders (R3, R5) are always shown as UNRESOLVED; nothing is styled as verified
unless a human verification record exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.boot import boot

boot("Evidence")

import streamlit as st
from ui import data
from ui.components import badge, e, footer, grid, note, page_header, reference_badge, stat

page_header("Evidence", "Sources, claims and their status",
            "What the project relies on, where each claim comes from, and how far it has been checked. "
            "A claim is verified only when a named person checked it in the publication itself.")

k = data.knowledge()
refs, claims = k["references"], k["claims"]
n_ver = sum(r["effective_status"] == "verified_against_source" and r["resolution"] != "unresolved" for r in refs)
n_unres = sum(r["resolution"] == "unresolved" for r in refs)
grid([
    stat(len(refs), "references"),
    stat(n_ver, "verified", "against the source, by a named person"),
    stat(len(refs) - n_ver - n_unres, "unverified", "bibliographic or transcribed only"),
    stat(n_unres, "unresolved", "the source work itself is not identified"),
], "cols-4")

st.html('<div style="display:flex;gap:.5rem;flex-wrap:wrap;margin:1rem 0 .2rem" aria-label="Status legend">'
        + badge("verified") + badge("transcribed") + badge("bibliographic") + badge("unresolved") + badge("ai")
        + '<span style="color:var(--muted);font-size:.82rem;align-self:center">AI observations never enter '
          "the knowledge base; they appear only on the Analysis page.</span></div>")

tab_refs, tab_claims, tab_verify = st.tabs(["References", "Claims", "Verification checklist"])

with tab_refs:
    flt = st.segmented_control("Status", ["All", "Unverified", "Unresolved", "Verified"], default="All", key="ev_ref")
    shown = [r for r in refs if flt in (None, "All")
             or (flt == "Unresolved" and r["resolution"] == "unresolved")
             or (flt == "Verified" and r["effective_status"] == "verified_against_source" and r["resolution"] != "unresolved")
             or (flt == "Unverified" and r["resolution"] != "unresolved" and r["effective_status"] != "verified_against_source")]
    cards = []
    for r in shown:
        cand = "".join(f"<li>{e(c)}</li>" for c in r["candidate_works"])
        cards.append(
            f'<article class="etp-card" style="padding:1rem 1.1rem"><div style="display:flex;justify-content:space-between;'
            f'gap:.6rem;align-items:center"><b class="etp-mono" style="color:var(--sand)">{e(r["ref_id"])}</b>'
            f'{reference_badge(r["effective_status"], r["resolution"])}</div>'
            f'<p style="margin:.55rem 0 0;color:var(--text);line-height:1.5;font-size:.92rem">{e(r["citation"])}</p>'
            + (f'<p style="margin:.5rem 0 0;color:var(--muted);font-size:.84rem">{e(r["notes"])}</p>' if r["notes"] else "")
            + (f'<div style="margin-top:.5rem;font-size:.82rem;color:var(--muted)">Candidate works (not established):'
               f'<ul style="margin:.3rem 0 0 1rem;padding:0">{cand}</ul></div>' if cand else "")
            + (f'<div style="margin-top:.5rem;font-size:.82rem;color:var(--ok)">Verified for: '
               f'{e("; ".join(r["verified_claims"]))}</div>' if r["verified_claims"] else "")
            + "</article>")
    grid(cards, "cols-2") if cards else note("No reference has this status.")

with tab_claims:
    st.caption("Each claim with its source, provenance, scope and uncertainty (python -m src.knowledge entries).")
    q = st.text_input("Search claims", placeholder="e.g. Kodumanal, position B, sathan", key="ev_q")
    rows = [c for c in claims if not q or q.lower() in (c["claim"] + c["id"]).lower()]
    for c in rows:
        unresolved = "unresolved placeholder" in c["uncertainty"]
        b = badge("unresolved") if unresolved else reference_badge(c["verification_status"])
        refs_txt = ", ".join(f'{s["ref_id"]}' for s in c["source"])
        st.html(
            f'<article class="etp-card" style="margin-bottom:.7rem;padding:1rem 1.1rem"><div style="display:flex;'
            f'justify-content:space-between;gap:.8rem;align-items:flex-start"><div><div class="etp-eyebrow">{e(c["id"])}</div>'
            f'<p style="margin:.35rem 0 0;color:var(--text);font-size:.98rem;line-height:1.5">{e(c["claim"])}</p></div>{b}</div>'
            f'<dl class="etp-kv" style="margin-top:.7rem"><dt>Source</dt><dd>{e(refs_txt)} · locator {e(c["locator"])}</dd>'
            f'<dt>Provenance</dt><dd>{e(c["provenance"])}</dd><dt>Scope</dt><dd>{e(c["scope"])}</dd>'
            f'<dt>Uncertainty</dt><dd>{e(c["uncertainty"])}</dd></dl></article>')
    if not rows:
        note("No claim matches.")

with tab_verify:
    st.caption("The claims the project relies on its key references for, plus the unresolved citations. "
               "Filled only by a human verifier (python -m src.knowledge import-checklist).")
    st.dataframe([{"ref": r["ref_id"], "claim": r["claim"], "status": r["verification_status"],
                   "verifier": r["verifier"], "date": r["verification_date"], "locator found": r["locator_found"],
                   "publication": r["expected_publication"]} for r in k["claim_report"]], hide_index=True)
footer()
