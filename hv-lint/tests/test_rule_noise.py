"""Rule noise removed from 3.9, 3.12 and 3.15 (#885 item 5), each pinned on the case that
produced the baseline rows, plus the genuine findings that must survive.

dbGaP metadata comes from the committed cache; the blocks are inline so a later data fix does not
change what these tests prove.

Run: python -m pytest hv-lint/tests/test_rule_noise.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

HVLINT = Path(__file__).resolve().parent.parent
for sub in ("", "phase-3"):
    sys.path.insert(0, str(HVLINT / sub) if sub else str(HVLINT))

import check_status_semantic as css  # noqa: E402
import validate_semantic as vs  # noqa: E402

CACHE = HVLINT / "dbgap-cache"
RELEASE = {"ARIC": "phs000280.v8", "FHS": "phs000007.v35", "JHS": "phs000286.v7"}
_cache: dict = {}


def detail(cohort):
    if cohort not in _cache:
        _cache[cohort] = vs.load_detail_index(CACHE, RELEASE[cohort])
    return _cache[cohort]


def stats(cohort):
    key = ("stats", cohort)
    if key not in _cache:
        _cache[key] = css.load_stats_index(CACHE, RELEASE[cohort])
    return _cache[key]


def _seed(phv, label):
    return {"expr": f'uuid5("https://w3id.org/bdchm/Visit", str({{{phv}}}) + ":{label}")'}


def _domain(block, cohort, filename):
    return vs.check_phv_domain_mismatch(block, 0, f"{cohort}-ingest/{filename}", detail(cohort),
                                        vs._filename_domain_keywords(filename))


# -- 3.12 ----------------------------------------------------------------------------------------

def _aric_hfa_stroke(status_phv):
    """ARIC stroke.yaml: a stroke question on the Heart Failure Hospital Record Abstraction Form,
    keyed by SUBJECT_ID (phv00207055), whose description names that form."""
    return {"class_derivations": {"Condition": {
        "populated_from": "pht004102",
        "slot_derivations": {
            "associated_participant": _seed("phv00207055", "ARIC"),
            "associated_visit": _seed("phv00207055", "ARIC HFA"),
            "condition_status": {"populated_from": status_phv,
                                 "value_mappings": {"Y": "PRESENT", "N": "ABSENT"}},
        }}}}


def test_312_skips_id_and_visit_slots():
    """SUBJECT_ID's description ends "[Heart Failure Hospital Record Abstraction Form, HFA]"."""
    f = _domain(_aric_hfa_stroke("phv00206998"), "ARIC", "stroke.yaml")
    assert [x for x in f if "associated_" in x.message] == []


def test_312_skips_fhs_cohort_identifier():
    """FHS idtype: "Framingham Heart Study cohort identifier", read by the visit seed."""
    block = {"class_derivations": {"Condition": {"slot_derivations": {
        "associated_visit": {"expr": "case((str({phv00276964}) == '0', 'FHS Original'))"}}}}}
    assert _domain(block, "FHS", "stroke.yaml") == []


def test_312_ignores_a_domain_word_inside_a_form_name():
    """HFAA75 "Q75 - Stroke [Heart Failure Hospital Record Abstraction Form, HFA]"."""
    assert _domain(_aric_hfa_stroke("phv00206998"), "ARIC", "stroke.yaml") == []


def test_312_ignores_a_domain_word_inside_a_study_name():
    """JHS SSFC1 "Since your last Jackson Heart Study exam ..." in stroke.yaml."""
    block = {"class_derivations": {"Condition": {"slot_derivations": {
        "condition_status": {"populated_from": "phv00403990",
                             "value_mappings": {"Y": "PRESENT"}}}}}}
    assert _domain(block, "JHS", "stroke.yaml") == []


def test_312_still_reports_a_conflicting_subject():
    """ARIC PHEA07A asks about surgery on the heart OR the arteries of the neck: a real mixed
    question in a coronary-bypass file, and no study or form name is involved."""
    block = {"class_derivations": {"Procedure": {"slot_derivations": {
        "procedure_status": {"populated_from": "phv00208846",
                             "value_mappings": {"Y": "PRESENT"}}}}}}
    f = _domain(block, "ARIC", "hist_cor_bypg.yaml")
    assert [(x.check, x.severity) for x in f] == [("3.12", "WARNING")] and "neck" in f[0].message


def test_proper_name_regex_keeps_the_subject():
    assert vs._PROPER_NAME_RE.sub(" ", "Q75 - Stroke [Heart Failure Form, HFA]").split() \
        == ["Q75", "-", "Stroke", "[", ",", "HFA]"]
    assert "heart" in vs._PROPER_NAME_RE.sub(" ", "Heart attack ever?").lower()


# -- 3.9 / 3.15: "<code>. <label>" keys ----------------------------------------------------------

def _jhs_pdsa28a(keys):
    """JHS fam_income.yaml block 0: PDSA28A (phv00128078) declares A-M; no var_report counts."""
    return {"class_derivations": {"SdohObservation": {
        "populated_from": "pht001966",
        "slot_derivations": {"value_quantity": {"class_derivations": [{"Quantity": {
            "populated_from": "pht001966",
            "slot_derivations": {"value_concept": {
                "populated_from": "phv00128078",
                "value_mappings": {k: "x" for k in keys}}}}}]}}}}}


_JOINED = [f"{c}. {lbl}" for c, lbl in detail("JHS").records["phv00128078"].codes.items()
           if c in "CDEFGHIJK"]


def test_39_accepts_code_dot_label_keys_and_still_reports_the_missing_codes():
    f = vs.check_value_mappings_completeness(
        _jhs_pdsa28a(_JOINED), 0, "JHS-ingest/fam_income.yaml", detail("JHS"), stats("JHS"))
    warned = sorted(x.message.split("code '")[1][0] for x in f if x.severity == "WARNING")
    assert warned == ["A", "B"]
    assert {x.message.split("code '")[1][0] for x in f if x.severity == "INFO"} == {"L", "M"}


def test_315_accepts_code_dot_label_keys():
    f = vs.check_phantom_codes(
        _jhs_pdsa28a(_JOINED), 0, "JHS-ingest/fam_income.yaml", detail("JHS"), stats("JHS"))
    assert f == []


def test_315_still_reports_a_misspelt_joined_key():
    f = vs.check_phantom_codes(
        _jhs_pdsa28a(["C. $8,000-11,999", "Z. Bogus"]), 0, "JHS-ingest/fam_income.yaml",
        detail("JHS"), stats("JHS"))
    assert sorted(x.message.split("key '")[1].split("'")[0] for x in f
                  if x.severity == "WARNING") == ["C. $8,000-11,999", "Z. Bogus"]


def _observed_case():
    idx = vs.DetailIndex({"phv00000001": vs.PhvDetail(
        "Q1", "pht000001", "encoded", None, "Ever smoked?", {"1": "Yes", "2": "No"})})
    st = {"phv00000001": SimpleNamespace(counts={"1": 40, "2": 60})}
    block = {"class_derivations": {"Observation": {"slot_derivations": {"value_concept": {
        "populated_from": "phv00000001", "value_mappings": {"1. Yes": "Y", "2": "N"}}}}}}
    return block, idx, st


def test_39_joined_key_does_not_cover_an_observed_code():
    """The var_report saw bare '1'; a key "1. Yes" never matches it, so the rows are lost."""
    block, idx, st = _observed_case()
    f = vs.check_value_mappings_completeness(block, 0, "X-ingest/x.yaml", idx, st)
    assert [(x.severity, "'1'" in x.message) for x in f] == [("WARNING", True)]


def test_315_joined_key_not_observed_is_still_a_dead_key():
    block, idx, st = _observed_case()
    f = vs.check_phantom_codes(block, 0, "X-ingest/x.yaml", idx, st)
    assert [(x.severity, "'1. Yes'" in x.message) for x in f] == [("INFO", True)]
