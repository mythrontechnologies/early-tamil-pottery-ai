"""SYNTHETIC DEMONSTRATION mode of the Analysis page (Milestone 10).

Run only after the user explicitly switches the data mode. Choose a generated, held-out (test-split)
synthetic image, press Run analysis, and the complete synthetic pipeline runs once, live: every stage
reports its real result and its measured latency as it finishes. The results are then shown with the
pipeline replay on the illustrative 3D sherd, the photograph viewer with the detected synthetic regions,
the language / reading results (synthetic glyph transcription, then the fictional synthetic-language
transliteration and English translation from the deterministic decoder — SYNTHETIC LANGUAGE, NOT TAMIL-BRAHMI),
the synthetic evidence chain, the reasoning, the ground-truth comparison and the performance figures.

Everything here is labelled SYNTHETIC. Nothing here reads or writes research data, annotations or the
knowledge base, and no real reference is shown in support of a synthetic result.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import streamlit as st
from PIL import Image

from ui import data
from ui.boot import research
from ui.chain import render_chain
from ui.components import badge, blocked_state, dataset_badge, e, kv, note, section
from ui.reading import field_map, reading_results_html
from ui.synthetic3d import render_replay
from ui.viewer import render_viewer

_LOCK = threading.Lock()            # one GPU pipeline shared by every session: runs take turns
MODE_STATEMENT = ("SYNTHETIC DEMONSTRATION MODE — generated images and synthetic models only. "
                  "Synthetic model output — not archaeological evidence.")


def mode_banner() -> None:
    st.html('<section class="etp-synthetic etp-mode-banner" role="note" aria-label="Synthetic demonstration mode">'
            f'{badge("synthetic", "Synthetic demonstration mode")}'
            "<h3>Synthetic demonstration — not archaeological evidence</h3>"
            "<p>Every image here was drawn by the project's generator and every result comes from models trained on "
            "generated data. Nothing on this page is a reading of Tamil-Brahmi, a date or an archaeological finding, "
            "and none of it has been validated on real material.</p></section>")


def _result_banner(a: dict[str, Any]) -> str:
    c = a["classification"]
    rows = [("Synthetic task class", f'{c["display_label"]} ({c["label"]})', True),
            ("Model confidence", f'{c["confidence"]:.0%} · {c["confidence_words"]}', False),
            ("Calibration status", c["calibration_status"], False)]
    return (f'<section class="etp-synthetic" role="note" aria-label="{e(a["statement"])}">{badge("synthetic")}'
            f'<h3>{e(a["statement"])}</h3><p>{e(a["label_warning"])} {e(a["purpose"])}</p>{kv(rows)}</section>')


def _panel(a: dict[str, Any]) -> str:
    c, o, it, ch = a["classification"], a["ocr"], a["interpretation"], a["chronology"]
    regs = a["inscription"]["regions"]
    reading = (f'<div class="v etp-mono">{e(o["transcription"])}</div><div class="who">{e(o["label"])} · '
               f'{o["glyph_count"]} glyph(s) · mean glyph score {o["mean_glyph_score"]:.2f} · {e(o["segmentation"])} segmentation</div>'
               if o["status"] == "read" else f'<div class="v">No synthetic glyph transcription</div><div class="who">{e(o["reason"])}</div>')
    return (
        '<section class="etp-shell" aria-label="Synthetic analysis panel"><div class="etp-core">'
        f'<div class="etp-finding"><div class="k">Synthetic classifier</div><div class="v">{e(c["display_label"])}</div>'
        f'<div class="who">Model confidence {c["confidence"]:.0%} ({e(c["confidence_words"])}) · '
        f'{"calibrated: " + e(c["calibration_status"]) if c["calibrated"] else e(c["calibration_status"])}</div></div>'
        f'<div class="etp-finding"><div class="k">Synthetic inscription region</div><div class="v">'
        + (", ".join(f"R{i + 1} · score {r['confidence']:.2f}" for i, r in enumerate(regs)) or "none detected")
        + f'</div><div class="who">class synthetic_inscription_region · {len(a["inscription"]["rows"])} glyph row(s)</div></div>'
        f'<div class="etp-finding"><div class="k">Synthetic glyph transcription</div>{reading}</div>'
        + _translation(a) + _interpretation(it) +
        f'<div class="etp-finding"><div class="k">Synthetic chronology</div><div class="v">{e(ch["display"])}</div>'
        f'<div class="who">{e(ch["statement"])} Synthetic confidence: {e(ch["confidence"])}.</div></div>'
        "</div></section>")


def _interpretation(it: dict[str, Any]) -> str:
    """Grammatical interpretation (agent / action / object); a field separate from the translation."""
    head = '<div class="etp-finding"><div class="k">Grammatical interpretation · synthetic language, not Tamil-Brahmi</div>'
    if "clauses" not in it:            # a result stored before 2026-10-09 (retired placeholder categories)
        return head + ('<div class="v">Not available for this stored result</div><div class="who">The placeholder '
                       'interpretation categories were retired; run the analysis again.</div></div>')
    rows = "".join(f'<div class="v">Agent: {e(c["agent"])} · Action: {e(c["action"])} · Object: {e(c["object"])}</div>'
                   for c in it["clauses"])
    return head + (rows or f'<div class="v">{e(it["summary"])}</div>') + f'<div class="who">{e(it["statement"])}</div></div>'


def _translation(a: dict[str, Any]) -> str:
    lang = field_map(a.get("reading_results"))
    info = (a.get("reading_results") or {}).get("language") or {}
    if not lang:
        return ""
    return (f'<div class="etp-finding"><div class="k">Synthetic translation · synthetic language, not Tamil-Brahmi</div>'
            f'<div class="v">{e(lang["translation"]["display"])}</div>'
            f'<div class="who">Transliteration: {e(lang["transliteration"]["display"])}</div>'
            f'<div class="who">{e(info.get("status_text", ""))} · {e(info.get("method", ""))}</div></div>')


def _ground_truth(gt: dict[str, Any]) -> str:
    rows = [("True synthetic class", f'{gt["true_label"]} → {"correct" if gt["label_correct"] else "WRONG"}', True),
            ("True glyph sequence", gt["true_transcription"] or "(none)", True),
            ("Predicted glyph sequence", gt["predicted_transcription"] or "(none)", True)]
    if gt["cer"] is not None:
        rows.append(("CER / WER", f'{gt["cer"]} / {gt["wer"]} · edit distance {gt["glyph_edit_distance"]}', True))
    rows += [("Best region IoU", gt["best_region_iou"] if gt["best_region_iou"] is not None else "—", True),
             ("Interpretation", f'{gt["true_interpretation"]} → {"same" if gt["interpretation_correct"] else "different"}', True)]
    if "true_synthetic_translation" in gt:
        rows += [("True synthetic translation", f'{gt["true_synthetic_translation"] or "—"} ({gt["true_synthetic_language_status"]})', False),
                 ("Predicted synthetic translation", f'{gt["predicted_synthetic_translation"] or "—"} → '
                  f'{"correct" if gt["synthetic_translation_correct"] else "WRONG"}', False)]
    return (f'<div class="etp-card" style="padding:.9rem 1.1rem"><div class="etp-eyebrow">Ground-truth check · synthetic benchmark only'
            f'</div><p style="color:var(--text-2);font-size:.88rem">{e(gt["note"])} Errors are shown exactly; nothing is corrected.</p>'
            f"{kv(rows)}</div>")


def _performance(a: dict[str, Any]) -> str:
    p = a["performance"]
    rows = [(f'{s["number"]:02d} {s["title"]}', f'{s["seconds"] * 1000:.1f} ms', True) for s in a["stages"]]
    rows += [("Total (measured)", f'{p["total_seconds"] * 1000:.1f} ms on {p["device"]}', True),
             ("Peak GPU memory", f'{p["peak_gpu_memory_mib"]} MiB' if p["peak_gpu_memory_mib"] is not None else "— (CPU)", True),
             ("CPU", f'{p["cpu_percent_of_one_core"]}% of one core during the run', True)]
    return f'<div class="etp-card" style="padding:.9rem 1.1rem"><div class="etp-eyebrow">Performance of this run</div>{kv(rows)}</div>'


def render_synthetic_demo() -> None:
    mode_banner()
    pipe, error = data.synthetic_pipeline()
    if pipe is None:
        st.html(blocked_state("blocked", "The synthetic models are not available", error or "",
                              ["python -m src.synthetic generate", "python -m src.training train --dataset synthetic",
                               "python -m src.synthetic calibrate", "python -m src.synthetic train-vision"],
                              why="How to create them"))
        return
    images = data.synthetic_images()
    if not images:
        note("No synthetic dataset on this machine. Run <code>python -m src.synthetic generate</code>.")
        return
    by_id = {r["image_id"]: r for r in images}
    ids = sorted(by_id)
    default = data.synthetic_demo_default()
    with st.container(border=True):
        c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
        image_id = c1.selectbox("Generated image (held-out test split)", ids, index=ids.index(default) if default in ids else 0,
                                key="synthetic_image", format_func=lambda i: f"{i}  ·  SYNTHETIC",
                                help="Images the models never saw during training or selection. Reproducible: the default is "
                                     "the first Tamil-Brahmi-like test image.")
        run = c2.button("Run analysis", type="primary", key="run_synthetic", use_container_width=True,
                        help="Runs the complete synthetic pipeline once, live (load → preprocess → classify → detect → "
                             "segment → OCR → interpret → reason).")
        if research():
            prov = pipe.provenance
            st.caption(f"Classifier {prov['classifier']['experiment_id']} · calibration "
                       f"{'T=' + str(prov['classifier']['calibration']['temperature']) if prov['classifier']['calibration'] else 'none'} · "
                       f"vision bundle {prov['vision_bundle']['run_id']} ({prov['vision_bundle']['segmentation']} segmentation) · "
                       f"dataset {prov['dataset_fingerprint'][:12]} · device {prov['device']}")
    rec = by_id[image_id]
    if run:
        with st.status("Running the synthetic pipeline…", expanded=True) as status:
            def on_stage(s: dict[str, Any]) -> None:
                status.write(f"**{s['number']:02d} {s['title'].upper()}** · {s['seconds'] * 1000:.1f} ms — {s['summary']}")

            with _LOCK:
                analysis = pipe.run(rec["path"], record={k: v for k, v in rec.items() if k != "path"}, on_stage=on_stage)
            status.update(label=f"Synthetic analysis complete · {analysis['performance']['total_seconds'] * 1000:.0f} ms measured",
                          state="complete", expanded=False)
        st.session_state["synthetic_result"] = {"image_id": image_id, "analysis": analysis}
    stored = st.session_state.get("synthetic_result")
    if not stored or stored["image_id"] != image_id:
        note("<b>Choose a generated image and press <i>Run analysis</i>.</b> The pipeline runs once, live; each stage shows its "
             "actual result and measured time.")
        return
    a = stored["analysis"]

    st.html(_result_banner(a))
    st.html(f'<div class="etp-title-bar" role="region" aria-label="Synthetic result status"><h2>{e(image_id)}</h2>'
            f'{dataset_badge("synthetic")}{badge("neutral", "model confidence " + format(a["classification"]["confidence"], ".0%"))}'
            f'{badge("neutral", "synthetic benchmark calibration" if a["classification"]["calibrated"] else "uncalibrated")}</div>'
            f'<p class="etp-verdict" style="font-size:clamp(1.15rem,1.8vw,1.5rem);margin:0 0 .8rem">{e(a["summary"])}</p>')

    section("Pipeline replay", "the recorded run · illustrative 3D")
    render_replay(a, height=520)
    st.caption("Left: an illustrative visualization, not a scan of the input image. Right: the eight stages of the recorded "
               "run with their actual results and measured latencies. Pause, Skip, Replay and a 2D view are available.")

    stage_col, panel_col = st.columns([1.4, 1], gap="large")
    with stage_col:
        img = Image.open(Path(rec["path"])).convert("RGB")
        regs = [{"x": r["x"], "y": r["y"], "width": r["width"], "height": r["height"], "source": "synthetic_prediction"}
                for r in a["inscription"]["regions"]]
        render_viewer(img, regs, alt=f"Synthetic generated image {image_id} (not a photograph of a real object)",
                      meta=f"{img.size[0]}×{img.size[1]} px · generated image · synthetic detector regions shown", height=460)
        st.caption("This is a GENERATED synthetic image, not a photograph of any real object. Dotted violet boxes are synthetic "
                   "detector output, never evidence.")
    with panel_col:
        st.html(_panel(a))

    if a.get("reading_results"):
        section("Language / reading results", "synthetic language — not Tamil-Brahmi · transliteration · translation")
        st.html(reading_results_html(a["reading_results"], research=research()))

    section("Synthetic evidence chain", "every node SYNTHETIC · select a step for detail")
    st.html(render_chain(a["evidence_chain"], label="Synthetic evidence chain, from observation to synthetic result",
                         note="Every node is synthetic task evidence produced by synthetic models. No real reference supports it."))

    section("Synthetic reasoning", "every line traces to a pipeline output")
    st.html('<ol style="margin:0;padding-left:1.2rem;color:var(--text-2);line-height:1.7;max-width:100ch">'
            + "".join(f"<li>{e(x)}</li>" for x in a["reasoning"]) + "</ol>")

    g1, g2 = st.columns(2, gap="large")
    with g1:
        if a.get("ground_truth_check"):
            st.html(_ground_truth(a["ground_truth_check"]))
    with g2:
        st.html(_performance(a))
    if research():
        with st.expander("Provenance of this synthetic run (fingerprints)"):
            prov = a["provenance"]
            st.html(kv([("Dataset fingerprint", prov["dataset_fingerprint"], True),
                        ("Synthetic fingerprint", prov["synthetic_fingerprint"], True),
                        ("Split digest", prov["split_digest"], True), ("Generator", prov["generator_version"], True),
                        ("Classifier", f'{prov["classifier"]["experiment_id"]} · {prov["classifier"]["fingerprint"]}', True),
                        ("Vision bundle", prov["vision_bundle"]["run_id"], True),
                        ("OCR crop", prov["vision_bundle"]["ocr_crop"], False)]))
    section("Warnings and limitations")
    st.html('<ul style="margin:0;padding-left:1.2rem;color:var(--text-2);line-height:1.7">'
            f'<li>{e(a["statement"])}</li><li>{e(a["label_warning"])}</li><li>{e(a["chronology"]["statement"])}</li>'
            "<li>This result has no archaeological significance and has not been validated on real material.</li>"
            f'<li>{e(a["purpose"])}</li></ul>')


__all__ = ["MODE_STATEMENT", "mode_banner", "render_synthetic_demo"]
