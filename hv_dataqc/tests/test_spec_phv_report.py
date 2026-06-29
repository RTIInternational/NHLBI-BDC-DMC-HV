"""Tests for the spec-sourced Table S4 generator (transform_assessment.spec_phv_report).

Locks the two behaviours that distinguish spec-sourcing from the old
sheet-based report:

1. Only *value-slot* PHVs are counted (participant/visit/age PHVs in the
   same block are provenance, not source variables).
2. N is resolved per (PHT, column), so a column name that recurs across
   PHTs (e.g. FHS "AST") is not double-counted.
"""

from __future__ import annotations

import json

import yaml

import csv

from transform_assessment.spec_phv_report import (
    parse_spec_file,
    _col_n_valid,
    build_cohort_rows,
    _write_csv,
)


# A two-block spec mimicking ast_sgot.yaml: each block's value column lives in
# a different PHT, and the same column name ("AST") recurs across PHTs.  Each
# block also carries participant/visit/age PHVs that must NOT be counted.
_SPEC = [
    {
        "class_derivations": {
            "MeasurementObservation": {
                "populated_from": "pht000030",
                "slot_derivations": {
                    "associated_participant": {"expr": "uuid5(str({phv00000001}))"},
                    "associated_visit": {"expr": "uuid5(str({phv00000002}))"},
                    "age_at_observation": {"expr": "{phv00000003} * 365"},
                    "observation_type": {"value": "OMOP:4263457"},
                    "value_quantity": {
                        "object_derivations": [
                            {"class_derivations": {"Quantity": {
                                "populated_from": "pht000030",
                                "slot_derivations": {
                                    "value_decimal": {"populated_from": "phv00007567"},
                                },
                            }}}
                        ]
                    },
                },
            }
        }
    },
    {
        "class_derivations": {
            "MeasurementObservation": {
                "populated_from": "pht002889",
                "slot_derivations": {
                    "associated_participant": {"expr": "uuid5(str({phv00000004}))"},
                    "observation_type": {"value": "OMOP:4263457"},
                    "value_quantity": {
                        "object_derivations": [
                            {"class_derivations": {"Quantity": {
                                "populated_from": "pht002889",
                                "slot_derivations": {
                                    "value_decimal": {"populated_from": "phv00172165"},
                                },
                            }}}
                        ]
                    },
                },
            }
        }
    },
]


def _write_spec(tmp_path):
    d = tmp_path / "FHS-ingest"
    d.mkdir()
    (d / "ast_sgot.yaml").write_text(yaml.safe_dump(_SPEC))
    return d


def test_only_value_phvs_counted(tmp_path):
    spec = tmp_path / "ast_sgot.yaml"
    spec.write_text(yaml.safe_dump(_SPEC))
    parsed = parse_spec_file(spec)
    # Two value PHVs; the four participant/visit/age PHVs are excluded.
    assert set(parsed["phv_pht"]) == {"phv00007567", "phv00172165"}
    assert parsed["phv_pht"]["phv00007567"] == "pht000030"
    assert parsed["phv_pht"]["phv00172165"] == "pht002889"
    assert parsed["observation_type"] == "OMOP:4263457"


def test_n_resolved_per_pht_no_double_count():
    # Same column name "AST" in two PHTs with different n_valid.
    source_doc = {
        "variables_by_pht": {
            "pht000030": {"a40": {"n_valid": 4754}},
            "pht002889": {"ast": {"n_valid": 3732}},
            "pht004802": {"ast": {"n_valid": 2507}},  # a third "ast", unrelated
        }
    }
    name_map = {"phv00007567": "A40", "phv00172165": "AST"}
    # PHT-scoped: picks the pht002889 "AST" (3732), not the sum of all "ast".
    assert _col_n_valid(source_doc, "phv00172165", "pht002889", name_map) == 3732
    assert _col_n_valid(source_doc, "phv00007567", "pht000030", name_map) == 4754
    # No-PHT fallback would sum both "ast" columns — confirm the scoping matters.
    assert _col_n_valid(source_doc, "phv00172165", None, name_map) == 3732 + 2507


def test_build_cohort_rows_end_to_end(tmp_path, monkeypatch):
    specs_dir = _write_spec(tmp_path)
    source_json = tmp_path / "src.json"
    source_json.write_text(json.dumps({
        "variables_by_pht": {
            "pht000030": {"a40": {"n_valid": 4754}},
            "pht002889": {"ast": {"n_valid": 3732}},
        }
    }))
    # Stub the dbGaP cache PHV->column map so no real cache is needed.
    monkeypatch.setattr(
        "transform_assessment.spec_phv_report.load_phv_name_map",
        lambda _cache: {"phv00007567": "A40", "phv00172165": "AST"},
    )
    rows = build_cohort_rows(specs_dir, source_json, tmp_path / "cache", {"ast_sgot": "AST SGOT"})
    assert rows["ast_sgot"]["phv_count"] == 2
    assert rows["ast_sgot"]["total_n"] == 4754 + 3732
    assert rows["ast_sgot"]["label"] == "AST SGOT"


def _read_csv(path):
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def test_layout_fixed_cohort_columns_with_blanks(tmp_path):
    # FHS has data; the layout fixes 3 cohort columns, so ARIC/MESA stay blank
    # but present, and FHS maps from internal key "FHS".
    per_cohort = {"FHS": {"ast_sgot": {"label": "AST SGOT", "phv_count": 5, "total_n": 15584}}}
    layout = {"cohorts": ["ARIC", "FHS", "MESA"], "cohort_keys": {}, "variables": []}
    out = tmp_path / "s4.csv"
    _write_csv(out, per_cohort, {"ast_sgot": "AST SGOT"}, layout)
    rows = _read_csv(out)
    r = rows[0]
    assert r["variable"] == "AST SGOT"
    assert r["ARIC_phv"] == "" and r["ARIC_n"] == ""
    assert r["FHS_phv"] == "5" and r["FHS_n"] == "15584"
    assert r["MESA_phv"] == "" and r["MESA_n"] == ""


def test_layout_cohort_key_mapping(tmp_path):
    # Display "HCHS/SOL" maps to internal cohort key "HCHS".
    per_cohort = {"HCHS": {"crp": {"label": "CRP", "phv_count": 1, "total_n": 99}}}
    layout = {"cohorts": ["HCHS/SOL"], "cohort_keys": {"HCHS/SOL": "HCHS"}, "variables": []}
    out = tmp_path / "s4.csv"
    _write_csv(out, per_cohort, {"crp": "CRP"}, layout)
    r = _read_csv(out)[0]
    assert r["HCHS/SOL_phv"] == "1" and r["HCHS/SOL_n"] == "99"


def test_layout_variable_list_fixes_rows_and_order(tmp_path):
    per_cohort = {"FHS": {
        "ast_sgot": {"label": "AST SGOT", "phv_count": 5, "total_n": 15584},
        "fibrin": {"label": "Fibrinogen", "phv_count": 8, "total_n": 15189},
    }}
    # Canonical list includes a row with no data ("BMI") and omits Fibrinogen
    # (which should trigger the drift warning and be dropped).
    layout = {"cohorts": ["FHS"], "cohort_keys": {}, "variables": ["BMI", "AST SGOT"]}
    out = tmp_path / "s4.csv"
    _write_csv(out, per_cohort, {"ast_sgot": "AST SGOT", "fibrin": "Fibrinogen"}, layout)
    rows = _read_csv(out)
    assert [r["variable"] for r in rows] == ["BMI", "AST SGOT"]  # fixed order, Fibrinogen dropped
    assert rows[0]["FHS_phv"] == ""        # BMI has no data -> blank
    assert rows[1]["FHS_phv"] == "5"       # AST populated
