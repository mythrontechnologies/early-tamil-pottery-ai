# Synthetic language 1 — SYNTHETIC LANGUAGE, NOT TAMIL-BRAHMI

**Specification `synthetic-language-1.0.0`** · code: [`src/synthetic/lexicon.py`](../src/synthetic/lexicon.py) ·
generator `1.1.0` · synthetic record schema `synthetic-1.1.0`

> The synthetic language, its vocabulary and its grammar are **fictional**. They were invented for engineering
> demonstration. An English sentence produced with them is correct **only under this specification**. It is not a
> reading of Tamil, Tamil-Brahmi (Tamiḻi) or any real inscription, not an archaeological translation and not a
> historical fact. The synthetic glyphs SG00–SG15 are invented shapes, not Tamil-Brahmi characters.

## Why it exists

The synthetic dataset exercises the complete AI pipeline on generated images. Until generator 1.1.0 its glyph rows
were random code sequences, so the last step — transcription → transliteration → English translation — could not
be demonstrated or measured. This specification gives the synthetic glyphs a small invented language with a
deterministic, documented, testable mapping, so that the whole chain runs and can be scored against held-out
targets without any leakage.

## Lexicon (one glyph = one word; every entry invented)

| Glyph | Reading | Gloss | Class | | Glyph | Reading | Gloss | Class |
|---|---|---|---|---|---|---|---|---|
| SG00 | kesu | pot | noun | | SG08 | seli | keep | verb |
| SG01 | pala | shelter | noun | | SG09 | taren | chief | noun |
| SG02 | maku | give | verb | | SG10 | nomi | potter | noun |
| SG03 | riso | jar | noun | | SG11 | sadu | trader | noun |
| SG04 | temi | basket | noun | | SG12 | na | not | negation |
| SG05 | dira | carry | verb | | SG13 | voka | make | verb |
| SG06 | voru | boat | noun | | SG14 | duve | two | numeral |
| SG07 | lune | lamp | noun | | SG15 | tiri | three | numeral |

## Grammar (word order OBJECT → AGENT → VERB)

```text
sentence := clause+                      clauses follow one another; spacing is not significant
clause   := np(object) np(agent) verb [negation]
np       := [numeral] noun
```

The grammar is unambiguous: a numeral can only open a noun phrase, a verb closes a clause and the negation can only
follow a verb, so a valid sequence has exactly one parse (checked exhaustively for every sequence of up to four
glyphs in `tests/test_synthetic_language.py`).

**Transliteration** — each glyph's reading, left to right, separated by spaces; a written word gap is kept as
` / `; an unknown glyph is written `[?]`.

**English translation of a clause** — `<Agent> <verb> <object>.` The agent takes *The* when singular and its numeral
when plural (*Two potters*); the verb agrees with the agent (*gives* / *give*), negation gives *does not give* /
*do not give*; a singular object takes its object form (*a jar*; *shelter* has no article), a plural object its
numeral (*three jars*). Each clause becomes its own English sentence.

## Reference example

| | |
|---|---|
| Transcription | `SG01 SG09 SG02` |
| Synthetic transliteration | `pala taren maku` |
| Synthetic English translation | **The chief gives shelter.** |
| Method | Deterministic synthetic lexicon and grammar |
| Status | Translated under the fictional synthetic-language specification |

`SG01` *pala* "shelter" is the object, `SG09` *taren* "chief" the agent, `SG02` *maku* "give" the verb. This is the
held-out test image `SYNTH-A0007-V1` (the demonstration's default image); its row was already a valid sentence, so
generator 1.1.0 left it byte-identical. More: `SG14 SG03 SG10 SG13` → *The potter makes two jars.*;
`SG00 SG15 SG11 SG05 SG12` → *Three traders do not carry a pot.*

## Statuses — what is never invented

| Status | When | Output |
|---|---|---|
| `translated` | every glyph known, the whole sequence parses | the English sentence(s) |
| `partial` | one or more complete clauses, then glyphs that form no clause | only the complete clauses; the remainder is listed, never completed |
| `unknown_glyph` | a glyph outside the lexicon | no translation; the unknown glyphs and positions are listed |
| `invalid_sequence` | known glyphs that form no clause (wrong order, missing verb, incomplete) | no translation; the reason and position |
| `insufficient_evidence` | no glyph read | nothing |

The decoder is **rule-based**, not a learned translation model. It consumes the **predicted** glyph codes only: never
the record, the artifact id, the file name or the generator's ground truth. OCR mistakes are kept: a misread glyph
gives a different (or no) sentence, which the ground-truth check then marks wrong. A model probability is never a
translation confidence: the translation is exact under the specification *for the given transcription* and inherits
any OCR error.

## Dataset and evaluation

* **Generator 1.1.0.** A Tamil-Brahmi-like row is laid out exactly as before (same random draws, same geometry, same
  glyph count). Its codes are kept when they already form a valid sentence; otherwise they are replaced by a
  sentence of the same length drawn from a separate random stream (`STREAM_LANGUAGE`). No other class changed, and
  the artifact-level split assignment is identical to the previous one. Rows of fewer than three glyphs (rare: the
  placer had to drop glyphs) cannot be sentences; their target says `invalid_sequence`.
* **Targets.** Every synthetic record carries `synthetic_language_target` = the specification applied to its TRUE
  glyph sequence. Validation rule S7 refuses a record whose target disagrees with the specification. The target is
  read only by evaluation (`ground_truth_check`, the benchmark), never by inference.
* **Archaeological fields stay empty.** `transcription` and `translation` remain `not_applicable`: a synthetic image
  has no archaeological reading. The fictional reading lives only in `synthetic_language_target` / `synthetic_language`.
* **Benchmark section H** (`python -m src.synthetic` benchmark) reports, on the held-out test split, exact translation,
  transliteration and status agreement between the decoder's output on the predicted codes and the targets. It
  measures the engineering of the pipeline, **not Tamil-Brahmi translation accuracy**.
* **Grammatical interpretation** (`grammatical_interpretation`): the 07 INTERPRET stage also reports who does what to
  what, clause by clause, from the same parse - `SG01 SG09 SG02` → agent *chief* · action *gives* · object *shelter*.
  It is a field of its own (`interpretation`), separate from the translation (`synthetic_language`); a sequence the
  grammar does not accept has none. These are roles of invented words: no person, personal name or real-world
  identity is ever inferred. It replaced, on 2026-10-09, the placeholder categories of `src/synthetic/interpretation.py`
  ("synthetic grammar", e.g. `synthetic_personal_name_like`), which contradicted the grammar; that module is kept only
  so that runs and reports stored before then stay readable. Benchmark section F now reports grammatical-role
  agreement with the held-out targets.
* **Near-duplicate grouping of the split.** 148 pairs of synthetic photographs across artifacts are near-duplicates by
  dHash (≤ 6 of 64 bits); they form 37 connected components over 141 artifacts. In the first 1.1.0 split, 61 pairs
  (29 test↔train, 2 test↔val, 30 train↔val) and 25 components crossed partitions, touching 23 test artifacts. The
  synthetic split now keeps every component in ONE partition (`group_near_duplicates`; class sizes per partition
  restored by swapping same-class artifacts outside any component), and the models were retrained and re-evaluated
  on it. See [`SYNTHETIC_DATASET.md`](SYNTHETIC_DATASET.md) §7.

## Where it appears

Analysis → *Synthetic Demonstration* (side panel, *Language / reading results* with a word-by-word gloss, pipeline
replay under 07 INTERPRET), `python -m src.synthetic demo`, `python -m src.synthetic translate SG01 SG09 SG02
[--json]`, `python -m src.inference synthetic --image … [--json]`, the HTTP API (`/synthetic/analyze`,
`synthetic_analysis.synthetic_language`) and benchmark section H. Every place says **SYNTHETIC LANGUAGE — NOT
TAMIL-BRAHMI**.

## Real data is unaffected

The lexicon is used only in synthetic mode. Real research photographs never pass through it: the real
Language / reading results still state "No translation established" unless a human recorded a reading and a
translation with a cited source, and real archaeological translation remains dependent on an established reading,
reliable references and expert review. No real image, record, annotation or readiness gate changed.
