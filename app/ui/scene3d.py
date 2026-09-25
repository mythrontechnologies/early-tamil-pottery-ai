"""Illustrative WebGL hero: a terracotta sherd floating above a museum plinth.

Three.js (vendored, MIT, served from /app/static/vendor/three) renders a PROCEDURAL sherd:
an irregular outline, extruded with a fired-clay core and bent onto a pot-wall curve, with a
procedural terracotta texture and a dark slip band. Surface markings are abstract grain and
scratches only. There are no letters, no inscription, no catalogue number.

It is labelled "Illustrative 3D visualization — not an archaeological artifact" on screen,
and screen readers get a text description. Every capability has a 2D fallback:

* no WebGL, or the library fails to load -> "3D unavailable — switching to accessible 2D
  inspection." and a static SVG illustration;
* the "2D" button switches manually at any time;
* prefers-reduced-motion (or the palette's "Reduce motion" preference) -> no auto-rotation,
  no drift, no camera easing; the scene renders only on interaction.

Interaction: mouse / trackpad orbit, one-finger orbit, two-finger pan and pinch zoom, wheel
zoom; keyboard: arrows orbit, + / - zoom, 0 reset, space auto-rotate, C focus mode,
F fullscreen. Rendering stops when the scene is off screen or the tab is hidden, the pixel
ratio is capped and lowered automatically if frames are slow, and nothing loads until the
scene is near the viewport.
"""

from __future__ import annotations

import streamlit as st

from .sherd3d import OUTLINE

LABEL = "Illustrative 3D visualization — not an archaeological artifact"
SR_TEXT = ("Illustrative terracotta sherd visualization, drawn by the interface above a museum plinth. "
           "This is a decorative representation, not an archaeological artifact: it has no inscription, "
           "no catalogue number and no date. Real photographs on the Analysis and Dataset pages are the "
           "authoritative visual sources.")
FALLBACK = "3D unavailable — switching to accessible 2D inspection."

_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>3D illustration</title>
<style>
:root{--line:rgba(236,228,216,.14);--muted:#b3a698;--text:#ece4d8;--copper:#c89260;--gold:#cfae6b;--bg:#14110f}
html,body{margin:0;background:transparent;color:var(--text);font-family:Geist,system-ui,-apple-system,"Segoe UI",sans-serif;overflow:hidden}
.stage{position:relative;height:__H__px;border-radius:22px;overflow:hidden;outline:none;
 background:radial-gradient(65% 75% at 50% 42%,rgba(200,105,63,.18),transparent 70%),radial-gradient(130% 90% at 50% 115%,rgba(0,0,0,.6),transparent 60%),#15110e}
.stage:focus-visible{box-shadow:0 0 0 2px var(--gold) inset}
.stage:fullscreen{height:100vh;border-radius:0}
canvas{display:block;width:100%;height:100%;touch-action:none;cursor:grab}
canvas:active{cursor:grabbing}
.sr{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.hud{position:absolute;inset:16px;pointer-events:none;font:10.5px/1.4 "JetBrains Mono",ui-monospace,"Cascadia Mono",monospace;letter-spacing:.06em;color:var(--muted)}
.tick{position:absolute;width:18px;height:18px;border-color:var(--line);border-style:solid}
.tl{left:0;top:0;border-width:1px 0 0 1px}.tr{right:0;top:0;border-width:1px 1px 0 0}.bl{left:0;bottom:0;border-width:0 0 1px 1px}.br{right:0;bottom:0;border-width:0 1px 1px 0}
.label{position:absolute;left:26px;top:1px;right:26px;color:var(--copper);text-transform:uppercase;letter-spacing:.14em}
.scale{position:absolute;left:26px;bottom:46px}
.hint{position:absolute;left:50%;bottom:58px;transform:translateX(-50%);background:rgba(20,17,15,.82);border:1px solid var(--line);border-radius:999px;padding:6px 12px;font:12px Geist,system-ui,sans-serif;color:var(--text);white-space:nowrap;transition:opacity .5s cubic-bezier(.32,.72,0,1)}
.hint.gone{opacity:0}
.bar{position:absolute;left:12px;right:12px;bottom:10px;display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;pointer-events:none}
.bar button{pointer-events:auto;font:500 12.5px Geist,system-ui,sans-serif;color:var(--text);background:rgba(30,26,22,.9);border:1px solid var(--line);
 border-radius:999px;padding:7px 12px;min-height:34px;cursor:pointer;transition:background .25s cubic-bezier(.32,.72,0,1),transform .15s}
.bar button:hover{background:rgba(62,53,45,.95)}.bar button:active{transform:scale(.97)}
.bar button[aria-pressed="true"]{border-color:var(--gold);color:var(--gold)}
.bar button:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.fallback{position:absolute;inset:0;display:none;place-items:center;text-align:center}
.fallback.on{display:grid}.fallback svg{width:min(78%,460px);height:auto}
.msg{position:absolute;top:34px;left:50%;transform:translateX(-50%);font:12.5px Geist,system-ui,sans-serif;color:var(--text);background:rgba(20,17,15,.85);border:1px solid var(--line);border-radius:8px;padding:6px 10px;display:none}
.msg.on{display:block}
.focus .hud .scale,.focus .hint{opacity:0}
@media (max-width:620px){.scale{display:none}.bar button{padding:7px 10px}}
</style></head><body>
<div class="stage" id="stage" tabindex="0" role="application" aria-roledescription="interactive 3D illustration" aria-label="__SR__">
 <p class="sr">__SR__ Keys: arrows orbit, plus and minus zoom, 0 resets, space toggles auto-rotation, C focus mode, F fullscreen.</p>
 <div class="fallback" id="fallback" aria-hidden="true">
  <svg viewBox="0 0 400 280"><defs><radialGradient id="t" cx="42%" cy="40%" r="75%"><stop offset="0" stop-color="#c77a4f"/><stop offset=".55" stop-color="#a6573a"/><stop offset="1" stop-color="#6e3824"/></radialGradient>
   <clipPath id="c"><path d="__OUTLINE__"/></clipPath></defs><path d="__OUTLINE__" fill="url(#t)"/>
   <g clip-path="url(#c)"><rect width="400" height="100" fill="#221a15" opacity=".9"/></g><path d="__OUTLINE__" fill="none" stroke="rgba(0,0,0,.4)"/></svg>
 </div>
 <div class="msg" id="msg" role="status" aria-live="polite"></div>
 <div class="hud" aria-hidden="true">
  <div class="tick tl"></div><div class="tick tr"></div><div class="tick bl"></div><div class="tick br"></div>
  <div class="label">__LABEL__</div>
  <div class="scale">grid: arbitrary units · no physical scale</div>
 </div>
 <div class="hint" id="hint" aria-hidden="true">Drag to orbit · scroll or pinch to zoom · two fingers to pan</div>
 <div class="bar" role="toolbar" aria-label="3D illustration controls">
  <button id="bAuto" aria-pressed="true">Auto-rotate</button>
  <button id="bFocus" aria-pressed="false" aria-label="Focus mode: move the camera closer">Focus</button>
  <button id="bIn" aria-label="Zoom in">+</button><button id="bOut" aria-label="Zoom out">−</button>
  <button id="bReset" aria-label="Reset camera">Reset</button>
  <button id="b2d" aria-pressed="false" aria-label="Switch to the 2D illustration">2D</button>
  <button id="bFs" aria-label="Toggle fullscreen">⤢</button>
 </div>
</div>
<script type="importmap">{"imports":{"three":"__BASE__/three.module.min.js","three/addons/controls/OrbitControls.js":"__BASE__/OrbitControls.js"}}</script>
<script>
// Decide before loading anything heavy: WebGL support, reduced motion, user preference.
window.ETP = {reduce: matchMedia('(prefers-reduced-motion: reduce)').matches, stats: {fps: 0, ratio: 0, frames: 0, mode: 'init'}};
try { if (localStorage.getItem('etp.reduceMotion') === '1') ETP.reduce = true; } catch (e) {}
ETP.webgl = (() => { try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch (e) { return false; } })();
ETP.fallback = (why) => {
  const m = document.getElementById('msg'); m.textContent = '__FALLBACK__' + (why ? ' (' + why + ')' : ''); m.classList.add('on');
  document.getElementById('fallback').classList.add('on');
  const c = document.querySelector('canvas'); if (c) c.style.display = 'none';
  for (const id of ['bAuto', 'bFocus', 'bIn', 'bOut', 'bReset']) document.getElementById(id).disabled = true;
  ETP.stats.mode = '2d';
};
let q = ''; try { q = parent.location.search; } catch (e) {}
if (!ETP.webgl || /[?&]no3d\b/.test(q)) ETP.fallback(ETP.webgl ? '2D requested' : 'WebGL not supported');
</script>
<script type="module">
if (ETP.stats.mode !== '2d') {
 const start = async () => {
  let THREE, OrbitControls;
  try { THREE = await import('three'); ({OrbitControls} = await import('three/addons/controls/OrbitControls.js')); }
  catch (e) { ETP.fallback('3D library unavailable'); return; }
  const stage = document.getElementById('stage');
  // the browser may still refuse a context (GPU reset, context blocked): fall back, never hang
  let renderer;
  try { renderer = new THREE.WebGLRenderer({antialias: true, alpha: true, powerPreference: 'low-power'}); }
  catch (e) { ETP.fallback('WebGL context unavailable'); return; }
  renderer.domElement.addEventListener('webglcontextlost', ev => { ev.preventDefault(); ETP.fallback('WebGL context lost'); });
  let ratio = Math.min(devicePixelRatio || 1, 1.5);
  renderer.setPixelRatio(ratio); renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  stage.prepend(renderer.domElement); renderer.domElement.setAttribute('aria-hidden', 'true');
  const scene = new THREE.Scene(); scene.fog = new THREE.FogExp2(0x15110e, 0.075);
  const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 60);
  const HOME = {pos: new THREE.Vector3(0.6, 1.35, 5.4), target: new THREE.Vector3(0, 0.55, 0)};
  const FOCUS = {pos: new THREE.Vector3(0.25, 0.9, 3.0), target: new THREE.Vector3(0, 0.7, 0)};
  camera.position.copy(HOME.pos);

  // ---- procedural terracotta texture (abstract grain + scratches; no letterforms) ----
  const tex = (() => {
    const S = 1024, cv = document.createElement('canvas'); cv.width = cv.height = S; const g = cv.getContext('2d');
    const grd = g.createRadialGradient(S * .42, S * .45, S * .05, S * .5, S * .5, S * .75);
    grd.addColorStop(0, '#c9804f'); grd.addColorStop(.6, '#a95c3b'); grd.addColorStop(1, '#6f3a26');
    g.fillStyle = grd; g.fillRect(0, 0, S, S);
    const slip = g.createLinearGradient(0, 0, 0, S * .42); slip.addColorStop(0, 'rgba(24,18,14,.96)'); slip.addColorStop(.85, 'rgba(40,29,22,.9)'); slip.addColorStop(1, 'rgba(40,29,22,0)');
    g.fillStyle = slip; g.fillRect(0, 0, S, S * .42);
    let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    for (let i = 0; i < 26000; i++) { const x = rnd() * S, y = rnd() * S, a = rnd() * .09; g.fillStyle = rnd() > .5 ? `rgba(255,236,210,${a})` : `rgba(20,10,5,${a * 1.4})`; g.fillRect(x, y, 1 + rnd() * 1.6, 1 + rnd() * 1.6); }
    g.strokeStyle = 'rgba(245,225,200,.10)'; g.lineWidth = 1.2;           // faint abrasion only
    for (let i = 0; i < 40; i++) { const x = rnd() * S, y = S * .45 + rnd() * S * .5; g.beginPath(); g.moveTo(x, y); g.lineTo(x + (rnd() - .5) * 60, y + (rnd() - .5) * 18); g.stroke(); }
    const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t;
  })();

  // ---- sherd: irregular outline, extruded, bent onto a vessel-wall curve ----
  // ---- sherd: outline from the SVG path (M / L / C / Z: curved rim, angular break edges) ----
  // Edge walls come from an extrusion; both faces are finely subdivided planes cut to the same
  // outline by an alpha mask, so bending onto the pot-wall curve stays smooth (no creases).
  const shape = new THREE.Shape();
  for (const [, cmd, args] of '__OUTLINE__'.matchAll(/([MLCZ])([^MLCZ]*)/g)) {
    const n = (args.match(/-?\d+(\.\d+)?/g) || []).map(Number), q = [];
    for (let i = 0; i < n.length; i += 2) q.push((n[i] - 200) / 150, -(n[i + 1] - 140) / 150);
    if (cmd === 'M') shape.moveTo(q[0], q[1]); else if (cmd === 'L') shape.lineTo(q[0], q[1]);
    else if (cmd === 'C') shape.bezierCurveTo(...q); else shape.closePath();
  }
  const DEPTH = .075, R = 1.9, PW = 2.4, PH = 1.7;
  const bend = (g) => { const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) { const x = p.getX(i), z = p.getZ(i), a = x / R; p.setX(i, (R - z) * Math.sin(a)); p.setZ(i, R - (R - z) * Math.cos(a)); }
    p.needsUpdate = true; g.computeVertexNormals(); return g; };
  const walls = bend(new THREE.ExtrudeGeometry(shape, {depth: DEPTH, bevelEnabled: false, curveSegments: 48, steps: 1}));
  const mask = (() => { const S = 1024, cv = document.createElement('canvas'); cv.width = cv.height = S; const g = cv.getContext('2d');
    g.fillStyle = '#000'; g.fillRect(0, 0, S, S); g.setTransform(S / 360, 0, 0, S / 255, -S * .05556, -S * .04902);   // SVG units -> plane uv (see PW, PH)
    g.fillStyle = '#fff'; g.fill(new Path2D('__OUTLINE__')); return new THREE.CanvasTexture(cv); })();
  const faceGeo = (z) => { const g = new THREE.PlaneGeometry(PW, PH, 160, 110); g.translate(0, 0, z); return bend(g); };
  const front = new THREE.MeshStandardMaterial({map: tex, bumpMap: tex, bumpScale: 1.1, roughness: .86, metalness: 0, alphaMap: mask, alphaTest: .5});
  const back = new THREE.MeshStandardMaterial({map: tex, roughness: .92, metalness: 0, color: 0xb9a08c, alphaMap: mask, alphaTest: .5, side: THREE.BackSide});
  const core = new THREE.MeshStandardMaterial({color: 0x8a5a3e, roughness: .95, side: THREE.DoubleSide});
  const sherd = new THREE.Group();
  for (const m of [new THREE.Mesh(faceGeo(DEPTH), front), new THREE.Mesh(faceGeo(0), back), new THREE.Mesh(walls, [new THREE.MeshBasicMaterial({visible: false}), core])]) { m.castShadow = true; sherd.add(m); }
  const box = new THREE.Box3().setFromObject(sherd), mid = box.getCenter(new THREE.Vector3());
  sherd.children.forEach(m => m.position.sub(mid));
  sherd.position.y = 1.05; sherd.rotation.set(-.1, -.55, .05); sherd.scale.setScalar(.9);
  scene.add(sherd);

  // ---- museum plinth, ground shadow, excavation grid, measurement ring ----
  const plinth = new THREE.Mesh(new THREE.CylinderGeometry(1.25, 1.32, .5, 72), new THREE.MeshStandardMaterial({color: 0x241d18, roughness: .9}));
  plinth.position.y = -.25; plinth.receiveShadow = true; scene.add(plinth);
  const top = new THREE.Mesh(new THREE.CircleGeometry(1.25, 72), new THREE.ShadowMaterial({opacity: .5}));
  top.rotation.x = -Math.PI / 2; top.position.y = .002; top.receiveShadow = true; scene.add(top);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.ShadowMaterial({opacity: .35}));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -.5; floor.receiveShadow = true; scene.add(floor);
  const grid = new THREE.GridHelper(16, 32, 0x6b5a4a, 0x3a3027); grid.position.y = -.499;
  grid.material.transparent = true; grid.material.opacity = .35; scene.add(grid);
  const ring = new THREE.Mesh(new THREE.RingGeometry(1.42, 1.44, 128), new THREE.MeshBasicMaterial({color: 0xcfae6b, transparent: true, opacity: .35, side: THREE.DoubleSide}));
  ring.rotation.x = -Math.PI / 2; ring.position.y = -.497; scene.add(ring);
  const ticks = new THREE.BufferGeometry(), tv = [];
  for (let i = 0; i < 72; i++) { const a = i / 72 * Math.PI * 2, r1 = 1.46, r2 = i % 6 ? 1.52 : 1.6; tv.push(Math.cos(a) * r1, -.497, Math.sin(a) * r1, Math.cos(a) * r2, -.497, Math.sin(a) * r2); }
  ticks.setAttribute('position', new THREE.Float32BufferAttribute(tv, 3));
  scene.add(new THREE.LineSegments(ticks, new THREE.LineBasicMaterial({color: 0xcfae6b, transparent: true, opacity: .3})));

  // ---- very sparse dust (static under reduced motion) ----
  const dust = new THREE.BufferGeometry(), dv = []; let s = 11; const r2 = () => (s = (s * 48271) % 2147483647) / 2147483647;
  for (let i = 0; i < 90; i++) dv.push((r2() - .5) * 6, r2() * 3.2 - .2, (r2() - .5) * 4);
  dust.setAttribute('position', new THREE.Float32BufferAttribute(dv, 3));
  const motes = new THREE.Points(dust, new THREE.PointsMaterial({color: 0xe8cfb0, size: .018, transparent: true, opacity: .45, depthWrite: false}));
  scene.add(motes);

  // ---- light: warm key (shadow), cool restrained rim, hemisphere fill ----
  scene.add(new THREE.HemisphereLight(0xf3dcc0, 0x1a120d, .45));
  const key = new THREE.DirectionalLight(0xffd6ad, 2.4); key.position.set(3, 5.5, 3.5); key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024); key.shadow.camera.near = 1; key.shadow.camera.far = 16; key.shadow.radius = 5; key.shadow.bias = -.0005;
  Object.assign(key.shadow.camera, {left: -3, right: 3, top: 3, bottom: -3}); scene.add(key);
  const rim = new THREE.DirectionalLight(0x9fc0d0, 1.3); rim.position.set(-3.5, 2.2, -4); scene.add(rim);

  // ---- controls: mouse, trackpad, touch (1 finger orbit, 2 fingers pan + pinch) ----
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.copy(HOME.target); controls.enableDamping = !ETP.reduce; controls.dampingFactor = .08;
  controls.minDistance = 2.2; controls.maxDistance = 9; controls.maxPolarAngle = Math.PI * .49; controls.enablePan = true;
  controls.touches = {ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN};
  controls.autoRotate = !ETP.reduce; controls.autoRotateSpeed = .7;

  const bAuto = document.getElementById('bAuto'), bFocus = document.getElementById('bFocus'), hint = document.getElementById('hint');
  const setAuto = (v) => { controls.autoRotate = v; bAuto.setAttribute('aria-pressed', v); kick(); };
  bAuto.setAttribute('aria-pressed', !ETP.reduce);   // the render loop starts with kick() at the end of start()
  let tween = null;
  const flyTo = (to) => {
    if (ETP.reduce) { camera.position.copy(to.pos); controls.target.copy(to.target); controls.update(); kick(); return; }
    tween = {t: 0, fromP: camera.position.clone(), fromT: controls.target.clone(), to}; kick();
  };
  const resize = () => { const w = stage.clientWidth, h = stage.clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h;
    camera.fov = w < 520 ? 44 : 34; camera.updateProjectionMatrix(); kick(); };
  new ResizeObserver(resize).observe(stage);

  // ---- render loop: only while something moves, only while visible ----
  let visible = true, raf = 0, last = performance.now(), slow = 0, clock = 0;
  // With motion allowed the loop runs (gentle float + damping) but only while visible; with
  // reduced motion it renders only on interaction ('change' events).
  const needsLoop = () => controls.autoRotate || tween || !ETP.reduce;
  function frame(now) {
    // raf stays non-zero while a frame runs, so the 'change' events fired by controls.update()
    // cannot schedule a second loop (two loops per frame would double every frame).
    raf = -1; if (!visible || document.hidden || ETP.stats.mode === '2d') { raf = 0; return; }
    const dt = Math.min(.05, (now - last) / 1000); last = now; clock += dt;
    if (tween) { tween.t = Math.min(1, tween.t + dt / .7); const e = 1 - Math.pow(1 - tween.t, 3);
      camera.position.lerpVectors(tween.fromP, tween.to.pos, e); controls.target.lerpVectors(tween.fromT, tween.to.target, e); if (tween.t >= 1) tween = null; }
    if (!ETP.reduce) { sherd.position.y = 1.05 + Math.sin(clock * .9) * .035; motes.rotation.y += dt * .01; }
    controls.update(); renderer.render(scene, camera);
    ETP.stats.frames++; const ft = dt * 1000; ETP.stats.fps = Math.round(1000 / Math.max(ft, 1));
    if (ft > 26) { if (++slow > 45 && ratio > .75) { ratio = Math.max(.75, ratio - .25); renderer.setPixelRatio(ratio); resize(); slow = 0; } } else slow = Math.max(0, slow - 1);
    ETP.stats.ratio = ratio;
    raf = needsLoop() ? requestAnimationFrame(frame) : 0;
  }
  function kick() { if (!raf && visible && !document.hidden) { last = performance.now(); raf = requestAnimationFrame(frame); } }
  controls.addEventListener('change', kick);
  controls.addEventListener('start', () => { hint.classList.add('gone'); try { localStorage.setItem('etp.hintSeen', '1'); } catch (e) {} });
  new IntersectionObserver(es => { visible = es[0].isIntersecting; kick(); }, {threshold: .02}).observe(stage);
  document.addEventListener('visibilitychange', kick);
  try { if (localStorage.getItem('etp.hintSeen') === '1') hint.classList.add('gone'); } catch (e) {}

  // ---- buttons and keyboard ----
  const zoom = (f) => { const d = camera.position.clone().sub(controls.target); const n = THREE.MathUtils.clamp(d.length() * f, controls.minDistance, controls.maxDistance);
    camera.position.copy(controls.target).add(d.setLength(n)); controls.update(); kick(); };
  const orbit = (dAz, dPol) => { const off = camera.position.clone().sub(controls.target); const sph = new THREE.Spherical().setFromVector3(off);
    sph.theta += dAz; sph.phi = THREE.MathUtils.clamp(sph.phi + dPol, .15, controls.maxPolarAngle); camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(sph)); controls.update(); kick(); };
  const focus = (v) => { bFocus.setAttribute('aria-pressed', v); stage.classList.toggle('focus', v); flyTo(v ? FOCUS : HOME); };
  const fs = () => { try { document.fullscreenElement ? document.exitFullscreen() : stage.requestFullscreen(); } catch (e) {} };
  bAuto.onclick = () => setAuto(!controls.autoRotate);
  bFocus.onclick = () => focus(bFocus.getAttribute('aria-pressed') !== 'true');
  document.getElementById('bIn').onclick = () => zoom(.85); document.getElementById('bOut').onclick = () => zoom(1 / .85);
  document.getElementById('bReset').onclick = () => { focus(false); setAuto(!ETP.reduce); };
  document.getElementById('bFs').onclick = fs;
  const b2d = document.getElementById('b2d');
  b2d.onclick = () => { const on = b2d.getAttribute('aria-pressed') !== 'true'; b2d.setAttribute('aria-pressed', on);
    document.getElementById('fallback').classList.toggle('on', on); renderer.domElement.style.display = on ? 'none' : 'block'; visible = !on; if (!on) kick(); };
  stage.addEventListener('keydown', (e) => { const k = e.key; let h = true;
    if (k === 'ArrowLeft') orbit(-.18, 0); else if (k === 'ArrowRight') orbit(.18, 0); else if (k === 'ArrowUp') orbit(0, -.12); else if (k === 'ArrowDown') orbit(0, .12);
    else if (k === '+' || k === '=') zoom(.85); else if (k === '-') zoom(1 / .85); else if (k === '0') { focus(false); }
    else if (k === ' ') setAuto(!controls.autoRotate); else if (k === 'c' || k === 'C') bFocus.click(); else if (k === 'f' || k === 'F') fs(); else h = false;
    if (h) { e.preventDefault(); hint.classList.add('gone'); } });
  ETP.view = () => ({cam: camera.position.toArray().map(v => +v.toFixed(3)), target: controls.target.toArray().map(v => +v.toFixed(3)),
                     auto: controls.autoRotate});   // read-only, for tests and debugging
  resize(); ETP.stats.mode = '3d'; kick();
 };
 // lazy: load three.js only when the stage is near the viewport
 const io = new IntersectionObserver(es => { if (es[0].isIntersecting) { io.disconnect(); start(); } }, {rootMargin: '200px'});
 io.observe(document.getElementById('stage'));
}
</script><script>addEventListener('keydown',function(e){if((e.ctrlKey||e.metaKey)&&(e.key==='k'||e.key==='K')){try{if(parent.__etpPalette){e.preventDefault();parent.__etpPalette.open();}}catch(_){}}});</script></body></html>"""


def scene_html(height: int = 520, base: str = "/app/static/vendor/three") -> str:
    return (_HTML.replace("__H__", str(height)).replace("__OUTLINE__", OUTLINE).replace("__LABEL__", LABEL)
            .replace("__SR__", SR_TEXT).replace("__FALLBACK__", FALLBACK).replace("__BASE__", base))


def render_scene(height: int = 520) -> None:
    st.iframe(scene_html(height), height=height + 4)   # our own markup only; no user data inside


__all__ = ["FALLBACK", "LABEL", "SR_TEXT", "render_scene", "scene_html"]
