"""Rule edges review round 1 (B 7) found unpinned: each test fails if the guarded line is removed.

3.9 severity by share (per code and over the slot), the race / ethnicity sibling suppression,
3.4 on a wrong table qualifier, the 3.5 nested-table exemption, and 2.7 at ERROR in all three
assignment forms. The component main() paths are in test_known_issues_e2e.py.

Run: python -m pytest hv-lint/tests/test_rule_edges_885.py
"""

import sys
from pathlib import Path

HVLINT = Path(__file__).resolve().parent.parent
for sub in ("", "phase-2", "phase-3"):
    sys.path.insert(0, str(HVLINT / sub))
import check_status_semantic as css  # noqa: E402
import validate_dbgap_crossref as xref  # noqa: E402
import validate_model_conformance as vmc  # noqa: E402
import validate_semantic as vs  # noqa: E402

PHV, PHT = "phv00000001", "pht000001"


def _status_block(mappings: dict) -> dict:
    return {"class_derivations": {"Condition": {"populated_from": PHT, "slot_derivations": {
        "condition_status": {"populated_from": PHV, "value_mappings": mappings}}}}}


def _detail(codes: dict, phv=PHV, name="X") -> vs.DetailIndex:
    idx = vs.DetailIndex()
    idx.records[phv] = vs.PhvDetail(name, PHT, "encoded value", None, name, codes)
    return idx


def _39(block, counts: dict, codes=None):
    stats = {PHV: css.PhvStats(sum(counts.values()), {k: v for k, v in counts.items()})}
    f = vs.check_value_mappings_completeness(block, 0, "X-ingest/x.yaml",
                                             _detail(codes or {}), stats)
    return sorted((x.severity, x.message.split("'")[1]) for x in f if x.check == "3.9")


# -- 3.9 ---------------------------------------------------------------------------------------

def test_39_one_code_losing_half_a_high_impact_slot_is_an_error():
    block = _status_block({"0": "ABSENT", "1": "PRESENT"})
    assert _39(block, {"0": 100, "1": 100, "7": 200}) == [("ERROR", "7")]
    assert _39(block, {"0": 100, "1": 100, "7": 199}) == [("WARNING", "7")]   # 49.9%


def test_39_several_codes_adding_up_to_half_the_slot_raise_the_largest_to_error():
    block = _status_block({"0": "ABSENT", "1": "PRESENT"})
    f = _39(block, {"0": 100, "1": 100, "7": 60, "8": 70, "9": 70})   # 15-17.5% each, 50% in all
    assert f == [("ERROR", "9"), ("WARNING", "7"), ("WARNING", "8")]


def test_39_small_codes_adding_up_to_a_tenth_raise_the_largest_to_warning():
    block = _status_block({"0": "ABSENT", "1": "PRESENT"})
    f = _39(block, {"0": 500, "1": 500, "7": 40, "8": 40, "9": 41})   # 3.6% each, 10.8% in all
    assert f == [("INFO", "7"), ("INFO", "8"), ("WARNING", "9")]


def test_39_race_code_mapped_by_the_ethnicity_sibling_is_not_dropped():
    block = {"class_derivations": {"Demography": {"populated_from": PHT, "slot_derivations": {
        "race": {"populated_from": PHV, "value_mappings": {"1": "OMOP:8527"}},
        "ethnicity": {"populated_from": PHV, "value_mappings": {"2": "OMOP:38003563"}},
    }}}}
    f = _39(block, {"1": 50, "2": 50})
    assert ("ERROR", "2") not in f and ("WARNING", "2") not in f
    del block["class_derivations"]["Demography"]["slot_derivations"]["ethnicity"]
    assert ("ERROR", "2") in _39(block, {"1": 50, "2": 50})


# -- 3.4 / 3.5 ---------------------------------------------------------------------------------

def _index(**phv_pht) -> xref.DbGaPIndex:
    return xref.DbGaPIndex(phv_to_pht=dict(phv_pht), valid_phts=set(phv_pht.values()))


def _measure(value_slot: dict, nested_pht: str | None = None, top_slots=None) -> dict:
    quantity = {"slot_derivations": {"value_decimal": value_slot}}
    if nested_pht:
        quantity["populated_from"] = nested_pht
    slots = {"value_quantity": {"class_derivations": [{"Quantity": quantity}]}}
    slots.update(top_slots or {})
    return {"class_derivations": {"MeasurementObservation": {"populated_from": PHT,
                                                             "slot_derivations": slots}}}


def _xr(block, idx):
    return sorted((x.check, x.severity) for x in xref.check_block(block, 0, "X-ingest/x.yaml", idx)
                  if x.check in ("3.4", "3.5"))


def test_34_qualifier_naming_the_wrong_table_is_an_error():
    idx = _index(phv00000001=PHT, phv00000002="pht000002")
    wrong = _measure({"populated_from": "phv00000001"},
                     top_slots={"age_at_observation": {"expr": "{pht000003.phv00000002} * 365"}})
    assert _xr(wrong, idx) == [("3.4", "ERROR")]
    right = _measure({"populated_from": "phv00000001"},
                     top_slots={"age_at_observation": {"expr": "{pht000002.phv00000002} * 365"}})
    assert _xr(right, idx) == []


def test_35_nested_populated_from_makes_its_table_reachable():
    idx = _index(phv00000001=PHT, phv00000002="pht000002")
    assert _xr(_measure({"populated_from": "phv00000002"}, nested_pht="pht000002"), idx) == []
    assert _xr(_measure({"populated_from": "phv00000002"}), idx) == [("3.5", "ERROR")]


# -- 2.7 ---------------------------------------------------------------------------------------

def test_27_every_assignment_form_reports_at_error():
    pvs = frozenset({"PRESENT", "ABSENT"})
    for slot in ({"value": "YES"},
                 {"populated_from": PHV, "value_mappings": {"1": "YES"}},
                 {"expr": "case(({phv00000001} == '1', 'YES'), (True, 'ABSENT'))"}):
        f = vmc.check_enum_membership(slot, "Condition", "condition_status", pvs, 0, "x.yaml", "")
        assert [(x.check, x.severity) for x in f] == [("2.7", "ERROR")], slot
