"""The end-to-end data workflow, checked stage by stage (read-only).

    python -m src.workflow status [--json] [--skip-decode]

When real, expert-labelled data arrives, it moves through these stages IN ORDER. Each stage
is checked with the project's own validators and reported as PASS, BLOCKED (something is
wrong or missing and later stages must wait) or WAITING (nothing wrong; it needs human input
or data). The first stage that is not PASS is where work continues, and the report prints
the exact command for it.

    1 raw data            records + image files present
    2 provenance          every record acquired with a provenance record; SHA-256 agrees
    3 schema              strict metadata validation (E*/R* rules)
    4 image hashes        every file's SHA-256 equals its record
    5 preprocessing       every image decodes under the guarded loader
    6 annotations         the store validates (N1-N16) and its ledger is intact
    7 expert agreement    both pilot tiers present; agreement measurable
    8 promotion           expert labels ready to promote (dry run)
    9 split               verified artifact-level split manifest (G11)
   10 training            readiness gate G1-G11
   11 evaluation          a trained experiment exists to evaluate

Nothing here writes, trains, promotes or relaxes a gate.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from src.console import utf8_console

PASS, BLOCKED, WAITING = "PASS", "BLOCKED", "WAITING"


@dataclass
class Stage:
    number: int
    name: str
    status: str
    detail: str
    next_action: str = ""
    human_action: bool = False


@dataclass
class WorkflowStatus:
    stages: list[Stage] = field(default_factory=list)

    @property
    def current(self) -> Stage | None:
        return next((s for s in self.stages if s.status != PASS), None)

    def to_dict(self) -> dict[str, Any]:
        cur = self.current
        return {"stages": [asdict(s) for s in self.stages],
                "current_stage": asdict(cur) if cur else None}


def workflow_status(*, decode_images: bool = True) -> WorkflowStatus:
    from src.acquisition.provenance import read_registry
    from src.annotation.agreement import compute_agreement
    from src.annotation.pilot import load_pilot, pilot_status
    from src.annotation.promote import plan_promotion
    from src.annotation.store import AnnotationStore
    from src.dataset.convert import read_jsonl
    from src.dataset.readiness import evaluate
    from src.dataset.schema import RESEARCH_DATA_ROOT, RESEARCH_RECORDS_PATH, ROOT
    from src.dataset.validation import validate_records
    from src.preprocessing import load_image

    ws = WorkflowStatus()

    def add(*a: Any, **k: Any) -> Stage:
        s = Stage(len(ws.stages) + 1, *a, **k)
        ws.stages.append(s)
        return s

    records = read_jsonl(RESEARCH_RECORDS_PATH) if RESEARCH_RECORDS_PATH.exists() else []
    present = [r for r in records if (RESEARCH_DATA_ROOT / r["image_path"]).is_file()]
    add("raw data", PASS if records and len(present) == len(records) else BLOCKED,
        f"{len(records)} record(s), {len(present)} image file(s) present, "
        f"{len({r['artifact_id'] for r in records})} artifact(s)",
        "python -m src.acquisition plan <plan.yaml> (dry run), then --commit" if not records else
        "restore the missing image files under data/raw/" if len(present) != len(records) else "")

    reg = {p["image_id"]: p for p in read_registry()}
    missing = [r["image_id"] for r in records if r["image_id"] not in reg]
    mismatch = [r["image_id"] for r in records if r["image_id"] in reg
                and reg[r["image_id"]].get("image_sha256") not in (None, r.get("image_sha256"))]
    add("provenance", PASS if records and not missing and not mismatch else BLOCKED,
        f"{len(records) - len(missing)}/{len(records)} with a provenance record; {len(mismatch)} SHA-256 mismatch(es)",
        "python -m src.acquisition registry" if missing or mismatch else "")

    strict = validate_records(records, data_root=RESEARCH_DATA_ROOT, strict=True)
    add("schema", PASS if records and strict.ok else BLOCKED,
        f"strict validation {strict.status}: {len(strict.errors)} error(s), {len(strict.warnings)} warning(s)",
        "python -m src.dataset validate data/metadata/records.jsonl --strict" if not strict.ok else "")

    hashed = validate_records(records, data_root=RESEARCH_DATA_ROOT, verify_hashes=True)
    add("image hashes", PASS if records and hashed.ok else BLOCKED,
        f"hash verification {hashed.status}",
        "python -m src.dataset validate data/metadata/records.jsonl --verify-hashes" if not hashed.ok else "")

    if decode_images:
        bad = [r["image_id"] for r in present
               if not load_image(RESEARCH_DATA_ROOT / r["image_path"], compute_hash=False).ok]
        add("preprocessing", PASS if present and not bad else BLOCKED,
            f"{len(present) - len(bad)}/{len(present)} image(s) decode under the guarded loader"
            + (f"; failing: {bad[:5]}" if bad else ""),
            "python -m src.preprocessing inspect <image>" if bad else "")
    else:
        add("preprocessing", PASS, "decode check skipped (--skip-decode)")

    store = AnnotationStore()
    val = store.validate()
    current = store.current()
    humans = [a for a in current if a["provenance_type"] != "ai_prediction"]
    add("annotations", BLOCKED if not val.ok else (PASS if humans else WAITING),
        f"{len(current)} current annotation(s), {len(humans)} human; validation {val.status}"
        + (": " + "; ".join(map(str, val.problems[:3])) if val.problems else ""),
        "python -m src.annotation validate" if not val.ok else
        "HUMAN: annotate in `streamlit run app/annotate.py` (docs/PILOT_ANNOTATION_CHECKLIST.md)",
        human_action=val.ok and not humans)

    pilot = load_pilot()
    ps = pilot_status(current, {r["artifact_id"] for r in records}, pilot)
    agr = compute_agreement(current, pilot.artifacts)
    add("expert agreement", PASS if ps.complete == len(ps.artifacts) and agr.artifacts_paired else WAITING,
        f"pilot {ps.complete}/{len(ps.artifacts)} complete; {len(agr.artifacts_paired)} project/expert pair(s)",
        "HUMAN: project annotator AND expert annotate independently; then python -m src.annotation agreement",
        human_action=True)

    plan = plan_promotion(store=store)
    add("promotion", PASS if plan.executable else WAITING,
        f"dry run: {len(plan.candidates)} candidate(s), {len(plan.rejections)} rejected",
        "python -m src.annotation promote --pilot (dry run), then HUMAN approval with --execute --approve <digest>",
        human_action=True)

    rep = evaluate()
    gate = {g["id"]: g for g in rep.gates}
    g11 = gate.get("G11")
    add("split", PASS if g11 and g11.get("passed") else WAITING,
        g11.get("detail", "") if g11 else "not evaluated",
        "python -m src.dataset split (after promotion has produced labels in every class)")

    add("training", PASS if rep.training_ready else WAITING,
        "training_ready=True" if rep.training_ready else f"BLOCKED by the readiness gate: {rep.reason}",
        "python -m src.training train" if rep.training_ready else
        "acquire and expert-label data: >=5 artifacts per class for grouped CV, >=20 for holdout "
        "(docs/NEXT_DATA_ACQUISITION.md)",
        human_action=not rep.training_ready)

    from src.training.config import TrainingConfig

    exp_dir = ROOT / TrainingConfig.load(None).experiments.directory
    experiments = sorted(exp_dir.glob("*.json")) if exp_dir.exists() else []
    add("evaluation", PASS if experiments and rep.training_ready else WAITING,
        f"{len(experiments)} experiment record(s)" if experiments else
        "Evaluation blocked — insufficient expert-labelled archaeological data.",
        "python -m src.evaluation evaluate --checkpoint <best.pt>")
    return ws


def render(ws: WorkflowStatus) -> str:
    L = ["DATA WORKFLOW (read-only; nothing is written, trained or promoted)"]
    for s in ws.stages:
        mark = {"PASS": "[x]", "BLOCKED": "[!]", "WAITING": "[ ]"}[s.status]
        L.append(f"  {mark} {s.number:>2} {s.name:<17} {s.status:<8} {s.detail}")
        if s.status != PASS and s.next_action:
            L.append(f"         -> {s.next_action}")
    cur = ws.current
    L += ["", f"CURRENT STAGE: {cur.number} {cur.name} ({cur.status})" + (" - HUMAN ACTION REQUIRED" if cur.human_action else "")
          if cur else "ALL STAGES PASS"]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    p = argparse.ArgumentParser(prog="python -m src.workflow")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("status", help="check every workflow stage in order")
    s.add_argument("--json", action="store_true")
    s.add_argument("--skip-decode", action="store_true", help="skip decoding every image (faster)")
    args = p.parse_args(argv)
    ws = workflow_status(decode_images=not args.skip_decode)
    print(json.dumps(ws.to_dict(), indent=2, ensure_ascii=False) if args.json else render(ws))
    return 0 if not any(st.status == BLOCKED for st in ws.stages) else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["BLOCKED", "PASS", "WAITING", "Stage", "WorkflowStatus", "main", "render", "workflow_status"]
