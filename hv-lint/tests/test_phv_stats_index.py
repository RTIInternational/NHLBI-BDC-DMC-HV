"""Tests for hv-lint/build_phv_stats_index.py (var_report value counts for 3.17b / 3.18).

Run: python -m pytest hv-lint/tests/test_phv_stats_index.py
"""

import gzip
import json
import sys
from pathlib import Path

import pytest

HVLINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HVLINT))
import build_phv_stats_index as bsi  # noqa: E402

VAR_REPORT = """<?xml version="1.0"?>
<data_table name="YR10" dataset_id="pht001474.v1" study_id="phs000287.v7">
<variable id="phv00101487.v1.p1" var_name="MIHOSP59"><total><stats>
  <stat n="38" nulls="5493"/><enum code="1" count="37">YES</enum><enum code="0" count="1">NO</enum>
</stats></total></variable>
<variable id="phv00101487.v1.p1.c1" var_name="MIHOSP59"><total><stats>
  <stat n="30"/><enum code="1" count="29">YES</enum><enum code="0" count="1">NO</enum>
</stats></total></variable>
<variable id="phv00121263.v2.p2" var_name="Y01MIEP"><total><stats>
  <stat n="146"/><enum count="132">1</enum><enum count="14">2</enum>
</stats></total></variable>
<variable id="phv00101324.v1.p1" var_name="Individual_ID"><total><stats>
  <stat n="5531" nulls="0"/>
</stats></total></variable>
</data_table>
"""


def test_parse_var_report(tmp_path):
    f = tmp_path / "phs000287.v7.pht001474.v1.p1.YR10.var_report.xml"
    f.write_text(VAR_REPORT, encoding="utf-8")
    recs = bsi.parse_var_report(f)
    # consent-group row (.c1) ignored; uncoded enum keyed by its text; a variable with no enum
    # keeps its n (rule 3.19) and no "c"
    assert recs == {
        "phv00101487": {"n": 38, "c": {"1": 37, "0": 1}},
        "phv00121263": {"n": 146, "c": {"1": 132, "2": 14}},
        "phv00101324": {"n": 5531},
    }


def test_build_respects_study_prefix_and_is_reproducible(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "phs000287.v7.pht001474.v1.p1.YR10.var_report.xml").write_text(VAR_REPORT, encoding="utf-8")
    (src / "phs000226.v7.pht003218.v2.p1.Other.var_report.xml").write_text(
        VAR_REPORT.replace("phv00101487", "phv09999999"), encoding="utf-8")
    out = tmp_path / "out"
    assert bsi.build_stats_index("chs", src, out, study_prefix="phs000287.v7.") == 3
    first = (out / "chs_stats.json.gz").read_bytes()
    with gzip.open(out / "chs_stats.json.gz", "rt", encoding="utf-8") as fh:
        assert "phv09999999" not in json.load(fh)
    bsi.build_stats_index("chs", src, out, study_prefix="phs000287.v7.")
    assert (out / "chs_stats.json.gz").read_bytes() == first


def test_both_builds_record_what_the_loader_verifies(tmp_path):
    """The stats and --tables builds each record their artifact, so the loader reads it."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "phs000287.v7.pht001474.v1.p1.YR10.var_report.xml").write_text(
        VAR_REPORT, encoding="utf-8")
    (src / "phs000287.v7.pht001474.v1.YR10.data_dict.xml").write_text(
        "<data_table><description>Year 10</description></data_table>", encoding="utf-8")
    out = tmp_path / "out"
    assert bsi.build_stats_index("k", src, out, study_prefix="phs000287.v7.") == 3
    assert bsi.build_tables_index("k", src, out, study_prefix="phs000287.v7.") == 1
    assert len(bsi._cohorts.load_cache_artifact(out, "k", "_stats")) == 3
    assert bsi._cohorts.load_table_names(out, "k") == {
        "pht001474": {"name": "YR10", "description": "Year 10"}}


def test_a_coded_variable_with_no_stat_has_no_n_and_is_not_empty(tmp_path):
    """Review 5 A N1 / B N3: no <stat> means n unknown. n = 0 would read as empty in 3.19."""
    import gzip as _gz
    sys.path.insert(0, str(HVLINT / "phase-3"))
    import check_status_semantic as css
    xml = VAR_REPORT.replace(
        "</data_table>",
        '<variable id="phv00100001.v1.p1" var_name="NOSTAT"><total><stats>\n'
        '  <enum code="1" count="3">YES</enum>\n</stats></total></variable>\n</data_table>')
    f = tmp_path / "phs000287.v7.pht001474.v1.p1.YR10.var_report.xml"
    f.write_text(xml, encoding="utf-8")
    recs = bsi.parse_var_report(f)
    assert recs["phv00100001"] == {"c": {"1": 3}}
    with _gz.open(tmp_path / "k_stats.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(recs, fh)
    bsi._record_artifact(tmp_path, "k", tmp_path / "k_stats.json.gz")
    nonnull = css.load_nonnull_counts(tmp_path, "k")
    assert "phv00100001" not in nonnull and nonnull["phv00101324"] == 5531
    assert css.load_stats_index(tmp_path, "k")["phv00100001"].counts == {"1": 3}


TRUNCATED_DATA_DICT = '<?xml version="1.0"?>\n<data_table id="pht001474.v1"><descr'


@pytest.mark.parametrize("tables", [False, True], ids=["stats", "tables"])
def test_main_publishes_nothing_over_a_truncated_xml(tmp_path, monkeypatch, capsys, tables):
    """A skipped file gave an index missing it while the manifest recorded a valid digest."""
    src = tmp_path / "src"
    src.mkdir()
    report = src / "phs000287.v7.pht001474.v1.p1.YR10.var_report.xml"
    report.write_text(VAR_REPORT, encoding="utf-8")
    ddict = src / "phs000287.v7.pht001474.v1.YR10.data_dict.xml"
    ddict.write_text("<data_table><description>Year 10</description></data_table>",
                     encoding="utf-8")
    out = tmp_path / "out"
    bsi.build_stats_index("k", src, out, study_prefix="phs000287.v7.")
    bsi.build_tables_index("k", src, out, study_prefix="phs000287.v7.")
    prior = {p.name: p.read_bytes() for p in out.iterdir()}
    assert {"k_stats.json.gz", "k_tables.json.gz", "manifest.json"} <= prior.keys()

    # A good file sorted BEFORE the bad one must not be published either.
    (src / "phs000287.v7.pht000001.v1.p1.A.var_report.xml").write_text(
        VAR_REPORT.replace("phv00101487", "phv09999999"), encoding="utf-8")
    (src / "phs000287.v7.pht000001.v1.A.data_dict.xml").write_text(
        "<data_table><description>A</description></data_table>", encoding="utf-8")
    if tables:
        ddict.write_text(TRUNCATED_DATA_DICT, encoding="utf-8")
    else:
        report.write_text(VAR_REPORT[: len(VAR_REPORT) // 2], encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["build_phv_stats_index.py", "--cohort", "phs000287.v7",
                                      "--source-dir", str(src), "--output-dir", str(out),
                                      "--study-prefix", "phs000287.v7."]
                        + (["--tables"] if tables else []))
    assert bsi.main() == 1
    err = capsys.readouterr().err
    assert "Publishing nothing" in err and ("data_dict" if tables else "var_report") in err
    assert {p.name: p.read_bytes() for p in out.iterdir()} == prior


@pytest.mark.parametrize("tables", [False, True], ids=["stats", "tables"])
@pytest.mark.parametrize("argv, why", [
    (["--cohort", "fhs"], "not a release key"),
    (["--cohort", "phs000287.v7", "--study-prefix", "phs000287.v6."], "does not match"),
    (["--cohort", "phs000287.v7"], None),  # files carry no release stamp
], ids=["cohort-name", "other-release", "unstamped"])
def test_main_publishes_nothing_without_a_single_release(tmp_path, monkeypatch, capsys,
                                                         tables, argv, why):
    """A key that is not one release wrote `<key>_stats.json.gz` with no provenance."""
    src = tmp_path / "src"
    src.mkdir()
    stamped = argv[1] != "phs000287.v7" or why is not None
    stem = "phs000287.v7.pht001474.v1." if stamped else ""
    (src / f"{stem}p1.YR10.var_report.xml").write_text(VAR_REPORT, encoding="utf-8")
    (src / f"{stem}YR10.data_dict.xml").write_text(
        "<data_table><description>Y</description></data_table>", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "manifest.json").write_text('{"manifest_version": 1, "entries": {}}',
                                       encoding="utf-8")
    prior = {p.name: p.read_bytes() for p in out.iterdir()}
    monkeypatch.setattr(sys, "argv", ["build_phv_stats_index.py", *argv,
                                      "--source-dir", str(src), "--output-dir", str(out)]
                        + (["--tables"] if tables else []))
    assert bsi.main() == 1
    if why:
        assert why in capsys.readouterr().err
    assert {p.name: p.read_bytes() for p in out.iterdir()} == prior
