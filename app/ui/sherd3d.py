"""An ILLUSTRATIVE 3D pottery sherd for the landing page (CSS 3D + inline SVG, no library).

It is not a model or photograph of any real artifact, and it says so on screen and to screen
readers. Its "marks" are abstract scratches, deliberately not letterforms, so nothing in it can
be mistaken for an inscription or a reading. Real photographs remain the authoritative source.

Interaction: drag to rotate; arrow keys rotate; + / - zoom; 0 resets; space pauses; F toggles
fullscreen. The animation runs only while the component is on screen and the tab is visible,
and never when the user prefers reduced motion (the object is then shown static).
"""

from __future__ import annotations

import streamlit as st

OUTLINE = "M40,78 C70,40 150,22 238,26 C300,30 350,52 372,86 L356,132 L366,176 L330,214 C290,246 226,262 168,254 L120,236 L96,248 L58,206 L64,168 L30,128 Z"
LAYERS = 16

_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Illustrative sherd</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;600&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
<style>
:root{--line:rgba(236,228,216,.14);--muted:#a3968a;--text:#ece4d8;--copper:#b8804a;--ai:#7fb3c8;--gold:#cfae6b}
html,body{margin:0;background:transparent;color:var(--text);font-family:Geist,system-ui,sans-serif;overflow:hidden}
.wrap{position:relative;height:__H__px;border-radius:22px;outline:none;user-select:none;
 background:radial-gradient(60% 70% at 50% 45%,rgba(200,105,63,.16),transparent 70%),
 radial-gradient(120% 90% at 50% 120%,rgba(0,0,0,.55),transparent 60%);}
.wrap:focus-visible{box-shadow:0 0 0 2px var(--gold) inset}
.wrap:fullscreen{height:100vh;background:#14110f}
.scene{position:absolute;inset:0;perspective:1100px;display:grid;place-items:center;cursor:grab}
.scene.drag{cursor:grabbing}
.obj{position:relative;width:400px;height:280px;transform-style:preserve-3d;will-change:transform}
.obj svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.shadow{position:absolute;left:50%;top:calc(50% + 150px);width:340px;height:46px;margin-left:-170px;border-radius:50%;
 background:radial-gradient(closest-side,rgba(0,0,0,.55),transparent);filter:blur(6px);transform:scaleX(var(--sx,1))}
.hud{position:absolute;inset:18px;pointer-events:none;font-family:"JetBrains Mono",ui-monospace,monospace;font-size:10.5px;color:var(--muted);letter-spacing:.06em}
.tick{position:absolute;width:18px;height:18px;border-color:var(--line);border-style:solid}
.tl{left:0;top:0;border-width:1px 0 0 1px}.tr{right:0;top:0;border-width:1px 1px 0 0}
.bl{left:0;bottom:0;border-width:0 0 1px 1px}.br{right:0;bottom:0;border-width:0 1px 1px 0}
.scan{position:absolute;left:8%;right:8%;height:1px;top:18%;background:linear-gradient(90deg,transparent,rgba(127,179,200,.55),transparent);
 box-shadow:0 0 12px rgba(127,179,200,.35);animation:scan 6.5s cubic-bezier(.45,0,.55,1) infinite}
@keyframes scan{0%{top:18%;opacity:0}10%{opacity:1}50%{top:80%}90%{opacity:1}100%{top:18%;opacity:0}}
.tag{position:absolute;display:flex;align-items:center;gap:6px;white-space:nowrap}
.tag i{display:block;width:26px;height:1px;background:var(--line)}
.tag b{font-weight:400;border:1px solid var(--line);padding:2px 6px;border-radius:3px;background:rgba(20,17,15,.6)}
.coord{position:absolute}
.label{position:absolute;left:28px;top:2px;font-size:10px;letter-spacing:.14em;color:var(--copper);text-transform:uppercase}
.ctrl{position:absolute;right:14px;bottom:12px;display:flex;gap:6px;pointer-events:auto}
.ctrl button{font:500 12px Geist,system-ui,sans-serif;color:var(--text);background:rgba(30,26,22,.85);border:1px solid var(--line);
 border-radius:7px;padding:5px 9px;cursor:pointer;transition:background .2s,transform .12s}
.ctrl button:hover{background:rgba(58,50,43,.95)}.ctrl button:active{transform:translateY(1px)}
.ctrl button:focus-visible{outline:2px solid var(--gold);outline-offset:1px}
@media (max-width:700px){.coord{display:none}.label{right:28px;line-height:1.5}}
@media (max-width:560px){.tag{display:none}}
@media (prefers-reduced-motion:reduce){.scan{animation:none;opacity:0}}
</style></head><body>
<div class="wrap" id="wrap" tabindex="0" role="img"
 aria-label="Illustrative visualization: a generic, computer-drawn pottery sherd. It is not a photograph or model of any real artifact and carries no real inscription. Drag or use the arrow keys to rotate.">
 <div class="scene" id="scene"><div class="shadow" id="shadow"></div><div class="obj" id="obj">__LAYERS__
  <svg viewBox="0 0 400 280" aria-hidden="true" style="transform:translateZ(1px)">
   <defs>
    <radialGradient id="terr" cx="42%" cy="40%" r="75%"><stop offset="0" stop-color="#c77a4f"/><stop offset=".55" stop-color="#a6573a"/><stop offset="1" stop-color="#6e3824"/></radialGradient>
    <linearGradient id="slip" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1c1714"/><stop offset=".75" stop-color="#2a2019"/><stop offset="1" stop-color="#2a2019" stop-opacity="0"/></linearGradient>
    <filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="3" seed="7"/>
     <feColorMatrix values="0 0 0 0 .1  0 0 0 0 .06  0 0 0 0 .03  0 0 0 .55 0"/><feComposite in2="SourceGraphic" operator="in"/></filter>
    <clipPath id="clip"><path d="__OUTLINE__"/></clipPath>
   </defs>
   <path d="__OUTLINE__" fill="url(#terr)"/>
   <g clip-path="url(#clip)"><rect x="0" y="0" width="400" height="104" fill="url(#slip)"/>
    <rect width="400" height="280" filter="url(#grain)" opacity=".9"/>
    <g stroke="#e9d3b8" stroke-opacity=".55" stroke-width="1.6" stroke-linecap="round" fill="none">
     <path d="M150 150 q8 -14 3 -30"/><path d="M178 122 l6 32"/><path d="M204 140 q10 6 18 -4"/><path d="M236 118 l-4 34"/>
    </g>
    <rect x="136" y="108" width="112" height="56" fill="none" stroke="#7fb3c8" stroke-opacity=".8" stroke-dasharray="4 4" rx="3"/>
   </g>
   <path d="__OUTLINE__" fill="none" stroke="rgba(0,0,0,.35)" stroke-width="1.2"/>
  </svg>
  <div id="spec" style="position:absolute;inset:0;clip-path:path('__OUTLINE__');transform:translateZ(2px);mix-blend-mode:soft-light;
   background:linear-gradient(115deg,transparent 30%,rgba(255,236,210,.55) 48%,transparent 62%);background-size:260% 100%"></div>
 </div></div>
 <div class="hud" aria-hidden="true">
  <div class="tick tl"></div><div class="tick tr"></div><div class="tick bl"></div><div class="tick br"></div>
  <div class="scan" id="scan"></div>
  <div class="tag" style="left:4%;top:24%"><b>surface</b><i></i></div>
  <div class="tag" style="right:4%;top:36%"><i></i><b>region of interest</b></div>
  <div class="tag" style="left:6%;bottom:22%"><b>break edge</b><i></i></div>
  <div class="coord" style="right:28px;top:2px">x 0.42 · y 0.31 · illustrative</div>
  <div class="label">Illustrative visualization · not an archaeological artifact</div>
 </div>
 <div class="ctrl" role="toolbar" aria-label="Illustration controls">
  <button id="bPause" aria-label="Pause rotation">Pause</button>
  <button id="bIn" aria-label="Zoom in">+</button><button id="bOut" aria-label="Zoom out">−</button>
  <button id="bReset" aria-label="Reset view">Reset</button><button id="bFs" aria-label="Toggle fullscreen">⤢</button>
 </div>
</div>
<script>
(()=>{
 const wrap=document.getElementById('wrap'),obj=document.getElementById('obj'),spec=document.getElementById('spec'),
  scene=document.getElementById('scene'),shadow=document.getElementById('shadow'),bPause=document.getElementById('bPause');
 const reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 let yaw=-18,pitch=12,zoom=1,auto=!reduce,visible=true,dragging=false,raf=0,t0=performance.now(),base=-18,px=0,py=0;
 function apply(){obj.style.transform=`scale(${zoom}) rotateX(${pitch}deg) rotateY(${yaw}deg)`;
  spec.style.backgroundPosition=`${50+yaw*1.4}% 0`;shadow.style.setProperty('--sx',(1-Math.abs(yaw)/180).toFixed(3));}
 function frame(now){raf=0;if(!auto||!visible||dragging||document.hidden)return;
  yaw=base+Math.sin((now-t0)/2600)*24;apply();raf=requestAnimationFrame(frame);}
 function run(){if(!raf&&auto&&visible&&!document.hidden)raf=requestAnimationFrame(frame);}
 function setAuto(v){auto=v&&!reduce;bPause.textContent=auto?'Pause':'Play';bPause.setAttribute('aria-label',auto?'Pause rotation':'Play rotation');
  if(auto){t0=performance.now()-Math.asin(Math.max(-1,Math.min(1,(yaw-base)/24)))*2600;run();}}
 new IntersectionObserver(es=>{visible=es[0].isIntersecting;run();},{threshold:.05}).observe(wrap);
 document.addEventListener('visibilitychange',run);
 scene.addEventListener('pointerdown',ev=>{dragging=true;scene.classList.add('drag');px=ev.clientX;py=ev.clientY;scene.setPointerCapture(ev.pointerId);});
 scene.addEventListener('pointermove',ev=>{if(!dragging)return;yaw+=(ev.clientX-px)*.4;pitch=Math.max(-40,Math.min(50,pitch-(ev.clientY-py)*.3));px=ev.clientX;py=ev.clientY;base=yaw;apply();});
 const end=()=>{if(!dragging)return;dragging=false;scene.classList.remove('drag');base=yaw;setAuto(false);};
 scene.addEventListener('pointerup',end);scene.addEventListener('pointercancel',end);
 const z=d=>{zoom=Math.max(.35,Math.min(1.8,zoom+d));apply();};
 const reset=()=>{yaw=-18;pitch=12;zoom=fitZ;base=-18;apply();setAuto(true);};
 const fs=()=>{try{document.fullscreenElement?document.exitFullscreen():wrap.requestFullscreen();}catch(e){}};
 document.getElementById('bIn').onclick=()=>z(.15);document.getElementById('bOut').onclick=()=>z(-.15);
 document.getElementById('bReset').onclick=reset;document.getElementById('bFs').onclick=fs;bPause.onclick=()=>setAuto(!auto);
 wrap.addEventListener('keydown',ev=>{const k=ev.key;let h=true;
  if(k==='ArrowLeft'){yaw-=8;base=yaw;setAuto(false);apply();}else if(k==='ArrowRight'){yaw+=8;base=yaw;setAuto(false);apply();}
  else if(k==='ArrowUp'){pitch=Math.max(-40,pitch-6);apply();}else if(k==='ArrowDown'){pitch=Math.min(50,pitch+6);apply();}
  else if(k==='+'||k==='='){z(.15);}else if(k==='-'){z(-.15);}else if(k==='0'){reset();}
  else if(k===' '){setAuto(!auto);}else if(k==='f'||k==='F'){fs();}else h=false;if(h)ev.preventDefault();});
 // fit the 400px object to narrow containers; the user can still zoom from there
 let fitZ=1;const fitW=()=>{fitZ=Math.min(1,(wrap.clientWidth-40)/440);};fitW();zoom=fitZ;
 new ResizeObserver(()=>{const old=fitZ;fitW();zoom=Math.max(.35,zoom*fitZ/old);apply();}).observe(wrap);
 apply();setAuto(!reduce);
})();
</script></body></html>"""


def _layers() -> str:
    """Stacked copies behind the face: the sherd's fired-clay thickness (darker toward the core)."""
    out = []
    for i in range(1, LAYERS + 1):
        shade = 92 - i * 3
        out.append(f'<svg viewBox="0 0 400 280" aria-hidden="true" style="transform:translateZ(-{i}px)">'
                   f'<path d="{OUTLINE}" fill="rgb({shade + 40},{shade},{max(shade - 30, 20)})"/></svg>')
    return "".join(out)


def sherd_html(height: int = 480) -> str:
    return (_HTML.replace("__H__", str(height)).replace("__LAYERS__", _layers())
            .replace("__OUTLINE__", OUTLINE))


def render_sherd(height: int = 480) -> None:
    st.iframe(sherd_html(height), height=height + 4)   # our own markup only; no user data inside


__all__ = ["render_sherd", "sherd_html"]
