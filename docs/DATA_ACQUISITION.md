# Data Acquisition

**Status:** implemented in Milestone 6 (`src/acquisition/`). Tested in
`tests/test_acquisition.py`.
**What it is for:** bringing openly licensed external images into the project in a
way that can be defended: licence read from the original source, every byte verified,
every file provenanced, nothing labelled that the source does not label.

```text
WEB (official API)
  -> candidate metadata + licence, read from the source itself
  -> policy A1-A9                         any failure: rejected, with reasons
  -> [dry run stops here: sizes and decisions reported]
  -> download to data/interim/acquisition_staging/   (size-capped, rate-limited)
  -> source checksum verified (Commons SHA-1)
  -> image checks: Milestone 3 loader P1-P7 (format, decode, dimensions, corruption)
  -> SHA-256 computed; duplicate check against records, registry and batch
  -> provenance record built and validated (acquisition_provenance.schema.json)
  -> path-safe move into data/raw/<subdir> (research) or data/external/<subdir> (supporting)
  -> research only: image_record built, validated (E*/R*) and ingested via src.dataset.ingest
       (if ingestion refuses, the placed files are removed)
  -> provenance registry + dataset manifest updated; staging cleared
```

---

## 1. Commands

```powershell
python -m src.acquisition rules                                    # A1-A9, allow-list, blocked sources
python -m src.acquisition plan configs/acquisition/milestone6_wikimedia_commons.yaml            # dry run
python -m src.acquisition plan configs/acquisition/milestone6_wikimedia_commons.yaml --commit   # acquire
python -m src.acquisition registry                                 # summary of acquired files
```

- **Dry run is the default.** It describes every candidate, applies the policy and
  reports sizes, and downloads nothing.
- Re-running is **idempotent**: files already in the registry are reported as
  `already_present` and not fetched again.
- Set `ETPAI_CONTACT` to add a contact to the User-Agent, as Wikimedia's policy
  recommends. No personal address is embedded in code.

## 2. Policy (`src/acquisition/policy.py`, `licenses.py`)

| Check | Rule |
|---|---|
| A1 | Source adapter is approved. Today only Wikimedia Commons via the MediaWiki API. |
| A2 | Source page and file URLs are https and **not** on the blocked-source list: Scribd, PDFCoffee, TOAZ, Internet Archive, tnarch.gov.in, tamildigitallibrary.in, ResearchGate, Academia.edu, and the news and mirror hosts of the Keeladi report. |
| A3 | Licence, **as returned by the source API**, is on the allow-list: CC0 1.0, CC BY 2.0–4.0, CC BY-SA 2.0–4.0. NC, ND, bare "public domain", GODL asserted by a re-uploader, and anything unrecognised are refused. |
| A4 | The uploader states own work ("Own work" / "self-made"), so the source *is* the original source. A re-upload would need its licence verified upstream, which automation cannot do. |
| A5 | No rights restrictions, and no copyright-violation, deletion or no-source categories at the source. |
| A6 | Title, record id, author and checksum are present (needed for attribution). |
| A7 | MIME type is JPEG, PNG, TIFF or WebP. |
| A8 | File size ≤ `max_file_mb` (40 MB). The batch total must be ≤ `max_total_mb` (500 MB), or the whole batch is refused for review. |
| A9 | Not excluded by the curator (the reason is recorded). |

Rights are **derived from the licence text, never guessed**. Every allowed licence
permits research use, redistribution and commercial use. All except CC0 require
attribution, and BY-SA requires share-alike. The five rights questions from Milestone 4
stay separate. The provenance record holds `research_usable`, `redistribution_allowed`
and `commercially_usable`. `viewable_online` and `downloadable` are true by construction
for anything that reached this stage.

## 3. The plan file (`configs/acquisition/*.yaml`)

The plan is the **curator's** document: which files to consider, how to group them into
artifacts, and what the source says each one shows. It contains **no licences**. Those
are read from the API at run time, so a licence changed at the source is noticed.

Per dataset: `dataset_id`, `target` (`research` | `external`), `subdir`, scope defaults.
Per item:

| Field | Meaning |
|---|---|
| `title` | Commons file title. |
| `artifact_group` | Becomes `artifact_id`, the split key. |
| `grouping_basis` | Why photographs were grouped. The rule is conservative: if two photographs might show the same object, they share an artifact id. |
| `object_type`, `find_site` | **As stated by the source**; "(not described by source)" otherwise. |
| `curation_note` | Why it was selected. Any description of image content is prefixed `AI-ASSISTED CURATION OBSERVATION, NOT A LABEL`. |
| `record` | Research-record fields the source supports (site, ware), else left to sentinels. |

The Milestone 6 plan was curated by an AI assistant. Every selection is pending human
review, and the plan's header says so.

## 4. What gets written

| Path | Content |
|---|---|
| `data/raw/tamil_nadu_pottery/wikimedia_commons/` | Research images, unmodified bytes (git-ignored). |
| `data/external/supporting_pottery/wikimedia_commons/` | Out-of-scope pottery for comparison (git-ignored). |
| `data/external/tamil_brahmi_inscriptions/wikimedia_commons/` | Tamil-Brahmi rock inscriptions, for future OCR (git-ignored). |
| `data/metadata/records.jsonl` | Research image records (schema 1.2.0), via `src.dataset.ingest`. |
| `data/metadata/acquisition/provenance.jsonl` | One provenance record per acquired file (research and external). |
| `data/metadata/acquisition/manifests/<dataset_id>.json` | Dataset manifest. |
| `data/metadata/acquisition/batches/<dataset_id>_<date>.jsonl` | The exact batch that was ingested. |

File names are `wmc_<commons page id>_<ascii slug>.<ext>`, and `image_id` is
`wmc_<page id>`, stable across re-runs.

## 5. Provenance record

Schema: `data/metadata/schema/acquisition_provenance.schema.json`. It covers every field
the brief requires:

- `source_name`, `source_url`, `dataset_name`, `dataset_record_id`,
  `original_image_url`, `download_date`;
- `license`, `license_url`, plus `license_verbatim` and `license_verified_from`;
- `copyright_holder`, `attribution_text`, `attribution_required`,
  `share_alike_required`, `redistribution_allowed`, `research_usable`,
  `commercially_usable`;
- `geographic_scope`, `find_site`, `archaeological_period`, `object_type`,
  `script_scope`;
- `source_label` (title and description **verbatim**), `project_label`,
  `project_label_basis`;
- `image_sha256`, `source_checksum`, `source_checksum_verified`;
- size, MIME type, dimensions, `local_path`, artifact grouping, curation note and curator.

**Source label and project label are separate.** `source_label` is whatever the source
said. `project_label` is `unknown` for every acquired file, with the basis "requires expert
epigraphic/archaeological annotation; not derived from the source caption or from AI
observation". Even a file titled "Tamil-Brahmi Inscription" keeps `project_label: unknown`.
The source's claim is recorded in `script_scope` as "Tamil-Brahmi (as stated in source
title)".

## 6. Schema 1.2.0

Acquired images needed an honest way to say *not yet labelled*:

- `script_type` gains `unknown`, which is held out of training (`project.yaml`
  `held_out_labels`), never trained on, and never inferred;
- `inscription_present` gains `unknown` (not yet examined), distinct from `uncertain`
  (examined, cannot tell).

The change is backward compatible (minor version), and existing 1.0.0 and 1.1.0 records
still validate.

## 7. Preprocessing change: MPO

Many cameras write MPO files: a baseline JPEG with extra preview or stereo frames
appended. 20 of the 45 selected photographs are MPO. The loader now treats MPO as a JPEG
variant (`FORMAT_ALIASES`). The primary frame (the photograph) is decoded, and an
**info** issue records that the other frames were ignored. The raw file is never
converted or modified.

## 8. Politeness

- Official API only; no HTML scraping.
- Requests are serialised with a configurable spacing (default 1 s; the Milestone 6
  commit run used 3 s).
- HTTP 429/503 responses are honoured: the client waits for `Retry-After` (capped at
  15 minutes) and retries at most 3 times.
- **Incident, recorded for transparency.** During source discovery, contact-sheet
  thumbnails were requested at non-standard widths. Wikimedia throttles those, and it
  returned HTTP 429 with `Retry-After: 600` for the first download attempt. Nothing was
  written by the failed attempt. The acquisition client now honours `Retry-After`.
  Future contact sheets should request only the standard thumbnail sizes (120, 250, 330,
  500, 960, 1280, 1920, 3840 px).

## 9. Adding a new source

1. Write an adapter implementing `describe(titles)` and `download(url, max_bytes)`
   (`src/acquisition/commons.py` is the model). The adapter must read the licence from the
   source's own API or record.
2. Add it to `APPROVED_SOURCES`, with the reason the source can be treated as original.
3. Extend `build_provenance` if the source has different identifiers.
4. Add tests with a fake fetcher. Never let a test touch the network or `data/`.

## 10. After acquisition: labels (Milestone 8)

Acquisition never labels. An acquired image enters with `script_type = unknown` and
`label_source = unknown`, whatever the source's title or caption says. The only route to a
label is:

1. independent annotation (project annotator + expert) in `app/annotate.py`;
2. expert resolution (`expert_label`);
3. a dry-run promotion plan, reviewed and approved by a human
   (`python -m src.annotation promote`), which writes only label fields and leaves every
   acquisition field untouched: source, source reference, licence, rights, image path,
   **SHA-256**, site-as-stated, collection. It checks this (P8), and verifies the file's
   SHA-256 on disk before writing (P7).

The provenance registry (`data/metadata/acquisition/provenance.jsonl`) is never modified by
promotion. A promoted record names its source annotations in `annotator` and `notes`, and
the promotion log keeps its full before and after state, so the promotion can be reversed.
See `docs/MILESTONE_8_REPORT.md`.
