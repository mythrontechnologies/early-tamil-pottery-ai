"""Archaeological photograph inspection viewer, 2D (sandboxed HTML component, no library).

Shows a DISPLAY COPY of the real photograph (downscaled JPEG; the stored file is only read):

* zoom (wheel, buttons, + / -, pinch), pan (drag, arrow keys), fit (0), fullscreen (F);
* measurement graticule (G) and a MEASURE tool (M): two clicks give a distance in ORIGINAL
  pixels and as a fraction of the long side. No physical scale is recorded for any
  photograph, so no millimetres are ever shown;
* exposure / contrast / edge emphasis and an original-vs-enhanced split comparison. Any of
  these makes the view derived, and it then says "Derived display — original source
  preserved.";
* region overlays from the analysis result only, each with an id (R1, R2, ...), its source
  label, and corner handles on human-marked regions. Sources differ by stroke PATTERN and
  label, not only colour: human = solid, user = dashed, AI = dotted ("AI observation — not
  evidence"). Nothing is drawn that no one marked.
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
    "ai_prediction": {"color": "#7fb3c8", "dash": "1.5 3.5", "label": "AI observation — not evidence"},
    "synthetic_prediction": {"color": "#b9a3e3", "dash": "2 4", "label": "Synthetic detector — not evidence"},
}
DERIVED = "Derived display — original source preserved."


def _data_uri(image: Image.Image, max_side: int) -> str:
    im = image.convert("RGB").copy()
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=86, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Photograph viewer</title>
<style>
:root{--line:rgba(236,228,216,.14);--text:#ece4d8;--muted:#b3a698;--gold:#cfae6b;--copper:#c89260}
html,body{margin:0;background:#14110f;color:var(--text);font-family:Geist,system-ui,-apple-system,"Segoe UI",sans-serif}
.v{position:relative;height:__H__px;border:1px solid var(--line);border-radius:16px;overflow:hidden;background:#0f0d0b;outline:none}
.v:focus-visible{box-shadow:0 0 0 2px var(--gold) inset}.v:fullscreen{height:100vh;border-radius:0}
.stage{position:absolute;inset:0;cursor:grab;touch-action:none}.stage.drag{cursor:grabbing}.measuring .stage{cursor:crosshair}
.canvas{position:absolute;left:0;top:0;transform-origin:0 0;will-change:transform}
.canvas img{display:block;user-select:none;-webkit-user-drag:none}
.cmp{position:absolute;inset:0;overflow:hidden}
svg.ov{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}
.grat{display:none}.show-grat .grat{display:block}.hide-ov .reg,.hide-ov .rtag,.hide-ov .hdl{display:none}
.rtag{position:absolute;transform-origin:0 100%;font:600 11px "JetBrains Mono",ui-monospace,monospace;padding:2px 6px;border-radius:3px;background:rgba(20,17,15,.88);white-space:nowrap;pointer-events:none}
.hdl{position:absolute;width:7px;height:7px;margin:-4px 0 0 -4px;background:#14110f;border:1.5px solid var(--gold);pointer-events:none}
.bar{position:absolute;left:10px;right:10px;top:10px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;pointer-events:none}
.bar>*{pointer-events:auto}
button{font:500 12.5px Geist,system-ui,sans-serif;color:var(--text);background:rgba(30,26,22,.9);border:1px solid var(--line);border-radius:999px;padding:6px 11px;min-height:32px;cursor:pointer;transition:background .25s cubic-bezier(.32,.72,0,1),transform .15s}
button:hover{background:rgba(62,53,45,.95)}button:active{transform:scale(.97)}button[aria-pressed="true"]{border-color:var(--gold);color:var(--gold)}
button:disabled{opacity:.45;cursor:not-allowed}
button:focus-visible,input:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.sp{flex:1}
.adj{display:none;gap:10px;flex-wrap:wrap;align-items:center;background:rgba(30,26,22,.92);border:1px solid var(--line);border-radius:12px;padding:5px 10px;font-size:12px;color:var(--muted)}
.adj.on{display:flex}.adj label{display:flex;align-items:center;gap:6px}.adj input[type=range]{width:90px;accent-color:#c8693f}
.read,.zoom{position:absolute;bottom:10px;font:11px "JetBrains Mono",ui-monospace,monospace;color:var(--muted);background:rgba(20,17,15,.85);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
.read{left:10px;max-width:70%}.zoom{right:10px}
.derived{position:absolute;right:10px;bottom:40px;display:none;font:11px "JetBrains Mono",ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;color:#e3c27f;border:1px dashed #e3c27f;border-radius:4px;padding:3px 7px;background:rgba(20,17,15,.88)}
.derived.on{display:block}
.slider{display:none;align-items:center;gap:6px;font-size:12px;color:var(--muted);background:rgba(30,26,22,.9);border:1px solid var(--line);border-radius:999px;padding:3px 10px}
.cmp-on .slider{display:flex}.split{position:absolute;top:0;bottom:0;width:1px;background:var(--gold);display:none;pointer-events:none}.cmp-on .split{display:block}
.legend{display:flex;gap:12px;flex-wrap:wrap;margin-top:8px;font-size:12.5px;color:var(--muted)}
.legend span{display:inline-flex;align-items:center;gap:6px}.legend svg{width:26px;height:10px}
.meta{margin-top:6px;font:11px "JetBrains Mono",ui-monospace,monospace;color:var(--muted);overflow-wrap:anywhere}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head><body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><filter id="edgef"><feConvolveMatrix order="3" kernelMatrix="-1 -1 -1 -1 9 -1 -1 -1 -1" preserveAlpha="true"/></filter></svg>
<div class="v" id="v" tabindex="0" role="application" aria-roledescription="image inspection viewer"
 aria-label="__ALT__. Keys: plus and minus zoom, arrow keys pan, 0 fits, G graticule, R regions, M measure, F fullscreen.">
 <div class="stage" id="stage"><div class="canvas" id="canvas">
  <img id="img" src="__SRC__" alt="__ALT__">
  <div class="cmp" id="cmpwrap" hidden><img id="img2" src="__SRC2__" alt="Contrast-enhanced copy of the same photograph: a derived viewing aid, not evidence"></div>
  <svg class="ov" id="ov" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true"><g class="grat" id="grat"></g><g id="regs"></g><g id="meas"></g></svg>
  <div id="tags"></div>
 </div><div class="split" id="split"></div></div>
 <div class="bar" role="toolbar" aria-label="Viewer controls">
  <button id="zin" aria-label="Zoom in" title="Zoom in (+)">+</button><button id="zout" aria-label="Zoom out" title="Zoom out (−)">−</button>
  <button id="fit" aria-label="Fit image to view" title="Fit (0)">Fit</button>
  <button id="bGrat" aria-pressed="false" aria-label="Toggle measurement graticule" title="Graticule (G)">Grid</button>
  <button id="bMeas" aria-pressed="false" aria-label="Measure: click two points" title="Measure (M)">Measure</button>
  <button id="bReg" aria-pressed="true" aria-label="Toggle region overlays (__NREG__ regions)" title="Regions (R)">Regions __NREG__</button>
  <button id="bAdj" aria-pressed="false" aria-expanded="false" aria-controls="adj" title="Exposure, contrast, edge emphasis">Adjust</button>
  <div class="adj" id="adj" role="group" aria-label="Derived display adjustments">
   <label>Exposure <input type="range" id="exp" min="0.4" max="2" step="0.05" value="1" aria-label="Exposure"></label>
   <label>Contrast <input type="range" id="con" min="0.5" max="2.5" step="0.05" value="1" aria-label="Contrast"></label>
   <label><input type="checkbox" id="edge"> Edge emphasis</label>
  </div>
  <button id="bCmp" aria-pressed="false" aria-label="Compare with the contrast-enhanced view" title="Split comparison" __CMPDIS__>Compare</button>
  <label class="slider" for="cmpR">split <input type="range" id="cmpR" min="0" max="100" value="50" aria-label="Comparison split position"></label>
  <span class="sp"></span><button id="bFs" aria-label="Toggle fullscreen" title="Fullscreen (F)">⤢</button>
 </div>
 <div class="derived" id="derived" role="status">__DERIVED__</div>
 <div class="read" id="read" aria-live="polite">x — · y —</div><div class="zoom" id="zl">100%</div>
</div>
<div class="legend" aria-label="Region legend">__LEGEND__</div>
<div class="meta">__META__</div>
<script>
(()=>{
const W=__W__,H=__H0__,OW=__OW__,OH=__OH__,regs=__REGS__;
const $=id=>document.getElementById(id),v=$('v'),stage=$('stage'),canvas=$('canvas'),img=$('img'),img2=$('img2'),ov=$('ov'),read=$('read'),zl=$('zl'),
 cmpwrap=$('cmpwrap'),split=$('split'),cmpR=$('cmpR'),tags=$('tags'),meas=$('meas');
img.width=W;img.height=H;img2.width=W;img2.height=H;canvas.style.width=W+'px';canvas.style.height=H+'px';ov.style.width=W+'px';ov.style.height=H+'px';
const NS='http://www.w3.org/2000/svg',mk=(t,a)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
for(let i=1;i<10;i++)for(const [x1,y1,x2,y2] of [[i/10,0,i/10,1],[0,i/10,1,i/10]])$('grat').appendChild(mk('line',{x1,y1,x2,y2,stroke:'rgba(236,228,216,.3)','stroke-width':1,'vector-effect':'non-scaling-stroke','stroke-dasharray':i%5?'2 4':''}));
regs.forEach((r,i)=>{const a={class:'reg',x:r.x,y:r.y,width:r.w,height:r.h,fill:'none',stroke:r.color,'stroke-width':2,'vector-effect':'non-scaling-stroke'};if(r.dash)a['stroke-dasharray']=r.dash;
 $('regs').appendChild(mk('rect',a));const t=document.createElement('div');t.className='rtag';t.style.color=r.color;t.textContent=`R${i+1} · ${r.label}`;t.dataset.x=r.x;t.dataset.y=r.y;tags.appendChild(t);
 if(r.human)for(const [hx,hy] of [[r.x,r.y],[r.x+r.w,r.y],[r.x,r.y+r.h],[r.x+r.w,r.y+r.h]]){const h=document.createElement('div');h.className='hdl';h.dataset.x=hx;h.dataset.y=hy;tags.appendChild(h);}});
let sc=1,tx=0,ty=0,drag=false,px=0,py=0,moved=0;
function place(){for(const el of tags.children){el.style.left=(el.dataset.x*W)+'px';el.style.top=(el.dataset.y*H)+'px';
 el.style.transform=el.classList.contains('rtag')?`translateY(-100%) scale(${1/sc})`:`scale(${1/sc})`;}}
function fit(){const b=stage.getBoundingClientRect();sc=Math.min(b.width/W,b.height/H)*.96;tx=(b.width-W*sc)/2;ty=(b.height-H*sc)/2;apply();}
function apply(){canvas.style.transform=`translate(${tx}px,${ty}px) scale(${sc})`;zl.textContent=(sc*W/OW*100).toFixed(1)+'% of original';
 const f=cmpR.value/100;cmpwrap.style.clipPath=`inset(0 0 0 ${f*100}%)`;split.style.left=(tx+W*sc*f)+'px';place();}
function zoomAt(f,cx,cy){const n=Math.max(.05,Math.min(40,sc*f));tx=cx-(cx-tx)*n/sc;ty=cy-(cy-ty)*n/sc;sc=n;apply();}
const center=()=>{const b=stage.getBoundingClientRect();return [b.width/2,b.height/2];};
const norm=e=>{const b=stage.getBoundingClientRect();return [(e.clientX-b.left-tx)/(W*sc),(e.clientY-b.top-ty)/(H*sc)];};
const expI=$('exp'),conI=$('con'),edgeI=$('edge'),der=$('derived');
function adjust(){const e=+expI.value,c=+conI.value,ed=edgeI.checked;img.style.filter=`brightness(${e}) contrast(${c})`+(ed?' url(#edgef)':'');
 der.classList.toggle('on',e!==1||c!==1||ed||$('bCmp').getAttribute('aria-pressed')==='true');}
for(const el of [expI,conI,edgeI])el.addEventListener('input',adjust);
let measuring=false,pts=[];
function drawMeas(){meas.innerHTML='';pts.forEach(p=>meas.appendChild(mk('circle',{cx:p[0],cy:p[1],r:.004,fill:'#cfae6b'})));
 if(pts.length===2){meas.appendChild(mk('line',{x1:pts[0][0],y1:pts[0][1],x2:pts[1][0],y2:pts[1][1],stroke:'#cfae6b','stroke-width':2,'vector-effect':'non-scaling-stroke'}));
  const dx=(pts[1][0]-pts[0][0])*OW,dy=(pts[1][1]-pts[0][1])*OH,d=Math.hypot(dx,dy);
  read.textContent=`distance ${d.toFixed(0)} px of original (${(d/Math.max(OW,OH)).toFixed(3)} of the long side) · no physical scale is recorded`;}}
const bM=$('bMeas');const setMeas=on=>{measuring=on;bM.setAttribute('aria-pressed',on);v.classList.toggle('measuring',on);if(!on){pts=[];drawMeas();read.textContent='x — · y —';}
 else read.textContent='Measure: click the first point';};
bM.onclick=()=>setMeas(!measuring);
stage.addEventListener('wheel',e=>{e.preventDefault();const b=stage.getBoundingClientRect();zoomAt(e.deltaY<0?1.15:1/1.15,e.clientX-b.left,e.clientY-b.top);},{passive:false});
const ptrs=new Map();let pinch0=0;
stage.addEventListener('pointerdown',e=>{ptrs.set(e.pointerId,e);drag=true;moved=0;stage.classList.add('drag');px=e.clientX;py=e.clientY;stage.setPointerCapture(e.pointerId);
 if(ptrs.size===2){const [a,b]=[...ptrs.values()];pinch0=Math.hypot(a.clientX-b.clientX,a.clientY-b.clientY);}});
stage.addEventListener('pointermove',e=>{const [nx,ny]=norm(e);
 if(!measuring)read.textContent=(nx>=0&&nx<=1&&ny>=0&&ny<=1)?`x ${nx.toFixed(3)} · y ${ny.toFixed(3)} · px ${Math.round(nx*OW)}, ${Math.round(ny*OH)}`:'x — · y —';
 if(ptrs.has(e.pointerId))ptrs.set(e.pointerId,e);
 if(ptrs.size===2){const [a,b]=[...ptrs.values()];const d=Math.hypot(a.clientX-b.clientX,a.clientY-b.clientY);if(pinch0){const r=stage.getBoundingClientRect();
  zoomAt(d/pinch0,(a.clientX+b.clientX)/2-r.left,(a.clientY+b.clientY)/2-r.top);}pinch0=d;return;}
 if(!drag)return;moved+=Math.abs(e.clientX-px)+Math.abs(e.clientY-py);tx+=e.clientX-px;ty+=e.clientY-py;px=e.clientX;py=e.clientY;apply();});
const end=e=>{ptrs.delete(e.pointerId);if(ptrs.size<2)pinch0=0;if(!drag)return;drag=false;stage.classList.remove('drag');
 if(measuring&&moved<6){const p=norm(e);if(p[0]>=0&&p[0]<=1&&p[1]>=0&&p[1]<=1){pts=pts.length>=2?[p]:[...pts,p];drawMeas();if(pts.length===1)read.textContent='Measure: click the second point';}}};
stage.addEventListener('pointerup',end);stage.addEventListener('pointercancel',end);
const tog=btn=>{const on=btn.getAttribute('aria-pressed')!=='true';btn.setAttribute('aria-pressed',on);return on;};
$('zin').onclick=()=>zoomAt(1.3,...center());$('zout').onclick=()=>zoomAt(1/1.3,...center());$('fit').onclick=fit;
const bG=$('bGrat'),bR=$('bReg'),bC=$('bCmp'),bA=$('bAdj');
bG.onclick=()=>v.classList.toggle('show-grat',tog(bG));bR.onclick=()=>v.classList.toggle('hide-ov',!tog(bR));
bA.onclick=()=>{const on=tog(bA);bA.setAttribute('aria-expanded',on);$('adj').classList.toggle('on',on);};
bC.onclick=()=>{const on=tog(bC);v.classList.toggle('cmp-on',on);cmpwrap.hidden=!on;adjust();apply();};cmpR.oninput=apply;
const fs=()=>{try{document.fullscreenElement?document.exitFullscreen():v.requestFullscreen();}catch(e){}};
$('bFs').onclick=fs;document.addEventListener('fullscreenchange',()=>setTimeout(fit,60));
v.addEventListener('keydown',e=>{const k=e.key,s=40;let h=true;
 if(k==='+'||k==='=')zoomAt(1.3,...center());else if(k==='-')zoomAt(1/1.3,...center());else if(k==='0')fit();
 else if(k==='ArrowLeft'){tx+=s;apply();}else if(k==='ArrowRight'){tx-=s;apply();}else if(k==='ArrowUp'){ty+=s;apply();}else if(k==='ArrowDown'){ty-=s;apply();}
 else if(k==='g'||k==='G')bG.click();else if(k==='r'||k==='R')bR.click();else if(k==='m'||k==='M')bM.click();else if(k==='Escape')setMeas(false);
 else if(k==='f'||k==='F')fs();else h=false;if(h)e.preventDefault();});
new ResizeObserver(fit).observe(stage);
if(img.complete)fit();else img.onload=fit;
})();
</script><script>addEventListener('keydown',function(e){if((e.ctrlKey||e.metaKey)&&(e.key==='k'||e.key==='K')){try{if(parent.__etpPalette){e.preventDefault();parent.__etpPalette.open();}}catch(_){}}});</script></body></html>"""


def render_viewer(image: Image.Image, regions: list[dict[str, Any]], *, alt: str, meta: str = "",
                  enhanced: Image.Image | None = None, height: int = 560, max_side: int = 1800) -> None:
    """Render the viewer. ``regions`` are analysis-result region dicts (normalised x, y, width,
    height, source). ``enhanced`` enables the split comparison."""
    ow, oh = image.size
    src = _data_uri(image, max_side)
    disp = image.copy()
    disp.thumbnail((max_side, max_side))
    w, h = disp.size
    regs = []
    for r in regions:
        s = SOURCE_STYLE.get(r["source"], SOURCE_STYLE["user_supplied"])
        regs.append({"x": r["x"], "y": r["y"], "w": r["width"], "h": r["height"], "color": s["color"],
                     "dash": s["dash"], "label": s["label"], "human": r["source"] == "human_annotation"})
    present = sorted({r["source"] for r in regions})
    legend = "".join(
        f'<span><svg viewBox="0 0 26 10" aria-hidden="true"><line x1="1" y1="5" x2="25" y2="5" stroke="{s["color"]}" '
        f'stroke-width="2" stroke-dasharray="{s["dash"]}"/></svg>{html.escape(s["label"])}</span>'
        for k, s in SOURCE_STYLE.items() if k in present) or "<span>No region is marked on this photograph.</span>"
    page = (_HTML.replace("__H__", str(height)).replace("__SRC__", src)
            .replace("__SRC2__", _data_uri(enhanced, max_side) if enhanced is not None else src)
            .replace("__CMPDIS__", "" if enhanced is not None else "disabled")
            .replace("__ALT__", html.escape(alt, quote=True)).replace("__NREG__", str(len(regions)))
            .replace("__LEGEND__", legend).replace("__META__", html.escape(meta)).replace("__DERIVED__", DERIVED)
            .replace("__W__", str(w)).replace("__H0__", str(h)).replace("__OW__", str(ow)).replace("__OH__", str(oh))
            .replace("__REGS__", json.dumps(regs)))
    # All interpolated values are escaped or numeric; the photograph is a data URI we encode ourselves.
    st.iframe(page, height=height + 70)


__all__ = ["DERIVED", "SOURCE_STYLE", "render_viewer"]
