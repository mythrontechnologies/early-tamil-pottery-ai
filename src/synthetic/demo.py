"""``python -m src.synthetic demo``: the complete synthetic pipeline on one held-out image.

    SYNTHETIC DEMONSTRATION — no archaeological significance.

The demo image is reproducible: by default the first ``synthetic_tamil_brahmi_like`` image of the TEST
split (sorted by id), so every stage, including OCR, has something to do. Any other test-split image
can be chosen with ``--image-id``. Every run is recorded under ``models/synthetic/runs/`` with the
dataset, model and calibration fingerprints, the generator version, configuration digest, seed, git
commit, environment, timings and the ground-truth comparison.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import MARKER, PURPOSE, SYNTHETIC_MODELS_ROOT, assert_synthetic_model_destination
from .dataset import SyntheticDatasetError, SyntheticPaths, find_manifest, load_synthetic_dataset
from .pipeline import STATEMENT, SyntheticPipeline

RUNS_DIR = SYNTHETIC_MODELS_ROOT / "runs"
DEMO_CLASS = "synthetic_tamil_brahmi_like"


def demo_images(root: Path | str | None = None) -> list[Any]:
    """Held-out (test-split) synthetic images, sorted by id."""
    paths = SyntheticPaths.at(root)
    ds = load_synthetic_dataset(paths.root, verify_hashes=False)
    if ds.is_empty:
        raise SyntheticDatasetError("no synthetic dataset; run `python -m src.synthetic generate`")
    test = find_manifest(ds, paths.root).artifacts_in("test")
    return sorted((r for r in ds.records if r.artifact_id in test), key=lambda r: r.image_id)


def default_demo_image(root: Path | str | None = None) -> Any:
    images = demo_images(root)
    return next((r for r in images if r.script_type == DEMO_CLASS), images[0])


def run_demo(*, image_id: str | None = None, root: Path | str | None = None, device: str = "auto",
             record: bool = True, pipeline: SyntheticPipeline | None = None) -> dict[str, Any]:
    images = demo_images(root)
    if image_id:
        chosen = next((r for r in images if r.image_id == image_id), None)
        if chosen is None:
            raise SyntheticDatasetError(f"{image_id!r} is not a test-split synthetic image")
    else:
        chosen = next((r for r in images if r.script_type == DEMO_CLASS), images[0])
    pipe = pipeline or SyntheticPipeline(device=device)
    pipe.run(chosen.image_path, record=dict(chosen.record))           # warm-up: kernels, caches
    analysis = pipe.run(chosen.image_path, record=dict(chosen.record))
    analysis["demo"] = {"image_id": chosen.image_id, "image_path": str(chosen.image_path),
                        "selection": "explicit" if image_id else f"first {DEMO_CLASS} image of the test split",
                        "timing_note": "second run after one warm-up run"}
    if record:
        analysis["run_record"] = str(write_run_record(analysis))
    return analysis


def write_run_record(analysis: dict[str, Any]) -> Path:
    from src.training.runtime import environment, git_commit

    from .config import SyntheticDatasetConfig

    now = datetime.now(timezone.utc)
    cfg = SyntheticDatasetConfig.load()
    prov = analysis["provenance"]
    run = {"run_id": f"demo_{now.strftime('%Y%m%dT%H%M%SZ')}_{analysis['input']['image_id']}", "marker": MARKER,
           "dataset_type": "synthetic", "created_utc": now.isoformat(timespec="seconds"), "git": git_commit(),
           "environment": environment(), "seed": cfg.seed, "generator_version": prov.get("generator_version"),
           "dataset_config_digest": cfg.digest, "dataset_fingerprint": prov["dataset_fingerprint"],
           "synthetic_fingerprint": prov.get("synthetic_fingerprint"), "split_digest": prov["split_digest"],
           "models": {"classifier": prov["classifier"], "vision_bundle": prov["vision_bundle"]},
           "input": analysis["input"], "summary": analysis["summary"], "performance": analysis["performance"],
           "ground_truth_check": analysis.get("ground_truth_check"), "reading_results": analysis.get("reading_results"),
           "synthetic_language": analysis.get("synthetic_language"),
           "warning": analysis["warning"]}
    out = RUNS_DIR / f"{run['run_id']}.json"
    assert_synthetic_model_destination(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return out


def render_demo(a: dict[str, Any]) -> str:
    c, o, it, ch, perf = a["classification"], a["ocr"], a["interpretation"], a["chronology"], a["performance"]
    regions = a["inscription"]["regions"]
    L = ["#" * 72, "#  SYNTHETIC DEMONSTRATION", f"#  {STATEMENT}", "#" * 72, "",
         f"Input:                         synthetic image {a['input']['image_id']} (artifact {a['input']['artifact_id']})",
         f"Classification:                {c['label']}  [{c['display_label']}]",
         f"Model confidence:              {c['confidence']:.2f} ({c['confidence_words']})",
         f"Calibration status:            {c['calibration_status']}",
         "Inscription region:            " + (", ".join(f"R{i + 1} ({r['confidence']:.2f})" for i, r in enumerate(regions)) or "none"),
         f"Synthetic glyph transcription: {o['transcription'] or '(none)'}",
         f"Synthetic interpretation:      {it['category']} (invented rule table: a placeholder, not a meaning)",
         f"Synthetic chronology:          {ch['display']} (synthetic confidence {ch['confidence']})", ""]
    if a.get("synthetic_language"):
        from .__main__ import render_language

        L += [render_language(a["synthetic_language"]), ""]
    rr = a.get("reading_results")
    if rr:
        L += ["Language / reading results (SYNTHETIC DEMONSTRATION — not archaeological evidence):"]
        L += [f"  {f['label'] + ':':<29}{f['display']}" for f in rr["fields"]]
        L.append("")
    L.append("Reasoning:")
    L += [f"  - {line}" for line in a["reasoning"]]
    gt = a.get("ground_truth_check")
    if gt:
        L += ["", "Ground-truth check (synthetic benchmark only):",
              f"  true class {gt['true_label']} -> {'correct' if gt['label_correct'] else 'WRONG'}",
              f"  true transcription  {gt['true_transcription'] or '(none)'}",
              f"  predicted           {gt['predicted_transcription'] or '(none)'}"
              + (f"   CER {gt['cer']}  WER {gt['wer']}" if gt["cer"] is not None else ""),
              f"  best region IoU {gt['best_region_iou']}   interpretation {'correct' if gt['interpretation_correct'] else 'different'}"]
        if "true_synthetic_translation" in gt:
            L += [f"  synthetic translation: true {gt['true_synthetic_translation']!r} ({gt['true_synthetic_language_status']})"
                  f" -> predicted {gt['predicted_synthetic_translation']!r} "
                  f"{'correct' if gt['synthetic_translation_correct'] else 'WRONG'}"]
    L += ["", "Stages:"] + [f"  {s['number']:02d} {s['title'].upper():<11} {s['seconds'] * 1000:8.1f} ms  {s['summary']}"
                            for s in a["stages"]]
    L += [f"  total {perf['total_seconds'] * 1000:.1f} ms on {perf['device']}; peak GPU memory "
          f"{perf['peak_gpu_memory_mib']} MiB; CPU {perf['cpu_percent_of_one_core']}% of one core", "",
          "Warning: This result has no archaeological significance and has not been validated on real material.",
          PURPOSE]
    if a.get("run_record"):
        L.append(f"run record: {a['run_record']}")
    return "\n".join(L)


__all__ = ["DEMO_CLASS", "RUNS_DIR", "default_demo_image", "demo_images", "render_demo", "run_demo", "write_run_record"]
