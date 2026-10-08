"""Reproducibility report: everything needed to say *exactly* which state a result came from.

    python -m src.evaluation reproducibility [--json]

Captures the code (git commit, dirty flag), the environment (Python, torch, CUDA, cuDNN,
platform, key package versions), the data (records file SHA-256, dataset and image-set
fingerprints), the configuration (SHA-256 of configs/project.yaml and configs/training.yaml,
the seed and determinism setting), the human-evidence stores (ledger chain heads of the
annotation store, verification registry and promotion log) and the readiness verdict.
Reads only.
"""

from __future__ import annotations

import hashlib
from importlib import metadata
from pathlib import Path
from typing import Any

from src.dataset.schema import RESEARCH_RECORDS_PATH, ROOT

PACKAGES = ("numpy", "pillow", "opencv-python", "scikit-learn", "jsonschema", "pyyaml", "streamlit")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "absent"


def _rel(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def reproducibility_report() -> dict[str, Any]:
    from src.annotation.model import ANNOTATIONS_PATH
    from src.annotation.promote import _settings as promotion_settings
    from src.dataset.convert import read_jsonl
    from src.dataset.fingerprint import dataset_fingerprint, image_set_fingerprint
    from src.dataset.readiness import evaluate
    from src.integrity import verify
    from src.knowledge.verification import registry_path
    from src.training.config import TrainingConfig
    from src.training.runtime import environment, git_commit

    records = read_jsonl(RESEARCH_RECORDS_PATH) if RESEARCH_RECORDS_PATH.exists() else []
    versions: dict[str, str | None] = {}
    for pkg in PACKAGES:
        try:
            versions[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            versions[pkg] = None
    cfg = TrainingConfig.load(None)
    readiness = evaluate()
    stores = {}
    for name, path in (("annotations", ANNOTATIONS_PATH), ("verification_registry", registry_path()),
                       ("promotion_log", promotion_settings(None)[0])):
        rep = verify(path)
        stores[name] = {"path": _rel(path), "lines": rep.lines, "ledger_head": rep.head, "status": rep.status}
    return {
        "code": git_commit(),
        "environment": environment() | {"packages": versions},
        "data": {"records_path": _rel(RESEARCH_RECORDS_PATH), "records_sha256": _sha(RESEARCH_RECORDS_PATH),
                 "records": len(records), "artifacts": len({r["artifact_id"] for r in records}),
                 "dataset_fingerprint": dataset_fingerprint(records) if records else None,
                 "image_set_fingerprint": image_set_fingerprint(records) if records else None},
        "configuration": {"project_yaml_sha256": _sha(ROOT / "configs" / "project.yaml"),
                          "training_yaml_sha256": _sha(ROOT / "configs" / "training.yaml"),
                          "seed": cfg.runtime.seed, "deterministic": cfg.runtime.deterministic},
        "human_evidence_stores": stores,
        "readiness": {"training_ready": readiness.training_ready, "reason": readiness.reason},
    }


def render_report(r: dict[str, Any]) -> str:
    L = ["REPRODUCIBILITY REPORT",
         f"  code        commit {r['code']['commit']}  dirty={r['code']['dirty']}",
         "  environment " + ", ".join(f"{k}={v}" for k, v in r["environment"].items() if k != "packages"),
         "  packages    " + ", ".join(f"{k}={v}" for k, v in r["environment"]["packages"].items()),
         f"  data        {r['data']['records']} records / {r['data']['artifacts']} artifacts; records sha256 "
         f"{r['data']['records_sha256'][:16]}; dataset fingerprint {str(r['data']['dataset_fingerprint'])[:16]}",
         f"  config      project.yaml {r['configuration']['project_yaml_sha256'][:16]}; training.yaml "
         f"{r['configuration']['training_yaml_sha256'][:16]}; seed {r['configuration']['seed']}; "
         f"deterministic {r['configuration']['deterministic']}"]
    for name, s in r["human_evidence_stores"].items():
        L.append(f"  {name:<22} {s['status']:<22} lines {s['lines']}  head {s['ledger_head'][:16]}")
    L.append(f"  readiness   training_ready={r['readiness']['training_ready']}  ({r['readiness']['reason']})")
    return "\n".join(L)


__all__ = ["render_report", "reproducibility_report"]
