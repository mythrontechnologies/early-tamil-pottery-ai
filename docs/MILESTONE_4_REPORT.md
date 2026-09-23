# Milestone 4: Completion Report

**Date:** 2026-09-23
**Scope:** research data acquisition and source audit (discovery only)
**Status:** complete. No model built. No images downloaded into the project, scraped or
fabricated. No records created. `data/raw/` untouched. ML architecture unchanged.

Full evidence is in [`DATA_SOURCE_AUDIT.md`](DATA_SOURCE_AUDIT.md). This report summarises it
and answers the milestone's question.

---

## 1. The question

> "Where can we obtain a defensible dataset for this research prototype?"

**Answer.** From the Tamil Nadu State Department of Archaeology (TNSDA), by permission.

In 2026 the department published a two-volume corpus: K. Rajan & R. Sivanantham, *Inscribed
Potsherds of Tamil Nadu: Graffiti and Tamiḻi* (Pub. No. 366, ISBN 978-81-977842-3-1).
According to the authors it documents more than 1,500 Tamiḻi-inscribed sherds from 42 sites
and more than 15,000 graffiti sherds from about 140 sites. Every sherd has a catalogue
number, a photograph and an expert reading, and many have trench and depth recorded.
Behind the book sits a documentation database with full photographs, AutoCAD drawings,
geocoordinates and context fields that nearly match this project's schema.

The corpus is freely *viewable* online. It is **not licensed for reuse**. A defensible dataset
therefore needs a written permission request to TNSDA and the authors, and that request is
the next action.

No source found in this audit is both in scope and licensed for model training today. The
dataset is still empty, and that is the correct state.

---

## 2. Completion summary

```text
Sources investigated:        23 catalogued (S01–S23).
                             4 primary documents read directly (S01 Vol I, S01 Vol II, S03, S04);
                             5 more confirmed bibliographically (S06–S09, and S10–S12 via S01);
                             2 official policy/listing pages read (ASI, IFP);
                             Wikimedia Commons and Internet Archive checked through metadata APIs.

Sources with usable images:  In-scope images of identifiable inscribed sherds EXIST in
                             S01 (hundreds of plates), S03 (3 figures), S06 (print), and S02
                             (not public).
                             In-scope images lawfully usable for training TODAY: 0.
                             Openly licensed images: S15 (174 files, but none is an
                             identified sherd) and S16 (1 object, Sri Lanka, out of region).

Sources with published
Tamil-Brahmi readings:       Read and confirmed: S01 (per-sherd, the full corpus), S03 (names,
                             3 figured), S04 (2 names quoted).
                             Bibliographic only: S06, S07, S08, S09.

Sources with translations:   None gives a translation for every record.
                             S01 ch. 11 glosses selected inscriptions. Most readings are
                             personal names (see §5.3). S06/S09 pottery translations
                             REQUIRE VERIFICATION.

Sources with dating/context: S01: context PARTIAL (trench/depth on many rows, blank on
                             many others); dating at site/layer level only.
                             S03: depth + layer for figured sherds; site-level AMS.
                             S04: site-level AMS only.
                             S08: AMS-dated grave context (reported; not read).
                             No source gives an individual date for each sherd.

Sources with clear licensing: Clear and OPEN: S15, S16 (CC BY-SA). Neither is in-scope
                             ground truth.
                             Clear and RESTRICTIVE: S01, S03, S04 (© / all rights reserved);
                             S14 (ASI: no reproduction without permission); S19 (IFP/EFEO
                             copyright form).
                             UNKNOWN: S08–S13, S20, S22.

Sources requiring permission: S01/S02 (TNSDA + authors; possibly also ASI, Govt Museums,
                             Madras Univ., Tamil Univ. for images they permitted),
                             S14 (ASI), S17 (Keeladi museum), S18 (Govt Museums),
                             S19 (IFP), S21 (Tamil Univ. / Pondicherry Univ.).

Major data gaps:             1. No reuse licence for any in-scope source.
                             2. No source for the `none` class (uninscribed sherds).
                             3. Published images are too small for character-level work
                                (~150–200 px per sherd on S01 plates).
                             4. No per-sherd dates; site-level dates at Keeladi are disputed.
                             5. Translations are sparse, and mostly not applicable (names).
                             6. One view per sherd; no controlled multi-view photography.
                             7. Still no supervising epigraphist (DATA_INVENTORY §3.4).

Recommended acquisition path: 1. Permission request to TNSDA + authors for S01 and S02.
                             2. Institutional access to physical collections (Keeladi
                                museum, Govt Museum Chennai, Tamil Univ./Pondicherry Univ.)
                                for new photography and the `none` class.
                             3. Legitimately acquire S06/S07/S09 and TNSDA reports as the
                                reference and knowledge base (text, not images).
                             4. CC BY-SA images only to test the pipeline, never as ground
                                truth.
```

---

## 3. What was found that changes the plan

### 3.1 The corpus already exists, and it is expert-labelled

`DATA_INVENTORY.md` §3.1 assumed data would have to be assembled piecemeal from excavation
reports, corpora, museums and fieldwork. That assumption is now out of date. S01
consolidates most of the known material into one catalogue:

- It separates **graffiti** from **Tamiḻi**, which are two of this project's classification
  classes, and the separation is made by the epigraphers themselves.
- It gives **readings in both transliteration and Tamil script**, which are ground truth for
  Milestones 7–8.
- It records **ware, trench and depth**, which feed context and chronology.
- Its catalogue numbers are stable identifiers, which is exactly what artifact-level
  splitting (`SPLIT_METHODOLOGY.md`) needs.

### 3.2 The best material is not in the book

The book's plates are print-resolution composites. Vol. I ch. 3 describes the underlying
database: full photographs, AutoCAD drawings, geocoordinates, the sherd's present location,
layer, context and cultural phase. That database (S02) is what the permission request
should target.

### 3.3 Keeladi dates must be carried as disputed positions

- The ASI excavators' 2018 article (S03) dates its inscribed sherds to c. 2nd century BCE to
  1st century CE.
- The TNSDA's 2019 report (S04) and the 2026 corpus (S01) argue for a 6th century BCE start.
- The ASI's own full report (S05) remains unpublished amid a reported dispute.

The schema's `reading_status`, `dating_basis` and chronological-scope rules were built for
exactly this situation. Keeladi will be the first real test of them.

---

## 4. Legal and research-integrity handling

- Primary PDFs were read in a scratch directory **outside the repository** and deleted
  afterwards. One S01 plate was extracted temporarily to see whether plates are photographs
  or drawings (they are colour photographs); it was deleted.
- Three online copies were identified as **not to be used**, even though they are freely
  downloadable:
  - an Internet Archive upload of Mahadevan 2003 with no rights information;
  - Scribd/pdfcoffee mirrors of Rajan & Yatheeskumar 2013;
  - an Internet Archive re-upload of the 2019 Keeladi report carrying an uploader-applied
    "Public Domain Mark".
- The five rights questions are kept separate throughout: viewable, downloadable, research
  use, redistribution, commercial use. `downloadable = YES` is never read as permission.
- No legal opinion was sought. Whether an Indian copyright exception would cover training on
  S01 is **unknown**, and the recommended path does not depend on it.

---

## 5. Implications for the existing schema (not changed in this milestone)

These are recorded for a later milestone. The schema was not modified, because this milestone
is research only.

### 5.1 `license` is one field; the brief requires five

`image_record.schema.json` has a single `license` field plus free-text `rights_notes`. Brief
§8 requires `viewable_online`, `downloadable`, `research_usable`, `redistributable` and
`commercially_usable` as separate fields. **Recommendation:** add them before any real record
is ingested, and make ingestion refuse records whose `research_usable` is not affirmatively
established.

### 5.2 Alternative readings need structure

S01 shows a published re-reading: Kodumanal *visāki* → *visākanan*. `alternative_readings`
is currently free text with inline attribution. **Recommendation:** a list of
`{reading, source, year, status}` objects, so a benchmark can be scored against a specific
published reading.

### 5.3 "Translation" is mostly not the right concept

Most pottery inscriptions are personal names, sometimes with a genitive or a word for the
vessel. For a name, the honest output is an identification ("personal name, Tamil *ātaṉ*"),
not a translation. **Recommendation:** add an `inscription_content_type` field (e.g.
`personal_name`, `name_plus_term`, `term`, `fragmentary`, `unread`), and allow
`translation_en = not_applicable` for names. Milestone 9 should be scoped to that reality
before any model is built.

### 5.4 Record provenance of the image separately from provenance of the sherd

An S01 plate crop is a *reproduction* of a photograph taken by the S01 team, of a sherd held
by (say) Tamil University. That involves three parties with potentially different rights.
The schema should say who took the image, who published it, and who holds the object.

### 5.5 Resolution threshold per task

Classification and character recognition have different minimum resolutions. Preprocessing
check `P5` currently applies one threshold. S01 plate crops will likely pass for
classification and fail for OCR, and the schema should be able to say so.

---

## 6. References confirmed this milestone

Three entries in `CHRONOLOGICAL_SCOPE.md` §6 now have **bibliographic** confirmation. Their
verification column was updated to say what was confirmed and what was not. Confirming that a
work exists is **not** confirming that it supports the claim attributed to it.

| Ref | Now confirmed | Still unverified |
|---|---|---|
| R1 Mahadevan 2003 | HOS vol. 62; Cre-A, Chennai & Dept. of Sanskrit and Indian Studies, Harvard; 2003; has a pottery-inscription section (§1.13) | Page-level support for Position A |
| R3 Rajan | Rajan & Yatheeskumar 2013, *Prāgdhārā* 21–22: 280–295; Rajan & Sivanantham 2026 (S01) | Contents of the 2013 paper (not read) |
| R6 Sivanantham & Seran 2019 | Editors, title, year, TNSDA Pub. No. 302 (read) | Nothing further for existence; claim support as stated in S04 |

---

## 7. Status of downstream milestones

Unchanged. The classifier, OCR, transcription, translation and dating components remain
blocked on data. The readiness gate in code still blocks training. **Do not start model
training** until at least Step 1 of the acquisition path has a written answer.

### Proposed next step (not started)

Draft the permission request for Step 1: a one- to two-page letter to TNSDA and the authors.
It should state the non-commercial research purpose, the exact materials requested (S01
plates + Appendix I; S02 photographs, drawings and context fields), the intended uses
(training, evaluation, publication of aggregate metrics), what will *not* be done (no
redistribution of images, no commercial use), and how attribution and the authors' readings
will be preserved. This needs the user's institutional affiliation and a named supervisor,
so it cannot be finalised by the assistant alone.
