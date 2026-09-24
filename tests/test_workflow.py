"""The read-only workflow report (src.workflow). Reads the live project; writes nothing."""

from __future__ import annotations

import json

from src.dataset.schema import RESEARCH_RECORDS_PATH
from src.workflow import BLOCKED, PASS, WAITING, main, workflow_status

NAMES = ["raw data", "provenance", "schema", "image hashes", "preprocessing", "annotations",
         "expert agreement", "promotion", "split", "training", "evaluation"]


def test_stages_in_order_and_honest(live_research):
    before = RESEARCH_RECORDS_PATH.stat().st_mtime_ns if RESEARCH_RECORDS_PATH.exists() else None
    ws = workflow_status(decode_images=False)
    assert [s.name for s in ws.stages] == NAMES
    assert all(s.status in (PASS, BLOCKED, WAITING) for s in ws.stages)
    by = {s.name: s for s in ws.stages}
    if live_research["records"]:
        assert by["raw data"].status == PASS and by["provenance"].status == PASS
    if by["training"].status != PASS:
        assert by["evaluation"].status == WAITING
        assert "Evaluation blocked" in by["evaluation"].detail
    if by["annotations"].status == WAITING:
        assert by["annotations"].human_action and "HUMAN" in by["annotations"].next_action
    json.dumps(ws.to_dict())
    after = RESEARCH_RECORDS_PATH.stat().st_mtime_ns if RESEARCH_RECORDS_PATH.exists() else None
    assert before == after


def test_cli(capsys):
    code = main(["status", "--skip-decode"])
    out = capsys.readouterr().out
    assert "DATA WORKFLOW" in out and "CURRENT STAGE" in out
    assert code in (0, 1)
