"""A skip is not a pass (#885 item 6): a rule that cannot judge a cohort says so, and a rule
whose input is missing fails.

- 1.14 has a visit-evidence pattern only for ARIC and MESA: every other cohort gets one INFO.
- 1.8's table-name ERROR arm needs FHS's ``_tables`` index: without it the run fails.
- 3.13 and 5.8 read only "Collected in: P1 P2" intervals (COPDGene): every other cohort gets one
  INFO -- including FHS, ARIC and CHS, whose detail indexes hold free-text intervals that the
  old ``any coll_interval`` test counted as coverage and then judged nothing with.

Each case drives the component's real main().

Run: python -m pytest hv-lint/tests/test_skip_notices.py
"""

import shutil
import sys
from pathlib import Path

HVLINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HVLINT / "tests"))
sys.path.insert(0, str(HVLINT))
import _e2e as E  # noqa: E402
import _visit_ids  # noqa: E402

P1 = "phase-1/check_cross_file_pht_consistency.py"
FHS_VISIT = E.visit_block("pht000012", "phv00001558", "FHS ORIGINAL EXAM 10")


def _cache_without(t: E.Tree, *names: str) -> Path:
    manifests = t.root / "hv_dataqc" / "cache_fetcher" / "manifests"
    shutil.copytree(HVLINT.parent / "hv_dataqc" / "cache_fetcher" / "manifests", manifests)
    cache = t.tmp / "cache"
    shutil.copytree(E.CACHE, cache)
    for n in names:
        (cache / n).unlink()
    return cache


# -- the shared collection-interval parse ---------------------------------------------------------

def test_collection_intervals_count_only_the_parseable_format():
    assert _visit_ids.has_collection_intervals([None, "Collected in: P1 P2"])
    # FHS / ARIC / CHS text: present, but names no phase -- the old test counted it.
    assert not _visit_ids.has_collection_intervals(
        ["Cancer Cases Reviewed through February 2019", "Collected in Exam 1",
         "1989 through 2014", None, ""])
    assert not _visit_ids.has_collection_intervals([])


# -- 1.14 ------------------------------------------------------------------------------------------

def test_114_reports_not_applicable_for_a_cohort_without_visit_evidence(tmp_path):
    t = E.Tree(tmp_path, "FHS")
    t.write("afib.yaml", [E.fixture_block("fhs_afib_b24.yaml")])
    res = t.run(P1, "--cohort", "FHS")
    assert res.returncode == 0, res.stdout[-1500:] + res.stderr[-800:]
    assert "INFO   block   0  [1.14] 1.14 not applicable: no visit-evidence pattern for cohort FHS" \
        in res.stdout, res.stdout[-1500:]


def test_114_says_nothing_for_a_cohort_it_judges(tmp_path):
    t = E.Tree(tmp_path, "ARIC")
    t.write("afib.yaml", [E.fixture_block("aric_afib_atrfib31.yaml")])
    res = t.run(P1, "--cohort", "ARIC")
    assert res.returncode == 0, res.stdout[-1500:]
    assert "not applicable" not in res.stdout


# -- 1.8 -------------------------------------------------------------------------------------------

def test_18_fails_when_the_fhs_tables_index_is_absent(tmp_path):
    t = E.Tree(tmp_path, "FHS")
    t.write("afib.yaml", [E.fixture_block("fhs_afib_b24.yaml")])
    full = t.run(P1, "--cohort", "FHS", "--cache-dir", str(_cache_without(t)))
    assert full.returncode == 0, full.stdout[-1500:] + full.stderr[-800:]
    shutil.rmtree(t.tmp / "cache")
    shutil.rmtree(t.root / "hv_dataqc")
    res = t.run(P1, "--cohort", "FHS", "--cache-dir",
                str(_cache_without(t, "phs000007.v35_tables.json.gz")))
    assert res.returncode == 1, res.stdout[-1500:]
    assert "1.8's table-name check DID NOT RUN" in res.stderr, res.stderr[-800:]
    # The remedy it names is runnable.
    assert "--tables --cohort phs000007.v35 --source-dir" in res.stderr


# -- 3.13 / 5.8 ------------------------------------------------------------------------------------

def test_313_reports_not_applicable_for_free_text_intervals(tmp_path):
    t = E.Tree(tmp_path, "FHS")
    t.write("afib.yaml", [E.fixture_block("fhs_afib_b24.yaml")])
    res = E.phase3(t, "validate_semantic.py", run_all=False)
    assert "[3.13] 3.13 not applicable for cohort FHS: no collection-interval metadata" \
        in res.stdout, res.stdout[-2000:]


def test_313_says_nothing_for_copdgene(tmp_path):
    t = E.Tree(tmp_path, "COPDGene")
    t.write("bdy_hgt.yaml", [E.fixture_block("copdgene_bdy_hgt_b0.yaml")])
    res = E.phase3(t, "validate_semantic.py", run_all=False)
    assert "Files checked:  1" in res.stdout, res.stdout[-2000:] + res.stderr[-800:]
    assert "not applicable" not in res.stdout


def test_58_reports_not_applicable_as_info_not_a_ratcheted_warning(tmp_path):
    t = E.Tree(tmp_path, "FHS")
    t.write("visit.yaml", [FHS_VISIT])
    t.write("afib.yaml", [E.fixture_block("fhs_afib_b24.yaml")])
    res = E.phase5(t)
    assert "[5.8] 5.8 not applicable for cohort FHS: no collection-interval metadata" \
        in res.stdout, res.stdout[-2000:]
    # Under GITHUB_ACTIONS an INFO prints as a ``::notice`` annotation, so test for what must
    # not appear (a WARNING or ERROR) rather than for the word INFO.
    assert not [x for x in res.stdout.splitlines()
                if "[5.8]" in x and ("WARNING" in x or "ERROR" in x
                                     or x.startswith(("::warning", "::error")))]
    assert "new WARNING [5.8]" not in res.stdout


def test_58_says_nothing_for_copdgene(tmp_path):
    t = E.Tree(tmp_path, "COPDGene")
    t.write("visit.yaml", [E.visit_block("pht002239", "phv00159568", "COPDGene P1", "COPDGene")])
    t.write("bdy_hgt.yaml", [E.fixture_block("copdgene_bdy_hgt_b0.yaml")])
    res = E.phase5(t)
    assert "1 cohort(s) processed" in res.stdout, res.stdout[-2000:]
    assert "5.8 not applicable" not in res.stdout
