"""#885 refinements after review round 4, each through the real component main().

- 3.18 / 3.9: a follow-up whose gate question names no condition (CHS DIABF38 under DIETF38
  "follow a special diet?", ARIC IFIA06A under IFIA05 "hospitalized in the past four weeks?").

Run: python -m pytest hv-lint/tests/test_refinements_885.py
"""

import copy
import sys
from pathlib import Path

HVLINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HVLINT / "tests"))
sys.path.insert(0, str(HVLINT / "phase-3"))
import _e2e as E  # noqa: E402
import check_status_semantic as css  # noqa: E402


def _status(block: dict) -> dict:
    return block["class_derivations"]["Condition"]["slot_derivations"]["condition_status"]


# -- 3.18 / 3.9: gate questions ----------------------------------------------------------------

def test_318_gated_follow_up_mapped_absent_is_reported_through_main(tmp_path):
    """DIABF38 '0' ("special diet not for diabetes") -> ABSENT is a new 3.18 WARNING."""
    t = E.Tree(tmp_path, "CHS")
    t.write("diabetes.yaml", [E.fixture_block("chs_diabetes_diabf38.yaml")])
    res = E.phase3(t, "check_status_semantic.py")
    assert res.returncode == 1, res.stdout[-1500:]
    assert "new WARNING [3.18]" in res.stdout
    assert "gate question DIETF38 (phv00104227)" in res.stdout


def test_318_unlabelled_n_of_a_gated_follow_up_is_an_error_through_main(tmp_path):
    """IFIA06A has no code labels; its 'N' is still the "No" of a follow-up (gate IFIA05)."""
    t = E.Tree(tmp_path, "ARIC")
    t.write("hist_my_inf.yaml", [E.fixture_block("aric_hist_my_inf_ifia06a.yaml")])
    res = E.phase3(t, "check_status_semantic.py")
    assert res.returncode == 1, res.stdout[-1500:]
    lines = t.suggested(res)
    assert len(lines) == 1 and '"3.18"' in lines[0] and "gate question IFIA05" in lines[0]


def test_39_dropping_the_no_of_a_gated_follow_up_passes_through_main(tmp_path):
    """The #888 fix (drop the follow-up's "No") must not trade 3.18 for a 3.9 ERROR."""
    t = E.Tree(tmp_path, "CHS")
    b = copy.deepcopy(E.fixture_block("chs_diabetes_diabf38.yaml"))
    _status(b)["value_mappings"] = {"1": "PRESENT"}
    t.write("diabetes.yaml", [b])
    res = E.phase3(t, "validate_semantic.py")
    assert res.returncode == 0, res.stdout[-1500:]
    assert "[3.9]" not in res.stdout.split("drops observed value '0'")[0] or \
        "drops observed value '0'" not in res.stdout

    t2 = E.Tree(tmp_path / "aric", "ARIC")
    a = copy.deepcopy(E.fixture_block("aric_hist_my_inf_ifia06a.yaml"))
    _status(a)["value_mappings"] = {"Y": "HISTORICAL"}
    t2.write("hist_my_inf.yaml", [a])
    res = E.phase3(t2, "validate_semantic.py")
    assert res.returncode == 0, res.stdout[-1500:]
    assert "drops observed value 'N'" not in res.stdout


def test_39_dropping_no_on_a_question_asked_of_everyone_still_fails_through_main(tmp_path):
    """Control: DIETF38 itself is asked of everyone; dropping its '0' is data loss."""
    t = E.Tree(tmp_path, "CHS")
    b = copy.deepcopy(E.fixture_block("chs_diabetes_diabf38.yaml"))
    _status(b)["populated_from"] = "phv00104227"
    _status(b)["value_mappings"] = {"1": "PRESENT"}
    t.write("diabetes.yaml", [b])
    res = E.phase3(t, "validate_semantic.py")
    assert res.returncode == 1 and "drops observed value '0'" in res.stdout


PHT = "pht000001"


def _gate_index(item_desc: str, between_n: int = 800, gate_desc: str = "FOLLOW A SPECIAL DIET"):
    recs = {
        "phv00000001": css._cvs.PhvDetail("FAR", PHT, "", None, "EVER HAD A COLD",
                                          {"0": "NO", "1": "YES"}),
        "phv00000002": css._cvs.PhvDetail("GATE", PHT, "", None, gate_desc,
                                          {"0": "NO", "1": "YES"}),
        "phv00000003": css._cvs.PhvDetail("MID", PHT, "", None, "TO LOSE WEIGHT",
                                          {"0": "NO", "1": "YES"}),
        "phv00000004": css._cvs.PhvDetail("ITEM", PHT, "", None, item_desc,
                                          {"0": "NO", "1": "YES"}),
    }
    stats = {
        "phv00000001": css.PhvStats(4600, {"0": 3600, "1": 1000}),
        "phv00000002": css.PhvStats(4600, {"0": 3680, "1": 920}),
        "phv00000003": css.PhvStats(between_n, {"0": 500, "1": between_n - 500}),
        "phv00000004": css.PhvStats(790, {"0": 545, "1": 245}),
    }
    return css.DetailIndex.from_records(recs), stats


def test_gate_needs_a_branch_item_the_nearest_gate_and_no_condition_in_the_gate():
    idx, st = _gate_index("FOR DIABETES")
    fu = css.detect_followup("phv00000004", idx, st)
    assert fu is not None and fu.gate and fu.sibling_name == "GATE"
    # Not worded as an item of the branch: its "No" is a real answer about the condition.
    idx, st = _gate_index("EVER HAD DIABETES")
    assert css.detect_followup("phv00000004", idx, st) is None
    # An item between them asked of more people ends the branch: GATE is not this item's gate.
    idx, st = _gate_index("FOR DIABETES", between_n=1100)
    assert css.detect_followup("phv00000004", idx, st) is None
    # A gate that names another condition screens for that one.
    idx, st = _gate_index("FOR DIABETES", gate_desc="EVER TOLD ANGINA")
    assert css.detect_followup("phv00000004", idx, st) is None


def test_gate_ratio_band():
    idx, st = _gate_index("FOR DIABETES")
    st["phv00000004"] = css.PhvStats(735, {"0": 500, "1": 235})     # 735 / 920 = 0.799
    assert css.detect_followup("phv00000004", idx, st) is None
    st["phv00000004"] = css.PhvStats(737, {"0": 500, "1": 237})     # 0.801
    assert css.detect_followup("phv00000004", idx, st) is not None
    # A gate with no "yes" answer is not a yes/no question.
    idx.records["phv00000002"].codes = {"0": "NO", "1": "SOMETIMES"}
    assert css.detect_followup("phv00000004", idx, st) is None
    idx.records["phv00000002"].codes = {"0": "NO", "1": "YES"}
    # A gate answered "yes" by more than half its respondents does not split the table.
    st["phv00000002"] = css.PhvStats(1700, {"0": 780, "1": 920})
    assert css.detect_followup("phv00000004", idx, st) is None


def test_negative_answer_reads_an_unlabelled_n_or_0():
    assert css.negative_answer("N", None) and css.negative_answer("0", "")
    assert not css.negative_answer("Y", None) and not css.negative_answer("U", None)
    assert css.negative_answer("1", "No") and not css.negative_answer("N", "Yes")
