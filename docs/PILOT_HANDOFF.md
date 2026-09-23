# Expert Annotation Pilot: Handoff Brief

**Project:** Early Tamil Pottery AI, an assistive research tool for Early Historic Tamil Nadu
pottery. It is not an autonomous archaeologist.
**For:** (1) the expert epigraphist/archaeologist, (2) the project annotator, (3) whoever checks
the references against the publications.
**Generate the worksheets:** `python -m src.annotation handoff` → `outputs/pilot_handoff/`

Nothing in this pack tells you what the sherds carry. No script, reading, translation or date
has been entered for them by anyone, and none has been suggested by software. That is what
we are asking you to establish, or to record as uncertain.

---

## 1. The six photographs

| Artifact | Image | Photograph (Wikimedia Commons) |
|---|---|---|
| `WMC_KEELADI_MUS_SHERD_105` | `wmc_157308858` | [Keeladi-archeological-site-photos 105](https://commons.wikimedia.org/wiki/File:Keeladi-archeological-site-photos_105.jpg) |
| `WMC_KEELADI_MUS_SHERD_106` | `wmc_157308869` | [Keeladi-archeological-site-photos 106](https://commons.wikimedia.org/wiki/File:Keeladi-archeological-site-photos_106.jpg) |
| `WMC_KEELADI_MUS_SHERD_107` | `wmc_157308866` | [Keeladi-archeological-site-photos 107](https://commons.wikimedia.org/wiki/File:Keeladi-archeological-site-photos_107.jpg) |
| `WMC_KEELADI_MUS_SHERD_108` | `wmc_157308870` | [Keeladi-archeological-site-photos 108](https://commons.wikimedia.org/wiki/File:Keeladi-archeological-site-photos_108.jpg) |
| `WMC_KEELADI_MUS_SHERD_109` | `wmc_157308868` | [Keeladi-archeological-site-photos 109](https://commons.wikimedia.org/wiki/File:Keeladi-archeological-site-photos_109.jpg) |
| `WMC_KEELADI_MUS_SHERD_110` | `wmc_157308873` | [Keeladi-archeological-site-photos 110](https://commons.wikimedia.org/wiki/File:Keeladi-archeological-site-photos_110.jpg) |

Photographs by Rajeshodayanchal, CC BY-SA 4.0, via Wikimedia Commons. They are close-ups of
sherds displayed at the Keezhadi site museum, taken through or near display glass. The project
knows **nothing else** about them: no excavation context, trench, layer, catalogue number or
publication is recorded.

**About the uploader's caption.** Each Commons page says the Keeladi cultural deposit "could be
safely dated between 6th century BCE and 1st century CE". That describes the site's deposit as
a whole, as the uploader understood it. It is **not** a date for any of these sherds, and it
must not be entered as one.

## 2. For the expert and the project annotator

Work **independently**. Do not look at each other's annotation, or discuss the sherds, before
both have saved. The disagreement between you is data. The project measures it, and the expert
settles it afterwards.

**Tool:** `streamlit run app/annotate.py`. Enter your id. Choose *Project annotator* or *Expert*
(experts state their qualification and affiliation). "Pilot artifacts only" is on. For each
sherd:

| Decide | How |
|---|---|
| Is there an inscription or mark? | `yes` / `no` / `uncertain` (examined, cannot tell) |
| What kind? | `tamil_brahmi`, `graffiti` (non-script marks), `tamil_brahmi_and_graffiti`, `none`, `uncertain`, `other_script`, with your confidence |
| Where? | zoom, then "Add region from zoom window" for every mark |
| Reading | **only characters you can actually see**; editorial marks for doubtful/lost letters; alternatives with their source; a confidence |
| What is it? | inscription type and interpretation type **only if a reading supports it** |
| Translation | only with a cited source. A personal name gets none ("Proper name; no literal translation established.") |
| Linguistic observations | each with a source |
| Dating evidence | one row per piece of evidence, with its type, what you observed, the years it supports (negative = BCE; there is no year 0) and its source. A script's general date range is not a date for this sherd. |
| References | knowledge-base ids (R1, S01, S03, R6 …) with page/plate |
| Usability | per photograph: can the sherd / the inscription / the characters be seen? |
| Review state (experts) | `expert_reviewed` when you stand by it; `disputed` if you think it cannot be settled from these photographs |

An honest `uncertain` or `unknown` is a good answer. A confident guess is the one thing that
damages the dataset. The worksheets `pilot_worksheet_expert.csv` and
`pilot_worksheet_project_annotator.csv` have the same columns, if you prefer to note your
observations on paper first. The tool is where the annotation is recorded and checked.

**After both have saved:**

```powershell
python -m src.annotation pilot        # is every sherd complete?
python -m src.annotation agreement    # where the two annotators differ, field by field
```

With six sherds the agreement statistic (Cohen's κ) is printed but marked *not interpretable*.
The item-by-item list of disagreements is what matters. The expert resolves each one by
revising **their own** annotation.

## 3. For the reference verifier

`outputs/pilot_handoff/verification_checklist.csv` lists the **10 claims** the project relies on
R1, S01 and S03 for. Each row gives the claim and the locator the project transcribed; that
locator is **unverified**. For each claim you can check:

1. Open the publication: a physical copy, an authorised digital copy, or the publisher's
   open-access version. **An unauthorised online copy does not count**, and neither does a
   citation or quotation found elsewhere.
2. Find the claim. Fill in `status`, `locator_found` (page / plate / figure / catalogue no.),
   `verifier_id`, `verifier_role`, `verification_date`, `source_location` (library and
   shelfmark, or URL) and `source_access`.
   - It says what the project says → `verified_against_source`.
   - It says something different → `discrepancy_found`, and write what it says in `notes`.
   - You could not consult it → `source_unavailable`, `source_access = not_accessed`, and why in `notes`.
3. Leave rows you did not check **blank**. They stay unverified.

Import (dry run first, all-or-nothing):

```powershell
python -m src.knowledge import-checklist outputs\pilot_handoff\verification_checklist.csv
python -m src.knowledge import-checklist outputs\pilot_handoff\verification_checklist.csv --commit
python -m src.knowledge status
```

| Ref | Work | Claims | Note |
|---|---|---|---|
| R1 | Mahadevan, *Early Tamil Epigraphy* (2003; rev. ed. 2014) | 1 | The project has no authorised copy. |
| S01 | Rajan & Sivanantham, *Inscribed Potsherds of Tamil Nadu* (TNSDA 2026) | 3 | Read via Tamil Digital Library; not checked. |
| S03 | Ramakrishna et al., "Excavations at Keeladi …", *Heritage* 6 (2018) | 6 | Transcribed; not checked. |

Two citation questions need a scholar's answer, and the project has not guessed them. The
"Early AMS determinations" position cites `R3`, while the knowledge base holds `R3a` (Rajan &
Yatheeskumar, *Pragdhara* 21–22). Is that the intended work? The "association not secure"
objection cites `R5`, which is not in the knowledge base. Which work is it?

## 4. What happens next (project team)

Only artifacts whose expert annotations agree and are `expert_reviewed` can become training
labels, and only through a reviewed, reversible step:

```powershell
python -m src.annotation promote --pilot         # dry run: every change, before -> after
python -m src.annotation promote --execute --approve <digest> --approver <id>
```

Disputed sherds, project-only labels and anything a model produced are never promoted.
Training stays blocked regardless: each class needs 20 artifacts, including sherds with **no**
mark, so this pilot tests the workflow and cannot yet supply a training set.
