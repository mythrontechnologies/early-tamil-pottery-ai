"""Acquisition policy: may this file be acquired automatically?

A candidate is accepted only if **every** check passes. Each failure is reported. The
checks are about rights and provenance, never about archaeological content:

``A1`` the source adapter is approved (official API, licence stated by the source itself)
``A2`` the source page and file URLs are https and not on the blocked-source list
``A3`` the licence, as read from the source API, is on the allow-list (see ``licenses``)
``A4`` the uploader states it is their own work (so the source *is* the original source);
       otherwise the licence must be verified upstream, which automation cannot do
``A5`` the source carries no rights restrictions or copyright-violation / deletion flags
``A6`` every provenance field needed for attribution is present
``A7`` the MIME type is a supported image type
``A8`` the file size is within the configured per-file limit
``A9`` the curator has not excluded the file

Blocked sources (``A2``) are the ones the Milestone 4 audit found to carry copyrighted or
unauthorised material: document-sharing mirrors, Internet Archive re-uploads, TNSDA and
Tamil Digital Library publications (no reuse licence), and academic-network copies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .licenses import LicenseDecision, evaluate_license

APPROVED_SOURCES: dict[str, str] = {
    "wikimedia_commons": "Wikimedia Commons (MediaWiki API; licence read from extmetadata)",
}

#: Hosts each adapter may name (defence in depth: a candidate is refused if its page or its
#: image URL points anywhere else, even when the domain is not on the block list).
APPROVED_HOSTS: dict[str, dict[str, tuple[str, ...]]] = {
    "wikimedia_commons": {"source_url": ("commons.wikimedia.org",),
                          "original_image_url": ("upload.wikimedia.org",)},
}

BLOCKED_DOMAINS: tuple[str, ...] = (
    "scribd.com", "pdfcoffee.com", "toaz.info", "archive.org",
    "tnarch.gov.in", "tamildigitallibrary.in",
    "researchgate.net", "academia.edu",
    "vinavu.com", "cdn.thewire.in",
)

SUPPORTED_MIME: tuple[str, ...] = ("image/jpeg", "image/png", "image/tiff", "image/webp")

OWN_WORK_MARKERS: tuple[str, ...] = ("own work", "self-made", "self made", "selbst fotografiert")

VIOLATION_CATEGORY_MARKERS: tuple[str, ...] = (
    "copyright violation", "deletion request", "possible copyright", "no permission",
    "no license", "no source", "media without a license", "speedy deletion",
)

RULES: dict[str, str] = {
    "A1": "source adapter is approved",
    "A2": "source URLs are https and not on the blocked-source list",
    "A3": "licence from the source API is on the allow-list",
    "A4": "uploader states own work (the source is the original source)",
    "A5": "no rights restrictions or copyright-violation flags at the source",
    "A6": "attribution provenance is complete",
    "A7": "supported image MIME type",
    "A8": "file size within the per-file limit",
    "A9": "not excluded by the curator",
}


@dataclass
class Candidate:
    """What the source says about one file. Filled from the source API, never by hand."""

    source: str
    title: str
    record_id: str
    source_url: str
    original_image_url: str
    license_verbatim: str
    artist: str
    credit: str
    description: str
    categories: list[str]
    restrictions: str
    mime: str
    size_bytes: int
    width: int
    height: int
    checksum: str                      # e.g. "sha1:<hex>"
    usage_terms: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    accepted: bool
    reasons: list[str]
    license: LicenseDecision

    def summary(self) -> str:
        return "ACCEPT" if self.accepted else "REJECT: " + "; ".join(self.reasons)


def _domain(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _blocked(url: str) -> bool:
    d = _domain(url)
    return any(d == b or d.endswith("." + b) for b in BLOCKED_DOMAINS)


def evaluate(candidate: Candidate, *, max_file_bytes: int, excluded: dict[str, str] | None = None
             ) -> Decision:
    reasons: list[str] = []
    c = candidate
    lic = evaluate_license(c.license_verbatim)

    if c.source not in APPROVED_SOURCES:
        reasons.append(f"A1: source {c.source!r} is not an approved adapter")
    for label, url in (("source_url", c.source_url), ("original_image_url", c.original_image_url)):
        if not url:
            reasons.append(f"A2: {label} is missing")
        elif not url.startswith("https://"):
            reasons.append(f"A2: {label} is not https: {url}")
        elif _blocked(url):
            reasons.append(f"A2: {label} is on a blocked source ({_domain(url)})")
        elif (hosts := APPROVED_HOSTS.get(c.source, {}).get(label)) and _domain(url) not in hosts:
            reasons.append(f"A2: {label} host {_domain(url)!r} is not an approved host for {c.source} "
                           f"({', '.join(hosts)})")
    if not lic.accepted:
        reasons.append(f"A3: {lic.reason}")
    if not any(m in c.credit.lower() for m in OWN_WORK_MARKERS):
        reasons.append(f"A4: credit {c.credit[:60]!r} does not state own work; the licence would "
                       "have to be verified at the upstream source")
    if c.restrictions.strip():
        reasons.append(f"A5: source lists rights restrictions: {c.restrictions[:80]!r}")
    flagged = [cat for cat in c.categories
               if any(m in cat.lower() for m in VIOLATION_CATEGORY_MARKERS)]
    if flagged:
        reasons.append(f"A5: source flags the file: {flagged[:3]}")
    for name in ("title", "record_id", "artist", "checksum"):
        if not str(getattr(c, name) or "").strip():
            reasons.append(f"A6: provenance field {name!r} is missing")
    if c.mime not in SUPPORTED_MIME:
        reasons.append(f"A7: MIME type {c.mime!r} is not a supported image type")
    if not c.size_bytes or c.size_bytes > max_file_bytes:
        reasons.append(f"A8: size {c.size_bytes} bytes outside (0, {max_file_bytes}]")
    if excluded and c.title in excluded:
        reasons.append(f"A9: excluded by curator: {excluded[c.title]}")
    return Decision(not reasons, reasons, lic)


__all__ = [
    "APPROVED_HOSTS",
    "APPROVED_SOURCES",
    "BLOCKED_DOMAINS",
    "RULES",
    "SUPPORTED_MIME",
    "Candidate",
    "Decision",
    "evaluate",
]
