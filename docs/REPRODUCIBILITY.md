# Reproducibility

```powershell
python -m src.evaluation reproducibility [--json]
```
prints the state any result comes from: git commit and dirty flag; Python, platform, torch,
torchvision, CUDA, cuDNN and key package versions; records SHA-256, dataset and image-set
fingerprints; SHA-256 of `configs/project.yaml` and `configs/training.yaml`, the seed and
determinism setting; the ledger heads of the annotation store, verification registry and
promotion log; and the readiness verdict.

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

GPU training with cuDNN may differ in the last bits between hardware/driver versions even in
deterministic mode; the environment block records what was used.

## To reproduce a (future) experiment

1. `git checkout <commit>`; recreate `.venv` (`scripts/setup.ps1`), matching the recorded torch/CUDA.
2. Obtain the same images; `python -m src.dataset validate data/metadata/records.jsonl --strict --verify-hashes`.
3. Check the dataset fingerprint and split digest match the experiment record in `models/experiments/`.
4. `python -m src.training train --config <recorded config>`.
