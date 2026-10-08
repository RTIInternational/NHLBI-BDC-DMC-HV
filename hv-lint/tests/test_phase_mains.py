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
    with gzip.open(cache / f"{KEY}_detail.json.gz", "wt", encoding="utf-8") as f:
        json.dump({phv: {"pht": pht} for phv, pht in index.items()}, f)
    if manifest == "ok":
        entries: object = {KEY: {"cohort": "HCHS", "study": STUDY, "study_version": VERSION}}
    else:
        entries = manifest
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


def test_a_cohort_without_visit_yaml_under_all_is_still_a_warning(tmp_path, monkeypatch, capsys):
    """Scope guard: under `all` the cohorts come from the directories, and a directory with no
    visit.yaml stays a 5.0 WARNING. Only a NAMED cohort without one is an unrun check."""
    cache = _make_tree(tmp_path)
    (tmp_path / "priority_variables_transform" / "EXTRA-ingest").mkdir()
    rc = _run_vvs(monkeypatch, tmp_path, "--cohort", "all", "--cache-dir", str(cache),
                  "--fail-on", "critical")
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "No visit.yaml found for cohort EXTRA" in out


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

_PHASE3_VALIDATORS = ["validate_dbgap_crossref", "validate_semantic", "check_value_semantic"]


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
