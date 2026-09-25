"""2.5D inspection of a REAL photograph (WebGL via vendored three.js, with a 2D fallback).

The photograph is mapped onto a gently curved surface so light and angle can be varied while
looking at incisions. It is labelled "2.5D inspection visualization": the curvature is
illustrative, not measured, and nothing is reconstructed. The photograph remains the
authoritative source.

Exposure, contrast and edge emphasis are applied to a DERIVED canvas copy in the browser; the
stored file is never touched. Whenever any adjustment is active the view says
"Derived display — original source preserved." Regions are drawn only from the analysis
result, with their source (human-marked solid, user dashed, AI dotted) and an id.
Without WebGL the same derived canvas is shown flat ("3D unavailable — switching to
accessible 2D inspection.").
"""

from __future__ import annotations

import html
import json
from typing import Any

import streamlit as st
from PIL import Image

from .scene3d import FALLBACK
from .viewer import SOURCE_STYLE, _data_uri

LABEL = "2.5D inspection visualization — photograph mapped onto an illustrative curved surface; curvature not measured"
DERIVED = "Derived display — original source preserved."

_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>2.5D photograph inspection</title><style>
:root{--line:rgba(236,228,216,.14);--muted:#b3a698;--text:#ece4d8;--gold:#cfae6b;--copper:#c89260;--ai:#7fb3c8}
html,body{margin:0;background:#14110f;color:var(--text);font-family:Geist,system-ui,-apple-system,"Segoe UI",sans-serif}
.stage{position:relative;height:__H__px;border:1px solid var(--line);border-radius:16px;overflow:hidden;background:#100d0b;outline:none}
.stage:focus-visible{box-shadow:0 0 0 2px var(--gold) inset}.stage:fullscreen{height:100vh;border-radius:0}
canvas.gl{display:block;width:100%;height:100%;touch-action:none;cursor:grab}
.flat{position:absolute;inset:0;display:none;place-items:center}.flat.on{display:grid}.flat canvas{max-width:96%;max-height:90%}
.top{position:absolute;left:10px;right:10px;top:10px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;pointer-events:none}
.top>*{pointer-events:auto}
button{font:500 12.5px Geist,system-ui,sans-serif;color:var(--text);background:rgba(30,26,22,.9);border:1px solid var(--line);border-radius:999px;padding:6px 11px;min-height:32px;cursor:pointer;transition:background .25s cubic-bezier(.32,.72,0,1),transform .15s}
button:hover{background:rgba(62,53,45,.95)}button:active{transform:scale(.97)}button[aria-pressed="true"]{border-color:var(--gold);color:var(--gold)}
button:focus-visible,input:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.adj{display:flex;gap:10px;flex-wrap:wrap;align-items:center;background:rgba(30,26,22,.9);border:1px solid var(--line);border-radius:12px;padding:5px 10px;font-size:12px;color:var(--muted)}
.adj label{display:flex;align-items:center;gap:6px}.adj input[type=range]{width:96px;accent-color:#c8693f}
.lbl{position:absolute;left:12px;bottom:10px;right:12px;font:11px "JetBrains Mono",ui-monospace,monospace;color:var(--copper);letter-spacing:.04em}
.derived{position:absolute;right:12px;top:58px;display:none;font:11px "JetBrains Mono",ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;color:#e3c27f;border:1px dashed #e3c27f;border-radius:4px;padding:3px 7px;background:rgba(20,17,15,.85)}
.derived.on{display:block}
.msg{position:absolute;top:58px;left:12px;display:none;font:12.5px Geist,system-ui,sans-serif;background:rgba(20,17,15,.88);border:1px solid var(--line);border-radius:8px;padding:6px 10px}.msg.on{display:block}
.sr{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
</style></head><body>
<div class="stage" id="stage" tabindex="0" role="application" aria-roledescription="2.5D inspection view" aria-label="__ALT__. __LABEL__. Keys: arrows tilt, plus and minus zoom, 0 resets, F fullscreen.">
 <div class="flat" id="flat"><canvas id="flatc" role="img" aria-label="__ALT__ (flat derived display)"></canvas></div>
 <div class="top" role="toolbar" aria-label="Inspection controls">
  <button id="bIn" aria-label="Zoom in">+</button><button id="bOut" aria-label="Zoom out">−</button><button id="bReset" aria-label="Reset view">Reset</button>
  <button id="bLight" aria-pressed="false" aria-label="Raking light: move the light low across the surface">Raking light</button>
  <button id="bReg" aria-pressed="true" aria-label="Toggle region outlines">Regions __NREG__</button>
  <div class="adj" role="group" aria-label="Derived display adjustments">
   <label>Exposure <input type="range" id="exp" min="-1.5" max="1.5" step="0.1" value="0" aria-label="Exposure"></label>
   <label>Contrast <input type="range" id="con" min="0.5" max="2.5" step="0.05" value="1" aria-label="Contrast"></label>
   <label><input type="checkbox" id="edge"> Edge emphasis</label>
  </div>
  <button id="b2d" aria-pressed="false" aria-label="Show flat 2D view">2D</button><button id="bFs" aria-label="Toggle fullscreen">⤢</button>
 </div>
 <div class="derived" id="derived" role="status">__DERIVED__</div>
 <div class="msg" id="msg" role="status" aria-live="polite"></div>
 <div class="lbl">__LABEL__</div>
</div>
<script type="importmap">{"imports":{"three":"__BASE__/three.module.min.js","three/addons/controls/OrbitControls.js":"__BASE__/OrbitControls.js"}}</script>
<script type="module">
const REGS = __REGS__, SRC = "__SRC__";
const stage = document.getElementById('stage'), flat = document.getElementById('flat'), flatc = document.getElementById('flatc');
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const img = new Image(); img.src = SRC; await img.decode();
// ---- derived canvas: exposure / contrast / edge emphasis + region outlines (source untouched) ----
const W = img.naturalWidth, H = img.naturalHeight, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
const g = cv.getContext('2d', {willReadFrequently: true}); g.drawImage(img, 0, 0); const base = g.getImageData(0, 0, W, H);
let sobel = null;
const edges = () => { if (sobel) return sobel; const d = base.data, L = new Float32Array(W * H); sobel = new Float32Array(W * H);
  for (let i = 0; i < W * H; i++) L[i] = .299 * d[i * 4] + .587 * d[i * 4 + 1] + .114 * d[i * 4 + 2];
  for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) { const i = y * W + x;
    const gx = -L[i - W - 1] - 2 * L[i - 1] - L[i + W - 1] + L[i - W + 1] + 2 * L[i + 1] + L[i + W + 1];
    const gy = -L[i - W - 1] - 2 * L[i - W] - L[i - W + 1] + L[i + W - 1] + 2 * L[i + W] + L[i + W + 1];
    sobel[i] = Math.min(255, Math.hypot(gx, gy) * .5); } return sobel; };
let showRegs = true;
function paint() {
  const e = +document.getElementById('exp').value, c = +document.getElementById('con').value, ed = document.getElementById('edge').checked;
  const derived = e !== 0 || c !== 1 || ed; document.getElementById('derived').classList.toggle('on', derived);
  const out = g.createImageData(W, H), s = base.data, o = out.data, k = Math.pow(2, e), S = ed ? edges() : null;
  for (let i = 0, p = 0; i < s.length; i += 4, p++) { for (let j = 0; j < 3; j++) { let v = ((s[i + j] / 255 - .5) * c + .5) * 255 * k; if (S) v += S[p] * .9; o[i + j] = v < 0 ? 0 : v > 255 ? 255 : v; } o[i + 3] = 255; }
  g.putImageData(out, 0, 0);
  if (showRegs) REGS.forEach((r, n) => { g.save(); g.lineWidth = Math.max(2, W / 400); g.strokeStyle = r.color; g.setLineDash(r.dash.length ? r.dash.map(x => x * W / 300) : []);
    g.strokeRect(r.x * W, r.y * H, r.w * W, r.h * H); g.setLineDash([]); g.fillStyle = 'rgba(20,17,15,.85)';
    const tag = `R${n + 1} · ${r.label}`; g.font = `${Math.max(12, W / 70)}px ui-monospace,monospace`; const tw = g.measureText(tag).width + 10;
    g.fillRect(r.x * W, Math.max(0, r.y * H - W / 45), tw, W / 50); g.fillStyle = r.color; g.fillText(tag, r.x * W + 5, Math.max(W / 60, r.y * H - W / 150)); g.restore(); });
  flatc.width = W; flatc.height = H; flatc.getContext('2d').drawImage(cv, 0, 0);
  if (window.__tex) window.__tex.needsUpdate = true; if (window.__kick) window.__kick();
}
for (const id of ['exp', 'con', 'edge']) document.getElementById(id).addEventListener('input', paint);
document.getElementById('bReg').onclick = (ev) => { showRegs = ev.currentTarget.getAttribute('aria-pressed') !== 'true'; ev.currentTarget.setAttribute('aria-pressed', showRegs); paint(); };
paint();
const toFlat = (why) => { flat.classList.add('on'); const c = stage.querySelector('canvas.gl'); if (c) c.style.display = 'none';
  if (why) { const m = document.getElementById('msg'); m.textContent = '__FALLBACK__'; m.classList.add('on'); } };
const fs = () => { try { document.fullscreenElement ? document.exitFullscreen() : stage.requestFullscreen(); } catch (e) {} };
document.getElementById('bFs').onclick = fs;
let webgl = false; try { const t = document.createElement('canvas'); webgl = !!(t.getContext('webgl2') || t.getContext('webgl')); } catch (e) {}
let THREE = null, OrbitControls = null;
if (webgl) { try { THREE = await import('three'); ({OrbitControls} = await import('three/addons/controls/OrbitControls.js')); } catch (e) { THREE = null; } }
// the browser may still refuse a context (GPU reset, context blocked): fall back, never hang
let renderer = null;
if (THREE) { try { renderer = new THREE.WebGLRenderer({antialias: true, alpha: true, powerPreference: 'low-power'}); } catch (e) { renderer = null; } }
if (!renderer) { toFlat(true); document.getElementById('b2d').disabled = true; }
else {
  renderer.domElement.addEventListener('webglcontextlost', ev => { ev.preventDefault(); toFlat(true); document.getElementById('b2d').disabled = true; });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5)); renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.domElement.className = 'gl'; renderer.domElement.setAttribute('aria-hidden', 'true'); stage.prepend(renderer.domElement);
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(32, 1, .05, 50);
  const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8; window.__tex = tex;
  const aspect = W / H, h = 2, w = h * aspect, R = w * 1.6;            // gentle curve: radius 1.6 x width
  const theta = w / R, geo = new THREE.CylinderGeometry(R, R, h, 96, 1, true, Math.PI - theta / 2, theta);
  const mat = new THREE.MeshStandardMaterial({map: tex, roughness: .8, metalness: 0, side: THREE.DoubleSide});
  const mesh = new THREE.Mesh(geo, mat); mesh.position.z = R; scene.add(mesh);
  scene.add(new THREE.AmbientLight(0xffffff, .55));
  const light = new THREE.DirectionalLight(0xfff1e0, 1.6); light.position.set(1.5, 2, 4); scene.add(light);
  const HOME = new THREE.Vector3(0, 0, 4.6);
  camera.position.copy(HOME);
  const controls = new OrbitControls(camera, renderer.domElement); controls.target.set(0, 0, 0);
  controls.enableDamping = !reduce; controls.minDistance = 1.2; controls.maxDistance = 8;
  controls.minAzimuthAngle = -.9; controls.maxAzimuthAngle = .9; controls.minPolarAngle = .75; controls.maxPolarAngle = 2.4;
  controls.touches = {ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN};
  let visible = true, raf = 0;
  // raf stays non-zero during a frame so 'change' events from controls.update() cannot start a second loop
  const frame = () => { raf = -1; if (!visible || document.hidden) { raf = 0; return; } const moving = controls.update(); renderer.render(scene, camera);
    raf = moving && !reduce ? requestAnimationFrame(frame) : 0; };
  const kick = () => { if (!raf) raf = requestAnimationFrame(frame); }; window.__kick = kick;
  controls.addEventListener('change', kick);
  const resize = () => { const cw = stage.clientWidth, ch = stage.clientHeight; renderer.setSize(cw, ch, false); camera.aspect = cw / ch;
    const fit = Math.max(h, w / camera.aspect) / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))) * 1.15; HOME.set(0, 0, fit); camera.updateProjectionMatrix(); kick(); };
  new ResizeObserver(resize).observe(stage); new IntersectionObserver(es => { visible = es[0].isIntersecting; kick(); }).observe(stage);
  document.addEventListener('visibilitychange', kick);
  const reset = () => { camera.position.copy(HOME); controls.target.set(0, 0, 0); controls.update(); kick(); };
  const zoom = (f) => { const d = camera.position.clone().sub(controls.target); camera.position.copy(controls.target).add(d.setLength(THREE.MathUtils.clamp(d.length() * f, 1.2, 8))); controls.update(); kick(); };
  const tilt = (dAz, dPol) => { const sph = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
    sph.theta = THREE.MathUtils.clamp(sph.theta + dAz, -.9, .9); sph.phi = THREE.MathUtils.clamp(sph.phi + dPol, .75, 2.4); camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(sph)); controls.update(); kick(); };
  document.getElementById('bIn').onclick = () => zoom(.85); document.getElementById('bOut').onclick = () => zoom(1 / .85); document.getElementById('bReset').onclick = reset;
  const bL = document.getElementById('bLight');
  bL.onclick = () => { const on = bL.getAttribute('aria-pressed') !== 'true'; bL.setAttribute('aria-pressed', on); light.position.set(on ? 4.5 : 1.5, on ? .35 : 2, on ? 1.2 : 4); kick(); };
  const b2d = document.getElementById('b2d');
  b2d.onclick = () => { const on = b2d.getAttribute('aria-pressed') !== 'true'; b2d.setAttribute('aria-pressed', on); flat.classList.toggle('on', on); renderer.domElement.style.display = on ? 'none' : 'block'; if (!on) kick(); };
  stage.addEventListener('keydown', e => { const k = e.key; let hd = true;
    if (k === 'ArrowLeft') tilt(-.1, 0); else if (k === 'ArrowRight') tilt(.1, 0); else if (k === 'ArrowUp') tilt(0, -.08); else if (k === 'ArrowDown') tilt(0, .08);
    else if (k === '+' || k === '=') zoom(.85); else if (k === '-') zoom(1 / .85); else if (k === '0') reset(); else if (k === 'f' || k === 'F') fs(); else hd = false;
    if (hd) e.preventDefault(); });
  resize(); reset(); window.__inspectReady = true;
}
</script><script>addEventListener('keydown',function(e){if((e.ctrlKey||e.metaKey)&&(e.key==='k'||e.key==='K')){try{if(parent.__etpPalette){e.preventDefault();parent.__etpPalette.open();}}catch(_){}}});</script></body></html>"""


def render_inspection(image: Image.Image, regions: list[dict[str, Any]], *, alt: str, height: int = 560,
                      max_side: int = 1600, base: str = "/app/static/vendor/three") -> None:
    regs = []
    for r in regions:
        s = SOURCE_STYLE.get(r["source"], SOURCE_STYLE["user_supplied"])
        regs.append({"x": r["x"], "y": r["y"], "w": r["width"], "h": r["height"], "color": s["color"],
                     "dash": [float(x) for x in s["dash"].split()] if s["dash"] else [], "label": s["label"]})
    page = (_HTML.replace("__H__", str(height)).replace("__SRC__", _data_uri(image, max_side))
            .replace("__ALT__", html.escape(alt, quote=True)).replace("__LABEL__", LABEL).replace("__DERIVED__", DERIVED)
            .replace("__FALLBACK__", FALLBACK).replace("__NREG__", str(len(regions))).replace("__BASE__", base)
            .replace("__REGS__", json.dumps(regs)))
    st.iframe(page, height=height + 4)   # escaped text, numeric regions, our own data URI


__all__ = ["DERIVED", "LABEL", "render_inspection"]
