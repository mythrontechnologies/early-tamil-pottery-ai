# Pilot Annotation Checklist (one page per sherd)

**For:** the expert and the project annotator, working **independently**.
**Artifacts:** `WMC_KEELADI_MUS_SHERD_105` … `_110` (one photograph each).
**Tool:** `streamlit run app/annotate.py` (or the worksheet `outputs/pilot_handoff/pilot_worksheet_*.csv`).

> **An uncertain answer is preferable to an unsupported positive identification.**
> `uncertain` = you examined it and cannot decide. `unknown` = you did not assess it.
> Both are good answers. A confident guess damages the dataset.

Do not use the site name, the file name, the Commons caption, or any AI suggestion as evidence.
The optional "AI draft" layer in the tool is **not archaeological evidence**. Leave it off unless
you have finished your own judgement.

## For each artifact, answer:

| # | Question | Tool field | If you cannot tell |
|---|---|---|---|
| 1 | Is this an **original archaeological object** or a **reproduction**? What is your basis? | OBJECT → object status, object comments | `uncertain` |
| 2 | Is an inscription or graffiti **actually visible**? | INSCRIPTION → present | `uncertain` |
| 3 | If visible, what script category is **defensible**? (`tamil_brahmi`, `graffiti`, `tamil_brahmi_and_graffiti`, `other_script`, `none`) | script type, with a confidence | `uncertain` |
| 4 | Which **exact region** holds the marks? | zoom, then "Add region from zoom window" (one region per group of marks) | describe it in a note |
| 5 | Are individual characters visible **well enough to read**? | characters visible; usability → characters readable | `uncertain` / `no` |
| 6 | If yes, **what is the reading**? Only characters you can see. Mark doubtful or lost letters; record alternatives separately. | reading, alternative readings, reading confidence | leave empty |
| 7 | Is there a **published reading** of this object? | alternative readings, source = ref id | "none known" in notes |
| 8 | If so, **cite it**: ref id, page, plate or figure. | references | – |
| 9 | Is a **translation actually established** by a source? | MEANING → translation + source | leave empty |
| 10 | If not, the record must say **"No translation established."** A personal name has no literal translation. | (automatic when the translation is empty) | – |
| 11 | What evidence **dates** it? One row per item: palaeography, linguistics, context, stratigraphy, absolute dating, typology, with its source. | DATING → evidence rows | no rows |
| 12 | Does that evidence date **the object itself**, or only its **archaeological context**? A site or caption date is not an object date. | evidence → association; proposed range only if the evidence bounds it | `Insufficient evidence` |
| 13 | **Confidence** for each answer | the confidence selectors | `unknown` |
| 14 | **What remains uncertain?** Include any dating conflict you cannot resolve (it is recorded, never averaged). | uncertainty notes; unresolved dating conflict | – |

**Experts only:** set the review state to `expert_reviewed` when you stand by the annotation, or
`disputed` if it cannot be settled from this photograph. State your qualification and affiliation.

## Two sherds to look at especially carefully

`_107` and `_109` carry the note **REVIEW REQUIRED — possible reproduction / duplicate
inscription**. The project suspects they are painted display reproductions of `_106` and `_108`.
This is **not confirmed**. Answer question 1 from your own knowledge or the museum's
information. If they are reproductions, set object status to `reproduction` and
usability to `no`. A reproduction is never promoted (rule P10).

## When you have saved all six

```powershell
python -m src.annotation pilot        # is every sherd complete?
```

Do not open the other annotator's work until both have saved. After that:
`python -m src.annotation agreement` lists every item on which you differ.
