"""Tests for hv-lint/_cohorts.py -- cohort/cache resolution and study provenance.

Every case here is a defect measured on 2026-09-10, not a hypothetical:

* ``--cohort LTRC`` was rejected by two Phase 1 scripts as an invalid argparse choice, so
  Phase 1 reported FAILED over 45 files it never read.
* ``--cohort all`` expanded to a fixed ten-cohort list, so a tree holding only an unlisted
  cohort scanned 0 files and exited 0.
* ``run_all.py`` upper-cased the cohort, producing ``COPDGENE`` against a mixed-case
  ``COPDGene`` choice -- so COPDGene's yamllint and quoting checks never ran through it either.
* the caches recorded no dbGaP study version at all, so nothing could say whether a PHV
  finding came from a current or a superseded release.

Run: python -m pytest hv-lint/tests/test_cohorts.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _cohorts  # noqa: E402


def _cache(tmp_path: Path, *keys: str, manifest: dict | None = None) -> Path:
    """Make a cache dir. ``tmp_path`` may be a pytest tmp_path (a `dbgap-cache` child is added)
    or an explicit directory to use as-is."""
    d = tmp_path if tmp_path.name == "dbgap-cache" else tmp_path / "dbgap-cache"
    d.mkdir(parents=True, exist_ok=True)
    for key in keys:
        (d / f"{key}.json.gz").write_bytes(b"")
        (d / f"{key}_detail.json.gz").write_bytes(b"")
    if manifest is not None:
        (d / _cohorts.MANIFEST_NAME).write_text(
            json.dumps({"manifest_version": 1, "entries": manifest}), encoding="utf-8")
    return d


def _ingest(tmp_path: Path, *cohorts: str) -> Path:
    d = tmp_path / "priority_variables_transform"
    for c in cohorts:
        (d / f"{c}-ingest").mkdir(parents=True)
    return d


def _staged(tmp_path: Path, name: str, accession: str, version: str, phts: int = 2) -> Path:
    d = tmp_path / name / "pheno_variable_summaries"
    d.mkdir(parents=True)
    for i in range(phts):
        (d / f"{accession}.{version}.pht01000{i}.v1.TABLE{i}.data_dict.xml").write_text(
            "<x/>", encoding="utf-8")
    return tmp_path / name


# --------------------------------------------------------------------- resolution by rule

def test_an_unlisted_cohort_resolves_by_rule_rather_than_failing(tmp_path):
    """The whole Phase 3 blocker: a name absent from the hard-coded dict resolved to nothing."""
    cache = _cache(tmp_path, "newstudy")
    assert _cohorts.cache_key_for("NEWSTUDY", cache) == "newstudy"
    # and with no cache file at all it still names a key rather than returning nothing
    assert _cohorts.cache_key_for("NEWSTUDY", tmp_path / "empty") == "newstudy"


def test_separator_variants_find_the_same_cache(tmp_path):
    """The HV cache holds hchs_sol; this pipeline's dbGaP staging names it hchs-sol."""
    cache = _cache(tmp_path, "hchs_sol")
    for token in ("HCHS", "HCHS-SOL", "HCHS_SOL", "hchs-sol"):
        assert _cohorts.cache_key_for(token, cache) == "hchs_sol", token


def test_a_manifest_entry_beats_the_filename_convention(tmp_path):
    """A rebuild from a differently-named source dir must not strand the lookup."""
    cache = _cache(tmp_path, "hchs-sol",
                   manifest={"hchs-sol": {"cohort": "HCHS", "study": "phs000810",
                                          "study_version": "v2"}})
    assert _cohorts.cache_key_for("HCHS", cache) == "hchs-sol"


def test_a_cohort_with_no_cache_file_still_yields_exactly_one_pair(tmp_path):
    """`cohorts_to_load` must never be silently empty -- that produced the misleading
    'No dbGaP indexes found. Run build_phv_index.py.' for a cohort that was merely unlisted."""
    pairs = _cohorts.cohorts_to_load("NEWSTUDY", _cache(tmp_path), _ingest(tmp_path, "NEWSTUDY"))
    assert pairs == [("NEWSTUDY", "newstudy")]


def test_all_is_derived_from_the_ingest_directories(tmp_path):
    """`--cohort all` scanning 0 files and exiting 0 was a pass that read nothing."""
    cache = _cache(tmp_path, "chs")
    names = [c for c, _ in _cohorts.cohorts_to_load("all", cache, _ingest(tmp_path, "LTRC", "CHS"))]
    assert names == ["CHS", "LTRC"]


def test_all_also_covers_a_cohort_present_only_in_the_manifest(tmp_path):
    cache = _cache(tmp_path, "mesa", manifest={"mesa": {"cohort": "MESA"}})
    names = [c for c, _ in _cohorts.cohorts_to_load("all", cache, _ingest(tmp_path, "CHS"))]
    assert names == ["CHS", "MESA"]


# --------------------------------------------------------------------- directory casing

def test_the_cohort_is_canonicalised_to_its_directory_casing(tmp_path):
    """`args.cohort.upper()` produced COPDGENE, which argparse rejected and which resolves to
    COPDGENE-ingest only on a case-insensitive filesystem -- not on CI's ubuntu runner."""
    transform = _ingest(tmp_path, "COPDGene", "CHS")
    for token in ("copdgene", "COPDGENE", "COPDGene"):
        assert _cohorts.canonical_cohort(token, transform) == "COPDGene", token


def test_an_unstaged_cohort_passes_through_canonicalisation_unchanged(tmp_path):
    assert _cohorts.canonical_cohort("NEWSTUDY", _ingest(tmp_path, "CHS")) == "NEWSTUDY"


# --------------------------------------------------------------------- cohort identity from
# the source directory name, and its accession-only blind spot

def test_cohort_from_source_dir_strips_the_legacy_version_suffix():
    assert _cohorts.cohort_from_source_dir("aric-v8") == "ARIC"
    assert _cohorts.cohort_from_source_dir("ltrc") == "LTRC"
    assert _cohorts.cohort_from_source_dir("hchs-sol") == "HCHS"


def test_an_accession_named_directory_has_no_cohort_the_rule_can_recover():
    """Measured 2026-09-16 against a real `data/dbgap/phs000284.v2.p1/`: a bare accession has
    no `-v#`/`_v#` suffix to strip (the character before the version token is `.`, not `-`/`_`),
    so the rule alone returns the accession itself, upper-cased -- silently wrong-shaped as a
    cohort name rather than failing loudly."""
    assert _cohorts.cohort_from_source_dir("phs000284.v2.p1") == "PHS000284.V2.P1"


def test_the_staging_pipeline_manifest_resolves_an_accession_directory(tmp_path):
    """The AI-harmonization pipeline's own data/dbgap/manifest.json is the only place a bare
    accession's cohort identity lives, and it must WIN over the rule above, not merely
    supplement it."""
    (tmp_path / "manifest.json").write_text(json.dumps({
        "entries": {"phs000284.v2.p1": {"cohort": "cfs", "fetched": "2026-09-16T00:00:00+00:00"}}
    }), encoding="utf-8")
    assert _cohorts.cohort_from_source_dir("phs000284.v2.p1", tmp_path) == "CFS"


def test_the_staging_manifest_falls_back_silently_when_absent_or_unlisted(tmp_path):
    # No manifest.json at all -- the legacy `<cohort>-v#` directories never have one.
    assert _cohorts.cohort_from_source_dir("aric-v8", tmp_path) == "ARIC"
    # A manifest.json that exists but says nothing about this directory.
    (tmp_path / "manifest.json").write_text(
        json.dumps({"entries": {}}), encoding="utf-8")
    assert _cohorts.cohort_from_source_dir("phs000284.v2.p1", tmp_path) == "PHS000284.V2.P1"


def test_rebuilding_an_already_staged_cohort_does_not_corrupt_its_manifest_entry(tmp_path):
    """COPDGene was re-staged as `phs000179.v7.p2/` the same day this was found. Measured against
    the real dbgap-cache/manifest.json: without the fix, rebuilding from that directory
    overwrites a PREVIOUSLY CORRECT `"cohort": "COPDGENE"` entry with `"PHS000179.V7.P2"` --
    worse than merely failing to add one, because the correct entry already existed."""
    (tmp_path / "manifest.json").write_text(json.dumps({
        "entries": {"phs000179.v7.p2": {"cohort": "copdgene", "fetched": "2026-09-16T00:00:00+00:00"}}
    }), encoding="utf-8")
    assert _cohorts.cohort_from_source_dir("phs000179.v7.p2", tmp_path) == "COPDGENE"


# --------------------------------------------------------------------- study provenance

def test_the_study_accession_and_version_come_from_the_data_dict_names(tmp_path):
    src = _staged(tmp_path, "ltrc", "phs001662", "v4", phts=3)
    assert _cohorts.study_from_data_dicts(src) == ("phs001662", "v4", 3)


def test_two_versions_staged_together_refuse_to_resolve(tmp_path):
    """LTRC held phs001662.v2 and phs001662.v4 side by side. Picking the higher number would
    invent a provenance the directory does not have."""
    src = _staged(tmp_path, "ltrc", "phs001662", "v4")
    (src / "pheno_variable_summaries"
     / "phs001662.v2.pht010099.v1.OLD.data_dict.xml").write_text("<x/>", encoding="utf-8")
    accession, version, seen = _cohorts.study_from_data_dicts(src)
    assert (accession, version) == (None, None) and seen == 3


def test_the_tables_own_version_is_not_mistaken_for_the_studys(tmp_path):
    src = _staged(tmp_path, "chs", "phs000287", "v7")
    assert _cohorts.study_from_data_dicts(src)[:2] == ("phs000287", "v7")


def test_a_cache_with_no_manifest_entry_reports_unknown_loudly(tmp_path):
    cache = _cache(tmp_path, "aric")
    label = _cohorts.study_label(cache, "aric")
    assert "PROVENANCE UNKNOWN" in label and "build_phv_index.py" in label


def test_a_recorded_cache_reports_its_study_and_version(tmp_path):
    cache = _cache(tmp_path, "ltrc",
                   manifest={"ltrc": {"cohort": "LTRC", "study": "phs001662",
                                      "study_version": "v4", "built": "2026-09-10"}})
    assert _cohorts.study_label(cache, "ltrc") == "phs001662.v4, built 2026-09-10"


# --------------------------------------------------------------------- the version pin

@pytest.mark.parametrize("expect,expected_ok", [
    ("phs001662.v4", True),    # exact
    ("phs001662", True),       # bare accession ignores the version
    ("phs001662.v2", False),   # superseded version
    ("phs000287", False),      # wrong study
    ("", True),                # no pin
])
def test_expect_study_accepts_only_the_recorded_release(tmp_path, expect, expected_ok):
    cache = _cache(tmp_path, "ltrc",
                   manifest={"ltrc": {"cohort": "LTRC", "study": "phs001662",
                                      "study_version": "v4"}})
    assert (_cohorts.study_mismatch(cache, "ltrc", expect) is None) is expected_ok


def test_an_unrecorded_cache_fails_a_pin_rather_than_passing_it(tmp_path):
    """Pinning a version against a cache that cannot say which version it holds is exactly the
    case the pin exists to catch, so silence would defeat it."""
    cache = _cache(tmp_path, "aric")
    assert "no recorded study provenance" in _cohorts.study_mismatch(
        cache, "aric", "phs000280.v9")


# --------------------------------------------------------------------- discovery + writing

def test_detail_indexes_fold_onto_their_base_key(tmp_path):
    assert _cohorts.discover_cache_keys(_cache(tmp_path, "chs", "ltrc")) == ["chs", "ltrc"]


def test_writing_the_manifest_merges_rather_than_replaces(tmp_path):
    """The builders are routinely run over a subset of the source cache; a replace would erase
    every other cohort's provenance."""
    cache = _cache(tmp_path, "chs", manifest={"chs": {"cohort": "CHS", "study": "phs000287"}})
    _cohorts.write_manifest_entries(cache, {"ltrc": {"cohort": "LTRC", "study": "phs001662"}})
    entries = _cohorts.read_manifest(cache)
    assert sorted(entries) == ["chs", "ltrc"]


def test_a_corrupt_manifest_degrades_to_unknown_rather_than_crashing(tmp_path):
    cache = _cache(tmp_path, "chs")
    (cache / _cohorts.MANIFEST_NAME).write_text("{not json", encoding="utf-8")
    assert _cohorts.read_manifest(cache) == {}
    assert "PROVENANCE UNKNOWN" in _cohorts.study_label(cache, "chs")


# --------------------------------------------------------------------- declared release

def _fetch_manifest(tmp_path: Path, cohort: str, study: str, version: str) -> Path:
    d = tmp_path / "hv_dataqc" / "cache_fetcher" / "manifests"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"_manifest-{cohort}.yaml").write_text(
        "current_version:\n"
        f'  study_id: "{study}"\n'
        f'  data_version: "{version}"\n',
        encoding="utf-8")
    return tmp_path


def test_the_declared_release_drops_the_participant_set(tmp_path):
    """`data_version` is `v8.p2`; artifacts are keyed by the STUDY version only."""
    root = _fetch_manifest(tmp_path, "aric", "phs000280", "v8.p2")
    assert _cohorts.declared_study("ARIC", root) == "phs000280.v8"


def test_an_aliased_cohort_finds_its_declaration(tmp_path):
    root = _fetch_manifest(tmp_path, "hchs_sol", "phs000810", "v2.p2")
    assert _cohorts.declared_study("HCHS", root) == "phs000810.v2"


def test_a_cohort_with_no_declaration_returns_none(tmp_path):
    """None must reach the caller as a hard failure, not a default -- linting against
    whichever cache happens to be present is how a superseded release goes unnoticed."""
    root = _fetch_manifest(tmp_path, "chs", "phs000287", "v7.p1")
    assert _cohorts.declared_study("NEWSTUDY", root) is None


def test_the_declared_release_picks_between_coexisting_versions(tmp_path):
    """The point of accession-keyed artifacts: two releases of one study side by side."""
    cache = _cache(tmp_path, "phs000280.v8", "phs000280.v9")
    root = _fetch_manifest(tmp_path, "aric", "phs000280", "v8.p2")
    assert _cohorts.cache_key_for("ARIC", cache, root) == "phs000280.v8"
    # bump the declaration and the same cache directory serves the other release
    _fetch_manifest(tmp_path, "aric", "phs000280", "v9.p3")
    assert _cohorts.cache_key_for("ARIC", cache, root) == "phs000280.v9"


def test_a_legacy_cohort_named_cache_still_resolves(tmp_path):
    """Caches built before the rename must keep working."""
    cache = _cache(tmp_path, "chs")
    root = _fetch_manifest(tmp_path, "chs", "phs000287", "v7.p1")  # declared, but no such file
    assert _cohorts.cache_key_for("CHS", cache, root) == "chs"


def test_manifest_entries_merge_field_wise(tmp_path):
    """Three builders contribute different fields for one key; an entry-wise replace would
    make whichever ran last erase the others' counts."""
    cache = _cache(tmp_path, "phs001662.v4")
    _cohorts.write_manifest_entries(cache, {"phs001662.v4": {"cohort": "LTRC", "phvs": 1577}})
    _cohorts.write_manifest_entries(cache, {"phs001662.v4": {"visit_tables": 27}})
    entry = _cohorts.manifest_entry(cache, "phs001662.v4")
    assert entry["phvs"] == 1577 and entry["visit_tables"] == 27 and entry["cohort"] == "LTRC"

# --------------------------------------------------------------------- staged-tree resolution
#
# Both cases below were found by a real run on 2026-09-10, not by inspection, and both were
# introduced by making the release check mandatory. The fleet regression ran against the REAL
# HV tree and could not see either.

def test_the_declaration_is_found_via_the_cache_dir_when_the_tree_is_staged(tmp_path):
    """A caller linting STAGED output points --hv-root at a temp tree holding only
    `<COHORT>-ingest`, which has no `hv_dataqc/` manifests. Resolving the root from the transform
    dir alone made the mandatory release check fail for every staged run -- which is how the
    AI-harmonization pipeline always invokes HV-Lint."""
    real = _fetch_manifest(tmp_path / "clone", "ltrc", "phs001662", "v4.p2")
    cache = _cache(real / "hv-lint" / "dbgap-cache", "phs001662.v4")
    staged = tmp_path / "staged"
    (staged / "priority_variables_transform" / "LTRC-ingest").mkdir(parents=True)
    # hv_root points at the staged tree, which knows nothing; the cache path reaches the clone
    assert _cohorts.declared_study("LTRC", staged) is None
    assert _cohorts.declared_study("LTRC", staged, cache_dir=cache) == "phs001662.v4"
    assert _cohorts.cache_key_for("LTRC", cache, staged) == "phs001662.v4"


def test_two_releases_of_one_study_are_never_disambiguated_by_sort_order(tmp_path):
    """Artifacts are keyed by release, so a study with two staged releases has two manifest
    entries carrying the same cohort. Appending both made the first one win: LTRC resolved to
    phs001662.v2 against a declared v4."""
    cache = _cache(tmp_path / "dbgap-cache", "phs001662.v2", "phs001662.v4",
                   manifest={
                       "phs001662.v2": {"cohort": "LTRC", "study": "phs001662",
                                        "study_version": "v2"},
                       "phs001662.v4": {"cohort": "LTRC", "study": "phs001662",
                                        "study_version": "v4"},
                   })
    # with a declaration, the declared release wins
    root = _fetch_manifest(tmp_path / "clone", "ltrc", "phs001662", "v4.p2")
    assert _cohorts.cache_key_for("LTRC", cache, root) == "phs001662.v4"
    # with NO declaration, the ambiguous cohort match is refused rather than guessed
    assert "phs001662.v2" not in _cohorts.candidate_keys("LTRC", cache, tmp_path / "nowhere")
