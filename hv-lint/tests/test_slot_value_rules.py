"""Slot-value rules new in #885 part 3, each pinned on a known case (fixtures copied from main
731984f5): 2.12 (a bare None), 2.7 (None not reported twice), 3.10 (a source type the target
slot cannot hold), 3.16 (a measured value with no unit, at any depth) and 1.13 (populated_from
beside expr). Rule 5.11 from the same part is in test_participant_ids.py.

Run: python -m pytest hv-lint/tests/test_slot_value_rules.py
"""

import sys
from pathlib import Path

import yaml

HVLINT = Path(__file__).resolve().parent.parent
for sub in ("", "phase-1", "phase-2", "phase-3"):
    sys.path.insert(0, str(HVLINT / sub) if sub else str(HVLINT))

import validate_model_conformance as vmc  # noqa: E402
import validate_semantic as vs  # noqa: E402
import validate_yaml_structure as vys  # noqa: E402

FIX = HVLINT / "tests" / "fixtures" / "known_cases"
CACHE = HVLINT / "dbgap-cache"


def case(name: str) -> dict:
    return yaml.safe_load((FIX / f"{name}.yaml").read_text(encoding="utf-8"))


# -- 2.12 bare None ------------------------------------------------------------------------------

def _212(block):
    f = vmc.validate_class_derivations(block["class_derivations"], 0, "x.yaml",
                                       vmc.ValidationContext())
    return [x for x in f if x.check == "2.12"]


def test_212_bare_none_top_level():
    f = _212(case("fhs_cig_smok_b0"))
    assert f and all(x.severity == "ERROR" for x in f)


def test_212_bare_none_nested_value_concept():
    f = _212(case("whi_fam_income_b0"))
    assert f and "Quantity" in f[0].message


def test_27_does_not_report_none_twice():
    vm = {"value_mappings": {"0": "None", "1": "PRESENT"}}
    assert vmc.check_enum_membership(vm, "Condition", "condition_status",
                                     frozenset({"PRESENT"}), 0, "x.yaml", "") == []


# -- 3.10 ----------------------------------------------------------------------------------------

def _310(name, release):
    idx = vs.load_detail_index(CACHE, release)
    return [x for x in vs.check_phv_type_compatibility(case(name), 0, "x.yaml", idx)]


def test_310_category_codes_into_a_numeric_slot():
    f = _310("whi_sleep_duration_daily_b0", "phs000200.v12")
    assert [(x.check, x.severity) for x in f] == [("3.10", "ERROR")]
    assert "category codes" in f[0].message


def test_310_age_into_a_status_slot():
    f = _310("aric_carotid_plaque_b0", "phs000280.v8")
    assert len(f) == 1 and "V1AGE01" in f[0].message and "condition_status" in f[0].message


def test_310_correct_measurement_is_quiet():
    assert _310("fhs_albumin_bld_b0", "phs000007.v35") == []


# -- 3.16 ----------------------------------------------------------------------------------------

def _quantity(unit: bool) -> dict:
    q = {"value_decimal": {"populated_from": "phv00000001"}}
    if unit:
        q["unit"] = {"value": "mg/dL"}
    mo = {"MeasurementObservation": {"slot_derivations": {
        "observation_type": {"value": "OMOP:1"},
        "value_quantity": {"class_derivations": [{"Quantity": {"slot_derivations": q}}]}}}}
    return {"class_derivations": {"MeasurementObservationSet": {"slot_derivations": {
        "observations": {"class_derivations": [mo]}}}}}


def test_316_measured_value_without_unit_at_any_depth():
    f = vs.check_quantity_missing_unit(_quantity(unit=False), 0, "x.yaml")
    assert [(x.check, x.severity) for x in f] == [("3.16", "ERROR")]
    assert vs.check_quantity_missing_unit(_quantity(unit=True), 0, "x.yaml") == []


# -- 1.13 ----------------------------------------------------------------------------------------

def test_113_populated_from_and_expr():
    block = {"class_derivations": {"Quantity": {"slot_derivations": {
        "value_decimal": {"populated_from": "phv00118957",
                          "expr": "None if str({phv00118957}) == 'M' else float({phv00118957})"}}}}}
    f = vys.check_expr_with_value_mappings(block, 0, "x.yaml")
    assert [(x.check, x.severity) for x in f] == [("1.13", "INFO")]
