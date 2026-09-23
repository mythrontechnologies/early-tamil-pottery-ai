"""Milestone 6 acquisition layer.

Every "downloaded" file here is a SYNTHETIC PNG generated in memory and served by a fake
fetcher. All output goes to pytest's tmp_path. No network, and nothing touches data/.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from src.acquisition.commons import user_agent
from src.acquisition.licenses import evaluate_license, normalise
from src.acquisition.pipeline import (
    DatasetPlan,
    ItemPlan,
    Plan,
    PlanError,
    load_plan,
    run,
    safe_destination,
)
from src.acquisition.policy import Candidate, evaluate
from src.acquisition.provenance import provenance_errors, read_registry
from src.dataset.convert import read_jsonl
from src.dataset.readiness import evaluate as readiness
from src.dataset.validation import validate_records

MB = 2**20


def png_bytes(seed: int, size: int = 64) -> bytes:
    """A SYNTHETIC flat-colour PNG, unique per seed. Not a photograph of anything."""
    img = Image.new("RGB", (size, size), (seed * 37 % 256, 80, 160))
    img.putpixel((seed % size, 0), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def candidate(title: str, data: bytes, **over) -> Candidate:
    base = dict(
        source="wikimedia_commons", title=title, record_id=str(abs(hash(title)) % 10**8),
        source_url=f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
        original_image_url=f"https://upload.wikimedia.org/fixture/{abs(hash(title))}.png",
        license_verbatim="CC BY-SA 4.0", artist="FIXTURE_PHOTOGRAPHER", credit="Own work",
        description="SYNTHETIC fixture description", categories=["Category:FIXTURE"],
        restrictions="", mime="image/png", size_bytes=len(data), width=64, height=64,
        checksum="sha1:" + hashlib.sha1(data).hexdigest(),
        extra={"license_url": "https://creativecommons.org/licenses/by-sa/4.0"},
    )
    base.update(over)
    return Candidate(**base)


class FakeFetcher:
    def __init__(self, cands: dict[str, Candidate], blobs: dict[str, bytes]) -> None:
        self.cands, self.blobs, self.downloads = cands, blobs, 0

    def describe(self, titles):
        return {t: self.cands.get(t) for t in titles}

    def download(self, url, max_bytes):
        self.downloads += 1
        return self.blobs[url]


def item(title: str, group: str = "FIXTURE_GROUP_1") -> ItemPlan:
    return ItemPlan(title=title, artifact_group=group, grouping_basis="SYNTHETIC fixture",
                    object_type="SYNTHETIC fixture object", curation_note="SYNTHETIC fixture",
                    find_site="FIXTURE_SITE", record={"site": "FIXTURE_SITE"})


def make_plan(items, target="research", subdir="fixture_pottery/commons", **kw) -> Plan:
    ds = DatasetPlan(dataset_id="fixture_ds", dataset_name="SYNTHETIC fixture dataset",
                     target=target, subdir=subdir, source="wikimedia_commons",
                     source_name="FIXTURE", source_url="https://commons.wikimedia.org/wiki/FIXTURE",
                     geographic_scope="unknown", archaeological_period="not_stated_by_source",
                     script_scope="not_stated_by_source", items=items, **kw)
    return Plan(curator="SYNTHETIC test", datasets=[ds])


@pytest.fixture
def roots(tmp_path: Path) -> dict[str, Path]:
    r = {k: tmp_path / k for k in ("raw", "external", "staging", "acq")}
    for p in r.values():
        p.mkdir()
    r["records"] = tmp_path / "records.jsonl"
    return r


def go(plan, fetcher, roots, dry_run=False):
    return run(plan, fetcher, dry_run=dry_run, raw_root=roots["raw"],
               external_root=roots["external"], staging_root=roots["staging"],
               records_path=roots["records"], acquisition_dir=roots["acq"], today="2026-09-23")


def single(roots, **over):
    data = png_bytes(1)
    c = candidate("File:FIXTURE one.png", data, **over)
    fetcher = FakeFetcher({c.title: c}, {c.original_image_url: data})
    return go(make_plan([item(c.title)]), fetcher, roots), fetcher


# --------------------------------------------------------------------------- #
# Licences
# --------------------------------------------------------------------------- #


class TestLicences:
    @pytest.mark.parametrize("text,expected", [
        ("CC BY-SA 4.0", "CC-BY-SA-4.0"), ("CC BY 4.0", "CC-BY-4.0"), ("CC0", "CC0-1.0"),
        ("cc-by-sa-3.0", "CC-BY-SA-3.0"), ("CC BY-NC-SA 4.0", "CC-BY-NC-SA-4.0"),
        ("Public domain", "public_domain"), ("GODL-India", "GODL-India"), ("", "unknown"),
        ("All rights reserved", "unknown"),
    ])
    def test_normalise(self, text, expected):
        assert normalise(text) == expected

    @pytest.mark.parametrize("text", ["CC BY-NC-SA 4.0", "CC BY-ND 4.0", "Public domain",
                                      "GODL-India", "", "Copyrighted free use"])
    def test_non_allow_listed_licences_are_refused(self, text):
        assert not evaluate_license(text).accepted

    def test_allowed_licence_rights_follow_the_licence(self):
        by_sa, cc0 = evaluate_license("CC BY-SA 4.0"), evaluate_license("CC0")
        assert by_sa.research_usable == "yes" and by_sa.share_alike_required
        assert by_sa.attribution_required and not cc0.attribution_required


# --------------------------------------------------------------------------- #
# Policy
# --------------------------------------------------------------------------- #


class TestPolicy:
    def ok(self, **over):
        return evaluate(candidate("File:x.png", b"x", **{"size_bytes": 10, **over}),
                        max_file_bytes=MB)

    def test_clean_candidate_accepted(self):
        assert self.ok().accepted

    def test_licence_required(self):
        d = self.ok(license_verbatim="")
        assert not d.accepted and any(r.startswith("A3") for r in d.reasons)

    def test_unknown_licence_rejected(self):
        assert any("A3" in r for r in self.ok(license_verbatim="Some licence").reasons)

    def test_missing_source_url_rejected(self):
        assert any(r.startswith("A2: source_url is missing") for r in self.ok(source_url="").reasons)

    def test_non_https_rejected(self):
        assert any("not https" in r for r in self.ok(source_url="http://example.org/x").reasons)

    @pytest.mark.parametrize("url", ["https://www.scribd.com/document/1", "https://archive.org/details/x",
                                     "https://www.tnarch.gov.in/keeladi",
                                     "https://tamildigitallibrary.in/assets/x.pdf",
                                     "https://pdfcoffee.com/x"])
    def test_copyrighted_or_unauthorised_sources_are_blocked(self, url):
        assert any("blocked source" in r for r in self.ok(original_image_url=url).reasons)

    def test_third_party_upload_rejected(self):
        d = self.ok(credit="From a newspaper website")
        assert any(r.startswith("A4") for r in d.reasons)

    def test_copyright_violation_flag_rejected(self):
        d = self.ok(categories=["Category:Copyright violations"])
        assert any(r.startswith("A5") for r in d.reasons)

    def test_restrictions_rejected(self):
        assert any(r.startswith("A5") for r in self.ok(restrictions="personality").reasons)

    def test_missing_provenance_rejected(self):
        d = self.ok(artist="", checksum="")
        assert sum(r.startswith("A6") for r in d.reasons) == 2

    def test_unsupported_mime_rejected(self):
        assert any(r.startswith("A7") for r in self.ok(mime="application/pdf").reasons)

    def test_oversized_file_rejected(self):
        assert any(r.startswith("A8") for r in self.ok(size_bytes=2 * MB).reasons)

    def test_unknown_adapter_rejected(self):
        assert any(r.startswith("A1") for r in self.ok(source="random_scraper").reasons)


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #


class TestPipeline:
    def test_dry_run_writes_nothing(self, roots):
        data = png_bytes(1)
        c = candidate("File:FIXTURE one.png", data)
        fetcher = FakeFetcher({c.title: c}, {c.original_image_url: data})
        report = go(make_plan([item(c.title)]), fetcher, roots, dry_run=True)
        assert report.count("planned") == 1 and fetcher.downloads == 0
        assert not any(roots["raw"].rglob("*.png")) and not roots["records"].exists()
        assert read_registry(roots["acq"] / "provenance.jsonl") == []

    def test_acquisition_end_to_end(self, roots):
        report, _ = single(roots)
        assert report.count("acquired") == 1, report.render()
        [f] = list(roots["raw"].rglob("*.png"))
        records = read_jsonl(roots["records"])
        assert len(records) == 1
        rec = records[0]
        assert rec["image_sha256"] == hashlib.sha256(f.read_bytes()).hexdigest()
        assert rec["script_type"] == "unknown" and rec["inscription_present"] == "unknown"
        assert rec["label_source"] == "unknown" and rec["verification_status"] == "unverified"
        assert rec["research_usable"] == "yes" and rec["license"] == "CC-BY-SA-4.0"
        assert validate_records(records, data_root=roots["raw"], verify_hashes=True).ok
        [prov] = read_registry(roots["acq"] / "provenance.jsonl")
        assert provenance_errors(prov) == []
        assert prov["project_label"] == "unknown" and prov["source_checksum_verified"]
        assert "FIXTURE" in prov["attribution_text"]
        manifest = json.loads((roots["acq"] / "manifests" / "fixture_ds.json").read_text())
        assert manifest["number_of_files"] == 1 and manifest["license"] == ["CC-BY-SA-4.0"]

    def test_checksum_mismatch_places_nothing(self, roots):
        data = png_bytes(1)
        c = candidate("File:FIXTURE one.png", data, checksum="sha1:" + "0" * 40)
        report = go(make_plan([item(c.title)]), FakeFetcher({c.title: c}, {c.original_image_url: data}),
                    roots)
        assert report.count("failed") == 1 and "checksum mismatch" in report.items[0].reasons[0]
        assert not any(roots["raw"].rglob("*.*")) and not roots["records"].exists()

    def test_corrupt_image_is_rejected(self, roots):
        data = b"\xff\xd8\xff not really a jpeg"
        c = candidate("File:FIXTURE broken.jpg", data, mime="image/jpeg")
        report = go(make_plan([item(c.title)]), FakeFetcher({c.title: c}, {c.original_image_url: data}),
                    roots)
        assert report.count("failed") == 1 and "image checks failed" in report.items[0].reasons[0]
        assert not any(roots["raw"].rglob("*.*"))

    def test_duplicate_bytes_within_batch(self, roots):
        data = png_bytes(1)
        a = candidate("File:FIXTURE a.png", data)
        b = candidate("File:FIXTURE b.png", data)
        fetcher = FakeFetcher({a.title: a, b.title: b}, {a.original_image_url: data,
                                                         b.original_image_url: data})
        report = go(make_plan([item(a.title), item(b.title, "FIXTURE_GROUP_2")]), fetcher, roots)
        assert report.count("acquired") == 1 and report.count("failed") == 1
        assert any("duplicate image" in r for i in report.items for r in i.reasons)

    def test_rerun_is_idempotent(self, roots):
        single(roots)
        report, fetcher = single(roots)
        assert report.count("already_present") == 1 and fetcher.downloads == 0
        assert len(read_jsonl(roots["records"])) == 1

    def test_policy_rejection_downloads_nothing(self, roots):
        report, fetcher = single(roots, license_verbatim="CC BY-NC 4.0")
        assert report.count("rejected") == 1 and fetcher.downloads == 0

    def test_total_size_budget(self, roots):
        data = png_bytes(1)
        c = candidate("File:FIXTURE one.png", data, size_bytes=3 * MB)
        plan = make_plan([item(c.title)])
        plan.max_total_mb = 1
        report = go(plan, FakeFetcher({c.title: c}, {c.original_image_url: data}), roots)
        assert report.count("rejected") == 1 and "max_total_mb" in report.items[0].reasons[0]

    def test_external_target_gets_no_research_record(self, roots):
        data = png_bytes(2)
        c = candidate("File:FIXTURE ext.png", data)
        report = go(make_plan([item(c.title)], target="external", subdir="fixture_supporting"),
                    FakeFetcher({c.title: c}, {c.original_image_url: data}), roots)
        assert report.count("acquired") == 1
        assert list(roots["external"].rglob("*.png")) and not any(roots["raw"].rglob("*.png"))
        assert not roots["records"].exists()

    def test_ingestion_refusal_rolls_back_files(self, roots):
        data = png_bytes(3)
        c = candidate("File:FIXTURE clash.png", data)
        # A pre-existing record claims the same image_id: ingestion (R1) must refuse.
        roots["records"].write_text(json.dumps({"image_id": f"wmc_{c.record_id}"}) + "\n",
                                    encoding="utf-8")
        report = go(make_plan([item(c.title)]), FakeFetcher({c.title: c}, {c.original_image_url: data}),
                    roots)
        assert report.count("failed") == 1
        assert not any(roots["raw"].rglob("*.png"))
        assert read_registry(roots["acq"] / "provenance.jsonl") == []

    def test_acquired_records_do_not_open_the_training_gate(self, roots):
        single(roots)
        report = readiness(roots["records"], roots["raw"], permit_noncanonical_source=True)
        gates = {g["id"]: g["passed"] for g in report.gates}
        assert not report.training_ready
        assert gates["G4"] and gates["G5"]              # data is valid...
        assert gates["G9"] is False                     # ...but carries no training labels


class TestPathSafety:
    def test_traversal_in_filename_refused(self, tmp_path):
        with pytest.raises(PlanError):
            safe_destination(tmp_path, "ok", "../escape.png")

    def test_traversal_in_subdir_refused(self, tmp_path):
        with pytest.raises(ValueError):
            safe_destination(tmp_path, "../../outside", "x.png")

    def test_unsafe_subdir_in_plan_refused(self, tmp_path):
        p = tmp_path / "plan.yaml"
        p.write_text("curator: SYNTHETIC\ndatasets:\n- dataset_id: fixture_ds\n  dataset_name: x\n"
                     "  target: research\n  subdir: ../raw\n  source: wikimedia_commons\n"
                     "  source_name: x\n  source_url: https://x\n  geographic_scope: unknown\n"
                     "  archaeological_period: x\n  script_scope: x\n  items: []\n", encoding="utf-8")
        with pytest.raises(PlanError, match="unsafe subdir"):
            load_plan(p)

    def test_research_record_must_live_under_raw(self, roots):
        single(roots)
        rec = read_jsonl(roots["records"])[0]
        assert not rec["image_path"].startswith(("/", "..", "data/"))


class TestProvenanceSchema:
    def test_missing_field_is_invalid(self, roots):
        single(roots)
        [prov] = read_registry(roots["acq"] / "provenance.jsonl")
        del prov["license"]
        assert any("license" in e for e in provenance_errors(prov))

    def test_disallowed_licence_cannot_be_recorded(self, roots):
        single(roots)
        [prov] = read_registry(roots["acq"] / "provenance.jsonl")
        prov["license"] = "CC-BY-NC-4.0"
        assert provenance_errors(prov)


class TestNetworkHygiene:
    def test_user_agent_has_no_personal_address_by_default(self, monkeypatch):
        monkeypatch.delenv("ETPAI_CONTACT", raising=False)
        assert "@" not in user_agent() and "EarlyTamilPotteryAI" in user_agent()

    def test_contact_is_opt_in(self, monkeypatch):
        monkeypatch.setenv("ETPAI_CONTACT", "SYNTHETIC-contact")
        assert "SYNTHETIC-contact" in user_agent()

    def test_shipped_plan_is_valid_and_excludes_known_problems(self):
        from src.dataset.schema import ROOT

        plan = load_plan(ROOT / "configs" / "acquisition" / "milestone6_wikimedia_commons.yaml")
        excluded = {t for d in plan.datasets for t in d.excluded}
        assert "File:Archaeological Excavation, Kodumanal.jpg" in excluded
        assert "File:Mangulam inscription.jpg" in excluded
        assert {d.target for d in plan.datasets} == {"research", "external"}
