# User Guide

## Start

```powershell
.\scripts\setup.ps1                 # once: .venv + dependencies (add -Cpu for CPU-only)
.\scripts\start_app.ps1             # http://localhost:8501
```
Linux/macOS: `scripts/setup.sh [--cpu]`, then `scripts/start_app.sh`.

The app has two pages.

## 1. Analyse a photograph

Upload a JPEG/PNG/TIFF/WebP/BMP, or choose a registered research photograph.

| Section | What it shows | Who asserts it |
|---|---|---|
| Summary | the headline: often **Insufficient evidence** | derived from the sections below |
| Image and regions | preview; green = human-marked, blue = yours, amber = AI | as coloured |
| Image quality | sharpness, brightness, contrast, clipping, flags | technical measurement, never evidence |
| Classification / script | the script as recorded by a human, with who said it | human annotation |
| Transcription | the human reading, or "No reliable transcription established." | human annotation |
| Translation | only with a source; "Proper name; no literal translation established." for names | human source |
| Estimated age / Period | an evidence-based range, an outer bound, or "Insufficient evidence" | dating evidence |
| Confidence | archaeological confidence from evidence and its verification status | rules, not scores |
| Reasoning | every step, traceable to an input | reasoning engine |
| Evidence layers | expert, project and verified evidence in separate panels | as labelled |
| AI observation | classifier, detector, mark analysis, OCR (amber banner) | **AI, not evidence** |
| Warnings | provenance, review flags, unverified references, disagreements | |

**An uploaded image that is not a registered research photograph** (no SHA-256 match) gets
no annotations, even if you type an artifact id. It will usually be "Insufficient evidence".
That is correct: the project knows nothing about it.

"Your regions" (`x,y,w,h`, fractions of width/height) help you look; they are not evidence.

## 2. Annotate

See [`ANNOTATION_GUIDE.md`](ANNOTATION_GUIDE.md) and the one-page
[`PILOT_ANNOTATION_CHECKLIST.md`](PILOT_ANNOTATION_CHECKLIST.md). Choose *Project annotator*
or *Expert*, enter your id, answer only what the photograph supports, and save. Saving
appends; nothing is overwritten.

## Command line

```powershell
python -m src.inference analyze photo.jpg [--json]      # the same analysis as the page
python -m src.workflow status                          # where the project is, and the next step
python -m src.annotation integrity                     # are the append-only stores intact?
python -m src.knowledge entries                        # every sourced claim and its status
```
