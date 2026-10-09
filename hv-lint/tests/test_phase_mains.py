"""Drive the real ``main()`` of the cache-reading validators, not their helpers.

The ``_cohorts`` tests pin what the resolver RETURNS; these pin what the validators DO with it --
in particular that a check which did not run fails the run instead of exiting PASSED. Each test
builds a small HV tree in ``tmp_path`` (one ``HCHS-ingest`` cohort, its ``_manifest-hchs_sol.yaml``
declaration, and a release-keyed cache) and points ``HV_ROOT`` at it, so nothing here reads the
real specs or the committed cache.

Run: python -m pytest hv-lint/tests/test_phase_mains.py
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

_HV_LINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HV_LINT))
sys.path.insert(0, str(_HV_LINT / "phase-5"))

import _cohorts  # noqa: E402
import run_phase5  # noqa: E402
import validate_visit_structure as vvs  # noqa: E402

STUDY = "phs999999"
VERSION = "v1"
KEY = f"{STUDY}.{VERSION}"
PHT = "pht000001"

VISIT_YAML = f"""\
- class_derivations:
    Visit:
      populated_from: {PHT}
      slot_derivations:
        id:
          expr: 'uuid5("https://w3id.org/bdchm/Visit", str({{phv00000001}}) + ":TEST Baseline")'
        name:
          value: TEST Baseline
        age_at_visit_start:
          expr: '{{phv00000002}} * 365'
        age_at_visit_end:
          expr: '{{phv00000002}} * 365'
"""


@pytest.fixture(autouse=True)
def _hv_root_does_not_leak():
    """The managers assign HV_ROOT in-process. Autouse fixtures are set up before `monkeypatch`,
    so this check runs after its undo: a test that lets the tmp tree escape fails here, not in
    whichever later test reads the real specs from the wrong root."""
    import os
    before = os.environ.get("HV_ROOT")
    yield
    assert os.environ.get("HV_ROOT") == before, "HV_ROOT leaked out of the test"


def _make_tree(root: Path, *, manifest: object = "ok") -> Path:
    """An HV root with one cohort (``HCHS``) and its cache; returns the cache directory.

    ``manifest="ok"`` records the declared release; any other value is written verbatim as the
    manifest's ``entries`` (``None`` leaves no ``manifest.json`` at all).
    """
    ingest = root / "priority_variables_transform" / "HCHS-ingest"
    ingest.mkdir(parents=True)
    (ingest / "visit.yaml").write_text(VISIT_YAML, encoding="utf-8")

    decl = root / "hv_dataqc" / "cache_fetcher" / "manifests"
    decl.mkdir(parents=True)
    (decl / "_manifest-hchs_sol.yaml").write_text(
        f'current_version:\n  study_id: "{STUDY}"\n  data_version: "{VERSION}.p1"\n',
        encoding="utf-8",
    )

    cache = root / "hv-lint" / "dbgap-cache"
    cache.mkdir(parents=True)
    index = {"phv00000001": PHT, "phv00000002": PHT}
    with gzip.open(cache / f"{KEY}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(index, f)
    # A collection interval on the visit seed lets 5.8 run, so the tree raises no 5.8 "did not
    # run" WARNING: these tests must pass on their own tree, not on a row in the committed
    # warning_baseline.json (tests/conftest.py gives every test an empty one).
    detail = {phv: {"pht": pht} for phv, pht in index.items()}
    detail["phv00000001"]["coll_interval"] = "Collected in: P1"
    with gzip.open(cache / f"{KEY}_detail.json.gz", "wt", encoding="utf-8") as f:
        json.dump(detail, f)
    # The value-count index 3.9 / 3.15, 3.19 and 5.12 read; validate_semantic refuses to run
    # without it, or when it has no n for uncoded variables (3.19).
    with gzip.open(cache / f"{KEY}_stats.json.gz", "wt", encoding="utf-8") as f:
        json.dump({phv: {"n": 1} for phv in index}, f)
    if manifest == "ok":
        entries: object = {KEY: {"cohort": "HCHS", "study": STUDY, "study_version": VERSION}}
    else:
        entries = manifest
    # Every entry for KEY records the artifacts actually written, as the builders do, so a test
    # of the release check reaches it instead of stopping at the integrity check before it.
    if isinstance(entries, dict) and isinstance(entries.get(KEY), dict):
        entries[KEY] = {**entries[KEY], _cohorts.ARTIFACTS_FIELD: {
            name: _cohorts.artifact_record(cache / name)
            for name in (f"{KEY}.json.gz", f"{KEY}_detail.json.gz", f"{KEY}_stats.json.gz")}}
    if entries is not None:
        (cache / "manifest.json").write_text(
            json.dumps({"manifest_version": 1, "entries": entries}), encoding="utf-8")
    return cache


def _run_vvs(monkeypatch, root: Path, *argv: str) -> int:
    monkeypatch.setenv("HV_ROOT", str(root))
    monkeypatch.setattr(sys, "argv", ["validate_visit_structure.py", *argv])
    return vvs.main()


# -- Phase 5: --cohort resolution ---------------------------------------------


def test_the_fixture_tree_passes_phase_5(tmp_path, monkeypatch, capsys):
    """Control: the tree the failure tests mutate is itself clean, so a 1 below means the
    mutation, not a broken fixture."""
    cache = _make_tree(tmp_path)
    rc = _run_vvs(monkeypatch, tmp_path, "--cohort", "HCHS", "--cache-dir", str(cache),
                  "--fail-on", "critical")
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "1 cohort(s) processed, 0 skipped" in out


@pytest.mark.parametrize("token", ["HCHS-SOL", "hchs_sol", "hchs"])
def test_phase_5_canonicalises_an_alias_or_miscased_cohort(tmp_path, monkeypatch, capsys, token):
    cache = _make_tree(tmp_path)
    rc = _run_vvs(monkeypatch, tmp_path, "--cohort", token, "--cache-dir", str(cache))
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "Phase 5: HCHS\n" in out
    assert "1 cohort(s) processed, 0 skipped" in out


@pytest.mark.parametrize("fail_on", ["error", "critical"])
def test_phase_5_fails_on_an_unknown_cohort(tmp_path, monkeypatch, capsys, fail_on):
    cache = _make_tree(tmp_path)
    rc = _run_vvs(monkeypatch, tmp_path, "--cohort", "NOPE", "--cache-dir", str(cache),
                  "--fail-on", fail_on)
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "No ingest directory for cohort 'NOPE'" in out
    assert "PASSED" not in out


def test_run_phase5_fails_on_an_unknown_cohort(tmp_path, monkeypatch, capsys):
    """The manager is the path CI takes; it runs the validator as a subprocess."""
    cache = _make_tree(tmp_path)
    # setenv registers an undo, so the HV_ROOT that run_phase5.main() assigns is removed at
    # teardown; delenv on an unset variable records nothing and the tmp tree leaks onward.
    monkeypatch.setenv("HV_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "argv", [
        "run_phase5.py", "--hv-root", str(tmp_path), "--cohort", "NOPE",
        "--cache-dir", str(cache), "--fail-on", "critical",
    ])
    assert run_phase5.main() == 1


def test_a_cohort_without_visit_yaml_under_all_fails_the_run(tmp_path, monkeypatch, capsys):
    """Under `all` the cohorts come from the directories; a directory with no visit.yaml had
    none of 5.1-5.12 run, so it is the same unrun check as for a NAMED cohort: CI lints `all`,
    and a deleted visit.yaml must fail it even at `--fail-on critical`."""
    cache = _make_tree(tmp_path)
    (tmp_path / "priority_variables_transform" / "EXTRA-ingest").mkdir()
    rc = _run_vvs(monkeypatch, tmp_path, "--cohort", "all", "--cache-dir", str(cache),
                  "--fail-on", "critical")
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "ERROR" in out and "No visit.yaml found for cohort EXTRA" in out
    assert "PASSED" not in out


@pytest.mark.parametrize("fail_on", ["error", "critical"])
def test_a_named_cohort_without_visit_yaml_fails_the_run(tmp_path, monkeypatch, capsys, fail_on):
    """Naming a cohort asks for it to be checked; an ingest directory with no visit.yaml means
    none of 5.1-5.10 ran for it, which is an unrun check at any threshold."""
    cache = _make_tree(tmp_path)
    (tmp_path / "priority_variables_transform" / "HCHS-ingest" / "visit.yaml").unlink()
    rc = _run_vvs(monkeypatch, tmp_path, "--cohort", "HCHS", "--cache-dir", str(cache),
                  "--fail-on", fail_on)
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "No visit.yaml found for cohort HCHS" in out
    assert "PASSED" not in out


@pytest.mark.parametrize("content", [
    "- foo: [unclosed\n",
    "",
    "- class_derivations:\n    Person:\n      populated_from: pht000001\n",
], ids=["unparseable", "empty", "no-visit-blocks"])
@pytest.mark.parametrize("cohort", ["HCHS", "all"])
def test_a_visit_yaml_that_yields_no_registry_fails_at_fail_on_critical(
        tmp_path, monkeypatch, capsys, content, cohort):
    cache = _make_tree(tmp_path)
    (tmp_path / "priority_variables_transform" / "HCHS-ingest" / "visit.yaml").write_text(
        content, encoding="utf-8")
    rc = _run_vvs(monkeypatch, tmp_path, "--cohort", cohort, "--cache-dir", str(cache),
                  "--fail-on", "critical")
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "Could not parse visit.yaml or no Visit blocks for HCHS" in out
    assert "PASSED" not in out


# -- Phase 5: the mandatory release check and missing inputs ------------------
# Each of these leaves 5.3/5.4/5.8 unrun. At `--fail-on critical` none of the ERROR findings is
# blocking, so a 1 here can only come from the `unrun_check` exit, which is the path that is
# meant to be independent of the threshold.


def _phase5_critical(monkeypatch, root: Path, cache: Path | None) -> int:
    argv = ["--cohort", "HCHS", "--fail-on", "critical"]
    if cache is not None:
        argv += ["--cache-dir", str(cache)]
    return _run_vvs(monkeypatch, root, *argv)


@pytest.mark.parametrize("entries, expect", [
    ({KEY: {"cohort": "HCHS", "study": STUDY, "study_version": "v2"}}, f"built from {STUDY}.v2"),
    ([], "no recorded study provenance"),
    (None, "no recorded study provenance"),
], ids=["wrong-release", "manifest-empty-list", "no-manifest"])
def test_phase_5_release_check_fails_the_run_at_fail_on_critical(
        tmp_path, monkeypatch, capsys, entries, expect):
    cache = _make_tree(tmp_path, manifest=entries)
    rc = _phase5_critical(monkeypatch, tmp_path, cache)
    out = capsys.readouterr().out
    assert rc == 1, out
    assert expect in out
    assert "DID NOT RUN" in out
    # The expectation here is the DECLARED release; the user never passed --expect-study.
    assert "--expect-study" not in out


def test_phase_5_without_cache_dir_fails_at_fail_on_critical(tmp_path, monkeypatch, capsys):
    _make_tree(tmp_path)
    rc = _phase5_critical(monkeypatch, tmp_path, None)
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "no --cache-dir supplied" in out
    # 5.4's structural half (age slots, `* 365`) reads no cache and still runs, so the message
    # must not claim all of 5.4 was skipped.
    assert "check 5.3 and the PHV-index half of 5.4 DID NOT RUN" in out


@pytest.mark.parametrize("missing, expect", [
    (f"{KEY}.json.gz", "no PHV index for HCHS"),
    (f"{KEY}_detail.json.gz", "no detail index for HCHS"),
], ids=["basic-index", "detail-index"])
def test_phase_5_missing_index_fails_at_fail_on_critical(
        tmp_path, monkeypatch, capsys, missing, expect):
    cache = _make_tree(tmp_path)
    (cache / missing).unlink()
    rc = _phase5_critical(monkeypatch, tmp_path, cache)
    out = capsys.readouterr().out
    assert rc == 1, out
    assert expect in out


# -- Phase 3: the same release check, through validate_dbgap_crossref.main() --


def _run_crossref(monkeypatch, root: Path, cache: Path) -> int:
    sys.path.insert(0, str(_HV_LINT / "phase-3"))
    try:
        import validate_dbgap_crossref as crossref
    finally:
        sys.path.remove(str(_HV_LINT / "phase-3"))
    monkeypatch.setenv("HV_ROOT", str(root))
    monkeypatch.setattr(sys, "argv", [
        "validate_dbgap_crossref.py", "--cache-dir", str(cache), "--cohort", "HCHS",
        "--fail-on", "critical",
    ])
    return crossref.main()


def test_phase_3_fixture_tree_passes(tmp_path, monkeypatch, capsys):
    cache = _make_tree(tmp_path)
    rc = _run_crossref(monkeypatch, tmp_path, cache)
    captured = capsys.readouterr()
    assert rc == 0, captured.out + captured.err


@pytest.mark.parametrize("entries, expect", [
    ({KEY: {"cohort": "HCHS", "study": STUDY, "study_version": "v2"}}, f"built from {STUDY}.v2"),
    (None, "no recorded study provenance"),
], ids=["wrong-release", "no-manifest"])
def test_phase_3_release_check_fails_the_run_at_fail_on_critical(
        tmp_path, monkeypatch, capsys, entries, expect):
    cache = _make_tree(tmp_path, manifest=entries)
    rc = _run_crossref(monkeypatch, tmp_path, cache)
    err = capsys.readouterr().err
    assert rc == 1, err
    assert expect in err


# -- Phase 3: validate_semantic.main() names the file it could not find -------


def _run_semantic(monkeypatch, root: Path, *argv: str) -> int:
    sys.path.insert(0, str(_HV_LINT / "phase-3"))
    try:
        import validate_semantic as semantic
    finally:
        sys.path.remove(str(_HV_LINT / "phase-3"))
    monkeypatch.setenv("HV_ROOT", str(root))
    monkeypatch.setattr(sys, "argv", ["validate_semantic.py", *argv])
    return semantic.main()


def test_phase_3_semantic_names_the_missing_detail_index(tmp_path, monkeypatch, capsys):
    """It reads only the detail index, so the message must name that file -- naming the basic
    index sends the reader to a file that exists."""
    cache = _make_tree(tmp_path)
    (cache / f"{KEY}_detail.json.gz").unlink()
    rc = _run_semantic(monkeypatch, tmp_path, "--cache-dir", str(cache), "--cohort", "HCHS",
                       "--fail-on", "critical")
    err = capsys.readouterr().err
    assert rc == 1, err
    assert f"'{KEY}_detail.json.gz'" in err
    assert f"'{KEY}.json.gz'" not in err


# -- --expect-study pins ONE release, so it needs ONE named cohort -------------
# Under `--cohort all` the single pin is compared with every cohort's cache: it either fails on
# the first cohort of another study or, in a one-study tree, quietly passes as if it were the
# declaration. Every entry point that accepts the flag refuses the combination up front.

_EXPECT_ENTRY_POINTS = {
    "run_all": ("", ["--skip", "phase1", "phase2", "phase5", "--no-report"]),
    "run_phase3": ("phase-3", []),
    "validate_dbgap_crossref": ("phase-3", []),
    "validate_semantic": ("phase-3", []),
    "check_value_semantic": ("phase-3", []),
    "check_status_semantic": ("phase-3", []),
}


@pytest.mark.parametrize("module", sorted(_EXPECT_ENTRY_POINTS))
@pytest.mark.parametrize("cohort", [None, "all", "ALL"], ids=["default", "all", "ALL"])
def test_expect_study_with_cohort_all_is_rejected_up_front(
        tmp_path, monkeypatch, capsys, module, cohort):
    import importlib
    subdir, extra = _EXPECT_ENTRY_POINTS[module]
    cache = _make_tree(tmp_path)
    monkeypatch.setenv("HV_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(_HV_LINT / subdir) if subdir else str(_HV_LINT))
    mod = importlib.import_module(module)
    argv = [f"{module}.py", "--cache-dir", str(cache), "--expect-study", KEY, *extra]
    if cohort is not None:
        argv += ["--cohort", cohort]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert "--expect-study needs one named --cohort" in capsys.readouterr().err


def test_expect_study_with_one_named_cohort_still_works(tmp_path, monkeypatch, capsys):
    """Control: the guard rejects only the `all` combination."""
    cache = _make_tree(tmp_path)
    sys.path.insert(0, str(_HV_LINT / "phase-3"))
    try:
        import validate_dbgap_crossref as crossref
    finally:
        sys.path.remove(str(_HV_LINT / "phase-3"))
    monkeypatch.setenv("HV_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "argv", [
        "validate_dbgap_crossref.py", "--cache-dir", str(cache), "--cohort", "HCHS",
        "--expect-study", KEY, "--fail-on", "critical",
    ])
    captured = capsys.readouterr()
    assert crossref.main() == 0, captured.out + captured.err


def test_phase_3_undeclared_cohort_says_where_the_override_applies(tmp_path, monkeypatch, capsys):
    """The remedy must not send the reader to a flag Phase 5 does not have."""
    cache = _make_tree(tmp_path)
    (tmp_path / "hv_dataqc" / "cache_fetcher" / "manifests" / "_manifest-hchs_sol.yaml").unlink()
    rc = _run_crossref(monkeypatch, tmp_path, cache)
    err = capsys.readouterr().err
    assert rc == 1, err
    assert "declares no dbGaP release" in err
    assert "Phase 5 has no override" in err


# -- Phase 3 run directly: an alias names the cohort's DIRECTORY, not just its cache ----------
# `cohorts_to_load` resolves `hchs_sol` to the HCHS cache, so the release check passes; the file
# scan then matched the raw token against `hchs_sol-ingest`, found nothing, and exited 0 having
# checked no file. Each validator canonicalises `--cohort` against the tree, and a NAMED cohort
# with no YAML is a failure, not a pass.

_PHASE3_VALIDATORS = ["validate_dbgap_crossref", "validate_semantic", "check_value_semantic",
                      "check_status_semantic"]


def _run_phase3_validator(monkeypatch, module: str, root: Path, cache: Path, cohort: str) -> int:
    import importlib
    monkeypatch.setenv("HV_ROOT", str(root))
    monkeypatch.syspath_prepend(str(_HV_LINT / "phase-3"))
    mod = importlib.import_module(module)
    monkeypatch.setattr(sys, "argv", [f"{module}.py", "--cache-dir", str(cache),
                                      "--cohort", cohort, "--fail-on", "critical"])
    return mod.main()


@pytest.mark.parametrize("module", _PHASE3_VALIDATORS)
@pytest.mark.parametrize("token", ["hchs_sol", "HCHS-SOL", "hchs"])
def test_phase_3_validators_scan_the_aliased_cohorts_files(tmp_path, monkeypatch, capsys,
                                                           module, token):
    cache = _make_tree(tmp_path)
    rc = _run_phase3_validator(monkeypatch, module, tmp_path, cache, token)
    captured = capsys.readouterr()
    assert rc == 0, captured.out + captured.err
    assert "Found 1 YAML files to validate" in captured.out
    assert "No YAML files found" not in captured.out


@pytest.mark.parametrize("module", _PHASE3_VALIDATORS)
def test_phase_3_validators_fail_a_named_cohort_with_no_yaml(tmp_path, monkeypatch, capsys,
                                                             module):
    cache = _make_tree(tmp_path)
    (tmp_path / "priority_variables_transform" / "HCHS-ingest" / "visit.yaml").unlink()
    rc = _run_phase3_validator(monkeypatch, module, tmp_path, cache, "HCHS")
    captured = capsys.readouterr()
    assert rc == 1, captured.out + captured.err
    assert "No YAML files found" in captured.out


@pytest.mark.parametrize("module", _PHASE3_VALIDATORS)
@pytest.mark.parametrize("token", [" all", "all ", " ALL "])
def test_phase_3_validators_read_a_padded_all_as_all(tmp_path, monkeypatch, capsys, module,
                                                     token):
    """A padded `all` loads every cache (`cohorts_to_load` strips), so the file scan must strip
    too: otherwise it filters on `" all-ingest"`, finds nothing, and the "all" branch of the
    no-YAML return passes a run that checked no file."""
    cache = _make_tree(tmp_path)
    rc = _run_phase3_validator(monkeypatch, module, tmp_path, cache, token)
    captured = capsys.readouterr()
    assert rc == 0, captured.out + captured.err
    assert "Found 1 YAML files to validate" in captured.out
    assert "No YAML files found" not in captured.out


@pytest.mark.parametrize("token", [" all", "ALL "])
def test_phase_5_reads_a_padded_all_as_all(tmp_path, monkeypatch, capsys, token):
    """`cohorts_to_load` and the --expect-study guard strip before comparing with `all`; Phase 5
    must agree, or the same token is every cohort to Phase 3 and an unknown cohort to Phase 5."""
    cache = _make_tree(tmp_path)
    rc = _run_vvs(monkeypatch, tmp_path, "--cohort", token, "--cache-dir", str(cache),
                  "--fail-on", "critical")
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "1 cohort(s) processed, 0 skipped" in out


@pytest.mark.parametrize("module", _PHASE3_VALIDATORS)
@pytest.mark.parametrize("case, expect", [
    ("wrong-release", f"built from {STUDY}.v2"),
    ("no-manifest", "no recorded study provenance"),
    ("undeclared", "declares no dbGaP release"),
    ("expect-study", f"--expect-study {STUDY}.v3"),
])
def test_phase_3_validators_each_run_the_release_check(tmp_path, monkeypatch, capsys, module,
                                                       case, expect):
    """Review round 2 B F2: every Phase 3 component checks the release it reads, so a component
    run directly cannot pass on a superseded cache because a sibling would have caught it."""
    entries = {"wrong-release": {KEY: {"cohort": "HCHS", "study": STUDY, "study_version": "v2"}},
               "no-manifest": None}.get(case, "ok")
    cache = _make_tree(tmp_path, manifest=entries)
    if case == "undeclared":
        (tmp_path / "hv_dataqc" / "cache_fetcher" / "manifests" /
         "_manifest-hchs_sol.yaml").unlink()
    import importlib
    monkeypatch.setenv("HV_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(_HV_LINT / "phase-3"))
    mod = importlib.import_module(module)
    argv = [f"{module}.py", "--cache-dir", str(cache), "--cohort", "HCHS", "--fail-on",
            "critical"]
    if case == "expect-study":
        argv += ["--expect-study", f"{STUDY}.v3"]
    monkeypatch.setattr(sys, "argv", argv)
    rc = mod.main()
    captured = capsys.readouterr()
    assert rc == 1, captured.out + captured.err
    assert expect in captured.err


# -- Cache integrity: the manifest records content, not just a release label (S1) ------------


def _swap_in_other_release(cache: Path, name: str) -> None:
    """Overwrite ``name`` with a same-shaped artifact built from different content, as copying
    another release's file over this release's name does. The manifest label is untouched."""
    other = {"phv00000001": PHT, "phv00000002": PHT, "phv00000003": "pht000002"}
    payload = other if name == f"{KEY}.json.gz" else {p: {"pht": t} for p, t in other.items()}
    with gzip.open(cache / name, "wt", encoding="utf-8") as f:
        json.dump(payload, f)


@pytest.mark.parametrize("name", [f"{KEY}.json.gz", f"{KEY}_detail.json.gz"],
                         ids=["phv-index", "detail-index"])
def test_phase_3_fails_on_an_artifact_swapped_for_another_release(
        tmp_path, monkeypatch, capsys, name):
    cache = _make_tree(tmp_path)
    _swap_in_other_release(cache, name)
    run = _run_crossref if name == f"{KEY}.json.gz" else (
        lambda mp, root, c: _run_semantic(mp, root, "--cache-dir", str(c), "--cohort", "HCHS",
                                          "--fail-on", "critical"))
    rc = run(monkeypatch, tmp_path, cache)
    err = capsys.readouterr().err
    assert rc == 1, err
    assert f"{name} does not match its manifest.json record" in err
    assert "3 PHVS on disk, 2 recorded" in err
    assert "update_data.py --build-only --cohort hchs_sol" in err


@pytest.mark.parametrize("name, check", [(f"{KEY}.json.gz", "5.3/5.4"),
                                         (f"{KEY}_detail.json.gz", "5.8")],
                         ids=["phv-index", "detail-index"])
def test_phase_5_fails_on_an_artifact_swapped_for_another_release(
        tmp_path, monkeypatch, capsys, name, check):
    cache = _make_tree(tmp_path)
    _swap_in_other_release(cache, name)
    rc = _phase5_critical(monkeypatch, tmp_path, cache)
    out = capsys.readouterr().out
    assert rc == 1, out
    assert f"{name} does not match its manifest.json record" in out
    assert "DID NOT RUN" in out


def test_an_artifact_with_no_digest_record_fails_closed(tmp_path, monkeypatch, capsys):
    """An entry carrying the right release label but no record for the file is not trusted."""
    cache = _make_tree(tmp_path, manifest={
        KEY: {"cohort": "HCHS", "study": STUDY, "study_version": VERSION}})
    data = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    del data["entries"][KEY][_cohorts.ARTIFACTS_FIELD]
    (cache / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    rc = _run_crossref(monkeypatch, tmp_path, cache)
    err = capsys.readouterr().err
    assert rc == 1, err
    assert "has no sha256/count record" in err


def _swap_stats(cache: Path) -> None:
    """Another release's value-count index copied over this one's name: three PHVs, not two."""
    with gzip.open(cache / f"{KEY}_stats.json.gz", "wt", encoding="utf-8") as f:
        json.dump({p: {"n": 1} for p in ("phv00000001", "phv00000002", "phv00000003")}, f)


@pytest.mark.parametrize("module", ["validate_semantic", "check_status_semantic"])
def test_phase_3_fails_on_a_swapped_stats_index(tmp_path, monkeypatch, capsys, module):
    cache = _make_tree(tmp_path)
    _swap_stats(cache)
    rc = _run_phase3_validator(monkeypatch, module, tmp_path, cache, "HCHS")
    err = capsys.readouterr().err
    assert rc == 1, err
    assert f"{KEY}_stats.json.gz does not match its manifest.json record" in err
    assert "3 PHVS on disk, 2 recorded" in err
    assert "build_phv_stats_index.py --cohort " + KEY in err


def test_phase_5_fails_on_a_swapped_stats_index(tmp_path, monkeypatch, capsys):
    cache = _make_tree(tmp_path)
    _swap_stats(cache)
    rc = _phase5_critical(monkeypatch, tmp_path, cache)
    out = capsys.readouterr().out
    assert rc == 1, out
    assert f"{KEY}_stats.json.gz does not match its manifest.json record" in out
    assert "5.12 DID NOT RUN" in out


def test_a_swapped_tables_index_is_refused(tmp_path):
    """``_tables`` (rules 1.8 / 1.14) is read through the same check as every other artifact."""
    cache = _make_tree(tmp_path)
    tables = cache / f"{KEY}_tables.json.gz"
    with gzip.open(tables, "wt", encoding="utf-8") as f:
        json.dump({PHT: {"name": "a", "description": ""}}, f)
    _cohorts.write_manifest_entries(cache, {KEY: {_cohorts.ARTIFACTS_FIELD: {
        tables.name: _cohorts.artifact_record(tables)}}})
    assert _cohorts.load_table_names(cache, KEY) == {PHT: {"name": "a", "description": ""}}
    with gzip.open(tables, "wt", encoding="utf-8") as f:
        json.dump({PHT: {"name": "b", "description": ""}}, f)
    with pytest.raises(_cohorts.CacheIntegrityError, match="sha256"):
        _cohorts.load_table_names(cache, KEY)


def test_a_same_count_rebuild_is_caught_by_the_digest(tmp_path):
    """Counts alone miss a stale artifact of the same table set; the sha256 does not."""
    cache = _make_tree(tmp_path)
    with gzip.open(cache / f"{KEY}.json.gz", "wt", encoding="utf-8") as f:
        json.dump({"phv00000001": PHT, "phv00000009": PHT}, f)
    with pytest.raises(_cohorts.CacheIntegrityError, match="sha256"):
        _cohorts.load_cache_artifact(cache, KEY)


CORRUPT_ARTIFACTS = {
    "truncated-gzip": lambda data: data[: len(data) // 2],
    "not-gzip": lambda data: b"this is not a gzip stream",
    "gzip-of-non-json": lambda data: gzip.compress(b"{not json"),
}


@pytest.mark.parametrize("corrupt", CORRUPT_ARTIFACTS.values(), ids=CORRUPT_ARTIFACTS.keys())
@pytest.mark.parametrize("phase", ["phase-3", "phase-5"])
def test_an_undecodable_artifact_is_an_integrity_error_not_a_traceback(
        tmp_path, monkeypatch, capsys, corrupt, phase):
    """A decode failure raised before the digest check escaped every phase's handler."""
    cache = _make_tree(tmp_path)
    path = cache / f"{KEY}.json.gz"
    path.write_bytes(corrupt(path.read_bytes()))
    if phase == "phase-3":
        rc = _run_crossref(monkeypatch, tmp_path, cache)
    else:
        rc = _phase5_critical(monkeypatch, tmp_path, cache)
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert rc == 1, text
    assert f"{KEY}.json.gz cannot be read as a cache artifact" in text
    assert "update_data.py --build-only --cohort hchs_sol" in text
    assert "Traceback" not in text


# -- Phase 1 components invoked directly: the `all` sentinel and aliases (PR #831 review) ----


def _phase1_targets(monkeypatch, tmp_path: Path, module: str, token: str) -> list[str]:
    """The ingest directories a Phase 1 component's main() selects for ``--cohort token``."""
    transform = tmp_path / "priority_variables_transform"
    for cohort in ("FHS", "HCHS"):
        (transform / f"{cohort}-ingest").mkdir(parents=True)
    sys.path.insert(0, str(_HV_LINT / "phase-1"))
    try:
        import importlib
        mod = importlib.import_module(module)
    finally:
        sys.path.remove(str(_HV_LINT / "phase-1"))
    monkeypatch.setattr(mod, "TRANSFORM_DIR", transform)
    seen: list[str] = []

    def record(targets, *a, **k):
        seen.extend(t.name for t in targets)
        return [] if module == "check_quoting_rules" else 0

    monkeypatch.setattr(mod, "run_yamllint" if module == "run_yamllint" else "collect_yaml_files",
                        record)
    monkeypatch.setattr(sys, "argv", [f"{module}.py", "--cohort", token])
    with pytest.raises(SystemExit) as exit_info:
        mod.main()
    assert exit_info.value.code == 0
    return sorted(seen)


@pytest.mark.parametrize("module", ["run_yamllint", "check_quoting_rules"])
@pytest.mark.parametrize("token, expect", [
    ("ALL", ["FHS-ingest", "HCHS-ingest"]),
    (" All ", ["FHS-ingest", "HCHS-ingest"]),
    ("hchs_sol", ["HCHS-ingest"]),
    ("HCHS-SOL", ["HCHS-ingest"]),
])
def test_phase_1_components_resolve_all_and_aliases_when_run_directly(
        tmp_path, monkeypatch, module, token, expect):
    assert _phase1_targets(monkeypatch, tmp_path, module, token) == expect


@pytest.mark.parametrize("manager", ["run_all", "run_phase1"])
@pytest.mark.parametrize("token", ["ALL", " all ", "All"])
def test_the_managers_forward_the_all_sentinel_lowercase(monkeypatch, capsys, manager, token):
    """Driven through each manager's main(), recording what it dispatches to its children."""
    import importlib
    sys.path.insert(0, str(_HV_LINT / "phase-1"))
    try:
        mod = importlib.import_module(manager)
    finally:
        sys.path.remove(str(_HV_LINT / "phase-1"))
    seen: list[str] = []
    if manager == "run_all":
        monkeypatch.setattr(mod, "run_phase",
                            lambda name, args, cache: (seen.append(args.cohort), (0, ""))[1])
        argv = ["run_all.py", "--cohort", token, "--no-report"]
    else:
        monkeypatch.setattr(mod, "run_component",
                            lambda name, cohort, fail_on: (seen.append(cohort), 0)[1])
        argv = ["run_phase1.py", "--cohort", token]
    monkeypatch.setattr(sys, "argv", argv)
    assert mod.main() == 0
    assert seen and set(seen) == {"all"}
