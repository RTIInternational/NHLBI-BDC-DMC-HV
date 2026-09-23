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


def test_a_version_bump_retires_the_superseded_data_dictionaries(tmp_path, monkeypatch):
    """The bump this branch exists to support was the one operation that did not work.

    One staging directory per cohort is reused across releases and the FTP fetch ADDS
    filenames rather than replacing them, so a v4 fetch over a v3 tree left both.
    `study_from_data_dicts` then refuses to choose -- correctly, the directory has no single
    answer -- and the documented update command could not build the new cache.
    """
    cache = _stage(tmp_path, "bumped", "phs009999", "v3")
    ftp = cache / "bumped" / "pheno_variable_summaries"
    assert len(list(ftp.glob("*.data_dict.xml"))) == 2
    monkeypatch.setattr(update_data, "CACHE_DIR", cache)

    assert update_data.staged_release_differs(cache / "bumped", "phs009999", "v4.p1") is True
    retired = update_data.retire_superseded_data_dicts(ftp, "phs009999", "v4.p1")
    assert retired == 2
    assert list(ftp.glob("*.data_dict.xml")) == []


def test_re_fetching_the_same_release_retires_nothing(tmp_path):
    """The guard must fire on a bump, not on every fetch."""
    cache = _stage(tmp_path, "same", "phs009999", "v3")
    ftp = cache / "same" / "pheno_variable_summaries"
    assert update_data.staged_release_differs(cache / "same", "phs009999", "v3.p1") is False
    assert update_data.retire_superseded_data_dicts(ftp, "phs009999", "v3.p1") == 0
    assert len(list(ftp.glob("*.data_dict.xml"))) == 2


def test_a_first_fetch_is_not_mistaken_for_a_bump(tmp_path):
    """Nothing staged means no disagreement, not a disagreement."""
    empty = tmp_path / "fresh"
    (empty / "pheno_variable_summaries").mkdir(parents=True)
    assert update_data.staged_release_differs(empty, "phs009999", "v3.p1") is False


def test_data_dictionaries_that_do_not_carry_a_release_are_left_alone(tmp_path):
    """A name that does not match the dbGaP stamp is not guessed about."""
    cache = _stage(tmp_path, "odd", "phs009999", "v3")
    ftp = cache / "odd" / "pheno_variable_summaries"
    (ftp / "hand_written.data_dict.xml").write_text("<x/>", encoding="utf-8")
    update_data.retire_superseded_data_dicts(ftp, "phs009999", "v4.p1")
    assert [p.name for p in ftp.glob("*.data_dict.xml")] == ["hand_written.data_dict.xml"]


def test_a_failed_fetch_is_not_indexed(tmp_path, monkeypatch):
    """The builders read whatever is on disk and stamp the release they find, so building over
    a half-fetched tree records a release it does not completely hold -- provenance it has not
    earned, indistinguishable at lint time from a complete cache."""
    cache = _stage(tmp_path, "partial", "phs009999", "v3")
    monkeypatch.setattr(update_data, "CACHE_DIR", cache)
    monkeypatch.setattr(update_data, "fetch_cgi_index", lambda *a, **k: True)
    monkeypatch.setattr(update_data, "fetch_ftp_data_dicts", lambda *a, **k: False)

    result = update_data.process_cohort(
        "partial", {"study_id": "phs009999", "data_version": "v3.p1"}, fetch=True, build=True
    )
    assert result is False
    assert list(cache.glob("*.json.gz")) == [], "nothing may be written after a failed fetch"
    assert _cohorts.read_manifest(cache) == {}


def test_both_builders_must_succeed_before_provenance_is_recorded(tmp_path, monkeypatch):
    """A valid PHV mapping must not mask a corrupt data-dictionary set.

    `variables.xml` can carry the PHV->PHT mapping on its own, so the basic index succeeds
    while the detail index -- which can only come from the dictionaries -- parses to zero
    records. Writing provenance then claims a complete cache, and the missing detail index
    surfaces much later as a lint-time ERROR against the cohort rather than a build failure.
    """
    cache = tmp_path / "dbgap-cache"
    ftp = cache / "halfbuilt" / "pheno_variable_summaries"
    ftp.mkdir(parents=True)
    # Valid FILENAME (so the release is parseable) over unparseable CONTENT.
    (ftp / "phs009999.v3.pht0000001.v1.T0.data_dict.xml").write_text(
        "<data_table><unclosed>", encoding="utf-8")
    (cache / "halfbuilt" / "variables.xml").write_text(
        "<table><tr><td>phv00000001.v1</td><td>n</td><td>d</td>"
        "<td>pht0000001.v1</td><td>ds</td></tr></table>", encoding="utf-8")
    monkeypatch.setattr(update_data, "CACHE_DIR", cache)

    assert _build(cohort="halfbuilt") is False
    assert _cohorts.read_manifest(cache) == {}, "no provenance for a half-built pair"
    assert not (cache / "phs009999.v3_detail.json.gz").exists()


def test_a_superseded_variables_xml_is_discarded_even_if_the_refetch_fails(tmp_path,
                                                                           monkeypatch):
    """Found by audit, not by review: re-fetching is not enough.

    `variables.xml` carries no release in its name and the PHV index merges it as a supplement.
    If it is merely marked for re-fetch and the re-fetch fails, the stale copy survives -- and
    a later `--build-only` run skips fetching entirely, so it never reaches this check and
    folds a superseded release's mappings into an artifact keyed to the new one. Discarding is
    the safe direction: a missing supplement costs coverage, a stale one costs correctness.
    """
    cache = _stage(tmp_path, "bump", "phs009999", "v3")
    variables = cache / "bump" / "variables.xml"
    variables.write_text("<table/>", encoding="utf-8")
    monkeypatch.setattr(update_data, "CACHE_DIR", cache)

    class _Dead:
        def get(self, *a, **k):
            raise RuntimeError("network down")

        cache = type("C", (), {"delete": staticmethod(lambda **k: None)})()

    monkeypatch.setitem(sys.modules, "_http", type(sys)("_http"))
    sys.modules["_http"].get_session = lambda: _Dead()

    assert update_data.fetch_cgi_index("bump", "phs009999", "v4.p1") is False
    assert not variables.exists(), "a superseded variables.xml must not survive a failed fetch"


def test_a_half_built_pair_publishes_neither_artifact(tmp_path, monkeypatch):
    """Returning False is not enough if the first builder's file is already on disk.

    Against an existing manifest entry from an earlier successful build, a freshly written but
    THINNER basic index reads as a valid release-keyed cache -- the failure is invisible to
    every consumer, because the one thing that would have flagged it (the manifest) still
    describes the older, complete build.
    """
    cache = tmp_path / "dbgap-cache"
    ftp = cache / "half" / "pheno_variable_summaries"
    ftp.mkdir(parents=True)
    (ftp / "phs009999.v3.pht0000001.v1.T0.data_dict.xml").write_text(
        "<data_table><unclosed>", encoding="utf-8")
    (cache / "half" / "variables.xml").write_text(
        "<table><tr><td>phv00000001.v1</td><td>n</td><td>d</td>"
        "<td>pht0000001.v1</td><td>ds</td></tr></table>", encoding="utf-8")
    # an existing good cache for the same release, as a prior successful build would leave
    (cache / "phs009999.v3.json.gz").write_bytes(b"prior")
    monkeypatch.setattr(update_data, "CACHE_DIR", cache)

    assert _build(cohort="half") is False
    assert (cache / "phs009999.v3.json.gz").read_bytes() == b"prior", \
        "the prior artifact must not be overwritten by a half-built pair"
    assert not (cache / "phs009999.v3_detail.json.gz").exists()
    assert list(cache.glob(".build-*")) == [], "the scratch directory is cleaned up"


def test_an_ftp_listing_with_no_dictionaries_refuses_to_leave_a_superseded_release(tmp_path,
                                                                                    monkeypatch):
    """The no-targets path returned success before reaching the retire step, so a bump over a
    cohort that previously had dictionaries kept the old release for the builders to index and
    provenance-stamp as the release that was asked for."""
    cache = _stage(tmp_path, "empty_listing", "phs009999", "v3")
    monkeypatch.setattr(update_data, "CACHE_DIR", cache)

    class _EmptyListing:
        text = "<html><a href='readme.txt'>readme</a></html>"

        def raise_for_status(self):
            return None

        def get(self, *a, **k):
            return self

    stub = type(sys)("_http")
    stub.get_session = lambda: _EmptyListing()
    monkeypatch.setitem(sys.modules, "_http", stub)

    # v4 asked for, no dictionaries offered, v3 still staged -> refuse
    assert update_data.fetch_ftp_data_dicts("empty_listing", "phs009999", "v4.p1") is False
    # a study that genuinely has none, with nothing staged, stays benign
    (cache / "nostage" / "pheno_variable_summaries").mkdir(parents=True)
    assert update_data.fetch_ftp_data_dicts("nostage", "phs009999", "v4.p1") is True


def test_the_index_holds_the_phvs_from_the_data_dictionaries(staged):
    """Guards the delegation itself: the old builder read variables.xml, which a staging tree
    fetched for a new cohort may not even have yet."""
    _build()
    with gzip.open(staged / "phs009999.v3.json.gz", "rt", encoding="utf-8") as f:
        mapping = json.load(f)
    assert mapping == {"phv00000000": "pht0000001", "phv00000001": "pht0010001"}
