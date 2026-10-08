# Troubleshooting

| Symptom | Cause | What to do |
|---|---|---|
| `python -m src.training train` exits 3, "Training blocked" | the readiness gate (G1-G11) fails: no expert labels yet | expected. `python -m src.workflow status` shows the next human step |
| `evaluate`, `detection`, `ocr` print `NO REAL DATA — EVALUATION BLOCKED` | no expert-promoted labels / regions / readings | expected; nothing to score against |
| The Analysis page says "Insufficient evidence" | the photograph has no expert annotation, or is not a registered research photograph | expected; upload alone never creates evidence |
| `src.inference synthetic --image …` exits 3 | the image is not in the synthetic dataset (a real photograph is never given to a synthetic model) | use an image from `data/synthetic/images/` |
| Synthetic Demonstration shows no images / no model | the synthetic dataset or models are not generated (git-ignored) | `python -m src.synthetic generate`, `python -m src.training train --dataset synthetic`, `python -m src.synthetic calibrate`, `python -m src.synthetic train-vision` |
| `python -m src.dataset split` refuses | too few labelled artifacts per class, inconsistent labels, or **near-duplicate photographs across artifacts** | add labels; or merge the artifacts / list them in `split.near_duplicate_exceptions` with a reason (`python -m src.dataset near-duplicates`) |
| Annotation not saved: `N1 …`, `N6 …`, `N18 …` | the record breaks an annotation rule (`python -m src.annotation rules`) | fix the field named in the message; `uncertain` and `unknown` are always allowed |
| `import-worksheet` says REJECTED | one row is invalid; the import is all-or-nothing | fix the listed rows; re-run without `--commit` until it says the records are valid |
| `import-worksheet`: "already has annotation … use --revise" | the annotator already annotated that artifact | add `--revise`; the earlier record is kept and superseded |
| `N16` / `V10` integrity failure | an append-only store or its ledger was edited by hand | restore the file from git; never edit `annotations.jsonl`, the verification registry or the promotion log by hand |
| `handoff` cannot write the worksheets | the CSV is open in Excel (Windows locks it) | close it and re-run |
| `verify-from-precheck` refused | the `--i-opened-the-source` attestation is missing, or the pre-check source is a catalogue record | open the copy at the page shown and confirm; R1 needs a library copy |
| `torch.cuda.is_available()` is False | CPU wheel installed, or driver / CUDA mismatch | `scripts\setup.ps1` (or `-Cpu`); everything runs on CPU, more slowly |
| Streamlit page blank, or `ModuleNotFoundError: src` | started from the wrong directory | run from the repository root: `streamlit run app/main.py` |
| Browser tests skipped | `playwright-cli` or the synthetic dataset is missing | `npm install -g @playwright/cli`; generate the synthetic dataset; `python -m pytest -m browser` |
| `python -m mypy` / ruff not found | dev dependencies not installed | `pip install -r requirements-dev.txt` |
| Unicode errors in a Windows console | legacy code page | the CLIs reconfigure stdout to UTF-8; otherwise `set PYTHONIOENCODING=utf-8` |
