# Chronological Scope

**Status: PROVISIONAL — NOT YET VERIFIED AGAINST PRIMARY SOURCES.**

> ⚠️ **Read this first.** Every bibliographic reference and every date range in this document was
> drafted by an AI assistant from general knowledge and **has not been checked against the physical
> publications**. Nothing here may be cited, displayed in the prototype UI, or used as evidence
> until a human has verified it. Each entry carries a `verification` marker. This file is a
> *research agenda* — a list of things to go and confirm — not a source of facts.
>
> This posture is required by §17 of the project brief. The alternative — quietly asserting a date
> range with a plausible-looking citation — is exactly the failure mode this project exists to
> avoid.

---

## 1. Why this document exists

The brief (§1) says:

> *Use the project's historically supported chronological range from authoritative archaeological
> sources rather than hard-coding an unsupported date.*

Accordingly:

- **No date range is hard-coded in source code.** The scope lives in
  [`../configs/project.yaml`](../configs/project.yaml) under `chronology:`, with each bound
  carrying its own citation pointer and verification status.
- The earliest date of Tamil-Brahmi is **an open and actively contested question**. A prototype
  that silently picks one position and presents it as settled would be misrepresenting the state of
  the field. The configuration therefore records **competing positions**, not one answer.

## 2. The structure of the problem

Three distinct chronological questions are easily conflated. The system must keep them apart:

| # | Question | What it constrains |
|---|---|---|
| Q1 | When was the **Early Historic period** in Tamil Nadu? | The project's overall scope. |
| Q2 | When was **Tamil-Brahmi** in use? | The plausible range for an inscribed sherd. |
| Q3 | When was **this particular sherd** made or inscribed? | The per-artifact estimate the prototype outputs. |

Q3 is never answered by Q1 or Q2 alone. An inscribed sherd whose script is securely identified as
Tamil-Brahmi inherits the *script's* range as an outer bound, and nothing narrower, unless
stratigraphy, associated datable finds, absolute dates, or close palaeographic parallels narrow it.
**The prototype must never present the script's range as if it were the object's date.**

## 3. Q1 — The Early Historic period in Tamil Nadu

| | |
|---|---|
| Conventional range | approximately 3rd century BCE – 3rd/4th century CE |
| Sometimes extended to | approximately 6th century CE (to the start of the Pallava/Pandya epigraphic record) |
| Preceded by | Iron Age / megalithic contexts, with no sharp break — the transition is gradual and regionally variable |
| Overlaps | the "Sangam age" of Tamil literary chronology — a **literary** periodisation that must not be treated as an independent archaeological date |
| **Verification** | ⛔ **unverified** — bounds and terminology to be confirmed |

A caution the system must encode: dating an artifact by reference to Sangam literature, and then
using that artifact to date Sangam literature, is circular. Literary and archaeological chronologies
are recorded as separate evidence types in the knowledge base (Milestone 11).

## 4. Q2 — Tamil-Brahmi: the contested early bound

There are at least four positions in the literature. **The prototype must surface this disagreement
rather than resolve it.**

| Position | Claim (approximate) | Principal basis | Verification |
|---|---|---|---|
| **A — Conventional / epigraphic** | Earliest Tamil-Brahmi around the 3rd–2nd century BCE | Palaeographic analysis of the cave-inscription corpus; diffusion of Brahmi in the post-Mauryan period | ⛔ unverified |
| **B — Early AMS dates** | Tamil-Brahmi in use by around the 5th century BCE | AMS radiocarbon determinations from excavated contexts (Porunthal, Kodumanal are the sites usually cited) | ⛔ unverified |
| **C — Keeladi / TNSDA** | Urban occupation with associated inscribed material from around the 6th century BCE | AMS dates from stratified deposits at Keeladi (Keezhadi), Sivagangai district | ⛔ unverified |
| **D — Sceptical** | Early determinations do not securely date the *inscriptions* | The dated sample and the inscribed sherd may not be in secure association; charcoal can be residual; stratigraphic integrity is questioned | ⛔ unverified |

Position D is a methodological objection, not a rival date, and it applies to B and C
specifically. The project records it as such: the knowledge base distinguishes *what was dated*
from *what the date is being used to date*.

**Consequence for the system.** Where a record's own evidence does not pin it down, the prototype
outputs the **union** of the ranges supported by the positions it can cite, together with the
disagreement itself — not a midpoint, and not a single number with a percentage attached.

## 5. Working scope (provisional)

Pending verification, the project operates over:

```
Outer scope for ingestion:   approximately 6th century BCE – 6th century CE
Core scope for modelling:    approximately 3rd century BCE – 3rd century CE
```

The outer bound is deliberately generous so that material relevant to positions B and C is not
excluded from the dataset by an assumption baked in before the evidence was examined. The core
scope is where data is expected to be densest. **Neither bound is an assertion about when
Tamil-Brahmi began.**

Encoded in [`../configs/project.yaml`](../configs/project.yaml); nothing reads these values from
anywhere else.

## 6. References to verify

**None of the following has been checked.** Author, year, title, publisher and — above all —
whether each work actually supports the claim attributed to it must be confirmed against the
physical publication. Page numbers are deliberately omitted rather than guessed. Entries marked
🔶 are ones the drafting assistant was least certain about.

### Epigraphy

| Ref | Work | Expected relevance | Verification |
|---|---|---|---|
| R1 | Mahadevan, Iravatham. *Early Tamil Epigraphy: From the Earliest Times to the Sixth Century A.D.* (2003). Cre-A, Chennai / Harvard Oriental Series. | The standard corpus. Primary source for Position A, for the palaeographic sequence, and for published readings. | 🟡 **Bibliographic details confirmed 2026-09-23** (HOS vol. 62; Cre-A, Chennai & Dept. of Sanskrit and Indian Studies, Harvard; 2003; 2nd rev. ed. CICT 2014). Contains a pottery-inscription section (§1.13). ⛔ Support for the attributed claims still unverified. See `DATA_SOURCE_AUDIT.md` S06/S07. |
| R2 | Salomon, Richard. *Indian Epigraphy: A Guide to the Study of Inscriptions in Sanskrit, Prakrit, and the Other Indo-Aryan Languages* (1998). Oxford University Press. | General methodology; Brahmi palaeography; standards for epigraphic argument. | ⛔ verify |
| R3 🔶 | Rajan, K. — publications on early writing, Porunthal and Kodumanal. | Primary source for Position B. | 🟡 **Titles located 2026-09-23:** Rajan & Yatheeskumar (2013), *Prāgdhārā* 21–22: 280–295 (bibliographic only, not read); Rajan & Sivanantham (2026), *Inscribed Potsherds of Tamil Nadu: Graffiti and Tamiḻi*, TNSDA (read; ch. 10 argues the chronology). ⛔ Claim support in the 2013 paper still unverified. See `DATA_SOURCE_AUDIT.md` S01/S08. |
| R4 🔶 | Subbarayalu, Y. — publications on Tamil epigraphy. | Corpus and chronology. | ⛔ **exact titles unverified** |
| R5 🔶 | Falk, Harry — publications on the origins of Brahmi. | Sceptical position (D); Brahmi origins. | ⛔ **exact titles unverified** |

### Excavation and site reports

| Ref | Work | Expected relevance | Verification |
|---|---|---|---|
| R6 🔶 | Sivanantham, R. & Seran, M. (eds.). *Keeladi: An Urban Settlement of Sangam Age on the Banks of River Vaigai* (2019). Department of Archaeology, Government of Tamil Nadu. | Primary source for Position C. | 🟡 **Confirmed 2026-09-23 from the publication itself:** editors, title, year, TNSDA Pub. No. 302. Critically edited by K. Rajan. Reports six AMS dates (Beta Analytic) from the 4th season. ⛔ The dating is disputed; see `DATA_SOURCE_AUDIT.md` S03–S05. |
| R7 | Wheeler, R.E.M., Ghosh, A. & Krishna Deva. "Arikamedu: An Indo-Roman Trading Station on the East Coast of India." *Ancient India* 2 (1946). | Foundational stratigraphy and ceramic sequence; Rouletted Ware; Mediterranean imports. | ⛔ verify volume/year |
| R8 | Begley, Vimala et al. *The Ancient Port of Arikamedu: New Excavations and Researches.* École française d'Extrême-Orient. | Revised Arikamedu chronology and ceramics. | ⛔ verify volumes and years |
| R9 | Archaeological Survey of India — *Indian Archaeology: A Review* series. | Annual excavation notices for Tamil Nadu sites. | ⛔ verify relevant years |

### Context and synthesis

| Ref | Work | Expected relevance | Verification |
|---|---|---|---|
| R10 | Champakalakshmi, R. *Trade, Ideology and Urbanization: South India 300 BC to AD 1300* (1996). Oxford University Press. | Early Historic urbanisation and trade context. | ⛔ verify |
| R11 🔶 | Ray, Himanshu Prabha — publications on early historic South Asian archaeology and maritime trade. | Regional context. | ⛔ **exact titles unverified** |
| R12 🔶 | Coningham, R. et al. — Anuradhapura early Brahmi publications. | Comparative Sri Lankan sequence; independent check on early Brahmi dating. | ⛔ **exact titles unverified** |

### Standards

| Ref | Work | Expected relevance | Verification |
|---|---|---|---|
| R13 | ISO 15919 — Transliteration of Devanagari and related Indic scripts into Latin characters. | Project default transliteration scheme. | ⛔ verify current edition |

## 7. Verification procedure

Before any reference leaves this file for the knowledge base or the UI:

1. Obtain the publication. Interlibrary loan or an institutional archaeology library — not a
   web summary of it.
2. Confirm author, year, title, publisher, edition.
3. Confirm **that the work actually makes the claim attributed to it**, and record the page.
4. Record whether the claim is the author's own finding or their report of someone else's.
5. Note explicitly whether the work has been challenged, and by whom.
6. Create the entry under `knowledge/references/` with
   `verification_status: verified_against_source` and the verifier's name and date.
7. Delete the entry from §6 of this file, or mark it ✅ verified with the date.

Any entry still carrying ⛔ is invisible to the prototype: the retrieval layer (Milestone 11) will
filter on `verification_status`, so unverified material cannot reach a user as evidence even by
accident.

## 8. Open questions for the domain expert

These are decisions the project cannot make on its own:

1. Should the outer ingestion scope be widened further to include Iron Age / megalithic graffiti
   contexts that may predate any Brahmi?
2. Which chronological framework should be the *default* presentation — A, or an explicit
   "positions differ" output? (Current design: the latter.)
3. Is `graffiti` vs `tamil_brahmi` an acceptable annotation dichotomy for the marks you work with,
   or is a third category needed for marks argued to be transitional?
4. Which corpus should supply ground-truth readings, and are its images licensed for our use?
5. For palaeographic dating (Milestone 10), is there a published letter-form sequence that can be
   encoded as discrete, checkable features — or is this irreducibly expert judgement?

---

*This system provides AI-assisted archaeological analysis and is not a substitute for expert
epigraphic or archaeological assessment.*
