"""Synthetic pipeline replay on an ILLUSTRATIVE 3D sherd (Milestone 10).

The left half is the CSS-3D illustrative sherd of the landing page (no WebGL, so nothing to fail),
carrying synthetic result markers: a callout for the detected synthetic inscription region (placed
illustratively: the sherd is NOT a scan of the input image and says so), the synthetic class and the
synthetic glyph transcription as text, and a ring of eight stage lights. The right half replays the
recorded pipeline run: each of the eight stages reveals its ACTUAL result and its MEASURED latency.
The replay uses a short fixed transition per stage; it never pretends a stage took longer than it did.

Accessibility: every control is a real button (Play/Pause, Skip, Replay, 2D view); stage reveals are
announced through an aria-live region; prefers-reduced-motion shows everything at once without
rotation; a 2D view is always available and is used automatically if CSS 3D is unsupported. Every value
is inserted with textContent (never HTML). The full results are also on the page itself, outside this
frame, so nothing depends on it.
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from .sherd3d import OUTLINE, _layers

_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Synthetic pipeline replay</title>
<style>
:root{--line:rgba(236,228,216,.14);--muted:#a3968a;--text:#ece4d8;--text2:#c9bdac;--syn:#b9a3e3;--gold:#cfae6b;--ok:#8fb57a}
html,body{margin:0;background:transparent;color:var(--text);font-family:Geist,system-ui,sans-serif;font-size:14px}
*{box-sizing:border-box}
.wrap{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);gap:14px;height:__H__px;border-radius:20px;padding:12px;
 border:1.5px dashed var(--syn);background:repeating-linear-gradient(135deg,rgba(185,163,227,.05) 0 10px,rgba(185,163,227,.015) 10px 20px)}
.stagebox{position:relative;border-radius:16px;overflow:hidden;background:radial-gradient(60% 70% at 50% 45%,rgba(185,163,227,.12),transparent 70%)}
.scene{position:absolute;inset:0;perspective:1100px;display:grid;place-items:center}
.obj{position:relative;width:400px;height:280px;transform-style:preserve-3d;will-change:transform}
.obj svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.flat .obj{transform:none!important;transform-style:flat}.flat .obj svg:not(.face){display:none}
.label{position:absolute;left:12px;top:10px;right:12px;font:11px/1.4 "JetBrains Mono",ui-monospace,monospace;letter-spacing:.08em;
 text-transform:uppercase;color:var(--syn)}
.marks{position:absolute;left:12px;right:12px;bottom:10px;font:12px/1.45 "JetBrains Mono",ui-monospace,monospace;color:var(--text2)}
.marks b{color:var(--text);font-weight:500}
.ring{position:absolute;left:50%;top:52%;width:0;height:0;pointer-events:none}
.ring i{position:absolute;width:22px;height:22px;margin:-11px;border-radius:50%;border:1.5px solid var(--line);background:#1c1814;
 display:grid;place-items:center;font:9.5px "JetBrains Mono",monospace;color:var(--muted);font-style:normal;transition:all .35s}
.ring i.on{border-color:var(--syn);color:#14110f;background:var(--syn);box-shadow:0 0 14px rgba(185,163,227,.55)}
.panel{display:flex;flex-direction:column;min-height:0}
.ctrl{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.ctrl button{font:500 13px Geist,system-ui,sans-serif;color:var(--text);background:rgba(30,26,22,.9);border:1px solid var(--line);
 border-radius:8px;padding:7px 11px;min-height:34px;cursor:pointer}
.ctrl button:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.ctrl button[aria-pressed="true"]{border-color:var(--syn);color:var(--syn)}
ol{list-style:none;margin:0;padding:0;overflow-y:auto;min-height:0;flex:1}
li{display:grid;grid-template-columns:2.1rem minmax(0,1fr);gap:2px 10px;padding:7px 4px;border-top:1px solid var(--line);
 opacity:.35;transition:opacity .35s}
li.on{opacity:1}
li .n{grid-row:span 2;width:1.8rem;height:1.8rem;border-radius:50%;border:1px solid var(--line);display:grid;place-items:center;
 font:11px "JetBrains Mono",monospace;color:var(--syn)}
li.on .n{border-color:var(--syn)}
li .t{font-weight:600;font-size:13px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
li .t small{font:400 11px "JetBrains Mono",monospace;color:var(--muted)}
li .s{color:var(--text2);font-size:12.5px;overflow-wrap:anywhere}
.status{font:11px "JetBrains Mono",monospace;color:var(--muted);margin-top:6px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
@media (max-width:640px){.wrap{grid-template-columns:1fr;grid-template-rows:270px minmax(0,1fr)}.ring{top:56%}
 .marks{display:none}.label{font-size:10px}}
@media (prefers-reduced-motion:reduce){.ring i,li{transition:none}}
</style></head><body>
<section class="wrap" id="wrap" aria-label="Synthetic pipeline replay with an illustrative 3D sherd. Synthetic demonstration, not archaeological evidence.">
 <div class="stagebox" id="stagebox" role="img"
  aria-label="Illustrative visualization: a generic computer-drawn sherd with synthetic result markers. It is not a scan or model of the input image.">
  <div class="scene"><div class="obj" id="obj">__LAYERS__
   <svg class="face" viewBox="0 0 400 280" aria-hidden="true" style="transform:translateZ(1px)">
    <defs><radialGradient id="terr" cx="42%" cy="40%" r="75%"><stop offset="0" stop-color="#c77a4f"/><stop offset=".55" stop-color="#a6573a"/><stop offset="1" stop-color="#6e3824"/></radialGradient>
     <clipPath id="clip"><path d="__OUTLINE__"/></clipPath></defs>
    <path d="__OUTLINE__" fill="url(#terr)"/>
    <g clip-path="url(#clip)"><g stroke="#e9d3b8" stroke-opacity=".5" stroke-width="1.6" stroke-linecap="round" fill="none">
     <path d="M150 150 q8 -14 3 -30"/><path d="M178 122 l6 32"/><path d="M204 140 q10 6 18 -4"/><path d="M236 118 l-4 34"/></g>
     <rect id="callout" x="132" y="104" width="120" height="62" rx="4" fill="rgba(185,163,227,.10)" stroke="#b9a3e3" stroke-width="2"
      stroke-dasharray="2 4" opacity="0"/></g>
    <text id="calloutLabel" x="132" y="96" fill="#b9a3e3" font-family="JetBrains Mono,monospace" font-size="11" opacity="0"></text>
    <path d="__OUTLINE__" fill="none" stroke="rgba(0,0,0,.35)" stroke-width="1.2"/>
   </svg></div></div>
  <div class="ring" id="ring" aria-hidden="true"></div>
  <div class="label">Illustrative visualization · not a scan of the input image · SYNTHETIC</div>
  <div class="marks" id="marks"></div>
 </div>
 <div class="panel">
  <div class="ctrl" role="toolbar" aria-label="Replay controls">
   <button id="bPlay" aria-label="Pause the replay">Pause</button>
   <button id="bSkip" aria-label="Skip to the end: show every stage">Skip</button>
   <button id="bReplay" aria-label="Replay the recorded run from the start">Replay</button>
   <button id="b2d" aria-pressed="false" aria-label="Show the illustration in 2D">2D view</button>
  </div>
  <ol id="list" aria-label="Pipeline stages of the recorded synthetic run"></ol>
  <div class="status" id="status"></div>
  <div class="sr" aria-live="polite" id="live"></div>
 </div>
</section>
<script>
(()=>{
 const DATA=__DATA__;
 const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const wrap=document.getElementById('wrap'),obj=document.getElementById('obj'),list=document.getElementById('list'),
  ring=document.getElementById('ring'),live=document.getElementById('live'),status=document.getElementById('status'),
  bPlay=document.getElementById('bPlay'),b2d=document.getElementById('b2d'),marks=document.getElementById('marks'),
  callout=document.getElementById('callout'),calloutLabel=document.getElementById('calloutLabel');
 const n=DATA.stages.length;const rows=[];const dots=[];
 DATA.stages.forEach((s,i)=>{const li=document.createElement('li');const num=document.createElement('span');num.className='n';
  num.textContent=String(s.number).padStart(2,'0');const t=document.createElement('div');t.className='t';const tt=document.createElement('span');
  tt.textContent=s.title.toUpperCase();const ms=document.createElement('small');ms.textContent=(s.seconds*1000).toFixed(1)+' ms';
  t.append(tt,ms);const sm=document.createElement('div');sm.className='s';sm.textContent=s.summary;li.append(num,t,sm);list.append(li);rows.push(li);
  const d=document.createElement('i');d.textContent=i+1;ring.append(d);dots.push(d);});
 // the ring fits the stage box (recomputed on resize), clear of the label and the result text
 const box=document.getElementById('stagebox');
 function layoutRing(){const narrow=box.clientWidth<520;const rx=Math.max(60,Math.min(box.clientWidth/2-22,190));
  const ry=Math.max(40,Math.min(box.clientHeight/2-(narrow?44:58),112));
  dots.forEach((d,i)=>{const a=(i/n)*Math.PI*2-Math.PI/2;d.style.left=(Math.cos(a)*rx)+'px';d.style.top=(Math.sin(a)*ry)+'px';});}
 layoutRing();new ResizeObserver(layoutRing).observe(box);
 const m=[];const add=(k,v)=>{const p=document.createElement('div');const b=document.createElement('b');b.textContent=k+' ';p.append(b,document.createTextNode(v));m.push(p);};
 add('class',DATA.label+' · '+Math.round(DATA.confidence*100)+'% model confidence (synthetic)');
 add('regions',DATA.regions+' synthetic inscription region(s)');
 add('glyphs',DATA.transcription||'no synthetic glyph transcription');
 calloutLabel.textContent=DATA.regions?'R1 · synthetic region (illustrative)':'';
 let step=0,timer=0,playing=!reduce,yaw=-16,raf=0,t0=performance.now();
 const flat=!CSS.supports('transform-style','preserve-3d');
 function show(k){rows.forEach((r,i)=>r.classList.toggle('on',i<k));dots.forEach((d,i)=>d.classList.toggle('on',i<k));
  if(k>=4){callout.setAttribute('opacity','1');calloutLabel.setAttribute('opacity','1');}else{callout.setAttribute('opacity','0');calloutLabel.setAttribute('opacity','0');}
  marks.replaceChildren(...m.slice(0,k>=6?3:k>=4?2:k>=3?1:0));
  status.textContent=k>=n?'Replay complete: '+n+' of '+n+' stages · total '+(DATA.total*1000).toFixed(1)+' ms measured':
   'Stage '+k+' of '+n+(playing?' · playing':' · paused');
  if(k>0){const s=DATA.stages[k-1];live.textContent='Stage '+s.number+' of '+n+', '+s.title+': '+s.summary;}}
 function tick(){if(!playing)return;if(step<n){step++;show(step);timer=setTimeout(tick,450);}else{setPlaying(false);}}
 function setPlaying(v){playing=v&&!reduce;bPlay.textContent=playing?'Pause':'Play';
  bPlay.setAttribute('aria-label',playing?'Pause the replay':'Play the replay');clearTimeout(timer);if(playing){timer=setTimeout(tick,200);spin();}show(step);}
 function spin(){if(raf||reduce||flat||b2d.getAttribute('aria-pressed')==='true')return;const f=now=>{raf=0;if(!playing)return;
  yaw=-16+Math.sin((now-t0)/2400)*20;obj.style.transform=`scale(${fit}) rotateX(12deg) rotateY(${yaw}deg)`;raf=requestAnimationFrame(f);};raf=requestAnimationFrame(f);}
 let fit=1;const doFit=()=>{const box=document.getElementById('stagebox');fit=Math.min(1,(box.clientWidth-30)/420,(box.clientHeight-60)/300);
  obj.style.transform=`scale(${fit}) rotateX(12deg) rotateY(${yaw}deg)`;};new ResizeObserver(doFit).observe(document.getElementById('stagebox'));doFit();
 bPlay.onclick=()=>{if(step>=n){step=0;}setPlaying(!playing);};
 document.getElementById('bSkip').onclick=()=>{setPlaying(false);step=n;show(step);};
 document.getElementById('bReplay').onclick=()=>{step=0;if(reduce){step=n;show(step);return;}setPlaying(true);};
 b2d.onclick=()=>{const on=b2d.getAttribute('aria-pressed')!=='true';b2d.setAttribute('aria-pressed',on);
  b2d.setAttribute('aria-label',on?'Show the illustration in 3D':'Show the illustration in 2D');wrap.classList.toggle('flat',on);if(!on)spin();};
 if(flat){wrap.classList.add('flat');b2d.setAttribute('aria-pressed','true');b2d.disabled=true;status.textContent='3D unavailable — showing 2D';}
 if(reduce){step=n;playing=false;bPlay.textContent='Play';bPlay.setAttribute('aria-label','Play the replay');show(step);}else{setPlaying(true);}
})();
</script></body></html>"""


def replay_html(analysis: dict[str, Any], height: int = 520) -> str:
    c, o, ins = analysis["classification"], analysis["ocr"], analysis["inscription"]
    data = {"stages": [{k: s[k] for k in ("number", "title", "seconds", "summary")} for s in analysis["stages"]],
            "label": c["display_label"], "confidence": c["confidence"], "regions": len(ins["regions"]),
            "transcription": o["transcription"] if o["status"] == "read" else "",
            "total": analysis["performance"]["total_seconds"]}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")      # values are set with textContent in JS
    return (_HTML.replace("__H__", str(height)).replace("__LAYERS__", _layers()).replace("__OUTLINE__", OUTLINE)
            .replace("__DATA__", payload))


def render_replay(analysis: dict[str, Any], height: int = 520) -> None:
    st.iframe(replay_html(analysis, height), height=height + 6)


__all__ = ["render_replay", "replay_html"]
