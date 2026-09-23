# Archaeological Reasoning

**Status:** Milestone 7: deterministic reasoning layer implemented and tested. It runs on
structured, provenance-tagged evidence. It does **not** look at images, and it cannot identify
Tamil-Brahmi from a photograph.

> **An archaeological research assistant, not an oracle.** Every conclusion traces to a
> recorded input, uncertainty is preserved, and unsupported information stays unknown.
> "Insufficient evidence" is a correct output, not a failure.

---

## 1. Architecture

```text
IMAGE ──► (future) visual / script / reading models ──► ai_prediction   (reported, never evidence)
   │
   └──► human annotation (project / source / expert), with provenance
             │
             ▼
   ReasoningInputs  (src/reasoning/types.py)
     visual_features · inscription · linguistic_features · archaeological_context
     dating_evidence · references · ai_predictions · annotation_status
             │
             ▼
   analyze_artifact  (src/reasoning/engine.py)
     ├─ script assessment        who says which script, with what confidence
     ├─ interpretation           src/translation/interpret.py
     ├─ age estimation           src/dating/estimate.py  (+ chronology.py)
     └─ period label             configs/project.yaml chronology.periods
             │
             ▼
   AnalysisResult: identification · script · reading · interpretation · period_estimate
                   age range · confidence · reasoning · evidence · limitations · disclaimer
```

- **Modular.** Each component takes structured input and returns a structured result. A
  future model replaces a component by *supplying* inputs tagged `ai_prediction`. It does not
  change the engine's rules about what counts as evidence.
- **Deterministic.** There is no randomness, clock, network or LLM. Collections are sorted,
  and an `inputs_digest` (SHA-256 of the canonical inputs) identifies what was analysed.
- **Entry points:** `analyze_artifact(inputs)` or `analyze_artifact(visual_features=...,
  inscription=..., linguistic_features=..., archaeological_context=...,
  dating_evidence=..., references=...)`; `python -m src.reasoning analyze <artifact_id>`
  builds inputs from the annotation store.

## 2. Where inputs come from

`src/reasoning/from_annotations.py` keeps four layers apart:

| Layer | Source | Use |
|---|---|---|
| A. Source information | `records.jsonl` (site as stated by source), acquisition provenance (`source_label`), `source_information` annotations | context; the source label is shown, never used as a label |
| B. Project annotation | project annotators | can drive the analysis, but caps confidence at *low* |
| C. Expert annotation | experts, `expert_reviewed` | the only route to *moderate* or *high* |
| D. AI inference | `ai_prediction` | listed under "AI PREDICTIONS (not evidence)"; never used |

One human annotation is the reasoning basis, chosen by provenance strength (expert-reviewed
expert > expert > source information > project). Other annotators are **not averaged in**:
disagreement is reported, and confidence is capped at *low*.

## 3. Age estimation

### 3.1 Why not `image → network → year`
A photograph does not contain its own date. A date for an inscribed sherd rests on:
- its **context** (stratigraphy, associated datable material, absolute dates tied to it);
- **comparison** (palaeography, comparable inscriptions, pottery typology);
- **language** (orthography, word forms, vocabulary).

Each of these is an explicit, citable evidence item. The estimate is a **range** derived from
them, and the method is visible in the output.

### 3.2 Evidence hierarchy

| Tier | Evidence types | Why this tier |
|---|---|---|
| 1 | `stratigraphy`, `absolute_dating` | Direct physical association with a dated context. **Used only when the association with this object is `direct` or `same_context_secure`,** and stratigraphy only for `excavated_stratified` context. This implements the sceptical Position D in `CHRONOLOGICAL_SCOPE.md`: a dated sample does not date an object not securely associated with it. |
| 2 | `associated_material`, `archaeological_context` | Datable finds or a dated phase in the same context. |
| 3 | `palaeography`, `comparative_inscription`, `pottery_typology` | Comparison with dated sequences; depends on the sequence's own dating. |
| 4 | `linguistics`, `historical_reference` | Broad and easily circular (e.g. dating by Sangam literature, then dating the literature by the object: `CHRONOLOGICAL_SCOPE.md` §3). |

### 3.3 Combination (deterministic)
1. **Screen:** exclude AI items, items without numeric bounds (kept as qualitative
   reasoning), insecurely associated contexts, stratigraphy without a stratified context, and
   unknown citations. Each exclusion is listed with its reason.
2. **Narrow:** process items by tier, then by id. Each item narrows the running range by
   intersection.
3. **Conflict:** an item that contradicts the range from stronger evidence is **reported and
   not used**. Nothing is averaged, and no midpoint is taken.
4. **Signed years, no year 0:** every bound is validated; spans skip year 0
   (`years_between(-1, 1) == 1`).

### 3.4 When there is no usable evidence
- If the **script is established** (expert or cited source) as Tamil-Brahmi, the output is
  only an **outer bound**: "no earlier than" the earliest of the competing positions in
  `configs/project.yaml`, at `very_low` confidence. All positions (A, B, C) and the
  objection (D) are listed. The positions concern when the script *began*, so no upper bound
  is claimed, and the script's range is never presented as the object's date
  (`CHRONOLOGICAL_SCOPE.md` §2).
- Otherwise the output is **"Insufficient evidence"**: no range, confidence `unknown`, and
  period "Undetermined".

### 3.5 Confidence (rules, not scores)

| Level | Requires |
|---|---|
| `high` | all evidence expert-annotated; ≥ 2 evidence types; tier-1 evidence; `excavated_stratified` context; **every citation `verified_against_source`**; no conflicts |
| `moderate` | all evidence expert-annotated; ≥ 2 evidence types incl. tier ≤ 2; no conflicts |
| `low` | any estimate otherwise, and the cap whenever evidence is project-annotated, conflicting, disputed, or cites unverified references |
| `very_low` | outer bound from script identification only |
| `unknown` | no estimate |

The overall level never exceeds the best individual evidence item's own confidence.
**Today every reference in the knowledge base is unverified, so nothing can exceed `low`.**
That is intended.

### 3.6 Period label
A range is described against `chronology.periods` in `project.yaml` (currently "Early
Historic Tamil Nadu", about 300 BCE – 400 CE, **unverified**) as "within", "overlaps" or
"outside". The label never produces a date, and an open-ended range gets "Undetermined".

## 4. Script, reading and linguistic evidence
- **Script:** reported with its provenance and confidence. A project identification triggers
  the limitation "not expert-reviewed". An AI script prediction is never used.
- **Palaeography:** letter forms become evidence only as a `palaeography` item, with bounds
  and a citation to a dated palaeographic sequence (e.g. a table in R1 or S01, once
  verified). The engine does not compare letter shapes itself.
- **Linguistic features:** reported with provenance, but they bound nothing unless a
  `linguistics` evidence item states bounds and a source.

## 5. Translation limits
`src/translation/interpret.py` composes nothing. It returns one of:

| Outcome | When |
|---|---|
| "No reading established; nothing can be translated." | no reading |
| personal name: translation not applicable; "Proper name; no literal translation established." | `interpretation_type = personal_name` |
| no translation | symbol / not translatable |
| the annotator's translation, with provenance and source | a human translation with a cited source |
| **"No translation established."** | anything else, including any AI-generated gloss |

## 6. Output
`render_text` produces the layout from the Milestone 7 brief: likely period, estimated age,
script, reading, meaning, **WHY?** (every line traced to an input, evidence ids in brackets),
confidence, AI predictions (separately), limitations, and the disclaimer:

> This is an AI-assisted research estimate built from recorded evidence. It is not a
> definitive archaeological identification, reading or date, and it is not a substitute for
> expert epigraphic or archaeological assessment.

The output never uses "definitely" or "certainly" (tested).

## 7. Knowledge base
`knowledge/*/*.yaml`, loaded and checked by `src/knowledge/base.py` (K1–K5):
- **Contains only** what the project has read (S01, S03, R6: `transcribed_unverified`) or
  bibliographically confirmed (R1, R3a: `bibliographic_only`), plus a few leads (`unverified`).
- Every assertion names references that resolve.
- `verified_against_source` requires a named verifier and a date.
- **Nothing is evidence-grade yet.** Published readings (`knowledge/inscriptions/`) are
  reference points for annotators and future benchmarks. They are not linked to any image in
  the dataset.
- Empty categories (periods, characters, linguistic features, pottery types, rulers) carry a
  README explaining why. The chronology stays in `project.yaml` and is not duplicated.

## 8. Expert verification
Expert verification is what the system is built to wait for:
- only an `expert_reviewed` expert annotation can make an artifact `ground_truth_eligible`;
- only verified references allow confidence above `low`;
- training stays blocked until expert labels are promoted into the records (Milestone 8).

## 9. Current behaviour on the real data
All 17 artifacts return: script **not determined**, reading **none**, meaning "No reading
established", age **Insufficient evidence**, confidence **unknown**. That is correct: no
annotation exists yet.
