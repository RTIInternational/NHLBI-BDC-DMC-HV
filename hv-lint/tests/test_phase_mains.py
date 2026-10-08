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
    monkeypatch.delenv("HV_ROOT", raising=False)
    monkeypatch.setattr(sys, "argv", [
        "run_phase5.py", "--hv-root", str(tmp_path), "--cohort", "NOPE",
        "--cache-dir", str(cache), "--fail-on", "critical",
    ])
    assert run_phase5.main() == 1


def test_a_cohort_without_visit_yaml_under_all_is_still_a_warning(tmp_path, monkeypatch, capsys):
    """Scope guard: only a NAMED cohort with no ingest directory is an unrun check. Under `all`
    the cohorts come from the directories, and a directory with no visit.yaml stays 5.0 WARNING."""
    cache = _make_tree(tmp_path)
    (tmp_path / "priority_variables_transform" / "EXTRA-ingest").mkdir()
    rc = _run_vvs(monkeypatch, tmp_path, "--cohort", "all", "--cache-dir", str(cache))
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "No visit.yaml found for cohort EXTRA" in out
