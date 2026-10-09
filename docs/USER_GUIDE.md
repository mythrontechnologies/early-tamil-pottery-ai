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
| Annotation | the annotation lab: inspection stage (photograph, overlays, region and glyph marking) beside the form (Object · Inscription · Meaning · Dating · Evidence · Review), provenance and revision history below; tabs **Review** (tier legend, field-level disagreements), **Pilot & agreement**, **Queue** (every artifact, its state and the next human step) |
| Dataset | the collection as museum plinths; **Inspect** opens the Artifact Inspector (source, licence, annotation, expert and training state); training readiness against the unchanged gate |
| Evidence | references and claims with their verification state: verified / transcribed / bibliographic / **unresolved**; where a software pre-check found a claim, the trail shows *Where to check* under the badge **Software pre-check · not verification** |
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
| Language / reading results | one card each for inscription or mark status, transcription, transliteration, translation and reading completeness (complete / partial / fragmentary / illegible / unknown), with its confidence, who asserts it and, when missing, why | human evidence, tiered: promoted ground truth · expert adjudication · expert-reviewed · expert (not reviewed) · published source · project annotation; AI drafts listed apart |
| Estimated age / Period | an evidence-based range, an outer bound, or "Insufficient evidence" | dating evidence |
| Confidence | archaeological confidence from evidence and its verification status | rules, not scores |
| Reasoning | every step, traceable to an input | reasoning engine |
| Evidence layers | expert, project and verified evidence in separate panels | as labelled |
| AI observation | classifier, detector, mark analysis, OCR (amber banner) | **AI, not evidence** |
| Warnings | provenance, review flags, unverified references, disagreements | |

**An uploaded image that is not a registered research photograph** (no SHA-256 match) gets
no annotations, even if you type an artifact id. It will usually be "Insufficient evidence".
That is correct: the project knows nothing about it.

**Language / reading results** sit directly below the photograph. A transcription is shown only when
a human recorded one; a partial or low-confidence reading is shown with that caveat, and alternative
readings are listed. A translation is shown only when a human recorded it with a cited source; otherwise
the card says so ("Not established — no human translation with a cited source has been recorded." or
"Not available — no reading has been established, so nothing can be translated."). A classifier
prediction or an OCR candidate never fills a card: OCR candidates appear apart as **AI drafts — not
readings**. Research mode adds the evidence behind each card (annotation id, source and its verification
status); Presentation mode keeps every value, caveat and explanation.

"Your regions" (`x,y,w,h`, fractions of width/height) help you look; they are not evidence.

## 1b. Data mode: Real Research or Synthetic Demonstration

The Analysis page opens in **Real Research** mode. That is the default and nothing synthetic runs
in it: an upload or a registered photograph is analysed exactly as above. A real photograph shows
**REAL RESEARCH PHOTO DETECTED — Real archaeological inference is unavailable until
expert-labelled training data is available.** Synthetic models are never applied to it.

**Synthetic Demonstration** must be chosen explicitly (the *Data mode* switch at the top of the
page, or *Run synthetic demonstration* on Overview, which opens `?data=synthetic`). It runs the
complete AI pipeline on images from the **synthetic engineering dataset only**:

| Stage | What it does (all SYNTHETIC) |
|---|---|
| 01 LOAD · 02 PREPROCESS | reads the image, confirms its SHA-256 is in the synthetic dataset, letterboxes |
| 03 CLASSIFY | ResNet-18 → a *Synthetic Tamil-Brahmi-like / graffiti-like / none / uncertain class*, temperature-calibrated |
| 04 DETECT | RegionNet → synthetic inscription regions and glyph rows (purple dotted, "Synthetic detector — not evidence") |
| 05 SEGMENT · 06 OCR | learned glyph centres → GlyphNet → a **Synthetic glyph transcription** (`SG03 SG11 …`) — not Tamil-Brahmi transcription |
| 07 INTERPRET | the deterministic **synthetic-language decoder** → a fictional transliteration and English translation of the *predicted* codes (`SG01 SG09 SG02` → `pala taren maku` → *The chief gives shelter.*), **SYNTHETIC LANGUAGE — NOT TAMIL-BRAHMI**; plus the grammatical interpretation, a separate field: agent *chief* · action *gives* · object *shelter* (roles of invented words; never a name or identity) |
| 08 REASON | synthetic chronology categories (`SYNTH_CAT_01`–`04`, never BCE/CE) and an 8-node synthetic evidence chain: **"Synthetic demonstration — not archaeological dating."** |

Each stage appears as it finishes (real timings, no artificial delay). The **pipeline replay**
re-plays the measured stages on an illustrative sherd — *not a scan of the input image* — with
Play/Pause, Skip, Replay and a 2D view; reduced motion shows every stage at once, and the 2D
view is used automatically without 3D support. The ground-truth card compares the result with
the generator's own record. Every block carries **SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE**.

The **Language / reading results** of a synthetic run show the synthetic glyph transcription
(`SG01 SG09 SG02`), then, under **SYNTHETIC LANGUAGE — NOT TAMIL-BRAHMI**, the fictional
transliteration (`pala taren maku`), the English translation (**The chief gives shelter.**), the
method (*Deterministic synthetic lexicon and grammar*), the status and a word-by-word gloss. The
language is invented for engineering demonstration ([`SYNTHETIC_LANGUAGE.md`](SYNTHETIC_LANGUAGE.md)):
the sentence is correct only under that specification and is never a reading of Tamil-Brahmi. An
unknown glyph, an invalid or incomplete sequence, or no reading gives **no** sentence, with the
reason; a partial reading translates only its complete clauses. The replay shows the same lines
under 07 INTERPRET; `python -m src.synthetic demo` and `python -m src.synthetic translate SG01 SG09 SG02`
print them. Real photographs never pass through this decoder.

The two modes never merge: a real photograph cannot be chosen in Synthetic mode, a synthetic
image uploaded in Real mode is refused, and no synthetic result is written to the research store.
See [`SYNTHETIC_END_TO_END.md`](SYNTHETIC_END_TO_END.md).

## 2. Annotate

See [`ANNOTATION_GUIDE.md`](ANNOTATION_GUIDE.md) and the one-page
[`PILOT_ANNOTATION_CHECKLIST.md`](PILOT_ANNOTATION_CHECKLIST.md). Choose *Project annotator*
or *Expert*, enter your id, answer only what the photograph supports, and save. Saving
appends; nothing is overwritten.

* **Signs.** Region label `character` marks one sign; give its position in the reading and, only if you
  can read it, the sign (`?` otherwise). Say whether the reading is complete, partial, fragmentary or
  illegible.
* **Adjudication (experts).** Tick *I am ADJUDICATING disagreeing annotations* in the sidebar, select the
  annotations you have read, state the outcome and your basis. The resolved annotations stay visible.
* **Offline.** `python -m src.annotation handoff --all` writes worksheets; `import-worksheet` brings them in
  (dry run first, all-or-nothing).
* **What the five kinds of statement look like** (Review tab legend): *Source metadata* (what the uploader
  or publisher said) · *Project annotation* (provisional) · *Expert annotation* · *AI draft* (never evidence)
  · *Promoted ground truth* (only after a human-approved promotion).

## 3. Check a reference (verifiers)

`python -m src.knowledge prechecks` lists where a software agent found each claim of R1, S01 and S03 (copy
URL and page). Open the copy at that page, read the passage, then
`python -m src.knowledge verify-from-precheck <PC-id> --verifier <you> --role project_member --date YYYY-MM-DD --i-opened-the-source`
(dry run; add `--commit`). The Evidence page and the Verification checklist tab show the same pointers.

## Command line

```powershell
python -m src.inference analyze photo.jpg [--json]      # the same analysis as the page
python -m src.workflow status                          # where the project is, and the next step
python -m src.annotation integrity                     # are the append-only stores intact?
python -m src.knowledge entries                        # every sourced claim and its status
python -m src.annotation queue                         # what to annotate next
python -m src.annotation disagreements --all           # who said what, field by field
```

Synthetic demonstration (SYNTHETIC engineering data only):

```powershell
python -m src.synthetic demo [--image-id SYNTH-A0007-V1]           # full pipeline on one synthetic image
python -m src.inference synthetic --image data/synthetic/images/SYNTH-A0007-V1.jpg [--json]
python -m src.inference serve --synthetic                          # adds POST /synthetic/analyze
python -m src.evaluation synthetic [--skip-robustness] [--json]    # SYNTHETIC ENGINEERING BENCHMARK
```
A real or unregistered photograph given to `synthetic` exits with code 3 and is not analysed.
