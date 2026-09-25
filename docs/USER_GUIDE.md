# User Guide

## Start

```powershell
.\scripts\setup.ps1                 # once: .venv + dependencies (add -Cpu for CPU-only)
.\scripts\start_app.ps1             # http://localhost:8501
```
Linux/macOS: `scripts/setup.sh [--cpu]`, then `scripts/start_app.sh`.

## The application

Seven pages in the top navigation:

| Page | What it is for |
|---|---|
| Overview | what the system is, live headline numbers, how it reasons; an interactive 3D sherd labelled **Illustrative 3D visualization — not an archaeological artifact** (drawn by the interface from abstract texture; not a model of any real object; carries no inscription) |
| Analysis | inspection workstation: the photograph (2D, authoritative) or a labelled 2.5D inspection view, a findings panel, and the **evidence chain** from observation to reference |
| Annotation | the annotation lab: inspection stage (photograph, overlays, region marking) beside the unchanged form (Object · Inscription · Meaning · Dating · Evidence · Review), provenance and revision history below |
| Dataset | the collection as museum plinths; **Inspect** opens the Artifact Inspector (source, licence, annotation, expert and training state); training readiness against the unchanged gate |
| Evidence | references and claims with their verification state: verified / transcribed / bibliographic / **unresolved** |
| Workflow | the eleven stages from `python -m src.workflow status` as a journey; stages after the current one read **not yet reached**; each stage expands to its detail and next action |
| About | purpose, limits, visual language, keyboard shortcuts, modes and 2D alternatives |

**Photograph viewer** (Analysis and Annotation): wheel or `+`/`-` to zoom, drag or arrow keys to
pan, `0` to fit, `G` graticule, `R` regions, `F` fullscreen, *Compare* for a split view against a
contrast-enhanced copy (a viewing aid, not evidence). The readout shows normalised and
original-pixel coordinates. Region outlines differ by pattern and label: human-marked (solid),
yours (dashed), AI proposal (dotted).

**Command palette:** `Ctrl + K` (`⌘ K`), or the *Commands* button, opens a searchable list:
analyse, dataset, annotation lab, evidence, workflow, about, search an artifact (opens its
inspector), switch mode, reduce motion, reset interface. Arrow keys, Enter and Esc work.

**Research and Presentation modes** (switch at the top right of each page, or `?mode=`).
Research shows hashes, paths, gate detail and verification tables; Presentation hides that
detail. AI warnings, labels and limitations stay in both.

**3D and 2.5D views.** Drag to orbit, wheel or pinch to zoom, right-drag or two fingers to pan;
arrow keys orbit, `+`/`-` zoom, `0` resets, `Space` pauses auto-rotate, `C` focus, `F`
fullscreen. Every 3D view has a **2D** button. Without WebGL the page says *"3D unavailable —
switching to accessible 2D inspection."*; `?no3d` in the address forces 2D. Adjusted,
edge-emphasised and 2.5D views are labelled *"Derived display — original source preserved."*

**Status never relies on colour alone:** every badge has a word and a glyph (✓ verified,
○ unverified, ? unresolved, ◇ AI observation, ■ blocked). Motion stops entirely when the
operating system asks for reduced motion, and the 3D illustration pauses when off screen.

## 1. Analyse a photograph

Upload a JPEG/PNG/TIFF/WebP/BMP, or choose a registered research photograph.

| Section | What it shows | Who asserts it |
|---|---|---|
| Summary | the headline: often **Insufficient evidence** | derived from the sections below |
| Image and regions | the inspection viewer; human-marked = gold solid, yours = sand dashed, AI proposal = cyan dotted (each also labelled) | as labelled |
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
