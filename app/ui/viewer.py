"""Archaeological photograph inspection viewer (sandboxed HTML component, no library).

Shows a DISPLAY COPY of the real photograph (downscaled JPEG; the stored file is only read):
zoom (wheel, buttons, + / -), pan (drag, arrow keys), fullscreen, a toggleable measurement
graticule, a live readout of normalised and original-pixel coordinates, region overlays and an
original / enhanced split comparison.

Regions are drawn only from the analysis result (human-marked, user-supplied or AI). Sources
are distinguished by stroke PATTERN and a text label, not by colour alone:
human = solid, user = dashed, AI = dotted. Nothing here draws an inscription boundary that no
one marked.
"""

from __future__ import annotations

import base64
import html
import io
import json
from typing import Any

import streamlit as st
from PIL import Image

SOURCE_STYLE = {
    "human_annotation": {"color": "#cfae6b", "dash": "", "label": "human-marked"},
    "user_supplied": {"color": "#d9c6a5", "dash": "6 4", "label": "your region"},
    "ai_prediction": {"color": "#7fb3c8", "dash": "1.5 3.5", "label": "AI proposal"},
}


def _data_uri(image: Image.Image, max_side: int) -> str:
    im = image.convert("RGB").copy()
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=86, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;600&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
<style>
:root{--bg:#14110f;--s:#1e1a16;--line:rgba(236,228,216,.14);--text:#ece4d8;--muted:#a3968a;--gold:#cfae6b;--copper:#b8804a}
html,body{margin:0;background:transparent;color:var(--text);font-family:Geist,system-ui,sans-serif}
.v{position:relative;height:__H__px;border:1px solid var(--line);border-radius:16px;overflow:hidden;background:#0f0d0b;outline:none}
.v:focus-visible{box-shadow:0 0 0 2px var(--gold) inset}
.v:fullscreen{height:100vh;border-radius:0}
.stage{position:absolute;inset:0;cursor:grab;touch-action:none}.stage.drag{cursor:grabbing}
.canvas{position:absolute;left:0;top:0;transform-origin:0 0;will-change:transform}
.canvas img{display:block;user-select:none;-webkit-user-drag:none}
.cmp{position:absolute;inset:0;overflow:hidden}
svg.ov{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}
.grat{display:none}.show-grat .grat{display:block}.hide-ov .reg{display:none}
.bar{position:absolute;left:10px;right:10px;top:10px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;pointer-events:none}
.bar>*{pointer-events:auto}
button{font:500 12px Geist,system-ui,sans-serif;color:var(--text);background:rgba(30,26,22,.88);border:1px solid var(--line);border-radius:7px;padding:5px 9px;cursor:pointer;transition:background .2s,transform .12s}
button:hover{background:rgba(58,50,43,.95)}button:active{transform:translateY(1px)}button[aria-pressed="true"]{border-color:var(--gold);color:var(--gold)}
button:focus-visible,input:focus-visible{outline:2px solid var(--gold);outline-offset:1px}
.sp{flex:1}
.read{position:absolute;left:10px;bottom:10px;font:11px "JetBrains Mono",ui-monospace,monospace;color:var(--muted);background:rgba(20,17,15,.8);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
.zoom{position:absolute;right:10px;bottom:10px;font:11px "JetBrains Mono",ui-monospace,monospace;color:var(--muted);background:rgba(20,17,15,.8);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
.slider{display:none;align-items:center;gap:6px;font-size:11px;color:var(--muted);background:rgba(30,26,22,.88);border:1px solid var(--line);border-radius:7px;padding:3px 8px}
.cmp-on .slider{display:flex}.split{position:absolute;top:0;bottom:0;width:1px;background:var(--gold);display:none;pointer-events:none}.cmp-on .split{display:block}
.legend{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px;font-size:12px;color:var(--muted)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend svg{width:26px;height:10px}
.meta{margin-top:6px;font:11px "JetBrains Mono",ui-monospace,monospace;color:var(--muted);overflow-wrap:anywhere}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head><body>
<div class="v" id="v" tabindex="0" role="application" aria-roledescription="image inspection viewer"
 aria-label="__ALT__. Keys: plus and minus zoom, arrow keys pan, 0 resets, G toggles the graticule, R toggles regions, F fullscreen.">
 <div class="stage" id="stage"><div class="canvas" id="canvas">
  <img id="img" src="__SRC__" alt="__ALT__">
  <div class="cmp" id="cmpwrap" hidden><img id="img2" src="__SRC2__" alt="Enhanced (contrast) version of the same photograph: a viewing aid only"></div>
  <svg class="ov" id="ov" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
   <g class="grat" id="grat"></g><g id="regs"></g></svg>
 </div><div class="split" id="split"></div></div>
 <div class="bar" role="toolbar" aria-label="Viewer controls">
  <button id="zin" aria-label="Zoom in">+</button><button id="zout" aria-label="Zoom out">−</button>
  <button id="fit" aria-label="Fit image to view" title="Fit (0)">Fit</button>
  <button id="bGrat" aria-pressed="false" aria-label="Toggle measurement graticule" title="Measurement graticule (G)">Grid</button>
  <button id="bReg" aria-pressed="true" aria-label="Toggle region overlays (__NREG__ regions)" title="Region overlays (R)">Regions __NREG__</button>
  <button id="bCmp" aria-pressed="false" aria-label="Compare with the contrast-enhanced view" title="Split comparison: original / enhanced" __CMPDIS__>Compare</button>
  <label class="slider" for="cmpR">split <input type="range" id="cmpR" min="0" max="100" value="50" aria-label="Comparison split position"></label>
  <span class="sp"></span><button id="bFs" aria-label="Toggle fullscreen" title="Fullscreen (F)">⤢</button>
 </div>
 <div class="read" id="read" aria-live="off">x — · y —</div><div class="zoom" id="zl">100%</div>
</div>
<div class="legend" aria-label="Region legend">__LEGEND__</div>
<div class="meta">__META__</div>
<script>
(()=>{
const W=__W__,H=__H0__,OW=__OW__,OH=__OH__,regs=__REGS__;
const v=document.getElementById('v'),stage=document.getElementById('stage'),canvas=document.getElementById('canvas'),img=document.getElementById('img'),
 ov=document.getElementById('ov'),read=document.getElementById('read'),zl=document.getElementById('zl'),cmpwrap=document.getElementById('cmpwrap'),
 split=document.getElementById('split'),cmpR=document.getElementById('cmpR');
img.width=W;img.height=H;const img2=document.getElementById('img2');img2.width=W;img2.height=H;
canvas.style.width=W+'px';canvas.style.height=H+'px';ov.style.width=W+'px';ov.style.height=H+'px';
const NS='http://www.w3.org/2000/svg',g=document.getElementById('grat'),rg=document.getElementById('regs');
for(let i=1;i<10;i++){for(const [x1,y1,x2,y2] of [[i/10,0,i/10,1],[0,i/10,1,i/10]]){const l=document.createElementNS(NS,'line');
 l.setAttribute('x1',x1);l.setAttribute('y1',y1);l.setAttribute('x2',x2);l.setAttribute('y2',y2);l.setAttribute('stroke','rgba(236,228,216,.28)');
 l.setAttribute('stroke-width','1');l.setAttribute('vector-effect','non-scaling-stroke');l.setAttribute('stroke-dasharray',i%5?'2 4':'');g.appendChild(l);}}
regs.forEach((r,i)=>{const s=document.createElementNS(NS,'rect');s.setAttribute('class','reg');
 for(const [k,val] of [['x',r.x],['y',r.y],['width',r.w],['height',r.h]])s.setAttribute(k,val);
 s.setAttribute('fill','none');s.setAttribute('stroke',r.color);s.setAttribute('stroke-width','2');s.setAttribute('vector-effect','non-scaling-stroke');
 if(r.dash)s.setAttribute('stroke-dasharray',r.dash);rg.appendChild(s);});
let sc=1,tx=0,ty=0,drag=false,px=0,py=0;
function fit(){const b=stage.getBoundingClientRect();sc=Math.min(b.width/W,b.height/H)*.96;tx=(b.width-W*sc)/2;ty=(b.height-H*sc)/2;apply();}
function apply(){canvas.style.transform=`translate(${tx}px,${ty}px) scale(${sc})`;zl.textContent=(sc*W/OW*100).toFixed(1)+'% of original';
 const f=cmpR.value/100;cmpwrap.style.clipPath=`inset(0 0 0 ${f*100}%)`;split.style.left=(tx+W*sc*f)+'px';}
function zoomAt(f,cx,cy){const n=Math.max(.05,Math.min(40,sc*f));tx=cx-(cx-tx)*n/sc;ty=cy-(cy-ty)*n/sc;sc=n;apply();}
function center(){const b=stage.getBoundingClientRect();return [b.width/2,b.height/2];}
stage.addEventListener('wheel',e=>{e.preventDefault();const b=stage.getBoundingClientRect();zoomAt(e.deltaY<0?1.15:1/1.15,e.clientX-b.left,e.clientY-b.top);},{passive:false});
stage.addEventListener('pointerdown',e=>{drag=true;stage.classList.add('drag');px=e.clientX;py=e.clientY;stage.setPointerCapture(e.pointerId);});
stage.addEventListener('pointermove',e=>{const b=stage.getBoundingClientRect();
 const nx=(e.clientX-b.left-tx)/(W*sc),ny=(e.clientY-b.top-ty)/(H*sc);
 read.textContent=(nx>=0&&nx<=1&&ny>=0&&ny<=1)?`x ${nx.toFixed(3)} · y ${ny.toFixed(3)} · px ${Math.round(nx*OW)}, ${Math.round(ny*OH)}`:'x — · y —';
 if(!drag)return;tx+=e.clientX-px;ty+=e.clientY-py;px=e.clientX;py=e.clientY;apply();});
const end=()=>{drag=false;stage.classList.remove('drag');};stage.addEventListener('pointerup',end);stage.addEventListener('pointercancel',end);
const tog=(btn,cls)=>{const on=btn.getAttribute('aria-pressed')!=='true';btn.setAttribute('aria-pressed',on);return on;};
document.getElementById('zin').onclick=()=>zoomAt(1.3,...center());document.getElementById('zout').onclick=()=>zoomAt(1/1.3,...center());
document.getElementById('fit').onclick=fit;
const bG=document.getElementById('bGrat'),bR=document.getElementById('bReg'),bC=document.getElementById('bCmp');
bG.onclick=()=>v.classList.toggle('show-grat',tog(bG));bR.onclick=()=>v.classList.toggle('hide-ov',!tog(bR));
bC.onclick=()=>{const on=tog(bC);v.classList.toggle('cmp-on',on);cmpwrap.hidden=!on;apply();};cmpR.oninput=apply;
const fs=()=>{try{document.fullscreenElement?document.exitFullscreen():v.requestFullscreen();}catch(e){}};
document.getElementById('bFs').onclick=fs;document.addEventListener('fullscreenchange',()=>setTimeout(fit,60));
v.addEventListener('keydown',e=>{const k=e.key,s=40;let h=true;
 if(k==='+'||k==='=')zoomAt(1.3,...center());else if(k==='-')zoomAt(1/1.3,...center());else if(k==='0')fit();
 else if(k==='ArrowLeft'){tx+=s;apply();}else if(k==='ArrowRight'){tx-=s;apply();}else if(k==='ArrowUp'){ty+=s;apply();}else if(k==='ArrowDown'){ty-=s;apply();}
 else if(k==='g'||k==='G')bG.click();else if(k==='r'||k==='R')bR.click();else if(k==='f'||k==='F')fs();else h=false;if(h)e.preventDefault();});
new ResizeObserver(fit).observe(stage);
if(img.complete)fit();else img.onload=fit;
})();
</script></body></html>"""


def render_viewer(image: Image.Image, regions: list[dict[str, Any]], *, alt: str, meta: str = "",
                  enhanced: Image.Image | None = None, height: int = 560, max_side: int = 1800) -> None:
    """Render the viewer. ``regions`` are analysis-result region dicts (normalised x, y, width,
    height, source). ``enhanced`` enables the split comparison."""
    ow, oh = image.size
    src = _data_uri(image, max_side)
    disp = image.copy()
    disp.thumbnail((max_side, max_side))
    w, h = disp.size
    regs = [{"x": r["x"], "y": r["y"], "w": r["width"], "h": r["height"],
             "color": SOURCE_STYLE.get(r["source"], SOURCE_STYLE["user_supplied"])["color"],
             "dash": SOURCE_STYLE.get(r["source"], SOURCE_STYLE["user_supplied"])["dash"]} for r in regions]
    present = sorted({r["source"] for r in regions})
    legend = "".join(
        f'<span><svg viewBox="0 0 26 10" aria-hidden="true"><line x1="1" y1="5" x2="25" y2="5" stroke="{s["color"]}" '
        f'stroke-width="2" stroke-dasharray="{s["dash"]}"/></svg>{html.escape(s["label"])}</span>'
        for k, s in SOURCE_STYLE.items() if k in present) or "<span>No region is marked on this photograph.</span>"
    page = (_HTML.replace("__H__", str(height)).replace("__SRC__", src)
            .replace("__SRC2__", _data_uri(enhanced, max_side) if enhanced is not None else src)
            .replace("__CMPDIS__", "" if enhanced is not None else "disabled")
            .replace("__ALT__", html.escape(alt, quote=True)).replace("__NREG__", str(len(regions)))
            .replace("__LEGEND__", legend).replace("__META__", html.escape(meta))
            .replace("__W__", str(w)).replace("__H0__", str(h)).replace("__OW__", str(ow)).replace("__OH__", str(oh))
            .replace("__REGS__", json.dumps(regs)))
    # All interpolated values are escaped or numeric; the photograph is a data URI we encode ourselves.
    st.iframe(page, height=height + 70)


__all__ = ["SOURCE_STYLE", "render_viewer"]
