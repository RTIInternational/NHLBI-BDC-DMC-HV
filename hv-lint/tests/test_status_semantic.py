"""Tests for HV-Lint rules 3.17 (status polarity) and 3.18 (follow-up mapped to ABSENT).

Fixtures are small in-memory detail / count indexes modelled on the cases
#879 lists: CHS DIABET32 "never told" -> PRESENT, CARDIA 1/2 endpoint flags
read with 0/1 keys, and CHS MIHOSP59 (n 38 = NEWMI59 yes 38).

Run: python -m pytest hv-lint/tests/test_status_semantic.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HVLINT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HVLINT))
sys.path.insert(0, str(HVLINT / "phase-3"))
import check_status_semantic as css  # noqa: E402


def _rec(name, pht, description, codes=None):
    return SimpleNamespace(name=name, pht=pht, type="encoded",
                           description=description, codes=codes)


def _index(records: dict) -> css.DetailIndex:
    return css.DetailIndex.from_records(records)


def _stats(raw: dict) -> dict:
    return {phv: css.PhvStats(n=r["n"], counts=r["c"]) for phv, r in raw.items()}


def _block(phv, mappings, cls="Condition", slot="condition_status"):
    return {"class_derivations": {cls: {
        "populated_from": "pht001474",
        "slot_derivations": {slot: {"populated_from": phv, "value_mappings": mappings}},
    }}}


# --- label classification ---------------------------------------------------

@pytest.mark.parametrize("label,expected", [
    ("NEVER TOLD", "negative"),
    ("No", "negative"),
    ("NO, NOT HOSPITALIZED", "negative"),
    ("None", "negative"),
    ("Not taking", "negative"),
    ("No plaque", "negative"),
    ("Yes", "affirmative"),
    ("YES, NOW", "affirmative"),
    ("Taking", "affirmative"),
    ("Yes, not now", None),
    ("Yes, doubtful", None),
    ("Don't know", None),
    ("Not sure", None),
    ("No answer", None),
    ("NOT PRESENT NOW, FORMERLY DEFINITE", None),
    ("Yes, in the past", None),
    ("TOLD DURING THE PAST YEAR", None),
])
def test_classify_label(label, expected):
    assert css.classify_label(label) == expected


def test_classify_label_strips_code_echo():
    assert css.classify_label("1 = Yes", "1") == "affirmative"
    assert css.classify_label("0: No", "0") == "negative"


# --- 3.17a label polarity ----------------------------------------------------

DIABET32 = {"phv00103169": _rec("DIABET32", "pht001476", "TOLD BY MD YOU HAD DIABETES",
                                {"1": "NEVER TOLD", "2": "TOLD DURING THE PAST YEAR",
                                 "3": "TOLD MORE THAN 1 YEAR AGO"})}


def test_never_told_to_present_is_error():
    block = _block("phv00103169", {"0": "ABSENT", "1": "PRESENT", "2": "PRESENT"})
    f = css.check_status_polarity(block, 9, "x.yaml", _index(DIABET32), None)
    assert [(x.check, x.severity) for x in f] == [("3.17", "ERROR")]
    assert "NEVER TOLD" in f[0].message


def test_correct_never_told_mapping_passes():
    block = _block("phv00103169", {"1": "ABSENT", "2": "PRESENT", "3": "HISTORICAL"})
    assert css.check_status_polarity(block, 0, "x.yaml", _index(DIABET32), None) == []


def test_yes_to_absent_is_error_on_any_status_slot():
    idx = _index({"phv00000001": _rec("MED", "pht000001", "TAKING ASPIRIN",
                                      {"0": "No", "1": "Yes"})})
    block = _block("phv00000001", {"0": "ABSENT", "1": "ABSENT"},
                   cls="DrugExposure", slot="exposure_status")
    f = css.check_status_polarity(block, 0, "x.yaml", idx, None)
    assert len(f) == 1 and "'1'" in f[0].message


def test_slot_not_named_status_is_ignored():
    block = _block("phv00103169", {"1": "PRESENT"}, slot="value_enum")
    assert css.check_status_polarity(block, 0, "x.yaml", _index(DIABET32), None) == []


# --- 3.17b unlabelled 1/2 flag read with 0/1 keys ----------------------------

Y01MIEP = {"phv00121263": _rec("Y01MIEP", "pht001869", "ENDPT - MYOCARDIAL INFARCTION")}


def test_unlabelled_one_two_flag_with_zero_one_keys_is_error():
    stats = _stats({"phv00121263": {"n": 146, "c": {"1": 132, "2": 14}}})
    block = _block("phv00121263", {"0": "ABSENT", "1": "PRESENT"})
    f = css.check_status_polarity(block, 0, "chd.yaml", _index(Y01MIEP), stats)
    assert len(f) == 1 and f[0].severity == "ERROR" and "1 = No" in f[0].message


def test_unlabelled_flag_rekeyed_to_one_two_passes():
    stats = _stats({"phv00121263": {"n": 146, "c": {"1": 132, "2": 14}}})
    block = _block("phv00121263", {"1": "ABSENT", "2": "PRESENT"})
    assert css.check_status_polarity(block, 0, "chd.yaml", _index(Y01MIEP), stats) == []


def test_unlabelled_flag_without_counts_is_not_judged():
    block = _block("phv00121263", {"0": "ABSENT", "1": "PRESENT"})
    assert css.check_status_polarity(block, 0, "chd.yaml", _index(Y01MIEP), None) == []


# --- 3.18 follow-up mapped to ABSENT -------------------------------------------

YR10 = {
    "phv00101485": _rec("NEWMI59", "pht001474", "NEW MYOCARDIAL INFARCTION",
                        {"0": "NO", "1": "YES", "9": "DON'T KNOW"}),
    "phv00101487": _rec("MIHOSP59", "pht001474", "HOSPITALIZED FOR MI",
                        {"0": "NO", "1": "YES", "9": "DON'T KNOW"}),
}
YR10_STATS = {
    "phv00101485": {"n": 3843, "c": {"0": 3805, "1": 38}},
    "phv00101487": {"n": 38, "c": {"1": 37, "0": 1}},
}


def test_followup_with_count_and_wording_is_error():
    block = _block("phv00101487", {"0": "ABSENT", "1": "PRESENT"})
    f = css.check_followup_absent(block, 0, "hist_mi.yaml", _index(YR10), _stats(YR10_STATS))
    assert [(x.check, x.severity) for x in f] == [("3.18", "ERROR")]
    assert "NEWMI59" in f[0].message and "n=38" in f[0].message


def test_followup_count_only_is_warning():
    recs = dict(YR10)
    recs["phv00101487"] = _rec("MI4WK", "pht001474", "MI IN LAST FOUR WEEKS",
                               {"0": "NO", "1": "YES"})
    f = css.check_followup_absent(_block("phv00101487", {"0": "ABSENT"}), 0, "x.yaml",
                                  _index(recs), _stats(YR10_STATS))
    assert [x.severity for x in f] == ["WARNING"]


def test_followup_key_removed_passes():
    block = _block("phv00101487", {"1": "PRESENT"})
    assert css.check_followup_absent(block, 0, "x.yaml", _index(YR10), _stats(YR10_STATS)) == []


def test_question_asked_of_everyone_is_not_a_followup():
    stats = dict(YR10_STATS)
    stats["phv00101487"] = {"n": 3840, "c": {"0": 3700, "1": 140}}
    block = _block("phv00101487", {"0": "ABSENT", "1": "PRESENT"})
    assert css.check_followup_absent(block, 0, "x.yaml", _index(YR10), _stats(stats)) == []


def test_drug_followup_is_not_checked():
    block = _block("phv00101487", {"0": "ABSENT", "1": "PRESENT"},
                   cls="DrugExposure", slot="exposure_status")
    assert css.check_followup_absent(block, 0, "x.yaml", _index(YR10), _stats(YR10_STATS)) == []


def test_sibling_must_precede_the_followup():
    recs = {
        "phv00101487": YR10["phv00101485"],   # screening question placed AFTER
        "phv00101485": YR10["phv00101487"],
    }
    stats = {"phv00101487": YR10_STATS["phv00101485"], "phv00101485": YR10_STATS["phv00101487"]}
    block = _block("phv00101485", {"0": "ABSENT"})
    assert css.check_followup_absent(block, 0, "x.yaml", _index(recs), _stats(stats)) == []


def test_family_history_sibling_is_ignored():
    recs = {
        "phv00105101": _rec("FHSTK", "pht001490", "Family History of stroke", {"0": "NO", "1": "YES"}),
        "phv00105471": _rec("HSSTK22", "pht001490", "EVER HOSPITALIZED FOR STROKE",
                            {"0": "NO", "1": "YES"}),
    }
    stats = _stats({"phv00105101": {"n": 573, "c": {"0": 479, "1": 94}},
                    "phv00105471": {"n": 59, "c": {"1": 40, "0": 19}}})
    block = _block("phv00105471", {"0": "ABSENT", "1": "PRESENT"})
    assert css.check_followup_absent(block, 0, "x.yaml", _index(recs), stats) == []


def test_confirmation_followup_is_not_checked():
    recs = {
        "phv00176281": _rec("prafib5", "pht003091", "PRESENCE OF: ATRIAL FIBRILLATION",
                            {"0": "NO", "1": "YES"}),
        "phv00176292": _rec("ecgafib5", "pht003091", "CONFIRMED: ATRIAL FIBRILLATION",
                            {"0": "NO", "1": "YES, CONFIRMED"}),
    }
    stats = _stats({"phv00176281": {"n": 4357, "c": {"0": 4288, "1": 69}},
                    "phv00176292": {"n": 69, "c": {"0": 33, "1": 36}}})
    block = _block("phv00176292", {"0": "ABSENT", "1": "PRESENT"})
    assert css.check_followup_absent(block, 0, "x.yaml", _index(recs), stats) == []


def test_wording_and_sibling_suffice_only_without_counts():
    block = _block("phv00101487", {"0": "ABSENT", "1": "PRESENT"})
    f = css.check_followup_absent(block, 0, "x.yaml", _index(YR10), None)
    assert [x.severity for x in f] == ["WARNING"]


def test_negative_label_on_followup_is_not_a_polarity_error():
    """'No' (not hospitalized) -> PRESENT is right on a follow-up: the person had the MI."""
    block = _block("phv00101487", {"0": "PRESENT", "1": "PRESENT"})
    assert css.check_status_polarity(block, 0, "x.yaml", _index(YR10), _stats(YR10_STATS)) == []


# --- known issues --------------------------------------------------------------

def test_known_issue_is_downgraded_to_info():
    f = css.Finding("priority_variables_transform/CHS-ingest/hist_mi.yaml", 0, "3.18",
                    "ERROR", "... phv00101487 (MIHOSP59 ...")
    css.apply_known_issues([f], {"CHS-ingest/hist_mi.yaml:phv00101487:3.18": "tracked"})
    assert f.severity == "INFO" and "known issue: tracked" in f.message


def test_known_issues_keys_are_well_formed():
    for key in css.KNOWN_ISSUES:
        path, phv, check = key.split(":")
        assert path.endswith(".yaml") and "-ingest/" in path
        assert css.PHV_RE.fullmatch(phv) and check in {"3.17", "3.18"}


# --- value-count index loading ---------------------------------------------------

def _write_stats(path, data):
    import gzip
    import json
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(data, fh)


def test_load_stats_index_by_cache_key(tmp_path):
    _write_stats(tmp_path / "phs000287.v7_stats.json.gz",
                 {"phv00101487": {"n": 38, "c": {"1": 37}}})
    st = css.load_stats_index(tmp_path, "phs000287.v7")
    assert st["phv00101487"].n == 38 and st["phv00101487"].counts == {"1": 37}
    assert css.load_stats_index(tmp_path, "phs000280.v8") is None


def test_every_committed_detail_index_has_a_stats_index():
    """The count index is named like the detail index, so each release resolves both."""
    cache = HVLINT / "dbgap-cache"
    import _cohorts
    from _paths import find_transform_dir
    for cohort, key in _cohorts.cohorts_to_load("all", cache, find_transform_dir()):
        assert (cache / f"{key}_detail.json.gz").is_file(), cohort
        assert (cache / f"{key}_stats.json.gz").is_file(), (cohort, key)
