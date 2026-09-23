"""Licence normalisation and the automatic-acquisition allow-list.

A file may be acquired **automatically** only under a licence that explicitly permits
reuse for research, including adaptation (preprocessing and training produce derivatives)
and redistribution with attribution:

    CC0 1.0, CC BY 2.0-4.0, CC BY-SA 2.0-4.0

Everything else is refused, with a reason, and at most recorded as a lead for human
review:

* **NC** licences permit non-commercial research, but not every use of a model trained
  on them. They need a human decision, not an automatic one.
* **ND** licences forbid adaptations, and preprocessing is an adaptation.
* **"Public domain"** labels cover many different legal bases (age, government work,
  dedication). They are too heterogeneous to accept without a human reading the basis.
* **GODL-India** and other government licences are refused when the licence is asserted by
  a re-uploader rather than by the originating government portal.
* Anything unrecognised is **unknown**, and unknown means no.

Rights derived from an accepted licence are fixed by the licence text, not guessed:
all allowed licences permit research use, redistribution and commercial use; all but CC0
require attribution; BY-SA requires share-alike.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ALLOWED: dict[str, str] = {
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY-2.0": "https://creativecommons.org/licenses/by/2.0/",
    "CC-BY-2.5": "https://creativecommons.org/licenses/by/2.5/",
    "CC-BY-3.0": "https://creativecommons.org/licenses/by/3.0/",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC-BY-SA-2.0": "https://creativecommons.org/licenses/by-sa/2.0/",
    "CC-BY-SA-2.5": "https://creativecommons.org/licenses/by-sa/2.5/",
    "CC-BY-SA-3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
}


@dataclass(frozen=True)
class LicenseDecision:
    accepted: bool
    license_id: str            # normalised id, or "unknown"
    verbatim: str
    reason: str
    license_url: str = ""
    attribution_required: bool = True
    share_alike_required: bool = False
    research_usable: str = "unknown"
    redistribution_allowed: str = "unknown"
    commercially_usable: str = "unknown"


def normalise(verbatim: str | None) -> str:
    """Map a licence string (e.g. Commons ``LicenseShortName``) to a normalised id."""
    if not verbatim:
        return "unknown"
    s = re.sub(r"\s+", " ", verbatim.strip()).upper().replace("_", " ")
    if s in {"CC0", "CC0 1.0", "CC ZERO", "CC-ZERO", "CC0-1.0"}:
        return "CC0-1.0"
    m = re.fullmatch(r"CC[ -]((?:BY)(?:[ -](?:SA|NC|ND))*)[ -]?(\d\.\d)(?: [A-Z ]+)?", s)
    if m:
        parts = m.group(1).replace(" ", "-")
        return f"CC-{parts}-{m.group(2)}"
    if "PUBLIC DOMAIN" in s or s in {"PD", "PDM", "PUBLIC-DOMAIN"}:
        return "public_domain"
    if "GODL" in s:
        return "GODL-India"
    return "unknown"


def evaluate_license(verbatim: str | None) -> LicenseDecision:
    lic = normalise(verbatim)
    text = verbatim or ""
    if lic in ALLOWED:
        return LicenseDecision(
            accepted=True, license_id=lic, verbatim=text,
            reason=f"{lic} explicitly permits reuse, adaptation and redistribution",
            license_url=ALLOWED[lic],
            attribution_required=lic != "CC0-1.0",
            share_alike_required="-SA-" in lic,
            research_usable="yes", redistribution_allowed="yes", commercially_usable="yes",
        )
    if lic == "unknown":
        reason = f"licence {text!r} not recognised; unknown licence means no"
    elif "-ND-" in lic or lic.endswith("-ND"):
        reason = f"{lic} forbids adaptations; preprocessing and training are adaptations"
    elif "-NC-" in lic:
        reason = f"{lic} is non-commercial; needs a human decision, not automatic acquisition"
    elif lic == "public_domain":
        reason = ("'public domain' label without a verified legal basis; needs a human to "
                  "read the specific PD rationale")
    elif lic == "GODL-India":
        reason = ("GODL-India asserted by a re-uploader, not by the originating government "
                  "portal; not verified from the original source")
    else:
        reason = f"{lic} is not on the automatic-acquisition allow-list"
    return LicenseDecision(accepted=False, license_id=lic, verbatim=text, reason=reason)


__all__ = ["ALLOWED", "LicenseDecision", "evaluate_license", "normalise"]
