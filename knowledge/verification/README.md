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
