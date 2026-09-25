"""Command palette (Ctrl/Cmd + K), skip link and launcher, injected into the app page.

A 1 px same-origin frame installs, once per page load, a script in the parent document that adds:

* a "Skip to main content" link (first focusable element);
* a visible "Commands" launcher (mouse and touch users; shows the Ctrl+K shortcut);
* an accessible dialog: role=dialog + aria-modal, a combobox input with a listbox of options
  (aria-activedescendant), arrow keys / Home / End / Enter / Escape, focus returned to where it
  came from, results announced politely.

Commands only navigate or change presentation preferences. They never write data. The
artifact list comes from the records (passed in), never from hard-coded constants.
"""

from __future__ import annotations

import json

import streamlit as st

# Runs in the PARENT page's own realm (installed once as a <script> element): navigation started
# from the sandboxed component frame is refused by the browser, and listeners owned by a frame
# die with it when Streamlit remounts the frame.
_PARENT_JS = r"""(() => {
const P = window, D = document;
const root = () => new URL('/', P.location.origin);
const go = (slug, params) => { const u = new URL(slug, root()); for (const [k, v] of Object.entries(params || {})) u.searchParams.set(k, v); P.location.assign(u.toString()); };
const build = (ARTS, MODE) => [
  {id: 'overview', label: 'Open overview', hint: 'page', run: () => go('')},
  {id: 'analyze', label: 'Analyze artifact', hint: 'page · inspect a photograph', run: () => go('analysis')},
  {id: 'annotate', label: 'Open annotation lab', hint: 'page', run: () => go('annotation')},
  {id: 'dataset', label: 'Open dataset', hint: 'page · gallery of artifacts', run: () => go('dataset')},
  {id: 'evidence', label: 'Open evidence', hint: 'page · references and claims', run: () => go('evidence')},
  {id: 'workflow', label: 'Open workflow', hint: 'page · stages and status', run: () => go('workflow')},
  {id: 'about', label: 'Open about', hint: 'page', run: () => go('about')},
  {id: 'mode', label: MODE === 'presentation' ? 'Switch to Research mode' : 'Switch to Presentation mode', hint: 'view',
   run: () => { const u = new URL(P.location.href); u.searchParams.set('mode', MODE === 'presentation' ? 'research' : 'presentation'); P.location.assign(u.toString()); }},
  {id: 'motion', label: (() => { try { return localStorage.getItem('etp.reduceMotion') === '1' ? 'Allow motion in 3D views (this browser)' : 'Reduce motion in 3D views (this browser)'; } catch (e) { return 'Reduce motion in 3D views (this browser)'; } })(),
   hint: 'accessibility', run: () => { try { localStorage.setItem('etp.reduceMotion', localStorage.getItem('etp.reduceMotion') === '1' ? '0' : '1'); } catch (e) {} P.location.reload(); }},
  {id: 'reset', label: 'Reset interface', hint: 'clears view preferences in this browser', run: () => { try { Object.keys(localStorage).filter(k => k.startsWith('etp.')).forEach(k => localStorage.removeItem(k)); } catch (e) {} go(''); }},
  ...Array.from(ARTS, a => ({id: 'art:' + a, label: 'Search artifact · ' + a, hint: 'open in the inspector', run: () => go('dataset', {inspect: a})})),
];
const cmds = build([], 'research');

const css = D.createElement('style'); css.id = 'etp-cmdk-style'; css.textContent = `
.etp-skip{position:fixed;left:12px;top:-60px;z-index:1001;background:#ece4d8;color:#14110f;padding:8px 14px;border-radius:8px;font:600 14px Geist,system-ui,sans-serif;text-decoration:none;transition:top .2s}
.etp-skip:focus{top:12px;outline:2px solid #cfae6b;outline-offset:2px}
.etp-launch{position:fixed;right:18px;top:12px;z-index:1000;display:inline-flex;align-items:center;gap:8px;font:500 13px Geist,system-ui,sans-serif;color:#ece4d8;
 background:rgba(30,26,22,.92);border:1px solid rgba(236,228,216,.16);border-radius:999px;padding:6px 8px 6px 14px;min-height:34px;cursor:pointer;transition:background .25s cubic-bezier(.32,.72,0,1),transform .15s}
.etp-launch:hover{background:rgba(62,53,45,.96)}.etp-launch:active{transform:scale(.97)}
.etp-launch:focus-visible{outline:2px solid #cfae6b;outline-offset:2px}
.etp-launch kbd{font:500 11px "JetBrains Mono",ui-monospace,monospace;color:#b3a698;border:1px solid rgba(236,228,216,.16);border-radius:6px;padding:2px 6px;background:rgba(20,17,15,.8)}
#etp-cmdk{position:fixed;inset:0;z-index:1002;display:none;align-items:flex-start;justify-content:center;padding-top:12vh;background:rgba(10,8,6,.62)}
#etp-cmdk.on{display:flex}
#etp-cmdk .box{width:min(640px,calc(100vw - 32px));background:#1e1a16;border:1px solid rgba(236,228,216,.16);border-radius:18px;box-shadow:0 30px 80px -20px rgba(0,0,0,.8);overflow:hidden;font-family:Geist,system-ui,sans-serif;color:#ece4d8}
#etp-cmdk input{width:100%;box-sizing:border-box;background:transparent;border:0;border-bottom:1px solid rgba(236,228,216,.12);color:#ece4d8;font:16px Geist,system-ui,sans-serif;padding:16px 18px;outline:none}
#etp-cmdk input:focus-visible{box-shadow:inset 0 -2px 0 #cfae6b}
#etp-cmdk ul{list-style:none;margin:0;padding:6px;max-height:min(52vh,420px);overflow:auto}
#etp-cmdk li{display:flex;justify-content:space-between;gap:12px;padding:10px 12px;border-radius:10px;cursor:pointer;font-size:14px}
#etp-cmdk li small{color:#b3a698;font-size:12px}
#etp-cmdk li[aria-selected="true"]{background:rgba(200,105,63,.18);outline:1px solid rgba(207,174,107,.55)}
#etp-cmdk .foot{display:flex;justify-content:space-between;padding:8px 14px;border-top:1px solid rgba(236,228,216,.1);font:11px "JetBrains Mono",ui-monospace,monospace;color:#b3a698}
@media (prefers-reduced-motion:reduce){.etp-skip,.etp-launch{transition:none}}
@media (max-width:640px),(pointer:coarse){.etp-launch kbd{display:none}.etp-launch{padding:6px 14px}}`;
D.head.appendChild(css);

const skip = D.createElement('a'); skip.className = 'etp-skip'; skip.href = '#'; skip.textContent = 'Skip to main content';
skip.addEventListener('click', ev => { ev.preventDefault(); const m = D.querySelector('[data-testid="stMainBlockContainer"]') || D.querySelector('[data-testid="stMain"]');
  if (m) { m.setAttribute('tabindex', '-1'); m.focus(); m.scrollIntoView({block: 'start'}); } });
D.body.prepend(skip);

const launch = D.createElement('button'); launch.className = 'etp-launch'; launch.type = 'button';
launch.setAttribute('aria-haspopup', 'dialog'); launch.setAttribute('aria-controls', 'etp-cmdk');
launch.innerHTML = '<span class="t">Commands</span><kbd>Ctrl K</kbd>'; D.body.appendChild(launch);

const wrap = D.createElement('div'); wrap.id = 'etp-cmdk'; wrap.setAttribute('role', 'dialog'); wrap.setAttribute('aria-modal', 'true'); wrap.setAttribute('aria-label', 'Command palette');
wrap.innerHTML = `<div class="box"><input id="etp-cmdk-in" type="text" role="combobox" aria-expanded="true" aria-controls="etp-cmdk-list" aria-autocomplete="list" aria-label="Type a command or an artifact id" placeholder="Type a command or an artifact id…" autocomplete="off">
 <ul id="etp-cmdk-list" role="listbox" aria-label="Commands"></ul>
 <div class="foot"><span id="etp-cmdk-count" aria-live="polite"></span><span>↑↓ move · Enter run · Esc close</span></div></div>`;
D.body.appendChild(wrap);
const input = D.getElementById('etp-cmdk-in'), list = D.getElementById('etp-cmdk-list'), count = D.getElementById('etp-cmdk-count');
let items = cmds, shown = [], sel = 0, back = null;
const render = () => { const q = input.value.trim().toLowerCase();
  shown = items.filter(c => !q || (c.label + ' ' + c.hint).toLowerCase().includes(q)).slice(0, 40);
  sel = Math.min(sel, Math.max(0, shown.length - 1));
  list.innerHTML = shown.map((c, i) => `<li role="option" id="etp-opt-${i}" aria-selected="${i === sel}"><span></span><small></small></li>`).join('');
  [...list.children].forEach((li, i) => { li.firstChild.textContent = shown[i].label; li.lastChild.textContent = shown[i].hint;
    li.addEventListener('click', () => run(i)); li.addEventListener('mousemove', () => { if (sel !== i) { sel = i; mark(); } }); });
  count.textContent = shown.length ? `${shown.length} result${shown.length > 1 ? 's' : ''}` : 'No matching command';
  mark(); };
const mark = () => { [...list.children].forEach((li, i) => li.setAttribute('aria-selected', i === sel));
  input.setAttribute('aria-activedescendant', shown.length ? `etp-opt-${sel}` : ''); const cur = list.children[sel]; if (cur) cur.scrollIntoView({block: 'nearest'}); };
const open = () => { back = D.activeElement; wrap.classList.add('on'); input.value = ''; sel = 0; render(); input.focus(); };
const close = () => { wrap.classList.remove('on'); if (back && back.focus) back.focus(); };
const run = (i) => { const c = shown[i]; if (!c) return; close(); c.run(); };
input.addEventListener('input', () => { sel = 0; render(); });
input.addEventListener('keydown', ev => { const k = ev.key;
  if (k === 'ArrowDown') { sel = (sel + 1) % Math.max(1, shown.length); mark(); } else if (k === 'ArrowUp') { sel = (sel - 1 + shown.length) % Math.max(1, shown.length); mark(); }
  else if (k === 'Home') { sel = 0; mark(); } else if (k === 'End') { sel = shown.length - 1; mark(); } else if (k === 'Enter') run(sel);
  else if (k === 'Escape') close(); else if (k === 'Tab') { /* keep focus in the dialog */ } else return; ev.preventDefault(); });
wrap.addEventListener('mousedown', ev => { if (ev.target === wrap) close(); });
launch.addEventListener('click', open);
D.addEventListener('keydown', ev => { if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'k' || ev.key === 'K')) { ev.preventDefault(); wrap.classList.contains('on') ? close() : open(); } });
P.__etpPalette = {open, close, configure: (arts, mode) => { items = build(arts, mode); if (wrap.classList.contains('on')) render(); }};
})();"""

_HTML = r"""<!doctype html><html lang="en"><head><title>Command palette host</title></head><body><script>
(() => { const P = window.parent, D = P.document;
  if (!P.__etpPalette) { const s = D.createElement('script'); s.id = 'etp-cmdk-js'; s.textContent = __JS__; D.head.appendChild(s); }
  P.__etpPalette.configure(__ARTS__, "__MODE__");
})();
</script></body></html>"""


def render_palette(artifact_ids: list[str], mode: str) -> None:
    assert "</script" not in _PARENT_JS
    page = (_HTML.replace("__JS__", json.dumps(_PARENT_JS)).replace("__ARTS__", json.dumps(sorted(artifact_ids)))
            .replace("__MODE__", "presentation" if mode == "presentation" else "research"))
    st.iframe(page, height=1)   # our own script; artifact ids are JSON-encoded record ids


__all__ = ["render_palette"]
