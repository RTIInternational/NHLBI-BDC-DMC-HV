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
    _resolve_label,
    _write_csv,
)


def test_resolve_label_prefers_observation_type():
    # obs_type concept code wins over the var_name/stem fallback — this is what
    # fixes basophil_ct.yaml (obs_type OBA:VT0002607) -> "basophils count"
    # instead of the raw filename stem.
    obs_labels = {"OBA:VT0002607": "basophils count"}
    assert _resolve_label("OBA:VT0002607", "basophil_ct", {}, obs_labels) == "basophils count"


def test_resolve_label_falls_back_to_var_name_then_stem():
    # No obs_type match -> try var_name map -> else the stem itself.
    assert _resolve_label("OMOP:999", "ast_sgot", {"ast_sgot": "AST SGOT"}, {}) == "AST SGOT"
    assert _resolve_label(None, "weird", {}, {}) == "weird"


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
    # Single concept (both blocks share OMOP:4263457) -> one concept group.
    assert len(parsed["concepts"]) == 1
    concept = parsed["concepts"][0]
    assert concept["observation_type"] == "OMOP:4263457"
    # Two value PHVs; the four participant/visit/age PHVs are excluded.
    phv_pht = concept["phv_pht"]
    assert set(phv_pht) == {"phv00007567", "phv00172165"}
    assert phv_pht["phv00007567"] == "pht000030"
    assert phv_pht["phv00172165"] == "pht002889"


# A nested MeasurementObservationSet mimicking blood_pressure.yaml: one set
# whose `observations` hold two MeasurementObservations (systolic + diastolic),
# each with its own observation_type and value PHV, in the same PHT.
_NESTED_BP = [
    {
        "class_derivations": {
            "MeasurementObservationSet": {
                "populated_from": "pht000035",
                "slot_derivations": {
                    "associated_participant": {"expr": "uuid5(str({phv00010138}))"},
                    "observations": {
                        "object_derivations": [
                            {"class_derivations": {"MeasurementObservation": {
                                "populated_from": "pht000035",
                                "slot_derivations": {
                                    "observation_type": {"value": "OMOP:4152194"},
                                    "value_quantity": {"object_derivations": [
                                        {"class_derivations": {"Quantity": {
                                            "populated_from": "pht000035",
                                            "slot_derivations": {
                                                "value_decimal": {"populated_from": "phv00009905"},
                                            },
                                        }}}
                                    ]},
                                },
                            }}},
                            {"class_derivations": {"MeasurementObservation": {
                                "populated_from": "pht000035",
                                "slot_derivations": {
                                    "observation_type": {"value": "OMOP:4154790"},
                                    "value_quantity": {"object_derivations": [
                                        {"class_derivations": {"Quantity": {
                                            "populated_from": "pht000035",
                                            "slot_derivations": {
                                                "value_decimal": {"populated_from": "phv00009906"},
                                            },
                                        }}}
                                    ]},
                                },
                            }}},
                        ]
                    },
                },
            }
        }
    }
]


def test_nested_set_splits_into_one_concept_per_observation_type(tmp_path):
    spec = tmp_path / "blood_pressure.yaml"
    spec.write_text(yaml.safe_dump(_NESTED_BP))
    parsed = parse_spec_file(spec)
    by_type = {c["observation_type"]: c for c in parsed["concepts"]}
    # Two distinct concepts, each with its own value PHV — not one merged row.
    assert set(by_type) == {"OMOP:4152194", "OMOP:4154790"}
    assert set(by_type["OMOP:4152194"]["phv_pht"]) == {"phv00009905"}
    assert set(by_type["OMOP:4154790"]["phv_pht"]) == {"phv00009906"}
    assert by_type["OMOP:4152194"]["phv_pht"]["phv00009905"] == "pht000035"


def test_nested_set_yields_two_labeled_rows(tmp_path, monkeypatch):
    specs_dir = tmp_path / "FHS-ingest"
    specs_dir.mkdir()
    (specs_dir / "blood_pressure.yaml").write_text(yaml.safe_dump(_NESTED_BP))
    source_json = tmp_path / "src.json"
    source_json.write_text(json.dumps({"variables_by_pht": {"pht000035": {
        "bp_sys": {"n_valid": 100}, "bp_dia": {"n_valid": 90},
    }}}))
    monkeypatch.setattr(
        "transform_assessment.spec_phv_report.load_phv_name_map",
        lambda _c: {"phv00009905": "BP_SYS", "phv00009906": "BP_DIA"},
    )
    obs_labels = {"OMOP:4152194": "Systolic blood pressure",
                  "OMOP:4154790": "Diastolic blood pressure"}
    rows = build_cohort_rows(specs_dir, source_json, tmp_path / "cache", {}, obs_labels)
    # One spec file -> two labeled rows, each with its own single PHV and N.
    assert set(rows) == {"Systolic blood pressure", "Diastolic blood pressure"}
    assert rows["Systolic blood pressure"]["phv_count"] == 1
    assert rows["Systolic blood pressure"]["total_n"] == 100
    assert rows["Diastolic blood pressure"]["phv_count"] == 1
    assert rows["Diastolic blood pressure"]["total_n"] == 90


def test_dual_coded_concepts_merge_to_one_row(tmp_path, monkeypatch):
    # Same file, two blocks coded differently (OBA vs OMOP) but resolving to
    # the SAME label must not split — HDL stays one row.
    spec = [
        {"class_derivations": {"MeasurementObservation": {
            "populated_from": "pht000395",
            "slot_derivations": {
                "observation_type": {"value": "OBA:VT0000184"},
                "value_quantity": {"object_derivations": [
                    {"class_derivations": {"Quantity": {
                        "populated_from": "pht000395",
                        "slot_derivations": {"value_decimal": {"populated_from": "phv00055263"}},
                    }}}
                ]},
            },
        }}},
        {"class_derivations": {"MeasurementObservation": {
            "populated_from": "pht004801",
            "slot_derivations": {
                "observation_type": {"value": "OMOP:4041720"},
                "value_quantity": {"object_derivations": [
                    {"class_derivations": {"Quantity": {
                        "populated_from": "pht004801",
                        "slot_derivations": {"value_decimal": {"populated_from": "phv00227099"}},
                    }}}
                ]},
            },
        }}},
    ]
    specs_dir = tmp_path / "FHS-ingest"
    specs_dir.mkdir()
    (specs_dir / "hdl.yaml").write_text(yaml.safe_dump(spec))
    source_json = tmp_path / "src.json"
    source_json.write_text(json.dumps({"variables_by_pht": {
        "pht000395": {"hdl1": {"n_valid": 10}},
        "pht004801": {"hdl2": {"n_valid": 5}},
    }}))
    monkeypatch.setattr(
        "transform_assessment.spec_phv_report.load_phv_name_map",
        lambda _c: {"phv00055263": "HDL1", "phv00227099": "HDL2"},
    )
    # OBA:VT0000184 resolves to "HDL" by concept code; OMOP:4041720 does NOT
    # resolve, so it falls back to the stem "hdl" -> var_label "HDL".  Both
    # land on "HDL" and collapse into one row rather than splitting.  This is
    # the real harmonized_vars.tsv situation (stem hdl -> "HDL", OBA -> "HDL",
    # OMOP:4041720 unmapped) — the OBA-preferred / stem-fallback merge.
    obs_labels = {"OBA:VT0000184": "HDL"}
    rows = build_cohort_rows(specs_dir, source_json, tmp_path / "cache", {"hdl": "HDL"}, obs_labels)
    assert set(rows) == {"HDL"}
    assert rows["HDL"]["phv_count"] == 2
    assert rows["HDL"]["total_n"] == 15


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
    # Rows are keyed by resolved label (stem "ast_sgot" -> "AST SGOT").
    assert rows["AST SGOT"]["phv_count"] == 2
    assert rows["AST SGOT"]["total_n"] == 4754 + 3732
    assert rows["AST SGOT"]["label"] == "AST SGOT"


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


def test_layout_variable_list_fixes_rows_and_appends_unmatched(tmp_path):
    per_cohort = {"FHS": {
        "ast_sgot": {"label": "AST SGOT", "phv_count": 5, "total_n": 15584},
        "fibrin": {"label": "Fibrinogen", "phv_count": 8, "total_n": 15189},
    }}
    # Template has BMI (no data) and AST SGOT; Fibrinogen is NOT a template row,
    # so it should be appended after a blank separator + note, not dropped.
    layout = {
        "cohorts": ["FHS"], "cohort_keys": {},
        "variables": ["BMI", "AST SGOT"],
        "unmatched_note": "No template row:",
    }
    out = tmp_path / "s4.csv"
    _write_csv(out, per_cohort, {"ast_sgot": "AST SGOT", "fibrin": "Fibrinogen"}, layout)
    rows = _read_csv(out)
    labels = [r["variable"] for r in rows]
    # Template rows first, in order; then blank, note, then unmatched Fibrinogen.
    assert labels[:2] == ["BMI", "AST SGOT"]
    assert "" in labels and "No template row:" in labels
    assert labels[-1] == "Fibrinogen"
    assert rows[0]["FHS_phv"] == ""        # BMI has no data -> blank
    assert rows[1]["FHS_phv"] == "5"       # AST populated
    assert rows[-1]["FHS_phv"] == "8"      # appended Fibrinogen keeps its data


def test_totals_column_sums_across_cohorts(tmp_path):
    per_cohort = {
        "ARIC": {"ast_sgot": {"label": "AST SGOT", "phv_count": 2, "total_n": 100}},
        "FHS": {"ast_sgot": {"label": "AST SGOT", "phv_count": 5, "total_n": 15584}},
    }
    layout = {"cohorts": ["ARIC", "FHS"], "cohort_keys": {}, "variables": ["AST SGOT"]}
    out = tmp_path / "s4.csv"
    _write_csv(out, per_cohort, {}, layout)
    r = _read_csv(out)[0]
    assert r["TOTALS_phv"] == "7"          # 2 + 5
    assert r["TOTALS_n"] == "15684"        # 100 + 15584
    # A no-data row leaves TOTALS blank, not 0.
    out2 = tmp_path / "s4b.csv"
    layout2 = {**layout, "variables": ["BMI"]}
    _write_csv(out2, per_cohort, {}, layout2)
    assert _read_csv(out2)[0]["TOTALS_phv"] == ""


def test_layout_case_insensitive_and_alias_matching(tmp_path):
    # Spec labels differ from template by case ("bilirubin total") and by a
    # genuine alias ("c-reactive protein CRP" -> "CRP c-reactive protein").
    per_cohort = {"FHS": {
        "bili": {"label": "bilirubin total", "phv_count": 6, "total_n": 16578},
        "crp": {"label": "c-reactive protein CRP", "phv_count": 10, "total_n": 33787},
    }}
    layout = {
        "cohorts": ["FHS"], "cohort_keys": {},
        "variables": ["Bilirubin Total", "CRP c-reactive protein"],
        "aliases": {"CRP c-reactive protein": ["c-reactive protein CRP"]},
    }
    out = tmp_path / "s4.csv"
    _write_csv(out, per_cohort, {}, layout)
    rows = {r["variable"]: r for r in _read_csv(out)}
    # Case-insensitive match places "bilirubin total" into "Bilirubin Total".
    assert rows["Bilirubin Total"]["FHS_phv"] == "6"
    # Alias places the reworded CRP label into the template row.
    assert rows["CRP c-reactive protein"]["FHS_phv"] == "10"
    # No unmatched block (both resolved).
    assert "" not in rows
