# Milestone 6: Public Dataset Acquisition

**Date:** 2026-09-23
**Status:** complete. The first real, legally reusable archaeological images are in the
project. **Training remains blocked**, because no acquired image carries an expert label.

Details: [`PUBLIC_DATASET_AUDIT.md`](PUBLIC_DATASET_AUDIT.md) (sources and decisions) and
[`DATA_ACQUISITION.md`](DATA_ACQUISITION.md) (procedure, policy, provenance).

---

## 1. Headline

> **No directly suitable openly licensed Tamil Nadu Early Historic pottery dataset was
> found.**

The legally reusable material that does exist is individual photographs by Wikimedia
contributors (own work, CC BY / CC BY-SA). The project acquired:

- **30 research images (17 artifacts)** of real archaeological pottery in Tamil Nadu:
  - Keezhadi site-museum displays, including incised sherds;
  - burial urns in situ at Adichanallur and Sivakalai.
- **15 supporting images (12 artifact groups)**, stored separately:
  - Tamil-Brahmi-inscribed pottery from Kerala and Sri Lanka;
  - pottery from Puducherry, Sri Lanka and of unknown provenance;
  - Tamil-Brahmi rock inscriptions, for future OCR work.

The flow the brief asked to be proven now works end to end, on real data:

```text
WEB (MediaWiki API) -> Wikimedia Commons (own-work uploads) -> licence read from source API
 -> download (SHA-1 verified) -> provenance record -> SHA-256 -> schema validation (strict)
 -> data/raw -> preprocessing (30/30) -> dataset audit -> statistics -> gate: BLOCKED
```

## 2. Acquired data

```text
Artifacts:     17 research artifacts (30 images)
               + 12 supporting artifact groups (15 images, data/external/)
Images:        30 research + 15 supporting = 45 files, 176.7 MB
Tamil-Brahmi:  0 (project label). 10 supporting files are titled Tamil-Brahmi BY THEIR
               SOURCE (3 pottery outside Tamil Nadu, 7 rock inscriptions); no project
               label is assigned.
Graffiti:      0
None:          0
Uncertain:     0
Unknown:       30 research images, 17 artifacts; script_type = unknown, pending expert annotation
Supporting:    15 (8 pottery outside the primary scope, 7 Tamil-Brahmi rock inscriptions)
```

### 2.1 Research dataset (`data/raw/tamil_nadu_pottery/wikimedia_commons/`)

| Group | Images | Artifacts | Licence | Photographer | Find-site per source |
|---|---:|---:|---|---|---|
| Keezhadi site-museum displays | 18 | 14 | CC BY-SA 4.0 | Rajeshodayanchal | **not stated** (museum photographs) |
| "Red slipped pots excavated … at Keezhadi" | 1 | (grouped with 2 museum photos) | CC BY 4.0 | N. Vivekananthamoorthy | Keezhadi |
| Adichanallur burial urns in situ | 10 | 1 (conservative grouping) | CC BY 4.0 ×4, CC BY-SA 4.0 ×6 | Perumalism, Venkadesh, Balurbala | Adichanallur |
| Sivakalai urn | 1 | 1 | CC BY-SA 4.0 | Balurbala | Sivakalai |

| Distribution | Values |
|---|---|
| By source | Wikimedia Commons: 30 |
| By class (artifacts / images) | unknown 17 / 30; every trainable class 0 / 0 |
| Licence | CC BY-SA 4.0: 25; CC BY 4.0: 5 |
| Geographic scope | tamil_nadu: 12; unknown: 18 (museum photos, find-site not stated) |
| Period | not stated by any source: 30 |
| Script | not stated by any source: 30 |
| Duplicates | 0 identical images; 0 artifacts across partitions (no split exists) |
| Rights | research_usable: yes 30; redistributable: yes (with attribution; BY-SA share-alike) 30 |

**Missing metadata** (sentinel in all 30 records, because no source states it):
- view, scale bar, catalogue number, district, excavation reference, stratigraphy and
  context reliability;
- artifact type, sherd part, fabric, surface treatment;
- inscription presence, technique and placement;
- script, label source and confidence;
- every reading, transliteration and translation field;
- every dating field.

Present: site (12, as stated by source), ware (1, "red slipped"), licence, rights and
attribution (30).

### 2.2 Supporting data (`data/external/`, never in `records.jsonl`)

| Dataset | Files | Content (as stated by source) | Licences |
|---|---:|---|---|
| `wmc_supporting_pottery_m6` | 8 | Pattanam "Tamil-Brahmi Inscription" sherd and Muziris "Tamil Brahmi writings" (Kerala); Tissamaharama Tamil-Brahmi potsherd and "South Indian type" black-and-red ware (Sri Lanka); 2 "Painted Potsherds" (Government Museum Chennai, find-site unknown); 2 Arikamedu objects (Puducherry) | CC BY-SA 4.0, CC BY 4.0, CC BY-SA 3.0 |
| `wmc_tamil_brahmi_rock_m6` | 7 | Tamil-Brahmi rock and cave inscriptions: Jambai, Nehanurpatti, Arittapatti (4), Kongar Puliyankulam | CC BY-SA 3.0 / 4.0 |

## 3. Web sources discovered

| Source | URL | Licence | Relevant? | Downloaded? | Reason |
|---|---|---|---|---|---|
| Wikimedia Commons: Keezhadi museum photos (Rajeshodayanchal) | commons.wikimedia.org/wiki/Category:Keezhadi_archeological_site | CC BY-SA 4.0 | Yes (Tamil Nadu pottery, incised sherds) | **Yes, 18** | Own work; licence from API; object-focused photos only |
| Commons: Red-Slipped-Pots-Keezhadi | commons.wikimedia.org/wiki/Category:Keezhadi_Museum | CC BY 4.0 | Yes | **Yes, 1** | Own work; Keezhadi stated by source |
| Commons: Adichanallur earthenware burial urns | commons.wikimedia.org/wiki/Category:Adichanallur_earthenware_burial_urns | CC BY 4.0 / BY-SA 4.0 | Yes (Tamil Nadu pottery) | **Yes, 10** | Own work |
| Commons: Sivakalai archaeological site | commons.wikimedia.org/wiki/Category:Sivakalai_archaeological_site | CC BY-SA 4.0 | Yes | **Yes, 1** (urn) | Other 17 are site views, not pottery |
| Commons: Adichanallur archaeological site 01–27 | commons.wikimedia.org/wiki/Category:Adichanallur_archaeological_site | CC BY-SA 4.0 | Yes | No | Near-duplicates of acquired pits; lead |
| Commons: Pattanam excavation museum / Muziris | commons.wikimedia.org/wiki/Category:Pattanam_excavation_museum | CC BY-SA 4.0 | Supporting (Kerala) | **Yes, 2** → external | Out of region |
| Commons: Arikamedu, Black and Red Ware, Tissamaharama, Egmore painted sherds | (categories in audit) | CC BY-SA / CC BY | Supporting | **Yes, 6** → external | Out of region or unknown provenance |
| Commons: Tamil Brahmi inscriptions (rock) | commons.wikimedia.org/wiki/Category:Tamil_Brahmi_inscriptions | CC BY-SA 3.0 / 4.0 | Supporting (not pottery) | **Yes, 7** → external | Future OCR |
| Commons: Mangulam models; "Paravar" news-text upload; Kovai press-style photo; Kodumanal banner (GODL) | — | claimed CC / GODL | Partly | No | Replica, doubtful own-work claim, or unverified government licence |
| Zenodo: BrahmiGAN | zenodo.org/records/14961074 | CC BY 4.0 | OCR only | No | Synthetic GAN images; excluded by the brief |
| Zenodo: Pauni Brahmi (Siddham) | zenodo.org/records/3569199, /3544411 | CC BY 4.0 (deposit) | Brahmi, Maharashtra | No | Anonymous creator; one file likely a report figure |
| Zenodo: British Museum Brahmi intaglios | zenodo.org/records/3804191 (and siblings) | CC BY 4.0 (deposit) | Brahmi, not pottery | No | Conflicts with the British Museum's own image terms |
| Zenodo: Maharashtra surface pottery | zenodo.org/records/1149684, /1149686 | CC BY 4.0 | Indian pottery | No | Spreadsheets only, no images |
| Zenodo: Early Medieval Pottery Marks (Moravia) | zenodo.org/records/7965768 | CC BY 4.0 | Analogue only | No | 219 MB of Czech drawings; not needed now |
| Figshare: Alagankulam/Keeladi pottery chemistry | springernature.figshare.com (article 12476789) | CC BY + CC0 | Knowledge base | No | Table, no images |
| Kaggle: Brahmi dataset | kaggle.com/datasets/gautamneha/brahmi-dataset | "© Original Authors" | OCR | No | Not open |
| GitHub: Tamil/Brahmi OCR repos | github.com (search) | none; one CC0 | OCR | No | No licence, or CC0 without image provenance |
| Hugging Face | huggingface.co/datasets | — | No | No | No Brahmi datasets; pottery sets irrelevant or unlicensed |
| Openverse | api.openverse.org | mirrors Commons; Flickr BY-NC | — | No (duplicates Commons) | NC needs a human decision |
| The Met / Cleveland (CC0) | collectionapi.metmuseum.org; openaccess-api.clevelandart.org | CC0 | No | No | No South Indian pottery |
| Europeana | api.europeana.eu | InC-EDU, BY-NC-SA | No | No | Not pottery or restricted |
| TNSDA corpus, reports, IA/Scribd copies | (Milestone 4) | © / none | Yes | No | Permission required; mirrors blocked in code |

## 4. Best source

**Wikimedia Commons, specifically the Keezhadi site-museum photographs by Rajeshodayanchal
(CC BY-SA 4.0).** It is the only openly licensed source with close-up photographs of
individual Early Historic Tamil Nadu sherds bearing incised marks. It combines:

- a licence stated at the original source;
- full-resolution originals (6000×4000, verified by SHA-1);
- stable identifiers (Commons page ids).

Its limits are what the audit predicted for anything short of institutional data:

- no find-site, catalogue number, context, reading or date for any object;
- no statement about whether the marks are Tamil-Brahmi or graffiti.

## 5. Biggest remaining gap

**Expert labels on identified objects.** Specifically:

1. **Labels for what we have.** An epigraphist must assign `script_type` (and, where
   visible, a reading) to the Keezhadi close-ups. The obvious candidates are site photos
   105–110. Until then they cannot train or test anything.
2. **Identity and context.** Catalogue numbers and find contexts for the museum objects.
   The Keezhadi museum or TNSDA is the only source.
3. **Volume per class.** Holdout needs ≥ 20 artifacts per class, and grouped k-fold needs
   ≥ 5. Today: 0 in every class.
4. **The `none` class.** Uninscribed sherds photographed as sherds, not whole pots in
   display cases. No open source has them.
5. **Controlled photography.** Close-up, scaled, multi-view images. The quality check
   flags 29/30 acquired images as `possibly_blurry` (a threshold still uncalibrated; see
   §6.3).

The route is unchanged from Milestone 4: **TNSDA and author permission for the 2026
corpus** (1,500+ expert-read Tamiḻi sherds with catalogue ids), plus institutional
photography of physical collections.

## 6. Engineering changes

### 6.1 New: `src/acquisition/`
- Licence allow-list and normaliser.
- Source policy A1–A9.
- Commons adapter: official API, rate limiting, `Retry-After`.
- Pipeline: staging, checksum, image checks, duplicate checks, path-safe placement,
  provenance, ingestion with rollback, manifests.
- CLI with dry run as the default.
- Provenance schema: `data/metadata/schema/acquisition_provenance.schema.json`.

### 6.2 Schema 1.2.0 (documented, backward compatible)
`script_type` and `inscription_present` gain `unknown` ("not yet examined"). It is held out
of training in `configs/project.yaml`. This was necessary: `uncertain` means "examined,
cannot assign", so using it for unexamined images would have mislabelled them.

### 6.3 Preprocessing
- **MPO support.** 20 of the 45 files are MPO (camera multi-picture JPEG). The loader now
  treats MPO as a JPEG variant, decodes the primary frame and records an info issue. Tested.
- **First real-data observation.** The Milestone 3 blur threshold (Laplacian variance
  100, measured at full resolution) flags 29/30 real photographs. It was documented as
  uncalibrated; this is the evidence that it needs recalibration, for instance by
  measuring at a fixed working resolution. Not changed in this milestone.

### 6.4 Tests updated because the dataset is no longer empty
Seven tests assumed "no data" as an invariant. They now assert invariants that hold either
way:
- every research record has matching acquisition provenance;
- no fixture ever appears in the research data;
- every image under `data/` is registered and unaltered;
- acquired records carry no invented labels;
- training stays blocked.

### 6.5 Training message
With data present but unlabelled, `python -m src.training train` now says:
"No expert-labelled training images are available: 30 acquired image(s) carry no project
label …". It still exits with code 3.

## 7. Tests and checks

```text
pytest tests/ -q                              453 passed (398 before this milestone + 55 new)
python -m src.dataset validate data/metadata/records.jsonl --verify-hashes --strict
                                              30 records, 0 errors, 0 warnings, PASS
python -m src.dataset audit                   30 records, 17 artifacts, 30 unique hashes,
                                              all script_type=unknown, validation PASS
python -m src.preprocessing run data/raw/tamil_nadu_pottery --out data/processed/tamil_nadu_pottery
                                              30 written, 0 failed (29 flagged possibly_blurry)
python -m src.dataset stats                   Artifacts: 17, Images: 30, Training readiness: BLOCKED
python -m src.dataset split                   SPLIT REFUSED (no artifacts in any trainable class)
python -m src.training train                  "Training blocked: No expert-labelled training images
                                              are available ..." (exit 3)
```

Gates on real data:
- **Passing:** G1 (canonical source), G2 (records exist), G3 (images exist),
  G4 (validation), G5 (loader and hashes), G6 (no duplicate photographs).
- **Failing, correctly:** G7–G11. There are no training-eligible labels, so no class is
  present and no split exists.

Audit caveat: the audit's "Records with dating_basis: 30" counts
`dating_basis: ["not_available"]` as present. That is a pre-existing counting quirk; no
record has a real dating basis.

## 8. Legal and rights limitations

- Every licence was read from the Wikimedia Commons API (`extmetadata.LicenseShortName`)
  for the specific file, at download time. The exact attribution line for each file is in
  `data/metadata/acquisition/provenance.jsonl`.
- CC BY-SA 4.0 (35 of 45 files) requires share-alike on adapted images. Crops or derived
  images must be released under CC BY-SA.
- The licence is the uploader's grant. "Own work" and the absence of copyright-violation
  flags are the strongest checks available without contacting each photographer.
- Images are git-ignored and not redistributed by this repository. Metadata, provenance
  and manifests are committed.
- **Network hygiene incident.** During discovery, my scratch search scripts (outside the
  repository) sent the user's email address in the User-Agent header to Wikimedia, Zenodo,
  GitHub, Figshare, Openverse, Kaggle and museum APIs. The committed client sends no
  personal data; a contact is opt-in via `ETPAI_CONTACT`. Contact-sheet thumbnail requests
  at non-standard widths also triggered Wikimedia throttling (HTTP 429, `Retry-After: 600`).
  The acquisition client honours `Retry-After`.

## 9. Recommended next acquisition route

1. **Expert annotation of the 30 acquired images.** This is the fastest way to get the
   first labelled records, and it needs no new rights. Priority: Keezhadi site photos
   105–110 (incised sherds).
2. **TNSDA / author permission** for the 2026 *Inscribed Potsherds of Tamil Nadu* corpus
   and its database (Milestone 4, Step 1). This is the only route to class volume.
3. **Institutional photography** (Keezhadi museum, Government Museum Chennai, Tamil
   University / Pondicherry University Kodumanal collections) for the `none` class and for
   controlled close-ups.
4. **Ask Commons photographers directly.** Rajeshodayanchal and Perumalism may hold more
   unpublished museum and site photographs that they would license the same way.
