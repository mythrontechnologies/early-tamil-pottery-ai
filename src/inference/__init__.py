"""The single inference interface: ``analyze(image) -> InferenceResult``.

    from src.inference import analyze
    result = analyze("photo.jpg")                 # or analyze(image_bytes)
    print(result.to_dict()["age"])                # "Insufficient evidence" is a valid answer

Pipeline (every stage replaceable, every output labelled with who asserts it):

    image (path or bytes; size, format, decompression-bomb and truncation checks)
      -> SHA-256 identity: is this a REGISTERED research photograph? (records.jsonl)
      -> image-quality assessment                 technical, uncalibrated, never evidence
      -> inscription regions                      human (annotation store) | user | detector (AI)
      -> enhancement                              viewing aid only
      -> mark analysis, OCR                       AI observation (null engines by default)
      -> script classification                    AI observation (no model until training runs)
      -> reasoning (src.reasoning)                ONLY human evidence: annotations, knowledge base

Human evidence is applied only to a registered photograph: an uploaded image picks up an
artifact's annotations **only if its SHA-256 equals a research record's** ``image_sha256``.
Naming an artifact id does not attach its annotations to an arbitrary picture.

Every result states its ``dataset_type`` (Milestone 9): ``research`` (REAL RESEARCH DATA),
``synthetic`` (SYNTHETIC DEMONSTRATION: the SHA-256 matches the synthetic engineering dataset) or
``unregistered``. A synthetic image receives no human evidence and is classified only by a
synthetic model (``synthetic_classifier``); a research or unregistered image is never shown to one.

The result keeps four layers apart - ``ai_observation``, ``project_annotation``,
``expert_annotation`` and ``verified_evidence`` - and nothing moves between them.
Nothing is written anywhere: no store, no record, no raw file.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from src.annotation.model import ANNOTATIONS_PATH
from src.annotation.store import AnnotationStore
from src.classification import ClassificationResult, NoModelClassifier, ScriptClassifier
from src.dataset.convert import read_jsonl
from src.dataset.schema import RESEARCH_RECORDS_PATH
from src.detection import NO_DETECTOR, NoDetector, Region, RegionDetector, crop, regions_from_annotations
from src.ocr import (
    NO_TRANSCRIPTION,
    MarkAnalyzer,
    NullMarkAnalyzer,
    NullTranscriber,
    Transcriber,
    screen_ocr,
)
from src.preprocessing import DISCLAIMER as QUALITY_DISCLAIMER
from src.preprocessing import PreprocessConfig, apply_exif_orientation, assess, load_image, to_rgb
from src.reasoning.engine import DISCLAIMER, INSUFFICIENT, analyze_artifact
from src.reasoning.from_annotations import build_inputs
from src.reasoning.types import ReasoningInputs
from src.synthetic import MARKER as SYNTHETIC_MARKER
from src.synthetic import PURPOSE as SYNTHETIC_PURPOSE
from src.synthetic import UI_BANNER as SYNTHETIC_BANNER
from src.synthetic.inference import NoSyntheticModel, dataset_block, synthetic_index

RESULT_SCHEMA_VERSION = "1.1.0"
MAX_UPLOAD_BYTES = 50 * 2**20          # 50 MiB; the pixel ceiling is preprocessing.max_pixels
LAYERS = ("ai_observation", "project_annotation", "expert_annotation", "verified_evidence")


class InferenceError(ValueError):
    """The image cannot be analysed (unreadable, unsupported, too large, not a file)."""


@dataclass
class InferenceResult:
    image: dict[str, Any]
    image_quality: dict[str, Any]
    regions: list[dict[str, Any]]
    classification: dict[str, Any]
    script: dict[str, Any]
    transcription: dict[str, Any]
    translation: dict[str, Any]
    age: dict[str, Any]
    period: str
    confidence: dict[str, Any]
    reasoning: list[str]
    evidence: dict[str, Any]
    warnings: list[str]
    layers: dict[str, Any]
    status_statements: list[str]
    summary: str
    dataset_type: str = "unregistered"            # research | synthetic | unregistered
    dataset: dict[str, Any] = field(default_factory=dict)
    synthetic_analysis: dict[str, Any] | None = None   # Milestone 10: synthetic images only (SyntheticPipeline)
    disclaimer: str = DISCLAIMER
    schema_version: str = RESULT_SCHEMA_VERSION
    analysis_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, sort_keys=False)


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def _load(image: Path | str | bytes, max_bytes: int, cfg: PreprocessConfig) -> tuple[Image.Image, dict[str, Any], list[str]]:
    warnings: list[str] = []
    with tempfile.TemporaryDirectory(prefix="etpai_upload_") as tmp:
        if isinstance(image, (bytes, bytearray)):
            data = bytes(image)
            if not data:
                raise InferenceError("empty upload")
            if len(data) > max_bytes:
                raise InferenceError(f"upload is {len(data)} bytes; the limit is {max_bytes}")
            path, name, uploaded = Path(tmp) / "upload.img", "upload", True
            path.write_bytes(data)
        else:
            path = Path(image)
            if not path.is_file():
                raise InferenceError(f"not a regular file: {path}")
            if path.stat().st_size > max_bytes:
                raise InferenceError(f"{path.name} is {path.stat().st_size} bytes; the limit is {max_bytes}")
            name, uploaded = path.name, False
        loaded = load_image(path, supported_formats=set(cfg.supported_formats),
                            min_dimension_px=cfg.min_dimension_px, max_pixels=cfg.max_pixels)
        if not loaded.ok or loaded.image is None:
            raise InferenceError("image rejected: " + "; ".join(str(i) for i in loaded.errors))
        for w in loaded.warnings:
            if uploaded and w.code == "P7":          # an upload has no meaningful extension
                continue
            warnings.append(f"Image: {w}")
        rgb = to_rgb(apply_exif_orientation(loaded.image), alpha_background=cfg.alpha_background)
        facts = {"name": name, "sha256": loaded.sha256, "format": loaded.detected_format,
                 "width_px": rgb.size[0], "height_px": rgb.size[1],
                 "file_size_bytes": loaded.file_size_bytes, "uploaded": uploaded}
        return rgb.copy(), facts, warnings


# --------------------------------------------------------------------------- #
# Layers
# --------------------------------------------------------------------------- #


def _annotation_summary(a: dict[str, Any]) -> dict[str, Any]:
    ins, it, d = a["inscription"], a["interpretation"], a["dating"]
    return {"annotation_id": a["annotation_id"], "annotator": a["annotator"]["annotator_id"],
            "qualification": a["annotator"].get("qualification"), "review_state": a["review_state"],
            "object_status": a["object"].get("object_status", "unknown"),
            "inscription_present": ins["inscription_present"], "script_type": ins["script_type"],
            "script_confidence": ins["script_confidence"], "reading": ins["reading"],
            "alternative_readings": ins.get("alternative_readings", []),
            "translation": it["translation"], "interpretation_type": it["interpretation_type"],
            "dating_range": [d["estimated_start_year"], d["estimated_end_year"]],
            "dating_basis": d["dating_basis"], "created_utc": a["created_utc"]}


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


# --------------------------------------------------------------------------- #
# analyze()
# --------------------------------------------------------------------------- #


def analyze(
    image: Path | str | bytes,
    *,
    artifact_id: str | None = None,
    regions: list[Region] | tuple[Region, ...] = (),
    classifier: ScriptClassifier | None = None,
    detector: RegionDetector | None = None,
    mark_analyzer: MarkAnalyzer | None = None,
    transcriber: Transcriber | None = None,
    store: AnnotationStore | None = None,
    records: list[dict[str, Any]] | None = None,
    max_bytes: int = MAX_UPLOAD_BYTES,
    config: dict[str, Any] | None = None,
    synthetic_classifier: ScriptClassifier | None = None,
    synthetic_records: dict[str, dict[str, Any]] | None = None,
    synthetic_pipeline: Any | None = None,
) -> InferenceResult:
    """Analyse one photograph. Raises InferenceError only when the image itself is unusable;
    otherwise always returns a result, which may well be "Insufficient evidence"."""
    cfg = PreprocessConfig.from_config(config)
    rgb, facts, warnings = _load(image, max_bytes, cfg)
    classifier = classifier or NoModelClassifier()
    detector = detector or NoDetector()
    mark_analyzer = mark_analyzer or NullMarkAnalyzer()
    transcriber = transcriber or NullTranscriber()
    store = store or AnnotationStore(ANNOTATIONS_PATH)
    if records is None:
        records = read_jsonl(RESEARCH_RECORDS_PATH) if RESEARCH_RECORDS_PATH.exists() else []

    # -- identity: registered research photograph? -------------------------------------
    matches = [r for r in records if r.get("image_sha256") == facts["sha256"]]
    rec = matches[0] if matches else None
    if len({r["artifact_id"] for r in matches}) > 1:
        warnings.append("This photograph is recorded under more than one artifact id; no annotations are applied.")
        rec = None
    if rec is not None:
        facts.update(registered=True, artifact_id=rec["artifact_id"], image_id=rec["image_id"],
                     source=rec.get("source_reference"), license=rec.get("license"),
                     attribution=rec.get("rights_notes"))
        from src.annotation.pilot import load_review_flags

        for f in load_review_flags(config).get(rec["artifact_id"], []):
            warnings.append(f"{f.label} ({f.kind}; related: {f.related_artifact or '-'}; "
                            f"{'confirmed' if f.confirmed else 'unconfirmed'}).")
        if artifact_id and artifact_id != rec["artifact_id"]:
            warnings.append(f"Requested artifact {artifact_id!r}, but this photograph is registered as "
                            f"{rec['artifact_id']!r}; the registered identity is used.")
    syn = None if rec is not None else (synthetic_index() if synthetic_records is None
                                        else synthetic_records).get(facts["sha256"])
    if rec is not None:
        dataset_type = "research"
    elif syn is not None:
        dataset_type = "synthetic"
        facts.update(registered=False, artifact_id=None, image_id=None, synthetic=True,
                     synthetic_artifact_id=syn["artifact_id"], synthetic_image_id=syn["image_id"])
        warnings.append(f"{SYNTHETIC_MARKER}. {SYNTHETIC_BANNER}: this image was drawn by the project's synthetic "
                        f"generator ({syn['image_id']}). {SYNTHETIC_PURPOSE}")
        classifier = (synthetic_pipeline.classifier if synthetic_pipeline is not None
                      else synthetic_classifier or NoSyntheticModel())
    else:
        dataset_type = "unregistered"
        facts.update(registered=False, artifact_id=None, image_id=None)
        warnings.append("Unregistered image: it matches no research record by SHA-256, so it has no provenance "
                        "and no human annotation is applied to it.")
        if artifact_id:
            warnings.append(f"This image is not a registered photograph of {artifact_id!r}; that artifact's "
                            "annotations are NOT applied to it.")

    # -- quality -----------------------------------------------------------------------
    q = assess(rgb, file_size_bytes=facts["file_size_bytes"], detected_format=facts["format"],
               thresholds=cfg.quality_thresholds)
    quality = asdict(q) | {"note": QUALITY_DISCLAIMER}
    if q.flags:
        warnings.append("Technical image-quality flags (uncalibrated; they describe the photograph, not the object): "
                        + ", ".join(q.flags))

    # -- regions -----------------------------------------------------------------------
    current = store.current(rec["artifact_id"]) if rec else []
    human_regions = regions_from_annotations(current, rec["image_id"]) if rec else []
    user_regions = [r for r in regions if r.source == "user_supplied"]
    ai_regions = detector.detect(rgb)
    synthetic_analysis = None
    if syn is not None and synthetic_pipeline is not None:     # synthetic images only, never a real photograph
        synthetic_analysis = synthetic_pipeline.run(rgb, record=syn)
        ai_regions = [*ai_regions, *(Region(r["x"], r["y"], min(r["width"], 1 - r["x"]), min(r["height"], 1 - r["y"]),
                                            "ai_prediction", label="synthetic_inscription_region",
                                            note=f"{SYNTHETIC_MARKER} · score {r['confidence']:.2f}")
                                     for r in synthetic_analysis["inscription"]["regions"])]
    all_regions = [*human_regions, *user_regions, *ai_regions]

    # -- AI stages ---------------------------------------------------------------------
    classification: ClassificationResult = classifier.classify(rgb)
    targets = all_regions or [None]
    ocr_rows, marks_rows = [], []
    for reg in targets:
        view = crop(rgb, reg) if reg is not None else rgb
        where = reg.to_dict() if reg is not None else {"whole_image": True}
        marks_rows.append({"region": where, **mark_analyzer.analyze(view).to_dict()})
        ocr_rows.append({"region": where, **screen_ocr(transcriber.transcribe(view)).to_dict()})

    ai_preds: list[dict[str, Any]] = []
    if classification.status == "predicted":
        ai_preds.append({"stage": "script_classification", "label": classification.label,
                         "probabilities": classification.probabilities, "model": classification.model})
    for row in ocr_rows:
        if row["status"] == "candidate":
            ai_preds.append({"stage": "ocr", "candidate_text": row["text"], "engine": row["engine"],
                             "engine_score": row["confidence"], "region": row["region"]})
    for reg in ai_regions:
        ai_preds.append({"stage": "region_detection", "region": reg.to_dict()})

    # -- reasoning on HUMAN evidence only -----------------------------------------------
    if rec is not None:
        inputs = build_inputs(rec["artifact_id"], store=store, records=records)
    elif syn is not None:
        inputs = ReasoningInputs(artifact_id=f"synthetic_image:{syn['image_id']}")
    else:
        inputs = ReasoningInputs(artifact_id=f"unregistered_image:{facts['sha256'][:12]}")
    inputs.ai_predictions = tuple(inputs.ai_predictions) + tuple(ai_preds)
    r = analyze_artifact(inputs, config=config)

    # -- layers --------------------------------------------------------------------------
    by_tier: dict[str, list[dict[str, Any]]] = {"project_annotation": [], "expert_annotation": [],
                                                "source_information": []}
    for a in current:
        if a["provenance_type"] in by_tier:
            by_tier[a["provenance_type"]].append(_annotation_summary(a))
    verified = [{"ref_id": ref.ref_id, "citation": ref.citation, "verified_claims": list(ref.verified_claims)}
                for ref in inputs.references.values() if ref.verification_status == "verified_against_source"]
    layers = {
        "ai_observation": {
            "label": "AI observation - not archaeological evidence",
            "classification": classification.to_dict(),
            "region_detection": {"detector": detector.name, "regions": [x.to_dict() for x in ai_regions],
                                 "statement": getattr(detector, "statement", "") or NO_DETECTOR},
            "mark_analysis": marks_rows, "ocr": ocr_rows,
            "image_quality_flags": q.flags,
        },
        "project_annotation": {"label": "Project annotation - not expert-reviewed", "annotations": by_tier["project_annotation"]},
        "expert_annotation": {"label": "Expert annotation", "annotations": by_tier["expert_annotation"]},
        "verified_evidence": {"label": "Verified archaeological evidence (a named human checked the source)",
                              "references": verified,
                              "statement": "None: no reference has been verified against its source." if not verified else ""},
        "source_information": {"label": "Transcribed from a published source", "annotations": by_tier["source_information"]},
    }

    human_reading = r.reading
    has_reading = human_reading.get("value") not in ("not_available", "not_applicable", "unknown", None, "")
    transcription = {
        "statement": (f"{human_reading['value']} ({human_reading['provenance_label']})" if has_reading
                      else NO_TRANSCRIPTION),
        "human_reading": human_reading,
        "ocr": ocr_rows,
        "note": "OCR output is an AI observation and is never used as a reading.",
    }
    summary = (INSUFFICIENT if INSUFFICIENT in r.status_statements else
               "; ".join(r.status_statements) or "See the sections below.")
    if dataset_type == "synthetic":
        summary = f"{SYNTHETIC_BANNER}. {summary}"
    warnings = list(dict.fromkeys([*warnings, *r.limitations]))
    if classification.status != "predicted":
        warnings.append(classification.statement)

    result = InferenceResult(
        image=facts,
        image_quality=quality,
        regions=[x.to_dict() for x in all_regions],
        classification={"human": r.script, "ai_observation": classification.to_dict()},
        script=r.script,
        transcription=transcription,
        translation=r.interpretation,
        age=r.age | {"dating_summary": r.dating_summary},
        period=r.period_estimate,
        confidence={"archaeological": r.confidence,
                    "note": ("Archaeological confidence comes from the recorded evidence and its verification "
                             "status. A model probability is not an archaeological confidence."),
                    "ai_model_probabilities": classification.probabilities},
        reasoning=r.reasoning,
        evidence={"dating_evidence": r.evidence, "identification": r.identification,
                  "references": {k: asdict(v) for k, v in inputs.references.items()},
                  "inputs_digest": r.inputs_digest},
        warnings=warnings,
        layers=layers,
        status_statements=r.status_statements,
        summary=summary,
        dataset_type=dataset_type,
        dataset=dataset_block(dataset_type, syn),
        synthetic_analysis=synthetic_analysis,
    )
    result.analysis_digest = _digest({k: v for k, v in result.to_dict().items() if k != "analysis_digest"})
    return result


def render(result: InferenceResult) -> str:
    """Plain-text report for the CLI. Every line comes from the result."""
    d = result.to_dict()
    img, q = d["image"], d["image_quality"]
    L = [f"DATASET      {d['dataset']['indicator']}: {d['dataset']['statement']}",
         f"IMAGE        {img['name']}  sha256 {img['sha256'][:16]}  {img['width_px']}x{img['height_px']} {img['format']}",
         f"REGISTERED   {'yes: ' + img['artifact_id'] + ' / ' + img['image_id'] if img['registered'] else 'no (no provenance; no annotations applied)'}",
         f"SUMMARY      {d['summary']}", ""]
    L += ["IMAGE QUALITY (technical, uncalibrated; not archaeological)",
          f"  sharpness {q['sharpness_laplacian_var']}  brightness {q['brightness_mean']}  contrast {q['contrast_std']}"
          f"  flags: {', '.join(q['flags']) or 'none'}", ""]
    L += ["SCRIPT (human evidence)", f"  {d['script'].get('statement')}",
          "CLASSIFICATION (AI observation, not evidence)", f"  {d['classification']['ai_observation']['statement']}", "",
          "TRANSCRIPTION", f"  {d['transcription']['statement']}",
          *[f"  OCR [{o['status']}] {o['statement']}" for o in d["transcription"]["ocr"]], "",
          "TRANSLATION", f"  {d['translation']['translation'] if d['translation']['state'] == 'translated' else d['translation']['meaning']}", "",
          "ESTIMATED AGE", f"  {d['age']['display']}", "PERIOD", f"  {d['period']}", "",
          "CONFIDENCE (archaeological)", f"  {d['confidence']['archaeological']}", "",
          "REASONING"] + [f"  - {x}" for x in d["reasoning"]]
    L += ["", "EVIDENCE LAYERS"]
    for name in LAYERS:
        layer = d["layers"][name]
        n = len(layer.get("annotations", layer.get("references", [])) or []) if name != "ai_observation" else None
        L.append(f"  {layer['label']}" + (f": {n} item(s)" if n is not None else ""))
    L += ["", "WARNINGS"] + [f"  - {w}" for w in d["warnings"]] + ["", d["disclaimer"]]
    return "\n".join(L)


__all__ = ["LAYERS", "MAX_UPLOAD_BYTES", "RESULT_SCHEMA_VERSION", "InferenceError", "InferenceResult",
           "analyze", "render"]
