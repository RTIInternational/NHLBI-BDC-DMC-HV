"""`update_data.py` must build the SAME artifact the standalone builders do.

The defect, raised on PR #831 and measured 2026-09-23: `process_cohort` called two builders of
its own that read only `variables.xml`, wrote `<cohort>.json.gz`, and never touched
`manifest.json`. Since this branch makes the release check mandatory, the onboarding command
MAINTENANCE.md documents -- `python hv-lint/update_data.py --cohort newcohort` -- produced a
provenance-unknown cache that Phase 3 then rejected. Nobody hit it because all eleven cohorts
already had caches built the other way; it was waiting for the next study to be onboarded.

These tests drive the real `process_cohort` with `fetch=False` against a synthetic staging
tree, so they exercise the path the documented command takes rather than calling `build_one`
directly -- the builders were never the broken part.

Run: python -m pytest hv-lint/tests/test_update_data_builds.py
"""

import gzip
import json
import sys
from pathlib import Path

import pytest

_HV_LINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HV_LINT))
import _cohorts  # noqa: E402
import update_data  # noqa: E402

DATA_DICT = """<?xml version="1.0"?>
<data_table id="{pht}.v1" study_id="{phs}.{ver}" participant_set="1">
  <variable id="{phv}.v1">
    <name>{name}</name>
    <description>a variable</description>
    <type>decimal</type>
  </variable>
</data_table>
"""


def _stage(tmp_path: Path, cohort: str, phs: str, ver: str, n: int = 2) -> Path:
    """A staging tree shaped like the one `fetch_ftp_data_dicts` writes."""
    cache = tmp_path / "dbgap-cache"
    ftp = cache / cohort / "pheno_variable_summaries"
    ftp.mkdir(parents=True)
    for i in range(n):
        pht = f"pht00{i}0001"
        (ftp / f"{phs}.{ver}.{pht}.v1.TABLE{i}.data_dict.xml").write_text(
            DATA_DICT.format(phs=phs, ver=ver, pht=pht, phv=f"phv0000000{i}", name=f"var{i}"),
            encoding="utf-8",
        )
    return cache


@pytest.fixture
def staged(tmp_path, monkeypatch):
    cache = _stage(tmp_path, "newcohort", "phs009999", "v3")
    monkeypatch.setattr(update_data, "CACHE_DIR", cache)
    return cache


def _build(cohort="newcohort", phs="phs009999", ver="v3.p1"):
    return update_data.process_cohort(
        cohort, {"study_id": phs, "data_version": ver}, fetch=False, build=True
    )


def test_the_documented_onboarding_command_writes_a_release_keyed_index(staged):
    """It wrote `<cohort>.json.gz` -- a name that records no release, which the mandatory
    check then rejects as unpinnable."""
    assert _build() is True
    assert (staged / "phs009999.v3.json.gz").is_file()
    assert (staged / "phs009999.v3_detail.json.gz").is_file()
    assert not (staged / "newcohort.json.gz").exists()
    assert not (staged / "newcohort_detail.json.gz").exists()


def test_it_records_provenance_so_the_mandatory_release_check_can_pass(staged):
    """The whole point: a cache built this way must be able to say which release it holds."""
    entry = _cohorts.manifest_entry(staged, "phs009999.v3")
    assert entry is None, "no manifest before the build"
    _build()
    entry = _cohorts.manifest_entry(staged, "phs009999.v3")
    assert entry["study"] == "phs009999"
    assert entry["study_version"] == "v3"
    assert entry["cohort"] == "NEWCOHORT"
    assert "PROVENANCE UNKNOWN" not in _cohorts.study_label(staged, "phs009999.v3")


def test_the_release_is_read_from_the_data_not_from_what_the_cohort_declares(staged):
    """A cohort declaring v9 over data dictionaries that say v3 must yield v3.

    Writing the DECLARED version would make the release check confirm itself: the cache would
    always agree with the declaration it is supposed to be checked against.
    """
    _build(ver="v9.p1")
    assert (staged / "phs009999.v3.json.gz").is_file()
    assert not (staged / "phs009999.v9.json.gz").exists()
    assert _cohorts.manifest_entry(staged, "phs009999.v3")["study_version"] == "v3"


def test_a_cohort_whose_data_dicts_name_two_releases_fails_rather_than_choosing(tmp_path,
                                                                                monkeypatch):
    """`study_from_data_dicts` refuses to choose; `process_cohort` must not paper over that
    with a directory-named, unprovenanced cache and a success return."""
    cache = _stage(tmp_path, "mixed", "phs009999", "v3")
    ftp = cache / "mixed" / "pheno_variable_summaries"
    (ftp / "phs009999.v4.pht0020001.v1.TABLE9.data_dict.xml").write_text(
        DATA_DICT.format(phs="phs009999", ver="v4", pht="pht0020001",
                         phv="phv00000099", name="var9"),
        encoding="utf-8",
    )
    monkeypatch.setattr(update_data, "CACHE_DIR", cache)
    assert _build(cohort="mixed") is False
    assert _cohorts.read_manifest(cache) == {}


def test_no_staged_source_is_an_error_rather_than_a_silent_no_op(tmp_path, monkeypatch):
    """`--build-only` on a fresh clone has no source tree: the XML is gitignored."""
    cache = tmp_path / "dbgap-cache"
    cache.mkdir()
    monkeypatch.setattr(update_data, "CACHE_DIR", cache)
    assert _build(cohort="absent") is False


def test_no_visit_cache_is_written(staged):
    """Step 5 wrote `<cohort>_visit.json` from regex-guessed metadata. Checks 5.5 and 5.7 were
    its only readers and both were removed, so the file is dead output."""
    _build()
    assert list(staged.glob("*_visit.json")) == []


def test_the_index_holds_the_phvs_from_the_data_dictionaries(staged):
    """Guards the delegation itself: the old builder read variables.xml, which a staging tree
    fetched for a new cohort may not even have yet."""
    _build()
    with gzip.open(staged / "phs009999.v3.json.gz", "rt", encoding="utf-8") as f:
        mapping = json.load(f)
    assert mapping == {"phv00000000": "pht0000001", "phv00000001": "pht0010001"}
