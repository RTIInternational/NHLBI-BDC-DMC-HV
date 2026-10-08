"""The enforcement model (#885 part 4): known issues, stale entries, the WARNING ratchet.

Run: python -m pytest hv-lint/tests/test_known_issues.py
"""

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

HVLINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HVLINT))
import _known_issues as K  # noqa: E402

TREE = HVLINT.parent / "priority_variables_transform"


@dataclass
class F:
    file: str
    block: int
    check: str
    severity: str
    message: str


AFIB = "priority_variables_transform/FHS-ingest/afib.yaml"
ENTRY = K.Entry(rule="5.11", file="FHS-ingest/afib.yaml", block=0, issue=882, status="defect")


def _run(findings, entries, baseline=None, scanned=(AFIB,), checks=("5.11",)):
    return K.finalize(findings, checks=checks, scanned_files=scanned, make_finding=F,
                      entries=entries, baseline=baseline or {}, update_baseline=False)


def test_every_entry_names_an_issue_and_a_status():
    entries = K.load_entries()
    assert entries, "hv-lint/known_issues.yaml is empty or missing"
    for e in entries:
        assert isinstance(e.issue, int) and e.issue > 0, e
        assert e.status in K.STATUSES, e
        assert re.fullmatch(r"\d\.\d+b?", e.rule), e
        assert re.fullmatch(r"[A-Za-z]+-ingest/[\w.-]+\.yaml", e.file), e


def test_every_entry_points_at_a_file_that_exists():
    if not TREE.is_dir():
        pytest.skip("no spec tree")
    missing = sorted({e.file for e in K.load_entries() if not (TREE / e.file).is_file()})
    assert missing == []


def test_entry_without_issue_or_with_unknown_status_is_rejected(tmp_path):
    p = tmp_path / "ki.yaml"
    p.write_text('- {rule: "5.11", file: FHS-ingest/a.yaml, status: defect}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="issue"):
        K.load_entries(p)
    p.write_text('- {rule: "5.11", file: FHS-ingest/a.yaml, issue: 1, status: maybe}\n',
                 encoding="utf-8")
    with pytest.raises(ValueError, match="status"):
        K.load_entries(p)


def test_matched_finding_is_info_with_its_issue():
    f = F(AFIB, 0, "5.11", "ERROR", "seed is idtype")
    assert _run([f], [ENTRY]) == []
    assert f.severity == "INFO" and "#882" in f.message and "defect" in f.message


def test_removing_the_entry_leaves_exactly_that_finding_at_error():
    f = F(AFIB, 0, "5.11", "ERROR", "seed is idtype")
    g = F(AFIB, 1, "5.11", "ERROR", "seed is idtype")
    entry_g = K.Entry(rule="5.11", file="FHS-ingest/afib.yaml", block=1, issue=882,
                      status="defect")
    assert _run([f, g], [entry_g]) == []
    assert [(x.block, x.severity) for x in (f, g)] == [(0, "ERROR"), (1, "INFO")]


def test_stale_entry_fails():
    extra = _run([], [ENTRY])
    assert [(x.check, x.severity) for x in extra] == [("KI", "ERROR")]
    assert "stale" in extra[0].message


def test_entry_out_of_scope_is_not_stale():
    # another cohort, or a rule this component did not run
    assert _run([], [ENTRY], scanned=("priority_variables_transform/ARIC-ingest/x.yaml",)) == []
    assert _run([], [ENTRY], checks=("3.5",)) == []


def test_entry_matching_two_findings_fails():
    loose = K.Entry(rule="5.11", file="FHS-ingest/afib.yaml", issue=882, status="defect")
    fs = [F(AFIB, 0, "5.11", "ERROR", "a"), F(AFIB, 1, "5.11", "ERROR", "b")]
    extra = _run(fs, [loose])
    assert [(x.check, x.severity) for x in extra] == [("KI", "ERROR")]
    assert "matches 2" in extra[0].message


def test_match_narrows_an_entry_within_one_block():
    e = K.Entry(rule="3.5", file="FHS-ingest/afib.yaml", block=0, match="phv00000002",
                issue=883, status="defect")
    fs = [F(AFIB, 0, "3.5", "ERROR", "PHV 'phv00000001'"), F(AFIB, 0, "3.5", "ERROR",
                                                            "PHV 'phv00000002'")]
    assert _run(fs, [e], checks=("3.5",)) == []
    assert [x.severity for x in fs] == ["ERROR", "INFO"]


def test_ratchet_fails_on_a_rise_and_on_a_fall():
    w = [F(AFIB, i, "5.2", "WARNING", "label") for i in range(3)]
    same = _run(w, [], baseline={"5.2": {"FHS": 3}}, checks=("5.2",))
    assert same == []
    up = _run(w, [], baseline={"5.2": {"FHS": 2}}, checks=("5.2",))
    assert [x.check for x in up] == ["RATCHET"] and "rose from 2 to 3" in up[0].message
    down = _run(w, [], baseline={"5.2": {"FHS": 4}}, checks=("5.2",))
    assert [x.check for x in down] == ["RATCHET"] and "fell from 4 to 3" in down[0].message


def test_baseline_update_replaces_only_the_rows_in_scope(tmp_path, monkeypatch):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"warnings": {"5.2": {"ARIC": 1, "FHS": 9}}}), encoding="utf-8")
    monkeypatch.setattr(K, "BASELINE_FILE", path)
    w = [F(AFIB, 0, "5.2", "WARNING", "label")]
    K.finalize(w, checks={"5.2"}, scanned_files=[AFIB], make_finding=F, entries=[],
               update_baseline=True)
    assert json.loads(path.read_text(encoding="utf-8"))["warnings"] == {
        "5.2": {"ARIC": 1, "FHS": 1}}


def test_committed_baseline_and_entries_load():
    assert K.load_baseline(), "hv-lint/warning_baseline.json is empty or missing"
    assert len(K.load_entries()) == len({(e.rule, e.file, e.block, e.match)
                                         for e in K.load_entries()})
