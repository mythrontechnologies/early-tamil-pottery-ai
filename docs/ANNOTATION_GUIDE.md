# Annotation Guide

**For:** anyone annotating artifacts in this project: project annotators and experts.
**Tool:** `streamlit run app/annotate.py`
**Store:** `data/metadata/annotations/annotations.jsonl` (append-only; created on first save)
**Schema:** `data/metadata/schema/annotation.schema.json`; rules N1–N14
(`python -m src.annotation rules`)

> **The one rule.** Record what *you* can see or what a *cited source* says, and nothing
> else. If you cannot tell, leave it `unknown`. An honest `unknown` is useful; a confident
> guess corrupts the dataset silently.

---

## 1. Who you are when you annotate

Choose one in the sidebar. It becomes the annotation's `provenance_type`, and it is never
blended with anyone else's.

| You are recording | `provenance_type` | Role | Can become ground truth? |
|---|---|---|---|
| your own examination of the photographs | `project_annotation` | project annotator | **No.** At best "provisional". |
| what a published source says about this object (you cite it) | `source_information` | project annotator | No. It is the source's claim, transcribed by you, and must cite a reference (N5). |
| your judgement as a qualified archaeologist or epigraphist | `expert_annotation` | expert (state qualification and affiliation) | **Only if** marked `expert_reviewed` and the experts agree. |
| model output | `ai_prediction` | ai_model | **Never.** Shown separately, used as nothing. |

The source's own description (the Commons title and caption) is shown above the photographs.
It is **not** a label. Do not copy "Tamil-Brahmi" into the script field because a file name
says so.

## 2. Unknown, uncertain, not available, not applicable

| Value | Means | Example |
|---|---|---|
| `unknown` | not determined, usually because not examined | You did not look for an inscription. |
| `uncertain` | examined, and it cannot be decided | Marks are visible, but you cannot say whether they are script. |
| `not_available` | there is nothing to determine it from | No reading exists. |
| `not_applicable` | the question does not apply | Translation of a personal name. |

Consistency rules the tool enforces (N6):
- `inscription_present = unknown` ⇒ `script_type = unknown`. You cannot name a script for
  something you did not examine.
- `inscription_present = no` ⇔ `script_type = none`, and the reading is `not_applicable`.
- Any asserted `script_type` needs a `script_confidence`.

## 3. What to annotate, section by section

### Object
`object_type` and `pottery_type` (ware) only if **you can see it or a source states it**.
Ware identification from a museum photo through glass is usually `unknown`. Free-text fields
(fabric, surface, manufacturing, colour, decoration, condition) describe what is visible. Write
"red surface" rather than "red slipped ware" unless you can tell a slip from the fabric.

### Inscription
- **Presence:** `yes`, `no` or `uncertain` after looking; otherwise `unknown`.
- **Script:** `tamil_brahmi`, `graffiti` (non-script marks), `tamil_brahmi_and_graffiti`,
  `other_script`, `uncertain`, `none`. If you are not trained in Brahmi palaeography, a
  script identification is at most `low` confidence, and `uncertain` is often the honest choice.
- **Inscription type** is a **project annotation category** (personal_name, word, mark,
  graffiti, donative, ownership, symbol, uncertain, unknown). It is working vocabulary, not an
  archaeological typology. Use it only when you can say what the mark does.
- **Regions:** zoom to the inscription, then "Add region from zoom window". Coordinates are
  **normalised** (0–1) on the stored image. The original file is never touched. Mark every
  photograph on which you can see the inscription.
- **Characters visible:** count only characters you can distinguish (0 = not counted).
- **Reading:** only characters you can actually see. Keep editorial marks for damage
  (e.g. `[ta]` for a doubtful letter, `..` for lost ones). **Never complete a word from
  expectation.** Every reading needs a source (`this_annotator` or a reference id) and a
  confidence (N7).
- **Alternative readings:** record them with their source. Disagreement is information.

### Translation / meaning
| Situation | `interpretation_type` | `translation` | `meaning` |
|---|---|---|---|
| no reading | `not_applicable` | `not_available` | — |
| a personal name | `personal_name` | **`not_applicable`** (forced) | "Proper name; no literal translation established." |
| a word with a sourced gloss | `lexical_word` | the gloss | explanation; `translation_source` required (N8) |
| a sign, not text | `symbol` / `not_translatable` | `not_applicable` | — |
| a reading exists but you do not know what it means | `unknown` | `not_available` | — |

The system will say **"No translation established."** rather than invent one. You should too.

### Linguistic features
One row per observation (word_form, orthography, phonology, morphology, vocabulary,
grammatical_feature) with a source. Features do **not** date anything by themselves. To use
one for dating, also add a `linguistics` dating-evidence row with bounds and a citation.

### Dating evidence
One row per piece of evidence. Years are signed: **negative = BCE, positive = CE, there is no
year 0** (−1 is 1 BCE, 1 is 1 CE).

| Column | Guidance |
|---|---|
| evidence_type | palaeography, linguistics, pottery_typology, archaeological_context, stratigraphy, absolute_dating, associated_material, historical_reference, comparative_inscription |
| observation | what you observed, in words |
| supports_start/end_year | the range this evidence supports; leave empty if it bounds nothing |
| association | **required** for stratigraphy and absolute_dating: how securely the dated material is tied to *this* object. Anything but `direct` / `same_context_secure` is not used to date it (Position D, `CHRONOLOGICAL_SCOPE.md`). |
| source_reference | a reference id, or `annotator_observation` |

An overall `estimated_start/end_year` is optional, and needs evidence, a real basis and a
confidence (N9). Usually leave it empty and let the reasoning layer combine the evidence.

**Do not** use the script's general date range as evidence for this object. **Do not** use
Keeladi's site-level AMS dates for an object whose context is not recorded.

### References
Each needs a `ref_id`, a citation, a locator (page, plate, figure) and a verification status:
- `verified_against_source`: **only** if the verification registry records a human check of
  this reference (`python -m src.knowledge status`). Rule N14 rejects a self-declared
  `verified_against_source`, and the reasoning layer uses the registry's status either way
  (Milestone 8, §7 below);
- `bibliographic_only`: the work exists, the claim is not checked;
- `unverified`.

Ids already in `knowledge/references/references.yaml` (R1, S01, S03, R6, …) can be cited
without re-entering them.

### Archaeological usability (per photograph)
`sherd_visible`, `inscription_visible`, `characters_readable`, `morphology_visible`,
`usable_for_annotation`. This is **your** judgement of usefulness for archaeology. It is
deliberately separate from the technical quality flags from preprocessing
(`python -m src.annotation quality`). A photograph flagged `possibly_blurry` may be perfectly
usable, and a sharp one may show nothing. Do not skip photos because of a technical flag.

## 4. Revisions, multiple annotators, review states

- **Saving always appends.** If you save again for the same artifact, the new record
  `supersedes` your previous one. The old record stays in the file.
- **You may only supersede your own annotation** (N11). To disagree with someone, save your
  own annotation. Disagreement is kept and analysed (`python -m src.annotation summary`).
- **Review states:** `unreviewed` → `project_reviewed` → `expert_reviewed`, or `disputed`.
  **`expert_reviewed` is reserved for expert annotations** (N4). A project annotation can
  never be made equivalent to an expert label.
- **Resolution** (per artifact): `expert_label` (expert-reviewed experts agree; the only
  status that is `ground_truth_eligible`), `disputed`, `provisional` (project annotators
  agree; **not** ground truth), `project_disagreement`, `unannotated`.

## 5. Do not

- label from the file name, the Commons caption, or an AI suggestion;
- read characters you cannot see, or "restore" a name you expect;
- translate a personal name;
- give a date without evidence, or use year 0;
- copy a site's date to an object whose context is not recorded;
- mark your own annotation `expert_reviewed`;
- edit `records.jsonl`, the provenance registry, or `annotations.jsonl` by hand.

## 6. After annotating

```powershell
python -m src.annotation validate     # N1-N14 over the whole store + knowledge base K1-K5
python -m src.annotation summary      # status and disagreements per artifact
python -m src.reasoning analyze <artifact_id>   # what the reasoning layer concludes, and why
```

Annotations do **not** change the training records. `script_type` in `records.jsonl` stays
`unknown` until an expert label is promoted by the explicit, reviewed process in §9.

## 7. The Milestone 8 pilot: six Keezhadi close-ups

The brief to hand to the expert and annotator is `docs/PILOT_HANDOFF.md`
(`python -m src.annotation handoff` writes the blank worksheets).

The pilot artifacts are `WMC_KEELADI_MUS_SHERD_105` … `_110` (Wikimedia Commons
"Keeladi-archeological-site-photos" 105–110), listed in `configs/project.yaml`
`annotation_pilot`. The sidebar's **"Pilot artifacts only"** box (on by default) restricts the
artifact list to them.

**They are not assumed to be Tamil-Brahmi.** For each one, decide from the photograph:

| Decide | Values |
|---|---|
| inscription present | `yes` / `no` / `uncertain` |
| script type | `tamil_brahmi`, `graffiti`, `tamil_brahmi_and_graffiti`, `none`, `uncertain`, `other_script` |
| inscription region(s) | mark every mark you can see |
| reading | **only if supported**; with alternatives and a confidence |
| interpretation / inscription type | only if a reading supports it |
| linguistic observations | with a source |
| dating evidence | per item, with a source; **never** from the uploader's caption |
| references | knowledge-base ids where they apply |
| image usability | every photograph |
| confidence and review state | experts: `expert_reviewed` when finished, `disputed` if unsure it can be settled |

The uploader's caption for these photos dates the Keeladi deposit as a whole. That is a
site-level statement. It is not a date for any of these sherds, and must not be entered as one.

Two annotators per artifact are required: a **project annotator** and an **expert**, working
independently. Do not look at each other's annotation before saving your own. Progress:

```powershell
python -m src.annotation pilot        # which tier is missing, which checklist items are unmet
```

The checklist asks whether presence and script are decided, a region is marked when an
inscription is present, every photograph's usability is assessed, and (for experts) a review
state is set. A reading is **not** on the checklist.

## 8. Agreement

```powershell
python -m src.annotation agreement                 # project annotator vs expert, pilot artifacts
python -m src.annotation agreement --rater-a ID1 --rater-b ID2
```

Each field gets its own measure. Presence, script, inscription type and interpretation type
get raw agreement, a confusion matrix and Cohen's κ. Regions get IoU. Readings get exact match
and character similarity. Dating evidence types get Jaccard. `unknown` is excluded from the
comparison and counted as such. With six artifacts, κ is printed beside the raw counts but
marked **not interpretable** (the threshold is `agreement.min_items_for_kappa`, 30). Agreement
**never resolves** a disagreement. The artifact's resolution status is unchanged, and every
disagreeing item is listed for an expert to settle.

## 9. From expert annotation to training label (promotion)

Only an expert can resolve a disagreement, by saving a revised annotation of their own. When
an artifact's status is `expert_label`, it can be promoted:

```powershell
python -m src.annotation promote --pilot           # DRY RUN (default): before -> after, checks P1-P9
python -m src.annotation promote --execute --approve <plan_digest> --approver <your id>
python -m src.annotation promote --log             # audit trail
python -m src.annotation promote --revert <promotion_id>   # dry run; add --execute --approve ...
```

Never promoted: disputed artifacts, project-only labels, AI predictions, experts without a
stated qualification, and anything that would overwrite a label from another source. Expert
readings or dates that differ are recorded as disputed, with every position kept.
