# ⚠️ TEST FIXTURES — NOT ARCHAEOLOGICAL DATA

Everything in this directory is **synthetic test data invented to exercise the validation
code**. None of it describes a real object, site, inscription, reading, date or publication.

## The rules

1. **Nothing here is research data.** Fixtures are never counted by the dataset audit, never
   ingested into `data/metadata/records.jsonl`, and never used to train anything.
2. **Fixtures never live under `data/`.** Not `data/raw/`, not `data/interim/`, not
   `data/processed/`, not `data/metadata/`. That separation is what keeps an audit count
   honest.
3. **Every fixture is marked.** Identifiers use `FIXTURE_` prefixes; text fields say
   `FIXTURE_..._PLACEHOLDER`; `notes` carries a pointer back to this file.
4. **No plausible archaeology.** Site names are `FIXTURE_SITE_A`, not real Tamil Nadu sites.
   Transcriptions are placeholder strings, not Tamil-Brahmi readings. Dates are labelled as
   placeholders. A fixture must never be mistakable for a genuine record if it escapes this
   directory.

The audit command enforces (1) in code: any source other than `data/metadata/records.jsonl`
prints a `SOURCE IS NOT THE RESEARCH DATASET` banner, and
`src/dataset/readiness.py` blocks training regardless of what fixtures exist.

## Layout

```
valid/
  base_record.json            one complete, fully-populated valid record (all 59 fields)
  minimal_record.json         only the 10 required fields — valid, but warns under R15
  multi_photo_artifact.jsonl  three photographs of one artifact, one split (R3/R4 happy path)
  unknown_heavy_record.json   correct use of unknown / not_available / not_applicable
invalid/
  empty_string.jsonl          empty string where a sentinel belongs            (E1)
  missing_required.jsonl      required fields absent                          (E1)
  year_zero.jsonl             dating bound of 0 — there is no year 0           (E1)
  bad_view.jsonl              unsupported `view` enum value                   (E1)
  reversed_dates.jsonl        lower year later than upper year                (R8)
  dating_no_basis.jsonl       numeric date with no source, empty basis        (E1/R9)
  script_inscription_clash.jsonl  inscription_present=no with a script        (R5/R6)
  duplicate_hash.jsonl        one photograph claimed by two artifacts         (R4)
  split_conflict.jsonl        one artifact spread across two splits           (R3)
  duplicate_image_id.jsonl    same image_id twice                             (R1)
  bad_label_source.jsonl      unsupported label_source value                  (E1)
  stratigraphy_unstratified.jsonl  stratigraphic date on a surface find       (R10)
  other_script_no_detail.jsonl     other_script without naming the script     (R7)
  excluded_no_reason.jsonl    split=excluded with no reason                   (R12)
  region_outside_image.jsonl  bounding box larger than the image              (R13)
  unknown_rights.jsonl        redistributable=unknown — blocked on export     (R11)
  unverified_test_label.jsonl unverified annotation in the test split          (R14, warning)
conversion/
  roundtrip.jsonl             exercises Unicode, semicolons in free text,
                              null integers, empty arrays, nested regions
```

The Tamil text in `conversion/roundtrip.jsonl` is the ordinary word *சோதனை* ("test"),
present only to prove UTF-8 survives the CSV round trip. It is not a transcription,
transliteration or translation of anything.
