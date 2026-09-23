"""Wikimedia Commons adapter, using the official MediaWiki API only.

* Metadata and licence come from ``prop=imageinfo&iiprop=extmetadata``. That is Commons'
  own statement of the licence, the "original source" for an own-work upload.
* Files are fetched from the ``url`` the API returns (``upload.wikimedia.org``), not
  scraped from HTML.
* Requests are serialised and spaced by ``min_interval`` seconds. The User-Agent names
  the project, as Wikimedia's policy asks; a contact can be supplied via the
  ``ETPAI_CONTACT`` environment variable. No personal address is embedded in code.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol

from .policy import Candidate

API = "https://commons.wikimedia.org/w/api.php"


def user_agent() -> str:
    contact = os.environ.get("ETPAI_CONTACT", "").strip()
    suffix = f"; {contact}" if contact else ""
    return f"EarlyTamilPotteryAI/0.6 (non-commercial research prototype{suffix})"


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


class Fetcher(Protocol):
    """Anything that can describe and download files. Tests use a fake."""

    def describe(self, titles: list[str]) -> dict[str, Candidate | None]: ...
    def download(self, url: str, max_bytes: int) -> bytes: ...


class CommonsClient:
    def __init__(self, min_interval: float = 1.0, timeout: float = 60.0,
                 max_retries: int = 3, max_retry_after: float = 900.0) -> None:
        self.min_interval = min_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_retry_after = max_retry_after
        self._last = 0.0

    def _wait(self) -> None:
        delay = self.min_interval - (time.monotonic() - self._last)
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()

    def _get(self, url: str, max_bytes: int | None = None) -> bytes:
        """GET with politeness: fixed spacing, and on 429/503 wait for ``Retry-After``
        (capped at ``max_retry_after`` seconds) before a limited number of retries."""
        for attempt in range(self.max_retries + 1):
            self._wait()
            req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    length = resp.headers.get("Content-Length")
                    if max_bytes is not None and length and int(length) > max_bytes:
                        raise ValueError(f"{url}: {length} bytes exceeds limit {max_bytes}")
                    data = resp.read(max_bytes + 1 if max_bytes is not None else -1)
                break
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 503) or attempt == self.max_retries:
                    raise
                try:
                    wait = float(exc.headers.get("Retry-After") or 60)
                except ValueError:
                    wait = 60.0
                wait = min(max(wait, self.min_interval), self.max_retry_after)
                print(f"  server asked us to slow down (HTTP {exc.code}); waiting {wait:.0f}s",
                      flush=True)
                time.sleep(wait)
        if max_bytes is not None and len(data) > max_bytes:
            raise ValueError(f"{url}: download exceeds limit {max_bytes}")
        return data

    def describe(self, titles: list[str]) -> dict[str, Candidate | None]:
        out: dict[str, Candidate | None] = {t: None for t in titles}
        for i in range(0, len(titles), 40):
            chunk = titles[i:i + 40]
            params = {
                "action": "query", "format": "json", "formatversion": "2",
                "titles": "|".join(chunk), "prop": "imageinfo|categories", "cllimit": "max",
                "iiprop": "url|size|mime|sha1|extmetadata",
                "iiextmetadatafilter": ("LicenseShortName|LicenseUrl|Artist|Credit|"
                                        "ImageDescription|Restrictions|UsageTerms|Copyrighted"),
            }
            data = json.loads(self._get(API + "?" + urllib.parse.urlencode(params)))
            norm = {n["to"]: n["from"] for n in data.get("query", {}).get("normalized", [])}
            for page in data.get("query", {}).get("pages", []):
                title = norm.get(page.get("title"), page.get("title"))
                info = (page.get("imageinfo") or [None])[0]
                if page.get("missing") or info is None:
                    continue
                meta = info.get("extmetadata", {})

                def val(key: str, meta: dict = meta) -> str:
                    return _strip_html(meta.get(key, {}).get("value", ""))

                out[title] = Candidate(
                    source="wikimedia_commons",
                    title=title,
                    record_id=str(page.get("pageid", "")),
                    source_url=info.get("descriptionurl", ""),
                    original_image_url=info.get("url", ""),
                    license_verbatim=val("LicenseShortName"),
                    artist=val("Artist"),
                    credit=val("Credit"),
                    description=val("ImageDescription"),
                    categories=[c["title"] for c in page.get("categories", [])],
                    restrictions=val("Restrictions"),
                    mime=info.get("mime", ""),
                    size_bytes=int(info.get("size") or 0),
                    width=int(info.get("width") or 0),
                    height=int(info.get("height") or 0),
                    checksum=f"sha1:{info['sha1']}" if info.get("sha1") else "",
                    usage_terms=val("UsageTerms"),
                    extra={"license_url": val("LicenseUrl")},
                )
        return out

    def download(self, url: str, max_bytes: int) -> bytes:
        return self._get(url, max_bytes)


__all__ = ["API", "CommonsClient", "Fetcher", "user_agent"]
