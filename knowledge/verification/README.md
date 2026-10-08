# Reference verification registry

`reference_verifications.jsonl` (created on the first committed check) records **human**
checks of specific claims against the publication itself. It is append-only; a later check
supersedes an earlier one. Schema: `data/metadata/schema/reference_verification.schema.json`;
rules V1–V8 and K6 (`python -m src.knowledge rules`).

**No reference has been verified.** As of Milestone 8 the registry is empty: nobody has yet
checked R1, S01 or S03 against a physical or authorised copy.

- `python -m src.knowledge status` shows the effective status of the key references (R1, S01, S03).
- `python -m src.knowledge claims --ref S03` lists the claims the project relies on S03 for.
- `python -m src.knowledge verify ...` records one check. It is a dry run unless `--commit` is given.

What counts as verification:
- a named human opened the physical publication, or an authorised digital copy, or the
  publisher's open-access version;
- found the claim at a stated page / plate / figure / catalogue number;
- and recorded where the copy is held.

What does not count: a citation found online, a library-catalogue entry, a quotation in
another work, an unauthorised copy (see `docs/DATA_SOURCE_AUDIT.md` S06, S08), or any
software output. If the publication cannot be consulted, record `source_unavailable` or
nothing. The claim stays unverified.

Verifying one claim verifies only that claim. Wherever the reference's status is shown,
the verified claims are listed with it.

## Software pre-checks (`source_prechecks.json`, Milestone 11) — not verification

A software agent read copies the project may consult (the journal's open-access PDF of S03, the Tamil
Digital Library copy of S01, the BnF catalogue record of R1) and recorded where each claim appears: page,
copy URL, the document's SHA-256 and a short excerpt. Schema `source_precheck.schema.json`, rules PC1–PC8
(`checked_by` is always `software_agent`, `effect` is always `none`). Pre-checks change no status, are
not read by the reasoning or by promotion, and are shown under the badge *Software pre-check · not
verification*.

To verify a pre-checked claim, open the copy at the page given and read the passage, then:

```powershell
python -m src.knowledge prechecks                        # what was found where
python -m src.knowledge verify-from-precheck PC-S03-02 --verifier <your id> --role project_member `
    --date YYYY-MM-DD --i-opened-the-source               # dry run; add --commit
python -m src.knowledge verify-from-precheck PC-S03-05 ... --status discrepancy_found --notes "..."   # if you confirm the difference
```

The record is yours: your id, your date, the copy you opened; it is validated by V1–V10 like any other.
R1's claim cannot be pre-checked online (no authorised copy); it needs a library copy and `verify`.
