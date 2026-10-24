"""silencing_summary.py lists exactly what a PR adds to the three silencing files.

Run: python -m pytest hv-lint/tests/test_silencing_summary.py
"""

import json
import sys
from pathlib import Path

HVLINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HVLINT))
import silencing_summary as S  # noqa: E402

KI_BASE = (
    '- {rule: "5.11", file: FHS-ingest/afib.yaml, block: "Condition@pht000012:phv00001339", '
    'message: "seed", issue: 882, status: defect}\n'
    '- {rule: "3.9", file: FHS-ingest/cig_smok.yaml, block: "Observation@pht000030:phv00007542",'
    ' message: "drops code", issue: 883, status: pending}\n')
KI_HEAD = (
    '- {rule: "5.11", file: FHS-ingest/afib.yaml, block: "Condition@pht000012:phv00001339", '
    'message: "seed", issue: 882, status: defect}\n'                       # unchanged
    '- {rule: "3.9", file: FHS-ingest/cig_smok.yaml, block: "Observation@pht000030:phv00007542",'
    ' message: "drops code", issue: 883, status: defect}\n'                # status changed
    '- {rule: "3.15", file: FHS-ingest/cig_smok.yaml, block: "Observation@pht000030:phv0000754|x",'
    ' message: "never mapped", issue: 873, status: pending}\n')            # new
BL_BASE = {"warnings": {"3.12": {"FHS": ["FHS-ingest/stroke.yaml | b | m1"]}}}
BL_HEAD = {"warnings": {"3.12": {"FHS": ["FHS-ingest/stroke.yaml | b | m1",
                                         "FHS-ingest/stroke.yaml | b | m2"]},
                        "2.6": {"CHS": ["CHS-ingest/x.yaml | c | HIGH"]}}}
REMOVED_HEAD = "# header\n" + (
    '- {rule: "3.5", file: "FHS-ingest/stroke.yaml", block: "Condition@pht006024:phv00276989", '
    'message: "m", issue: 883, date: "2026-10-09", why: "block removed: gone"}\n')


def _write(d: Path, ki: str, bl: dict, removed: str | None) -> Path:
    d.mkdir()
    (d / "known_issues.yaml").write_text(ki, encoding="utf-8")
    (d / "warning_baseline.json").write_text(json.dumps(bl), encoding="utf-8")
    if removed is not None:
        (d / "removed.yaml").write_text(removed, encoding="utf-8")
    return d


def test_lists_only_what_the_head_adds(tmp_path, capsys):
    base = _write(tmp_path / "base", KI_BASE, BL_BASE, None)          # no removed.yaml yet
    head = _write(tmp_path / "head", KI_HEAD, BL_HEAD, REMOVED_HEAD)
    assert S.main(["--base-dir", str(base), "--head-dir", str(head)]) == 0
    out = capsys.readouterr().out
    assert "this PR silences 5 finding(s)" in out
    assert "2 known-issue entries added or changed" in out
    assert "2 WARNING/HIGH baseline row(s) added" in out and "1 removal(s)" in out
    assert "| 3.15 |" in out and "phv0000754\\|x" in out and "| 873 | pending |" in out
    assert "| 3.9 |" in out and "| 883 | defect |" in out
    assert "| 5.11 |" not in out and "m1" not in out
    assert "| 3.12 | FHS | FHS-ingest/stroke.yaml \\| b \\| m2 |" in out
    assert "block removed: gone" in out


def test_nothing_added_says_so(tmp_path, capsys):
    base = _write(tmp_path / "base", KI_HEAD, BL_HEAD, REMOVED_HEAD)
    head = _write(tmp_path / "head", KI_HEAD.split("\n")[0] + "\n", BL_BASE,
                  REMOVED_HEAD)                                     # only removals
    assert S.main(["--base-dir", str(base), "--head-dir", str(head)]) == 0
    out = capsys.readouterr().out
    assert "silences 0 finding(s)" in out and "No known-issue entry" in out
