# Reproducibility

```powershell
python -m src.evaluation reproducibility [--json]
```
prints the state any result comes from: git commit and dirty flag; Python, platform, torch,
torchvision, CUDA, cuDNN and key package versions; records SHA-256, dataset and image-set
fingerprints; SHA-256 of `configs/project.yaml` and `configs/training.yaml`, the seed and
determinism setting; the ledger heads of the annotation store, verification registry and
promotion log; and the readiness verdict.

## Environment

| | |
|---|---|
| Python | 3.13 (tested on 3.13.7; code targets ≥ 3.10) |
| Exact packages | `requirements-lock.txt` (`pip freeze` of the tested environment); `requirements.txt` holds minimums |
| PyTorch / CUDA | torch 2.14.0 + torchvision 0.29.0, CUDA 12.6 wheels (`scripts/setup.ps1`); CPU wheels with `-Cpu` / `--cpu` |
| GPU | optional. Tested on an NVIDIA RTX 4050 Laptop (6 GiB). A ResNet-18 step at 224 px, batch 16, fp16 peaks at ~383 MiB; the synthetic pipeline at ~69 MiB |
| CPU fallback | `runtime.device: auto` falls back to CPU and records why; an explicit `cuda` request on a machine without CUDA is an error, never a silent fallback. Mixed precision is enabled only on CUDA |
| Checks | `python scripts/check_env.py`, `python -m pytest -q`, `python -m mypy`, `python -m src.synthetic verify` |

## What is deterministic

| Component | How |
|---|---|
| Preprocessing | fixed resampling, letterbox, no randomness; tests compare outputs byte for byte |
| Splits | seeded, artifact-level; manifest digest verified by gate G11 |
| Reasoning | no clock, randomness or network; `inputs_digest` over canonical inputs |
| Inference | `analysis_digest` over the whole result; same image → same digest |
| Training | `seed_everything(seed, deterministic=True)`; seeded workers and sampler; a CPU test reproduces weights bit for bit |
| Checkpoints | `model_fingerprint` (SHA-256 of weights) stored and re-verified on load |
| Human evidence | append-only, ledger-chained; promotion entries record the store's ledger head |
| Synthetic data | `python -m src.synthetic verify` V14 re-renders images from seed + version + config and compares bytes |
| Near-duplicate check, robustness perturbations | deterministic (dHash; perturbations seeded per image id) |
| Reference pre-checks | each consulted document's SHA-256 is recorded in `source_prechecks.json` |

GPU training with cuDNN may differ in the last bits between hardware/driver versions even in
deterministic mode; the environment block records what was used.

## To reproduce a (future) experiment

1. `git checkout <commit>`; recreate `.venv` (`scripts/setup.ps1`), matching the recorded torch/CUDA.
2. Obtain the same images; `python -m src.dataset validate data/metadata/records.jsonl --strict --verify-hashes`.
3. Check the dataset fingerprint and split digest match the experiment record in `models/experiments/`.
4. `python -m src.training train --config <recorded config>`.

## Synthetic demonstration (Milestone 10)

All of it is regenerated from the repository; nothing generated is committed (`data/synthetic/`
and `models/` are git-ignored).

```powershell
python -m src.synthetic generate                    # deterministic: fingerprint d61e25c6…14240
python -m src.training train --dataset synthetic    # ResNet-18 (seed in configs/synthetic_training.yaml)
python -m src.synthetic calibrate                   # temperature on the synthetic val split
python -m src.synthetic train-vision                # RegionNet, GlyphCenterNet, GlyphNet (seed 20261003)
python -m src.synthetic demo                        # writes models/synthetic/runs/demo_*.json
python -m src.evaluation synthetic                  # writes models/synthetic/reports/benchmark/*.json
```

Every record written (calibration, vision manifest, demo run, benchmark report) holds the dataset
fingerprint, split digest, model fingerprints, git commit and dirty flag, and the environment
block. Post-processing choices (region threshold 0.7 and erosion 1, the OCR crop policy, the
segmentation strategy) were selected on the **validation** split and recorded; the test split
was only scored. GPU timings vary with hardware and are reported, not reproduced.
