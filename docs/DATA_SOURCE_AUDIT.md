# Data Source Audit: Early Historic Tamil Nadu Inscribed Pottery

**Audit date:** 2026-09-23
**Milestone:** 4 (research and discovery only)
**Images acquired:** 0. **Records created:** 0. `data/raw/` was not touched.

This document records what was checked, how it was checked, and what is still unknown. It
is not legal advice. Every statement about copyright or permitted use is a finding about what
a source *says about itself*. It is not a determination of what the law allows.

---

## 0. How to read this document

### 0.1 Verification levels used

| Level | Meaning |
|---|---|
| **VERIFIED (read)** | The primary document itself was opened and read for this audit. Claims about its contents come from that reading. |
| **VERIFIED (bibliographic)** | The work's existence and bibliographic details are confirmed by two or more independent catalogue or citation sources. **The contents were not read.** |
| **VERIFIED (exists)** | An official page or listing shows it exists. The contents were not inspected. |
| **REPORTED** | Known only from news, secondary or tertiary sources. Not usable as evidence. |
| **UNVERIFIED** | Could not be reached or confirmed. |

### 0.2 Cell values

`YES` / `NO` / `UNKNOWN` / `REQUIRES VERIFICATION`, as specified. `PARTIAL` is used only
where a source demonstrably has the property for some records and not others. Each `PARTIAL`
is explained in §2.

### 0.3 Rights are five separate questions

Rights are never collapsed into one field. For each source:

| Field | Question |
|---|---|
| `viewable_online` | Can anyone look at it on the web without credentials? |
| `downloadable` | Does the host serve a file that can be saved? *(This is a technical fact, not a permission.)* |
| `research_usable` | Does the rights holder permit, or has the law clearly been established to permit, using it to train or evaluate this project's models? |
| `redistributable` | May the images or data be republished, for example in a released dataset or repository? |
| `commercially_usable` | May it be used commercially? |

**No source audited here has a `research_usable` value of YES established by an explicit
licence.** This is the central finding of the audit.

---

## 1. Acquisition matrix

`TB` = Tamil-Brahmi / Tamiḻi. The "Images" column means *images of individual identifiable
inscribed sherds*, not site photographs.

| ID | Source | Institution | Site(s) | Images | TB | Graffiti | Context | Transcription | Translation | Dating | License | Status |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| S01 | Rajan & Sivanantham, *Inscribed Potsherds of Tamil Nadu: Graffiti and Tamiḻi*, Vols I–II (2026) | Dept. of Archaeology, Govt. of Tamil Nadu (TNSDA); hosted by Tamil Virtual Academy | 42 sites for TB, about 140 for graffiti (as stated by the authors) | YES | YES | YES | PARTIAL | YES | PARTIAL | PARTIAL | © TNSDA. No reuse licence. | VERIFIED (read) |
| S02 | Documentation database underlying S01 (catalogue, photographs, AutoCAD drawings, context fields) | TNSDA / project team led by K. Rajan | Same as S01 | YES | YES | YES | YES | YES | UNKNOWN | UNKNOWN | Not public | VERIFIED (exists, per S01 Vol I, ch. 3). Access requires permission. |
| S03 | Ramakrishna, Swain, Rajesh & Veeraraghavan, "Excavations at Keeladi… (2014–15 and 2015–16)", *Heritage* 6 (2018): 30–72 | ASI (authors); Dept. of Archaeology, Univ. of Kerala (journal) | Keeladi | YES (3 figured sherds) | YES | YES (described, no catalogue) | YES (for the figured sherds) | YES (names) | NO | YES (site-level AMS) | Open access, "All Rights Reserved". No CC licence found. | VERIFIED (read) |
| S04 | Sivanantham & Seran (eds.), *Keeladi: An Urban Settlement of Sangam Age on the Banks of River Vaigai* (2019), Pub. No. 302 | TNSDA | Keeladi | NO (collage only, no catalogue IDs) | YES (summary) | YES (summary) | NO (per sherd) | PARTIAL (2 names quoted) | NO | YES (site-level AMS) | © TNSDA | VERIFIED (read) |
| S05 | Amarnath Ramakrishna, ASI final report on Keeladi seasons 1–2 (982 pp., submitted Jan 2023) | ASI | Keeladi | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | REPORTED as unpublished |
| S06 | Mahadevan, *Early Tamil Epigraphy: From the Earliest Times to the Sixth Century A.D.* (2003), Harvard Oriental Series 62 | Cre-A, Chennai & Dept. of Sanskrit and Indian Studies, Harvard | Pottery inscriptions incl. Arikamedu, Kodumanal (§1.13); primarily cave inscriptions | YES (photographs credited to IFP and ASI) | YES | UNKNOWN | REQUIRES VERIFICATION | YES | REQUIRES VERIFICATION (pottery) | REQUIRES VERIFICATION | © publisher | VERIFIED (bibliographic); table of contents seen |
| S07 | Mahadevan, *Early Tamil Epigraphy*, 2nd revised & enlarged ed. (2014), ISBN 978-93-81744-14-7 | Central Institute of Classical Tamil (CICT) | As S06, plus sections on Prakrit and Sinhala-Prakrit pottery inscriptions | REQUIRES VERIFICATION | YES | UNKNOWN | REQUIRES VERIFICATION | YES | REQUIRES VERIFICATION | REQUIRES VERIFICATION | © CICT | VERIFIED (bibliographic) |
| S08 | Rajan & Yatheeskumar, "New evidences on scientific dates for Brāhmī script as revealed from Porunthal and Kodumanal excavations", *Prāgdhārā* 21–22 (2013): 280–295 | (journal publisher REQUIRES VERIFICATION) | Porunthal, Kodumanal | REQUIRES VERIFICATION | YES | UNKNOWN | YES (as reported) | YES (as reported) | UNKNOWN | YES (AMS) | UNKNOWN | VERIFIED (bibliographic). Only unauthorised mirror copies were found online. |
| S09 | Mahadevan, "Pottery inscriptions in Brāhmī and Tamil-Brāhmī", in Begley et al., *The Ancient Port of Arikamedu*, vol. 1, pp. 287–315 | École française d'Extrême-Orient (EFEO) | Arikamedu | REQUIRES VERIFICATION | YES | UNKNOWN | REQUIRES VERIFICATION | YES | REQUIRES VERIFICATION | REQUIRES VERIFICATION | © EFEO | VERIFIED (bibliographic). Publication year REQUIRES VERIFICATION. |
| S10 | Sridhar, Thulasiraman, Selvaraj & Vasanthi, *Alagankulam: An Ancient Roman Port City of Tamil Nadu* (2005) | TNSDA | Alagankulam | UNKNOWN | YES (per S01) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | © TNSDA (presumed) | VERIFIED (bibliographic, via S01 bibliography only) |
| S11 | Sridhar, *Koḍumaṇal akaḻāivu (Kodumanal Excavations)* (2011, Tamil) | TNSDA | Kodumanal | UNKNOWN | YES (per S01) | YES (per S01) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | © TNSDA (presumed) | VERIFIED (bibliographic, via S01 only) |
| S12 | Sivanantham, Baskar, Prabakaran & Thangadurai, *Porunai River Civilization* (2022) | TNSDA | Sivagalai, Adichanallur, Korkai, etc. | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | © TNSDA (presumed) | VERIFIED (bibliographic, via S01 only) |
| S13 | TNSDA website: excavation pages and e-publications, tnarch.gov.in | TNSDA | Many | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNVERIFIED. Every connection from this environment was reset. |
| S14 | ASI, *Indian Archaeology: A Review* (volumes 2001–02 to 2013–14 online) | Archaeological Survey of India | Annual notices | REQUIRES VERIFICATION | REQUIRES VERIFICATION | REQUIRES VERIFICATION | REQUIRES VERIFICATION | REQUIRES VERIFICATION | NO (presumed) | REQUIRES VERIFICATION | No reproduction without ASI permission | VERIFIED (exists) |
| S15 | Wikimedia Commons, Category:Keezhadi archeological site (174 files) | Wikimedia contributors | Keeladi | NO (site, camp and museum photos; no identified sherd) | NO | NO | NO | NO | NO | NO | CC BY-SA 3.0 / 4.0 | VERIFIED (metadata read) |
| S16 | Wikimedia Commons, 2 photographs of a Tamil-Brahmi potsherd from Tissamaharama | Contributor "Metta79" (own work) | Tissamaharama, **Sri Lanka** (out of region) | YES (1 object) | YES (per caption) | NO | NO | NO | NO | NO | CC BY-SA 4.0 | VERIFIED (metadata read) |
| S17 | Keeladi Heritage Museum (opened 5 Mar 2023) | TNSDA / Govt. of Tamil Nadu | Keeladi | Physical objects on display | YES (on display) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | Photography policy UNKNOWN | REPORTED (tourism and news sources) |
| S18 | Government Museum, Chennai, and other Govt. Museums | Dept. of Museums, Govt. of Tamil Nadu | Various | Physical objects | YES (per S01 acknowledgements) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | Permission required | REPORTED (S01 credits them for photo permission) |
| S19 | Photo archive of the French Institute of Pondicherry (IFP) | IFP / EFEO | Mostly temple art; pottery coverage REQUIRES VERIFICATION | REQUIRES VERIFICATION | REQUIRES VERIFICATION | UNKNOWN | UNKNOWN | NO | NO | NO | Joint © IFP/EFEO for photos to 1999; copyright form required | VERIFIED (exists) |
| S20 | Red Sea and Arabian finds (Berenike, Quseir al-Qadim, Khor Rori) | Various excavation projects | **Outside Tamil Nadu** | UNKNOWN | YES (reported) | UNKNOWN | UNKNOWN | YES (reported) | PARTIAL (reported) | YES (reported, 1st c. BCE to 1st c. CE) | UNKNOWN | REPORTED. Also listed in S01. |
| S21 | Tamil University & Pondicherry University Kodumanal collections ("TU-PU": 551 Tamiḻi + 598 graffiti sherds per S01) | Tamil University, Thanjavur; Pondicherry University | Kodumanal | Physical objects | YES | YES | UNKNOWN | YES (in S01) | UNKNOWN | UNKNOWN | Permission required | REPORTED (via S01) |
| S22 | "Tamil-Brahmi (Tamili) Pottery Shards of Tamil Nadu: A Study" (ResearchGate / Academia.edu) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNVERIFIED (HTTP 403). Authorship not confirmed. |
| S23 | News, blogs, Wikipedia (The Wire, The Federal, Scroll, harappa.com, etc.) | Various | Keeladi and others | NO (ground truth) | — | — | — | — | — | — | Various | Context only. **Never ground truth.** |

### 1.1 Rights matrix

| ID | viewable_online | downloadable | research_usable | redistributable | commercially_usable |
|---|---|---|---|---|---|
| S01 | YES | YES (public PDF) | REQUIRES VERIFICATION | NO (no licence granted) | NO |
| S02 | NO | NO | REQUIRES PERMISSION | REQUIRES PERMISSION | REQUIRES PERMISSION |
| S03 | YES | YES | REQUIRES VERIFICATION | NO (no licence granted) | NO |
| S04 | YES (official site; also third-party copies) | YES | REQUIRES VERIFICATION | NO | NO |
| S05 | NO | NO | NO | NO | NO |
| S06 | Only through an unauthorised-looking Internet Archive upload. **Do not use that copy.** | — | REQUIRES VERIFICATION (lawfully obtained copy) | NO | NO |
| S07 | NO (print) | NO | REQUIRES VERIFICATION | NO | NO |
| S08 | Only unauthorised mirrors (Scribd, pdfcoffee). **Do not use.** | — | REQUIRES VERIFICATION | NO | NO |
| S09 | UNKNOWN | UNKNOWN | REQUIRES VERIFICATION | NO | NO |
| S10–S12 | UNKNOWN | UNKNOWN | REQUIRES VERIFICATION | UNKNOWN | UNKNOWN |
| S13 | UNKNOWN (unreachable) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| S14 | YES | YES | REQUIRES PERMISSION (ASI policy) | NO without permission | NO without permission |
| S15 | YES | YES | YES under CC BY-SA terms, but useless as ground truth | YES under CC BY-SA (attribution + share-alike) | YES under CC BY-SA |
| S16 | YES | YES | YES under CC BY-SA terms | YES under CC BY-SA | YES under CC BY-SA |
| S17, S18, S21 | NO (physical) | NO | REQUIRES PERMISSION | REQUIRES PERMISSION | REQUIRES PERMISSION |
| S19 | NO (on request) | NO | REQUIRES PERMISSION (copyright form) | REQUIRES PERMISSION | REQUIRES PERMISSION |
| S20, S22 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

A CC BY-SA licence on S15/S16 is only the uploader's grant. It has not been confirmed that
the uploader had the right to grant it. For museum-display photographs this is generally
unproblematic, but it has not been checked for any individual file.

---

## 2. Source notes

### S01: *Inscribed Potsherds of Tamil Nadu: Graffiti and Tamiḻi* (2026). The key source.

- **Bibliographic facts (from the title pages, read):** K. Rajan and R. Sivanantham.
  Department of Archaeology, Government of Tamil Nadu, Chennai. First edition 2026,
  Publication No. 366. Vol. I 740 pp., Vol. II 712 pp. ISBN 978-81-977842-3-1 (set). Rs. 2900
  for the set. "© Department of Archaeology, Government of Tamil Nadu".
- **Where:** Tamil Digital Library (Tamil Virtual Academy). Vol. I is catalogue item
  `TVA_BOK_062969`, Vol. II `TVA_BOK_062968`. Both PDFs are served publicly. TDL's site
  footer says "Copyright © 2026, All rights reserved by Tamil Virtual Academy". **No reuse
  licence was found on the book or the host.**
- **Scale (as the authors state):** more than 1,500 Tamiḻi-inscribed sherds from 42 sites,
  and more than 15,000 graffiti-bearing sherds from about 140 sites. These are the authors'
  figures. They were not counted for this audit.
- **Structure (read):**
  - Vol. I: ch. 1 Introduction; ch. 2 Site Descriptions; ch. 3 Methods and Materials; chs. 4–5
    Graffiti.
  - Vol. II: ch. 6 Concordance of Graffiti Signs; chs. 7–11 Tamiḻi (introduction,
    palaeography, orthography, chronology, contents); Bibliography; Appendix I (tabular list of
    Tamiḻi sherds); Appendix II (plate index); Appendix III (photo catalogue).
- **Appendix I fields (read):** serial no., site, plate no., catalogue no. (e.g.
  `Keeladi_TNSDA_023`, `Kodumanal-TNSDA_151`, `Kodumanal-TU-PU_457`), year of excavation,
  trench/grave, depth, pottery ware (BRW, RW, RSW, BW, RCW…), reading in transliteration, and
  reading in Tamil script. **Trench and depth are blank for many rows.**
- **Appendix III (sampled, read):** colour photographs of individual sherds on a black
  background, 12 per plate, each labelled with its catalogue number and reading. On the
  sampled plates each plate image is about 654 × 925 px, so one sherd is roughly 150–200 px
  across. That is too small for character-level work and marginal for classification.
- **Per-site distribution:** a rough tally of Appendix I rows by site from extracted PDF text
  put Kodumanal first by a wide margin, then Keeladi, Alagankulam, Arikamedu and Uraiyur.
  Porunthal had a single row. The tally is **unreliable** because multi-line rows break text
  extraction, so no per-site counts are recorded here. Recount from the printed book if needed.
- **Kodumanal breakdown (Vol. I ch. 2, read):** 1,109 Tamiḻi sherds (TU-PU 551 + ASI 375 +
  TNSDA 183) and 2,622 graffiti sherds (TU-PU 598 + TNSDA 2,024; ASI graffiti data "not
  available").
- **Translation: PARTIAL.** There is no per-record translation column. Chapter 11 ("Contents
  of the Pottery Inscriptions") discusses meanings for selected inscriptions, e.g. *pati* =
  pot or vessel, genitive forms such as *dataśa* "of Data". Most readings are personal names,
  and "translation" in the usual sense does not apply to them. See the report, §5.3.
- **Dating: PARTIAL.** There is no per-sherd date. Chapter 10 argues a chronology from
  site-level AMS dates (Porunthal c. 490 BCE, Keeladi c. 580 BCE, Sivagalai c. 685 BCE, as
  stated) and from palaeography. **These dates are contested** (see S03/S04 note). Treat them
  as the authors' published position, not as settled.
- **Third-party image rights:** Vol. I thanks the ASI, TNSDA, Government Museums, Madras
  University, Tamil University and others "for permitting us to take photographs … and to
  utilize them in the present work". It specifically notes that *unpublished* ASI Keeladi
  material was included with the ASI Director General's permission. **Permission to reuse
  these images may therefore rest with several institutions, not with TNSDA alone.**
- **Expert authorship:** readings are *published expert interpretation* by a named
  epigraphic team: Rajan (Principal Investigator), Sivanantham and Sundar (Co-Investigators),
  Yatheeskumar, and research staff listed in the book.

### S02: The documentation database behind S01

Vol. I ch. 3 (read) describes the project's method in detail:

- Every sherd was given a catalogue number (e.g. `TN-TKP-G-0001`, `TN-AGM-D-0001`), then
  photographed and drawn in AutoCAD.
- Images and drawings have their own IDs, e.g. `0121_TKP_Graffiti_Image_01`.
- The fields recorded include site, geocoordinates, taluk, district, excavator,
  institution, year, **present location of the sherd**, trench, depth, layer, context
  (habitation/burial), cultural phase, ware, shape, and position of the signs.
- The images and drawings "are inserted in the database for the purpose of verification".

This is almost exactly this project's schema. The database is not public. It is the single
highest-value target for a permission request, because it would provide full-resolution
photographs, drawings for rubbing/drawing-view separation, and structured context,
all tied to published expert readings.

### S03: *Heritage* 6 (2018), ASI Keeladi seasons 1–2 (read)

- Authors: K. Amarnath Ramakrishna, Nanda Kishor Swain, M. Rajesh, N. Veeraraghavan (ASI).
  Received 29 Jul 2018, accepted 18 Oct 2018.
- Reports "about 70" Tamil-Brahmi sherds (another passage says "more than seventy") and about
  600 graffiti sherds from two seasons, all from Locality II. Readings given are personal names
  (e.g. *ātan*, *tisan*, *sātan*, *eravātan*), plus some Prakrit readings the authors suggest
  may be of Sri Lankan origin.
- **Figured with readings:** Fig. 16 (*eravathan*), Fig. 17 (BRW dish, *ce n ta n a va (ta)
  thi*), Fig. 18 (*va se i y pe ru mu va r u n…*).
- **Stratigraphic context in text:** one sherd at 1.60 m (Layer 4, no reading given), *sathan*
  at 2.16 m (Layer 4), *eravathan* on a red-ware lid at 2.36 m (Layer 5).
- **Dating:** two AMS samples from Beta Analytic, from YF1/1 at 2.50 m and YF4/2 at 1.95 m.
  The article prints the calibrated result as "200 BC – 195 BC". The authors call the period
  scheme "purely tentative" and date the inscribed sherds to "c. 2nd cent BCE – c. 1st cent
  CE" in the same article.
- **Licence:** the journal site describes itself as open access. Its footer reads "Copyrights
  © 2016 All Rights Reserved by Department of Archaeology". No Creative Commons licence was
  found.

### S04 and S05: Keeladi, and why its dating is a live dispute

- **S04** (read) is a 66-page public summary, not a catalogue. It reports 56 Tamiḻi sherds
  and 1,001 graffiti sherds from the TNSDA seasons. It also reports six AMS dates from Beta
  Analytic, from the 4th season (2018), running from the end of the 6th century BCE (353 cm)
  to the early 3rd century BCE (200 cm).
- **S05** (reported only): the ASI excavator's 982-page final report on seasons 1–2 was
  submitted in January 2023. News sources report that the ASI asked for revisions and the
  author declined. It is **not published** and cannot be used.
- News and commentary report scholars questioning whether the inscribed sherds come from the
  same layers as the 6th-century-BCE samples (S23). S03 itself places its inscribed sherds
  in the 2nd c. BCE to 1st c. CE.
- **Consequence for this project:** a Keeladi sherd's date must be recorded as a *published
  position with its basis*, never as a fact. `docs/CHRONOLOGICAL_SCOPE.md` already requires
  this, and Keeladi is the case that shows why.

### S06–S09: the epigraphic literature

- **S06** is the standard corpus. Bibliographic details were confirmed from multiple
  catalogues and from S01's bibliography. The table of contents (seen via a text copy) has
  §1.13 "Pottery inscriptions" covering Arikamedu, Kodumanal and others. Acknowledgements
  credit pottery photographs to the Institut Français de Pondichéry and the ASI.
  **The only online full copy found is an Internet Archive upload with no rights
  information. It appears to be unauthorised and must not be used or cited as the access
  route.** Acquire the book legitimately (purchase or library).
- **S08**'s citation is confirmed. The Porunthal inscribed ring-stand is reported read as
  *vayra* ("diamond"), from a grave context dated by AMS on paddy grains. Only mirror
  copies on document-sharing sites were found. **Do not use those copies.**

### S13: TNSDA website

The site's own pages were found by search: excavation list, e-publications, Keeladi and
Alagankulam pages, a 2020 "Ongoing Archaeological Excavations" status report. Every
fetch attempt from this environment failed with a connection reset. **Nothing is claimed
about its contents or terms.** Check it manually from another network.

### S15/S16: Wikimedia Commons

Metadata was queried through the Commons API. No images were downloaded. The Keezhadi
category holds 174 files, all CC BY-SA 3.0 or 4.0. Their subjects are the excavation site,
camp, museum exterior and general "artifacts" displays. None is described as an identified
inscribed sherd with a catalogue number or reading. Searches for Kodumanal, Porunthal,
Alagankulam and "Tamili potsherd" returned no files. The only explicit Tamil-Brahmi
potsherd images are two photographs of one object from Tissamaharama, Sri Lanka, which is
outside this project's region.

---

## 3. Evidence tiers

Tiers apply to **records**, not sources. One source can produce records of different tiers.

| Tier | Definition | Where records could come from |
|---|---|---|
| **A** | Image + artifact identity + archaeological context + published dating + published reading + translation (if applicable) | **Few, and only after cross-referencing.** The candidates are S01 records that also (a) have trench/depth, (b) come from a layer with a published date, and (c) are discussed in S01 ch. 11 or in S06/S08. Candidates are listed in §4. |
| **B** | Image + artifact identity + context + script/inscription information | **S01 records with trench/depth filled in.** S02 would make most S01 records Tier B at full resolution. S03 Figs. 16–18 (2 of 3 have depth). |
| **C** | Image + basic metadata only | S01 records without trench/depth: catalogue ID, site, ware and reading, but no context. S16. |
| **D** | Image without trustworthy provenance | S15, news photographs, social media, unidentified museum-display photographs, anything re-hosted by third parties. **Never ground truth.** |

Two tiering rules follow from what was found:

1. **Low resolution does not change the tier, but it changes the use.** An S01 plate crop
   can be Tier B in evidence and still be unfit for character recognition. Record resolution
   separately.
2. **A date inherited from a site or layer is not a date of the sherd.** It counts toward
   Tier A only if the published source ties the sherd to that dated layer. The Keeladi
   dispute is exactly about whether that tie holds.

---

## 4. Potential benchmark material

These are **pointers for a human to check against the printed plates**. They are not records.
Nothing here goes into `data/` until a person has confirmed every field against the source.

| Candidate | Reading (as published) | Sources to reconcile | What is known | What is missing |
|---|---|---|---|---|
| Porunthal ring-stand, grave context | *vayra* | S01 (Appendix I has one Porunthal row), S08 | Reading, grave context, AMS-dated context (as reported) | Image rights; confirm S01 plate; S08 not read |
| Keeladi, red-ware lid, Layer 5, 2.36 m (ASI) | *eravathan* | S03 Fig. 16; S01 Keeladi ASI rows | Image, reading, depth, layer | Link to S01 catalogue number; dating is site-level and disputed |
| Keeladi, Layer 4, 2.16 m (ASI) | *sathan* | S03 text; S01 | Reading, depth, layer | Image not figured in S03 |
| Keeladi, BRW dish (ASI) | *ce n ta n a va (ta) thi* | S03 Fig. 17; S01 | Image, reading | Depth not in the passage read |
| Kodumanal, transepted cist | *visāki*, re-read as *visākanan* | S01 Vol. I ch. 2 | Reading history, burial context | Image and catalogue number not located; the re-reading means two expert readings exist and both must be kept |
| Keeladi TNSDA rows with trench + depth (e.g. `Keeladi_TNSDA_023`–`048`) | Various (Appendix I) | S01 | Catalogue ID, trench, depth, ware, reading, plate | Per-sherd date; translation (mostly names) |

The Kodumanal *visāki* → *visākanan* case is useful in its own right. It is a published
expert re-reading, so the schema must be able to hold more than one reading per record,
each with its own source and date.

---

## 5. Expert annotation assessment

| ID | Script label | Transcription | Translation | Dating | Dating basis | Context | Annotation type |
|---|---|---|---|---|---|---|---|
| S01 | YES | YES | PARTIAL | PARTIAL (site/layer) | AMS (site) + palaeography | PARTIAL | Published expert interpretation |
| S02 | YES | YES | UNKNOWN | UNKNOWN | UNKNOWN | YES | Expert project records; would become *published* only by citation to S01 |
| S03 | YES | YES (names) | NO | YES (site) | AMS (2 samples) + ceramics | YES (figured items) | Published expert interpretation |
| S04 | YES | PARTIAL | NO | YES (site) | AMS (6 samples) | NO | Published, popular summary. Weaker than S01/S03. |
| S06/S07/S09 | YES | YES | REQUIRES VERIFICATION | REQUIRES VERIFICATION | REQUIRES VERIFICATION | REQUIRES VERIFICATION | Published expert interpretation |
| S08 | YES | YES (reported) | UNKNOWN | YES | AMS | YES | Published expert interpretation |
| S15/S16 | NO (caption only) | NO | NO | NO | — | NO | None. The caption is uploader text, not an expert label. |
| S23 | — | — | — | — | — | — | Journalism / commentary. Not annotation. |

The three categories required by the brief map directly onto the existing schema's
`label_source` field:

- **Published expert interpretation**: a reading or date printed in S01, S03, S06–S09, cited
  to page/plate/catalogue number.
- **Project annotation**: anything this project's annotators write, including copying a
  published reading into a record. The copying step is itself a project action and needs its
  own verification flag.
- **AI prediction**: model output. It never enters `data/metadata/` as a label.

---

## 6. Recommended acquisition sequence

This is ordered by **what can be done lawfully and defensibly next**, not by a quality score.

### Step 1: Request permission for the S01 corpus and its S02 database (highest value)

**Why first:** one request, to one department, covers the largest known expert-labelled
corpus of this exact material. It spans more than 1,500 Tamiḻi and more than 15,000 graffiti
sherds, with catalogue IDs, readings and context fields already structured almost the same
way as this project's schema.

**What to ask for:** written permission to use (a) the S01 plate images and Appendix I data,
and ideally (b) S02's full-resolution photographs, drawings and context fields, for
non-commercial research model training and evaluation. Ask separately about publishing
derived metrics, and about redistribution (probably refused; plan for "no").

**Who:** Commissioner/Director, Department of Archaeology, Govt. of Tamil Nadu, and the
authors (Prof. K. Rajan, Dr. R. Sivanantham). Because S01 includes images photographed by
permission of the ASI, Government Museums, Madras University and Tamil University, ask
TNSDA to state whether its permission covers those images or whether each holder must be
approached.

**Until permission arrives:** S01 can be *read* as a reference, to design the label set,
check schema fields and plan benchmarks. No image or table row is copied into `data/`.

### Step 2: Institutional permission for physical collections (S17, S18, S21, S19)

**Why:** this is the only route to (a) new, controlled, high-resolution photographs with
clean rights, and (b) the **`none` class**, which is uninscribed sherds from the same
contexts. No published source supplies that class, because publications only illustrate
inscribed sherds. It is also the only route to multiple views of one artifact under
controlled lighting.

**Who:** Keeladi Heritage Museum / TNSDA; Government Museum, Chennai; Tamil University
(Thanjavur) and Pondicherry University for the TU-PU Kodumanal material; IFP photo archive
(copyright form) for historical photographs.

**Precondition:** an institutional affiliation and a supervising epigraphist or
archaeologist. `docs/DATA_INVENTORY.md` §3.4 already identifies this as the non-data
dependency.

### Step 3: Reference and knowledge-base use only, without image reuse (S03, S04, S06–S12, S14)

**Why:** these are the evidence for readings, context and dating arguments. They supply the
text of benchmark records and the knowledge base (Milestone 11), with citations. Images in
them are not reused without permission.

**Action:** acquire S06/S07 and S09 legitimately (purchase or library). Check S10–S12 in
print. Retry S13 from a network that can reach tnarch.gov.in.

### Step 4: Open-licence material, for pipeline testing only (S15, S16)

**Why:** CC BY-SA images are lawful to use with attribution and share-alike, but they are
Tier C/D and mostly not inscribed sherds. They are suitable for exercising the preprocessing
and ingestion code on real photographs. They are **not** suitable for training or evaluating
the classifier as archaeological ground truth. If used, the share-alike obligation must be
honoured.

### Do not use

| What | Why |
|---|---|
| Internet Archive upload of Mahadevan 2003 (S06) | No rights information; appears to be an unauthorised copy of an in-copyright book |
| Scribd / pdfcoffee copies of Rajan & Yatheeskumar 2013 (S08) | Unauthorised mirrors |
| Internet Archive re-uploads of the Keeladi 2019 report (S04) | Third-party uploads. One carries a "Public Domain Mark" chosen by the uploader, which has **no legal effect** on a 2019 © TNSDA publication. Use the official source. |
| News, blog and social-media photographs of sherds (S23) | Tier D: no provenance, no catalogue ID, rights held by publishers |
| Any image whose only justification is "it is visible online" | Brief §8 |
| The unpublished ASI Keeladi report (S05) | Not published; readings and dates not citable |
| Red Sea / Arabian / Sri Lankan finds (S16, S20) as in-scope training data | Outside the region. Usable only as labelled out-of-region comparanda, if at all. |

---

## 7. Method and limits of this audit

- **Tools:** web search; direct reading of four primary PDFs (S01 Vols I–II, S03, S04);
  Internet Archive metadata API; Wikimedia Commons API (metadata only); official ASI and IFP
  pages.
- **Handling:** PDFs were read in a temporary scratch directory outside the repository and
  **deleted after reading**. One S01 plate was viewed to find out whether plates are
  photographs or drawings; the extracted image was deleted. **No image was saved into the
  project.**
- **Not reached:** tnarch.gov.in (connection reset); ResearchGate and Academia.edu (HTTP
  403); harappa.com (HTTP 403).
- **Not done:** no legal opinion was sought. Whether Indian copyright exceptions for private
  research would cover model training on S01 is **unknown** and must not be assumed.
  Institutional permission (Steps 1–2) avoids depending on that question.
