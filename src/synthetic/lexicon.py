"""Synthetic language 1: an INVENTED logographic language over the synthetic glyphs SG00-SG15.

    SYNTHETIC LANGUAGE — NOT TAMIL-BRAHMI. Fictional vocabulary and grammar, made up for engineering
    demonstration. It is not Tamil, Tamil-Brahmi (Tamiḻi) or any real language; nothing decoded with it is a
    reading of a real inscription, an archaeological translation or a historical fact.

Why it exists: to exercise a complete transcription -> transliteration -> English translation pipeline end to
end, with a deterministic, documented, testable target. The synthetic generator (``src.synthetic.generator``,
version 1.1.0) writes sentences of this language, the synthetic OCR reads glyph codes, and this module decodes
the PREDICTED codes. It is a rule-based decoder, not a learned translation model.

Lexicon (``LEXICON``): one glyph = one word. Every reading and gloss below is invented.

    SG00 kesu  pot       noun     SG06 voru  boat     noun     SG12 na    not      negation
    SG01 pala  shelter   noun     SG07 lune  lamp     noun     SG13 voka  make     verb
    SG02 maku  give      verb     SG08 seli  keep     verb     SG14 duve  two      numeral
    SG03 riso  jar       noun     SG09 taren chief    noun     SG15 tiri  three    numeral
    SG04 temi  basket    noun     SG10 nomi  potter   noun
    SG05 dira  carry     verb     SG11 sadu  trader   noun

Grammar (word order OBJECT → AGENT → VERB):

    sentence := clause+                       clauses follow one another; spacing is not significant
    clause   := np(object) np(agent) verb [negation]
    np       := [numeral] noun

The grammar is unambiguous: a numeral can only open a noun phrase, a verb closes the clause and the negation
can only follow a verb, so every valid sequence has exactly one parse.

Transliteration: each glyph's reading, left to right, separated by spaces; written word gaps are kept as " / "
(as in the transcription). An unknown glyph is written "[?]".

English translation of a clause: "<Agent> <verb> <object>." The agent takes "The" when singular and its
numeral when plural ("Two potters"); the verb agrees with the agent ("gives" / "give"), negation gives
"does not give" / "do not give"; a singular object takes its object form ("a jar"; "shelter" is used without
an article), a plural object its numeral ("three jars"). Clauses become separate English sentences.

Statuses (``STATUSES``):

    translated             every glyph is known and the whole sequence parses
    partial                one or more complete clauses parse, then the rest does not: only those clauses
                           are translated; the remainder is reported, never completed or guessed
    unknown_glyph          a glyph outside the lexicon: no translation at all (the unknown glyphs are listed)
    invalid_sequence       known glyphs that do not form a clause (wrong order, missing verb, incomplete)
    insufficient_evidence  no glyph was read

Reference example (SPEC): ``SG01 SG09 SG02`` -> ``pala taren maku`` -> ``The chief gives shelter.``
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

SPEC_NAME = "synthetic-language"
SPEC_VERSION = "1.0.0"
SPEC_ID = f"{SPEC_NAME}-{SPEC_VERSION}"
BANNER = "SYNTHETIC LANGUAGE — NOT TAMIL-BRAHMI"
METHOD = "Deterministic synthetic lexicon and grammar"
METHOD_NOTE = "Rule-based decoder over the predicted glyph codes; not a learned translation model."
FICTION = ("Fictional language invented for engineering demonstration. Correct only under this specification; "
           "not a reading of Tamil-Brahmi or of any real inscription.")
STATUSES = ("translated", "partial", "unknown_glyph", "invalid_sequence", "insufficient_evidence")
STATUS_TEXT = {
    "translated": "Translated under the fictional synthetic-language specification",
    "partial": "Partly translated: only the complete clauses are translated under the fictional specification",
    "unknown_glyph": "Not translated: the sequence contains a glyph outside the synthetic lexicon",
    "invalid_sequence": "Not translated: the glyphs do not form a clause of the synthetic grammar",
    "insufficient_evidence": "Not translated: no synthetic glyph was read",
}
WORD_SEPARATOR = " / "
CLASSES = ("noun", "verb", "numeral", "negation")


@dataclass(frozen=True)
class Entry:
    glyph: str
    reading: str
    word_class: str            # noun | verb | numeral | negation
    gloss: str                 # dictionary gloss (English)
    plural: str = ""           # nouns
    object_form: str = ""      # nouns: singular object ("a jar"; "shelter")
    third_person: str = ""     # verbs: "gives"
    value: int = 0             # numerals


def _noun(g: str, r: str, s: str, p: str, obj: str) -> Entry:
    return Entry(g, r, "noun", s, plural=p, object_form=obj)


def _verb(g: str, r: str, base: str, third: str) -> Entry:
    return Entry(g, r, "verb", base, third_person=third)


LEXICON: dict[str, Entry] = {e.glyph: e for e in (
    _noun("SG00", "kesu", "pot", "pots", "a pot"),
    _noun("SG01", "pala", "shelter", "shelters", "shelter"),
    _verb("SG02", "maku", "give", "gives"),
    _noun("SG03", "riso", "jar", "jars", "a jar"),
    _noun("SG04", "temi", "basket", "baskets", "a basket"),
    _verb("SG05", "dira", "carry", "carries"),
    _noun("SG06", "voru", "boat", "boats", "a boat"),
    _noun("SG07", "lune", "lamp", "lamps", "a lamp"),
    _verb("SG08", "seli", "keep", "keeps"),
    _noun("SG09", "taren", "chief", "chiefs", "a chief"),
    _noun("SG10", "nomi", "potter", "potters", "a potter"),
    _noun("SG11", "sadu", "trader", "traders", "a trader"),
    Entry("SG12", "na", "negation", "not"),
    _verb("SG13", "voka", "make", "makes"),
    Entry("SG14", "duve", "numeral", "two", value=2),
    Entry("SG15", "tiri", "numeral", "three", value=3),
)}
BY_CLASS: dict[str, tuple[str, ...]] = {c: tuple(g for g, e in LEXICON.items() if e.word_class == c) for c in CLASSES}
assert len(LEXICON) == 16 and len({e.reading for e in LEXICON.values()}) == 16


class _Stop(Exception):
    def __init__(self, position: int, reason: str) -> None:
        super().__init__(reason)
        self.position, self.reason = position, reason


@dataclass
class Clause:
    start: int
    glyphs: list[str]
    object: dict[str, Any]
    agent: dict[str, Any]
    verb: str
    negated: bool
    english: str


def _np(tokens: list[str], i: int, role: str) -> tuple[dict[str, Any], int]:
    if i >= len(tokens):
        raise _Stop(i, f"incomplete clause: the {role} noun phrase is missing")
    e = LEXICON[tokens[i]]
    if e.word_class == "numeral":
        if i + 1 >= len(tokens):
            raise _Stop(i + 1, f"incomplete clause: the numeral '{e.reading}' is not followed by a noun")
        n = LEXICON[tokens[i + 1]]
        if n.word_class != "noun":
            raise _Stop(i + 1, f"a numeral must be followed by a noun, found {n.word_class} '{n.reading}'")
        return {"noun": n.glyph, "numeral": e.glyph}, i + 2
    if e.word_class != "noun":
        raise _Stop(i, f"expected the {role} (a noun phrase), found {e.word_class} '{e.reading}'")
    return {"noun": e.glyph, "numeral": None}, i + 1


def _agent_text(np_: dict[str, Any]) -> str:
    n = LEXICON[np_["noun"]]
    return f"{LEXICON[np_['numeral']].gloss.capitalize()} {n.plural}" if np_["numeral"] else f"The {n.gloss}"


def _object_text(np_: dict[str, Any]) -> str:
    n = LEXICON[np_["noun"]]
    return f"{LEXICON[np_['numeral']].gloss} {n.plural}" if np_["numeral"] else n.object_form


def english(obj: dict[str, Any], agent: dict[str, Any], verb: str, negated: bool) -> str:
    """The English sentence for one parsed clause (the translation rules of the module docstring)."""
    v, plural = LEXICON[verb], agent["numeral"] is not None
    if negated:
        vp = f"{'do' if plural else 'does'} not {v.gloss}"
    else:
        vp = v.gloss if plural else v.third_person
    return f"{_agent_text(agent)} {vp} {_object_text(obj)}."


def _clause(tokens: list[str], i: int) -> tuple[Clause, int]:
    start = i
    obj, i = _np(tokens, i, "object")
    agent, i = _np(tokens, i, "agent")
    if i >= len(tokens):
        raise _Stop(i, "incomplete clause: the verb is missing")
    v = LEXICON[tokens[i]]
    if v.word_class != "verb":
        raise _Stop(i, f"expected a verb after the agent, found {v.word_class} '{v.reading}'")
    i += 1
    negated = i < len(tokens) and LEXICON[tokens[i]].word_class == "negation"
    i += negated
    return Clause(start, tokens[start:i], obj, agent, v.glyph, negated, english(obj, agent, v.glyph, negated)), i


@dataclass
class SyntheticTranslation:
    """The decoder's structured result. Every field comes from the predicted glyph codes and this spec."""

    status: str
    status_text: str
    transcription: str
    transliteration: str | None
    translation: str | None
    gloss: list[dict[str, Any]]
    parse: list[dict[str, Any]]
    unknown_glyphs: list[dict[str, Any]] = field(default_factory=list)
    untranslated: list[str] = field(default_factory=list)
    reason: str = ""
    spec: str = SPEC_ID
    banner: str = BANNER
    method: str = METHOD
    method_note: str = METHOD_NOTE
    fiction: str = FICTION
    confidence_note: str = ("Exact under the specification for the given transcription; any OCR error is "
                            "inherited. A model score is not a translation confidence.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _words(sequence: list[list[str]] | list[str] | str) -> list[list[str]]:
    if isinstance(sequence, str):
        return [w.split() for w in sequence.split(WORD_SEPARATOR.strip()) if w.split()]
    if sequence and isinstance(sequence[0], str):
        return [[str(t) for t in sequence]]
    return [list(w) for w in sequence if w and not isinstance(w, str)]


def decode(sequence: list[list[str]] | list[str] | str) -> SyntheticTranslation:
    """Decode a glyph sequence: words of codes (``[["SG01", "SG09", "SG02"]]``), a flat list, or text
    (``"SG01 SG09 SG02"``, words separated by " / "). Uses nothing but the codes and this specification."""
    words = _words(sequence)
    tokens = [t for w in words for t in w]
    transcription = WORD_SEPARATOR.join(" ".join(w) for w in words)
    if not tokens:
        return SyntheticTranslation("insufficient_evidence", STATUS_TEXT["insufficient_evidence"], "", None, None, [],
                                    [], reason="no synthetic glyph was read, so there is nothing to transliterate or "
                                               "translate")
    translit = WORD_SEPARATOR.join(" ".join(LEXICON[t].reading if t in LEXICON else "[?]" for t in w) for w in words)
    unknown: list[dict[str, Any]] = [{"position": i, "glyph": t} for i, t in enumerate(tokens) if t not in LEXICON]
    if unknown:
        gloss = [({"position": i, "glyph": t, "reading": LEXICON[t].reading, "gloss": LEXICON[t].gloss,
                   "class": LEXICON[t].word_class, "role": "not parsed"} if t in LEXICON else
                  {"position": i, "glyph": t, "reading": None, "gloss": None, "class": "unknown", "role": "unknown glyph"})
                 for i, t in enumerate(tokens)]
        return SyntheticTranslation("unknown_glyph", STATUS_TEXT["unknown_glyph"], transcription, translit, None, gloss,
                                    [], unknown, tokens, reason="unknown glyph(s) "
                                    + ", ".join(f"{u['glyph']!r} at position {u['position'] + 1}" for u in unknown)
                                    + ": no translation is given, and no glyph is guessed")
    clauses: list[Clause] = []
    stop: _Stop | None = None
    i = 0
    while i < len(tokens):
        try:
            c, i = _clause(tokens, i)
        except _Stop as s:
            stop = s
            break
        clauses.append(c)
    role: dict[int, str] = {}
    for c in clauses:
        k = c.start
        for part, np_ in (("object", c.object), ("agent", c.agent)):
            if np_["numeral"]:
                role[k] = f"numeral of the {part}"
                k += 1
            role[k] = part
            k += 1
        role[k] = "verb"
        if c.negated:
            role[k + 1] = "negation"
    gloss = [{"position": j, "glyph": t, "reading": LEXICON[t].reading, "gloss": LEXICON[t].gloss,
              "class": LEXICON[t].word_class, "role": role.get(j, "not parsed")} for j, t in enumerate(tokens)]
    parse = [{"clause": n + 1, "glyphs": c.glyphs, "object": c.object, "agent": c.agent, "verb": c.verb,
              "negated": c.negated, "english": c.english} for n, c in enumerate(clauses)]
    sentences = " ".join(c.english for c in clauses)
    if stop is None:
        return SyntheticTranslation("translated", STATUS_TEXT["translated"], transcription, translit, sentences,
                                    gloss, parse)
    rest = tokens[clauses[-1].start + len(clauses[-1].glyphs):] if clauses else tokens
    where = f"at glyph {stop.position + 1}: {stop.reason}"
    if clauses:
        return SyntheticTranslation("partial", STATUS_TEXT["partial"], transcription, translit, sentences, gloss, parse,
                                    untranslated=rest, reason=f"{len(clauses)} complete clause(s) translated; the "
                                    f"remaining {len(rest)} glyph(s) do not form a clause ({where}) and are not translated")
    return SyntheticTranslation("invalid_sequence", STATUS_TEXT["invalid_sequence"], transcription, translit, None,
                                gloss, [], untranslated=rest, reason=f"no clause of the synthetic grammar ({where})")


# --------------------------------------------------------------------------- #
# Generation (used by the synthetic generator; never by the decoder)
# --------------------------------------------------------------------------- #


def _split(rng: np.random.Generator, n: int) -> list[int]:
    """Clause lengths (3-6 glyphs each) that add up to ``n`` (n >= 3)."""
    ks = [k for k in range(1, n // 3 + 1) if 3 * k <= n <= 6 * k]
    k = int(ks[int(rng.integers(len(ks)))])
    lengths = [3] * k
    for _ in range(n - 3 * k):
        open_ = [j for j, L in enumerate(lengths) if L < 6]
        lengths[open_[int(rng.integers(len(open_)))]] += 1
    return lengths


def sample_clause(rng: np.random.Generator, length: int) -> list[str]:
    """One valid clause of ``length`` glyphs (3-6): the extra glyphs are numerals and/or the negation."""
    slots = ["obj_num", "agent_num", "neg"]
    extras = set(rng.choice(slots, size=length - 3, replace=False).tolist()) if length > 3 else set()
    nouns, verbs, nums = BY_CLASS["noun"], BY_CLASS["verb"], BY_CLASS["numeral"]
    obj = nouns[int(rng.integers(len(nouns)))]
    agent = obj
    while agent == obj:
        agent = nouns[int(rng.integers(len(nouns)))]
    out = []
    if "obj_num" in extras:
        out.append(nums[int(rng.integers(len(nums)))])
    out.append(obj)
    if "agent_num" in extras:
        out.append(nums[int(rng.integers(len(nums)))])
    out += [agent, verbs[int(rng.integers(len(verbs)))]]
    if "neg" in extras:
        out.append(BY_CLASS["negation"][0])
    return out


def sample_sentence(rng: np.random.Generator, n: int) -> list[str]:
    """A valid sentence of exactly ``n`` glyphs (n >= 3)."""
    if n < 3:
        raise ValueError("a sentence of the synthetic language needs at least 3 glyphs")
    return [g for L in _split(rng, n) for g in sample_clause(rng, L)]


def target(sequence: list[list[str]]) -> dict[str, Any]:
    """The benchmark target of a TRUE glyph sequence (written into synthetic records; evaluation only)."""
    d = decode(sequence)
    return {"spec": SPEC_ID, "status": d.status, "transliteration": d.transliteration, "translation": d.translation}


__all__ = ["BANNER", "BY_CLASS", "CLASSES", "FICTION", "LEXICON", "METHOD", "METHOD_NOTE", "SPEC_ID", "SPEC_NAME",
           "SPEC_VERSION", "STATUSES", "STATUS_TEXT", "Entry", "SyntheticTranslation", "decode", "english",
           "sample_clause", "sample_sentence", "target"]
