"""Tests for hv-lint/build_phv_stats_index.py (var_report value counts for 3.17b / 3.18).

Run: python -m pytest hv-lint/tests/test_phv_stats_index.py
"""

import gzip
import json
import sys
from pathlib import Path

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
    # consent-group row (.c1) ignored; uncoded enum keyed by its text; no-enum var skipped
    assert recs == {
        "phv00101487": {"n": 38, "c": {"1": 37, "0": 1}},
        "phv00121263": {"n": 146, "c": {"1": 132, "2": 14}},
    }


def test_build_respects_study_prefix_and_is_reproducible(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "phs000287.v7.pht001474.v1.p1.YR10.var_report.xml").write_text(VAR_REPORT, encoding="utf-8")
    (src / "phs000226.v7.pht003218.v2.p1.Other.var_report.xml").write_text(
        VAR_REPORT.replace("phv00101487", "phv09999999"), encoding="utf-8")
    out = tmp_path / "out"
    assert bsi.build_stats_index("chs", src, out, study_prefix="phs000287.v7.") == 2
    first = (out / "chs_stats.json.gz").read_bytes()
    with gzip.open(out / "chs_stats.json.gz", "rt", encoding="utf-8") as fh:
        assert "phv09999999" not in json.load(fh)
    bsi.build_stats_index("chs", src, out, study_prefix="phs000287.v7.")
    assert (out / "chs_stats.json.gz").read_bytes() == first
