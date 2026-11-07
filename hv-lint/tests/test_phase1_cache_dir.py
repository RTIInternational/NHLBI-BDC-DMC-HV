"""Rules 1.8 and 1.14 read the cache a run names, and only the release the cohort declares.

``check_cross_file_pht_consistency.py`` is the one Phase 1 component that reads the dbGaP cache.
``run_all.py --cache-dir`` and ``run_phase1.py --cache-dir`` must reach it, or a full run lints
those rules against the committed default cache instead of the one named. It runs the same
release check as Phases 3 and 5 (``_cohorts.release_check_error``), so a stale but valid cache
fails rather than passing or failing against the wrong release.

Each case drives a real ``main()``: the checker's, ``run_phase1.py``'s, and ``run_all.py``'s.
Through the managers, every other component and phase is replaced (they need yamllint and a
network fetch of the BDC-HM schema), and ``run_phase1.py`` keeps only the cache-reading
component, so the path under test is the managers' own argument forwarding.

Run: python -m pytest hv-lint/tests/test_phase1_cache_dir.py
"""

import json
import shutil
import sys
from pathlib import Path

HVLINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HVLINT / "tests"))
import _e2e as E  # noqa: E402

P1 = "phase-1/check_cross_file_pht_consistency.py"
FHS_KEY = "phs000007.v35"
NO_TABLES = "1.8's table-name check DID NOT RUN"
WRONG_RELEASE = f"built from phs000007.v34, not {FHS_KEY}"

_PHASE1_ONLY_PHT = """import sys
sys.path.insert(0, {phase1!r})
import run_phase1
run_phase1.COMPONENTS = {{"cross-file-pht": run_phase1.COMPONENTS["cross-file-pht"]}}
sys.exit(run_phase1.main())
"""

_RUN_ALL = """import sys
from pathlib import Path
sys.path.insert(0, {hvlint!r})
import run_all
for name in ("phase2", "phase3", "phase5"):
    stub = Path({tmp!r}) / f"stub_{{name}}.py"
    stub.write_text("raise SystemExit(0)\\n", encoding="utf-8")
    run_all.PHASES[name]["script"] = stub
run_all.PHASES["phase1"]["script"] = Path({phase1!r})
sys.exit(run_all.main())
"""


def _tree(tmp_path: Path) -> E.Tree:
    t = E.Tree(tmp_path, "FHS")
    t.write("afib.yaml", [E.fixture_block("fhs_afib_b24.yaml")])
    shutil.copytree(HVLINT.parent / "hv_dataqc" / "cache_fetcher" / "manifests",
                    t.root / "hv_dataqc" / "cache_fetcher" / "manifests")
    return t


def _cache(t: E.Tree, sub: str, *, drop_tables: bool = False,
           wrong_release: bool = False) -> Path:
    """A copy of the committed cache, without FHS's ``_tables`` index or with FHS's manifest
    entry recording another release (its artifact records untouched, so the integrity check
    still passes and the release check is what must refuse it)."""
    cache = t.tmp / sub
    shutil.copytree(E.CACHE, cache)
    if drop_tables:
        (cache / f"{FHS_KEY}_tables.json.gz").unlink()
    if wrong_release:
        manifest = cache / "manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["entries"][FHS_KEY]["study_version"] = "v34"
        manifest.write_text(json.dumps(data), encoding="utf-8")
    return cache


def _run_phase1(t: E.Tree, cache: Path):
    driver = t.tmp / "run_phase1_driver.py"
    driver.write_text(_PHASE1_ONLY_PHT.format(phase1=str(HVLINT / "phase-1")), encoding="utf-8")
    return t.run(str(driver), "--cohort", "FHS", "--cache-dir", str(cache))


def _run_all(t: E.Tree, cache: Path):
    phase1 = t.tmp / "run_phase1_driver.py"
    phase1.write_text(_PHASE1_ONLY_PHT.format(phase1=str(HVLINT / "phase-1")), encoding="utf-8")
    driver = t.tmp / "run_all_driver.py"
    driver.write_text(_RUN_ALL.format(hvlint=str(HVLINT), tmp=str(t.tmp), phase1=str(phase1)),
                      encoding="utf-8")
    return t.run(str(driver), "--cohort", "FHS", "--no-report", "--cache-dir", str(cache))


def _out(res) -> str:
    return res.stdout + res.stderr


# -- the cache a manager names reaches the checker --------------------------------------------

def test_run_phase1_passes_a_good_cache_dir_to_the_checker(tmp_path):
    t = _tree(tmp_path)
    res = _run_phase1(t, _cache(t, "good"))
    assert res.returncode == 0, _out(res)[-2000:]
    assert "Cross-File PHT Visit Label Consistency (1.8, 1.14)" in res.stdout


def test_run_phase1_forwards_cache_dir_to_the_checker(tmp_path):
    """Without the forwarding the checker read the committed cache, which has FHS's names."""
    t = _tree(tmp_path)
    res = _run_phase1(t, _cache(t, "no_tables", drop_tables=True))
    assert res.returncode == 1, _out(res)[-2000:]
    assert NO_TABLES in _out(res), _out(res)[-2000:]


def test_run_all_forwards_cache_dir_to_phase_1(tmp_path):
    t = _tree(tmp_path)
    good = _run_all(t, _cache(t, "good"))
    assert good.returncode == 0, _out(good)[-2000:]
    res = _run_all(t, _cache(t, "no_tables", drop_tables=True))
    assert res.returncode == 1, _out(res)[-2000:]
    assert NO_TABLES in _out(res), _out(res)[-2000:]
    assert "Phase 1 -- YAML Structure & Formatting" in res.stdout


def test_run_phase1_does_not_pass_cache_dir_to_components_that_reject_it(tmp_path):
    """Every other component's argparse would exit 2 on --cache-dir."""
    sys.path.insert(0, str(HVLINT / "phase-1"))
    try:
        import run_phase1
    finally:
        sys.path.remove(str(HVLINT / "phase-1"))
    takes = {n for n, c in run_phase1.COMPONENTS.items() if c.get("supports_cache_dir")}
    assert takes == {"cross-file-pht"}


# -- the release check ----------------------------------------------------------------------

def test_checker_fails_on_a_cache_of_another_release(tmp_path):
    t = _tree(tmp_path)
    res = t.run(P1, "--cohort", "FHS", "--cache-dir", str(_cache(t, "stale", wrong_release=True)))
    assert res.returncode == 1, _out(res)[-2000:]
    assert f"declared release {FHS_KEY}" in res.stderr, res.stderr[-800:]
    assert WRONG_RELEASE in res.stderr


def test_checker_fails_when_the_cohort_declares_no_release(tmp_path):
    t = _tree(tmp_path)
    cache = _cache(t, "good")
    shutil.rmtree(t.root / "hv_dataqc")
    res = t.run(P1, "--cohort", "FHS", "--cache-dir", str(cache))
    assert res.returncode == 1, _out(res)[-2000:]
    assert "declares no dbGaP release" in res.stderr, res.stderr[-800:]


def test_checker_release_check_ignores_fail_on(tmp_path):
    t = _tree(tmp_path)
    res = t.run(P1, "--cohort", "FHS", "--fail-on", "critical", "--cache-dir",
                str(_cache(t, "stale", wrong_release=True)))
    assert res.returncode == 1, _out(res)[-2000:]
    assert WRONG_RELEASE in res.stderr


def test_run_all_fails_phase_1_on_a_cache_of_another_release(tmp_path):
    t = _tree(tmp_path)
    res = _run_all(t, _cache(t, "stale", wrong_release=True))
    assert res.returncode == 1, _out(res)[-2000:]
    assert WRONG_RELEASE in _out(res)
