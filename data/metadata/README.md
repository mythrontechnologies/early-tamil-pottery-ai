# Dataset Documentation — Early Tamil Pottery AI

**Schema version:** 1.0.0
**Status:** schema defined, **no data ingested yet** (see [`../../docs/DATA_INVENTORY.md`](../../docs/DATA_INVENTORY.md))
**Authoritative schema file:** [`schema/image_record.schema.json`](schema/image_record.schema.json)

This document explains every field in a dataset record. The JSON Schema is the machine-readable
contract; this README is the human-readable explanation of intent. Where the two disagree, the
schema file wins and this README is the bug.

---

## 1. The unit of a record

**One record = one photograph.** Not one artifact.

A single physical sherd may be documented by several photographs (exterior, interior, close-up of
the inscription, a rubbing, a published line drawing). Each gets its own record, and **all of them
share one `artifact_id`**.

```
image_id                              artifact_id
─────────────────────────────────────────────────────
KDM_0041__exterior__1                 KDM_0041
KDM_0041__closeup__1                  KDM_0041     ← same physical object
KDM_0041__rubbing__1                  KDM_0041
```

`artifact_id` is the **train/validation/test split key**. This is not a stylistic preference; it is
the single most important integrity property of this dataset. See
[`../../docs/SPLIT_METHODOLOGY.md`](../../docs/SPLIT_METHODOLOGY.md).

---

## 2. How missing information is recorded

**Never invent a value.** Three distinct sentinels exist because they mean genuinely different
things, and conflating them destroys the ability to audit the dataset later:

| Sentinel | Meaning | Example |
|---|---|---|
| `unknown` | The value exists in reality but we have not determined it. | The sherd came from *somewhere*, but the site is not recorded. |
| `not_available` | The value was not recorded by the source we are working from. | The excavation report simply does not print a layer number. |
| `not_applicable` | The field does not apply to this record. | `transcription` on a sherd with no inscription. |

Rules:

- **Empty strings are forbidden.** Absence must be explicit and typed.
- Integer fields use JSON `null` rather than a sentinel string (`image_width_px`,
  `character_count_visible`, `dating_lower_year`, `dating_upper_year`).
- `dating_basis` is an array and may not be empty — use `["unknown"]`.
- A record that omits an optional field entirely is *not* an error at the schema level, but the
  Milestone 2 validator will warn. Prefer an explicit sentinel over omission.

---

## 3. File formats

| Layer | Format | Location | Produced by |
|---|---|---|---|
| Annotation (human-facing) | CSV / spreadsheet | `annotations/*.csv` | annotators |
| Canonical (machine-facing) | JSON Lines, one record per line | `records.jsonl` | Milestone 2 ingestion |
| Contract | JSON Schema draft 2020-12 | `schema/image_record.schema.json` | this milestone |

**CSV ⇄ JSONL conventions** (implemented in Milestone 2, specified here):

- Array fields (`dating_basis`, `alternative_readings`) are semicolon-separated in CSV:
  `stratigraphy;palaeography`
- `inscription_regions` is a JSON string inside the CSV cell.
- `null` integers are the empty cell in CSV.
- Any leading-underscore key is a comment and is stripped before validation. This is how
  `schema/_example_record.json` carries its `_WARNING` banner.

---

## 4. Field reference

### 4.1 Identity and file

| Field | Type | Req. | Notes |
|---|---|:--:|---|
| `schema_version` | string | | Schema version the record was authored against, e.g. `1.0.0`. |
| `image_id` | string | ✔ | Unique per **photograph**. Convention `<artifact_id>__<view>__<n>`. Pattern-constrained: alphanumerics, `_`, `.`, `-`. |
| `artifact_id` | string | ✔ | Identifies the **physical object**. **Split key.** If you cannot tell whether two photographs show the same sherd, give them the *same* id (conservative grouping) and say so in `notes`. Over-merging costs a little training data; under-merging silently inflates your test scores. |
| `image_path` | string | ✔ | Relative to `data/raw/`, forward slashes. |
| `image_sha256` | hex(64) \| sentinel | | Content hash. Catches the same photograph entering twice under different ids — a direct leakage route that `artifact_id` grouping alone will not catch. |
| `view` | enum | | `exterior`, `interior`, `profile`, `closeup`, `detail`, `rubbing`, `drawing`, `composite`, `unknown`. `rubbing` and `drawing` are **not photographs of the object** — they are scholarly renderings, and a classifier trained on them will not transfer to photographs. Track them separately. |
| `image_width_px`, `image_height_px` | int \| null | | Of the original file in `data/raw/`. |
| `scale_bar_present` | `yes`/`no`/`unknown` | | Whether a measuring reference is visible. Without one, absolute-size features are unusable. |

### 4.2 Provenance and rights

| Field | Type | Req. | Notes |
|---|---|:--:|---|
| `source` | enum | ✔ | `museum_collection`, `excavation_report`, `published_epigraphic_corpus`, `academic_publication`, `fieldwork_photograph`, `online_repository`, `other`, `unknown`. |
| `source_reference` | text | | Must be specific enough that a third party can find the original: page, plate, figure, accession, URL. "Mahadevan" is not a reference; a volume/page/plate is. |
| `collection` | text | | Holding institution. |
| `catalogue_reference` | text | | Accession / corpus number **as printed**. Never construct one. |
| `license` | string | ✔ | Verbatim rights status. Recommended: SPDX id (`CC-BY-4.0`), `public_domain`, `permission_granted_see_rights_notes`, `rights_reserved_no_redistribution`, `permission_pending`, `unknown`. |
| `redistributable` | `yes`/`no`/`unknown` | ✔ | Whether the image may ship with the dataset. **`unknown` is treated as `no`.** Most Indian excavation-report plates and museum photographs are *not* freely redistributable; assume restriction until confirmed. |
| `rights_notes` | text | | Permission correspondence, embargo terms, attribution required. |

### 4.3 Archaeological context

| Field | Type | Req. | Notes |
|---|---|:--:|---|
| `site` | text | | Site name **as published**. Never invent a site. Transliteration varies in the literature (e.g. Keeladi / Keezhadi / Kīḻaṭi); record the source's spelling here and normalise in the knowledge base (Milestone 11), not here. |
| `site_district`, `site_state` | text | | Administrative location. |
| `excavation_reference` | text | | Season / trench / quadrant as published. |
| `stratigraphic_context` | text | | Layer / depth / phase, **verbatim**. Do not paraphrase into a period. |
| `context_reliability` | enum | | `excavated_stratified`, `excavated_unstratified`, `surface_collection`, `museum_unprovenanced`, `unprovenanced`, `unknown`. **This field governs how much weight stratigraphic evidence may carry in Milestone 10 chronological reasoning.** A surface find carries no stratigraphic date, however well published. |

### 4.4 The artifact

| Field | Type | Req. | Notes |
|---|---|:--:|---|
| `artifact_type` | enum | | `pottery_sherd`, `complete_vessel`, `lid`, `ring_stand`, `other`, `unknown`. |
| `pottery_type` | enum | | Ware category **as published**: `black_and_red_ware`, `black_ware`, `red_ware`, `red_slipped_ware`, `russet_coated_painted_ware`, `rouletted_ware`, `coarse_red_ware`, `grey_ware`, `amphora`, `terra_sigillata`, `other`, `unknown`, `not_available`. Do not assign a ware from a photograph unless the source states it or an expert annotator determines it — ware identification depends on fabric and section, not surface colour in a JPEG. |
| `sherd_part` | enum | | `rim`, `neck`, `shoulder`, `body`, `carination`, `base`, `handle`, `spout`, `complete_profile`, `other`, `unknown`, `not_available`. |
| `fabric_notes` | text | | Free text from the source. |
| `surface_treatment` | enum | | `slipped`, `burnished`, `plain`, `painted`, `other`, `unknown`, `not_available`. |

### 4.5 Inscription and classification label

This block carries the **target label for Milestone 4**.

| Field | Type | Req. | Notes |
|---|---|:--:|---|
| `inscription_present` | `yes`/`no`/`uncertain` | ✔ | Any deliberate mark, script or not. |
| `script_type` | enum | ✔ | **The classifier label.** See below. |
| `script_type_other_detail` | text | | Which script, when `script_type = other_script`. |
| `label_source` | enum | ✔ | `published_epigraphic_corpus`, `excavation_report`, `museum_catalogue`, `expert_annotation`, `project_annotation_unverified`, `unknown`. **Determines whether the label is usable as ground truth.** |
| `label_confidence` | enum | | `high`/`medium`/`low`/`unknown`. |
| `inscription_technique` | enum | | `incised_pre_firing`, `incised_post_firing`, `incised_timing_unknown`, `painted`, `stamped`, `impressed`, `other`, `unknown`, `not_applicable`. Pre- vs post-firing is archaeologically significant and frequently undetermined — `incised_timing_unknown` exists so that annotators are not forced to guess. |
| `inscription_placement` | enum | | `exterior_body`, `exterior_rim`, `exterior_base`, `exterior_shoulder`, `interior`, `other`, `unknown`, `not_applicable`. |
| `inscription_regions` | array | | Bounding boxes; supervision for Milestone 6. Coordinate system `xywh_pixels`, origin top-left, measured on the **original unrotated** image in `data/raw/`. `region_label` ∈ `inscription`, `graffiti`, `possible_inscription`, `decoration_non_script`, `damage`, `other`. **An empty array means "not yet annotated", not "no inscription"** — that is what `inscription_present` records. |
| `character_count_visible` | int \| null | | `null` = not counted. |

**`script_type` values**

| Value | Meaning |
|---|---|
| `tamil_brahmi` | Tamil-Brahmi / Tamili script. |
| `graffiti` | Non-script or undeciphered incised marks (the "megalithic graffiti symbols" class of the literature). |
| `tamil_brahmi_and_graffiti` | Both occur on the same sherd. |
| `none` | No visible deliberate mark. |
| `uncertain` | A mark is present but cannot be assigned. |
| `other_script` | A different script — Prakrit-Brahmi, Vatteluttu, Grantha, later Tamil. |

Milestone 4 trains a **4-class** classifier over `tamil_brahmi`, `graffiti`, `none`, `uncertain`.
`other_script` and `tamil_brahmi_and_graffiti` records are **held out** of that first model rather
than being forced into an ill-fitting class. They are retained in the dataset because they are real
and will matter later.

Note that `graffiti` vs `tamil_brahmi` is a genuinely contested boundary in the scholarship for
some marks, not merely a hard visual problem. `uncertain` is a legitimate, expected label — not a
failure to annotate.

### 4.6 Reading

| Field | Type | Req. | Notes |
|---|---|:--:|---|
| `transcription` | text | | **As published**, or as read by an expert annotator. Never supply characters that are not visible. Preserve the source's editorial conventions for damaged and restored text. |
| `transcription_encoding` | enum | | `tamil_unicode`, `brahmi_unicode`, `romanized`, `mixed`, `not_available`, `not_applicable`. Recorded because Tamil-Brahmi readings circulate in at least three encodings and silently mixing them corrupts any character-level model. |
| `transliteration` | text | | |
| `transliteration_scheme` | enum | | `iso_15919`, `mahadevan_2003`, `other`, `unknown`, `not_available`, `not_applicable`. ISO 15919 is the project default for new transliteration. |
| `translation_en`, `translation_ta` | text | | |
| `reading_status` | enum | | `published_secure`, `published_tentative`, `disputed`, `unread`, `illegible`, `not_applicable`, `unknown`. **Records marked `disputed` or `published_tentative` must never be shown by the prototype as settled readings.** |
| `alternative_readings` | array of strings | | Competing readings, each with inline attribution: `"reading (Author Year)"`. Populating this is how the system meets the "show alternatives rather than inventing a definite reading" requirement. |
| `reading_source` | text | | Who produced the reading above, with citation. |

### 4.7 Dating

| Field | Type | Req. | Notes |
|---|---|:--:|---|
| `dating_text` | text | | **The date as the source states it, verbatim** (e.g. `"c. 2nd century BCE"`). This is the primary record. |
| `dating_lower_year` | int \| null | | Signed year. **Negative = BCE, positive = CE. There is no year 0** (1 BCE = `-1`, 1 CE = `1`). Derived convenience only. |
| `dating_upper_year` | int \| null | | As above. |
| `dating_basis` | array of enum | | `stratigraphy`, `radiocarbon_c14`, `ams_radiocarbon`, `thermoluminescence_osl`, `palaeography`, `pottery_typology`, `associated_finds`, `associated_coins`, `published_attribution`, `unknown`, `not_available`. Non-empty. **This is what makes Milestone 10 auditable** — it records *why* a date is claimed, not just what it is. |
| `dating_reliability` | enum | | `published_secure`, `published_tentative`, `disputed`, `project_estimate`, `unknown`. |
| `dating_source` | text | | Citation. Required in practice whenever a numeric bound is given. |

The `dating_text` / numeric-bounds split matters: converting `"c. 2nd century BCE"` to
`(-200, -101)` discards the hedge in "c.". The verbatim text is the record of what was actually
claimed; the integers exist only so code can compute range overlap (Milestone 16 evaluation).

### 4.8 Publication

| Field | Type | Req. | Notes |
|---|---|:--:|---|
| `publication` | text | | Full bibliographic reference. **Never invent a publication.** |
| `publication_doi_or_url` | text | | |

### 4.9 Dataset management

| Field | Type | Req. | Notes |
|---|---|:--:|---|
| `split` | enum | | `train`, `val`, `test`, `unassigned`, `excluded`. Assigned in Milestone 2 **by `artifact_id`**. |
| `split_exclusion_reason` | text | | Why a record is `excluded`. Excluded records are kept, never silently deleted. |
| `verification_status` | enum | ✔ | `verified_against_source`, `needs_verification`, `unverified`. **A record that is not `verified_against_source` must not back any claim the prototype presents to a user as evidence.** |
| `annotator` | text | | |
| `annotation_date` | `YYYY-MM-DD` \| sentinel | | |
| `notes` | text | | Anything an auditor would want to know. |

---

## 5. Validating a record

The Milestone 2 ingestion tool will wrap this, but the check is plain `jsonschema`:

```python
import json
from jsonschema import Draft202012Validator

schema = json.load(open("data/metadata/schema/image_record.schema.json"))
record = json.load(open("data/metadata/schema/_example_record.json"))
record = {k: v for k, v in record.items() if not k.startswith("_")}   # strip comment keys

errors = sorted(Draft202012Validator(schema).iter_errors(record), key=lambda e: e.path)
for e in errors:
    print(list(e.path), e.message)
```

Cross-field rules that JSON Schema does **not** express, and which the Milestone 2 validator will
enforce, are listed in [`../../docs/SPLIT_METHODOLOGY.md`](../../docs/SPLIT_METHODOLOGY.md) §4.

---

## 6. What this schema deliberately does not do

- **It does not assign a date to anything.** Dates are copied from sources with their basis and
  reliability attached, or left `null`.
- **It does not resolve site-name spellings, ware typologies, or script chronology.** Those belong
  in the knowledge base (Milestone 11), where they can carry citations and be revised without
  rewriting every record.
- **It does not permit a "best guess".** There is no field for one. `label_confidence: low` plus
  `verification_status: unverified` is the supported way to record a tentative annotation.

---

*This dataset supports an AI-assisted research prototype. It is not a substitute for expert
epigraphic or archaeological assessment.*
