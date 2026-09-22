# Data Inventory

**Surveyed:** 2026-09-22
**Result: zero images. The dataset is empty.**

---

## 1. What was searched

The working directory `V:\ADM` and its subtrees were inspected for any existing pottery,
Tamil-Brahmi, epigraphy or archaeological image data, and for any prior code for this project.

| Location | Contents | Relevant? |
|---|---|---|
| `V:\ADM\*.pdf`, `*.pptx` | Coursework material — linear algebra, Ayurveda, Bhagavad Gita, yoga, Indian historiography, Chanakya, ADM chapter notes | **No.** Unrelated subject matter; no pottery, epigraphy or archaeological image content. |
| `V:\ADM\VIDURA_THE_WARNING\` | Animation pre-production for a Mahabharata short film (script, character sheets, environments, props) | **No.** Textual/narrative research, not archaeological data. |
| `V:\ADM\simulator\` | A JavaScript + Python application with its own `requirements.txt`, tests, and a SQLite database | **No.** Unrelated project. |
| Filename search for `*pottery*`, `*brahmi*`, `*tamil*`, `*sherd*` | 0 matches | — |

**Conclusion: this project starts from nothing.** There is no prior code, no images, and no
metadata to migrate. Nothing in `V:\ADM` was modified; the new project lives in its own directory.

## 2. Current dataset state

| | Count |
|---|---|
| Images in `data/raw/` | **0** |
| Records in `data/metadata/records.jsonl` | **0** (file not yet created) |
| Distinct artifacts | **0** |
| Verified references | **0** |

The only file under `data/metadata/schema/` besides the schema is `_example_record.json`, which is
a **fictitious structural placeholder** carrying an explicit warning banner. It contains no
archaeological assertion and is excluded from all data loading by its leading underscore.

**No dataset has been fabricated, and none will be.** A synthetic pottery corpus would be worse
than no corpus: a model trained on it would produce confident output with no evidential basis,
which is the specific failure this project is built to avoid.

## 3. What acquiring real data requires

This is the blocking dependency for Milestones 2 onward. It is a **research access problem, not an
engineering problem**, and it is unlikely to be solved from a laptop.

### 3.1 Routes worth pursuing, roughly in order of tractability

| Route | What it could yield | Obstacle |
|---|---|---|
| **Published excavation reports** — ASI *Indian Archaeology: A Review*, Tamil Nadu State Department of Archaeology site reports | Plates of inscribed sherds with site, layer and published readings | Plate images are low-resolution halftone; copyright usually reserved; scanning quality varies |
| **Published epigraphic corpora** | Readings, transliterations, palaeographic charts, catalogue numbers — the highest-quality *metadata*, and the ground truth for OCR stages | Images are often line drawings or rubbings, not photographs. See §3.3. |
| **Museum collections** — Government Museum Chennai, and other Tamil Nadu institutions | Photographs with accession numbers | Requires formal permission; digitisation coverage is uneven |
| **University archaeology departments in Tamil Nadu** | Excavation archives, unpublished photographs, and — more importantly — expert annotation | Requires an institutional relationship; this is the route that also solves §3.4 |
| **Direct fieldwork / site-museum photography** | New, rights-clean, high-resolution images under controlled conditions | Requires permits, travel, and supervision |
| **Open repositories** (e.g. Wikimedia Commons, institutional open-access archives) | A small number of rights-clean images | Very small volume; provenance metadata usually thin or absent |

### 3.2 Minimum viable dataset

Before Milestone 4 is worth attempting, a defensible rough target:

- **≥ 150–200 distinct artifacts**, not images, with **≥ 30–40 artifacts in each of the four
  classes**. Fewer than this and a 15% test split contains single-digit counts per class, at which
  point a quoted accuracy figure is noise. The `min_artifacts_per_class_for_holdout: 20` gate in
  `configs/project.yaml` triggers grouped k-fold reporting below that threshold.
- Class balance matters less than **artifact** count. Twenty photographs of one sherd is one
  artifact's worth of evidence, not twenty.
- The `none` class (uninscribed sherds) is the easiest to collect in volume and will skew the
  dataset if collected opportunistically. Collect it deliberately and cap it.

### 3.3 A distinction that must be preserved

The brief (§8) requires separating **existing external data** from **our pottery-specific
dataset**. Concretely, three kinds of material will be encountered and must not be mixed:

| Kind | Where it goes | Why |
|---|---|---|
| Photographs of inscribed sherds | `data/raw/`, `view: exterior`/`closeup` | The actual task distribution |
| Rubbings and published line drawings | `data/raw/`, `view: rubbing`/`drawing` | **Scholarly renderings, not photographs.** High-contrast, idealised, noise-free. A classifier trained on these will not transfer to a worn sherd photographed in the field. Usable for OCR pretraining; must be excluded from, or reported separately in, any photograph-based evaluation. |
| Handwritten / font-rendered Tamil-Brahmi character sets | `data/external/` | Useful for OCR pretraining (Milestone 7). **Performance on these says nothing about performance on worn inscriptions carved into ancient pottery** and must never be reported as if it did. |

### 3.4 The non-data dependency

Every route above yields images with *published* labels at best. The project also needs an
**epigraphist or archaeologist** who can:

- adjudicate `graffiti` vs `tamil_brahmi` on ambiguous sherds;
- confirm that `uncertain` is being used honestly rather than as an annotator's escape hatch;
- verify the references in `docs/CHRONOLOGICAL_SCOPE.md` §6;
- answer the open questions in `docs/CHRONOLOGICAL_SCOPE.md` §8.

Without this, `label_source` can never rise above `project_annotation_unverified`, and the
resulting metrics measure agreement with an untrained annotator rather than with the field.

## 4. What can proceed without data

To be explicit about what is and is not blocked:

| Milestone | Blocked on data? |
|---|---|
| M1 — structure, schema | ✅ complete |
| M2 — ingestion and validation | ⚠️ The **tooling** can be built and tested against fixtures now. The **ingestion** cannot run. |
| M3 — preprocessing | ⚠️ Same: code testable on any images, tuning needs real sherds |
| M4 — classifier | ⛔ Blocked |
| M5 — evaluation | ⛔ Blocked |
| M6–M9 — detection, OCR, transcription, translation | ⛔ Blocked |
| M10 — chronological reasoning | ⚠️ Partly. The evidence-table structure and reasoning separation are data-independent; the evidence is not. |
| M11 — knowledge base | ⚠️ Partly. Structure now; contents need verified references. |
| M12 — Streamlit UI | ⚠️ Shell can be built; it must not display fabricated results. |
| M13 — end-to-end testing | ⛔ Blocked |

Building M2 tooling against fixtures is the right next move: it makes the schema executable and
means real data can be ingested the day it arrives, rather than starting the pipeline then.
