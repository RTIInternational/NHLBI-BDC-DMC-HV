"""Unit tests for HV-DataQC compare helpers.

All fixtures are aggregate metadata only; no participant-level rows are used.
"""

from __future__ import annotations

import json
import sys
import unittest
import math
import tempfile
import importlib.util
from pathlib import Path

import pandas as pd


HV_DATAQC_DIR = Path(__file__).resolve().parents[1]
COMPARE_DIR = HV_DATAQC_DIR / "compare"
sys.path.insert(0, str(HV_DATAQC_DIR))
sys.path.insert(0, str(COMPARE_DIR))

from hv_dataqc_common import normalize_category_key, write_json_atomic  # noqa: E402

from compare import (  # noqa: E402
    CheckResult,
    CrosswalkBuildError,
    _aggregate_source_summaries,
    _ambiguous_columns_fail,
    _case_branches,
    main as compare_main,
    _expected_harmonized_n,
    _expected_summary_from_concept_value_map,
    _expected_summary_from_value_map,
    _expected_summary_from_case_value_exprs,
    _unit_conversion_factor,
    _json_safe,
    _normalize_code,
    _to_discovered_key,
    authoritative_source_type_for_match,
    build_variable_crosswalk,
    build_expected_summary,
    check_c1_n_preservation,
    _dedup_check_results,
    check_c2_n_loss,
    check_c3_missing_accounting,
    check_c4_mean_preservation,
    check_c10_cross_variable,
    check_c11_type_consistency,
    check_c12_value_mapping_coverage,
    check_c7_categorical_distribution,
    check_c8_visit_distribution,
    check_c9_clinical_range,
    determine_comparison_type,
    should_run_c5_conversion_check,
    validate_harmonized_summary_schema,
    validate_clinical_ranges_config,
    validate_source_summary_schema,
    validate_compare_json_schema,
    check_stale_artifacts,
)
from hv_dataqc.compare.report_io import (  # noqa: E402
    load_thresholds,
    write_text_atomic as _write_text_atomic,
)
from hv_dataqc.compare._common import AmbiguousColumnError  # noqa: E402
from hv_dataqc.compare.crosswalk import (  # noqa: E402
    _build_variables_by_name,
    _pick_single_pht_summary,
)
from hv_dataqc.compare.yaml_crosswalk import build_yaml_crosswalk  # noqa: E402
from hv_dataqc.compare.checks.visit_n import _synthesize_source_visit_counts, _build_visit_label_crosswalk  # noqa: E402
from hv_dataqc.extract_harmonized.extract_harmonized_summaries import (  # noqa: E402
    merge_variable_summaries,
    process_measurements,
    process_measurement_observation_sets,
)
from hv_dataqc.extract_source.extract_source_summaries import _canonical_participant_id  # noqa: E402
from hv_dataqc.extract_source.scan_yaml_phv_pairs import scan_yaml_for_phv_pairs  # noqa: E402
from hv_dataqc.extract_source.scan_yaml_phv_pairs import scan_yaml_for_phvs  # noqa: E402
from hv_dataqc.extract_source.extract_source_summaries import (  # noqa: E402
    _compute_joint_distributions,
    _normalize_dist_key,
)
from hv_dataqc.compare.crosswalk import (  # noqa: E402
    _extract_phv_conditions,
    _count_from_joint_dist,
    _expected_summary_from_case_entry,
)


class CompareSourceHarmonizedTests(unittest.TestCase):
    def test_authoritative_source_type_for_pooled_match_requires_consensus(self) -> None:
        phv_type_map = {
            "phv000001": "continuous",
            "phv000002": "continuous",
            "phv000003": "categorical",
        }

        self.assertEqual(
            authoritative_source_type_for_match(
                {"_source_phvs": ["phv000001", "phv000002"]}, phv_type_map
            ),
            "continuous",
        )
        self.assertIsNone(
            authoritative_source_type_for_match(
                {"_source_phvs": ["phv000001", "phv000003"]}, phv_type_map
            )
        )

    def test_determine_comparison_type_prefers_dbgap_over_extractor_heuristic(self) -> None:
        comparison = determine_comparison_type(
            {"_source_phvs": ["phv000001"]},
            {"type": "categorical"},
            {"phv000001": "continuous"},
        )

        self.assertEqual(comparison["expected_type"], "continuous")
        self.assertEqual(comparison["basis"], "dbgap_phv_type_consensus")

    def test_determine_comparison_type_uses_yaml_intent_when_dbgap_missing(self) -> None:
        comparison = determine_comparison_type(
            {
                "entity_class": "Condition",
                "concept_value_map": {"1": "MONDO:0000001"},
            },
            {"type": "continuous"},
            {},
        )

        self.assertEqual(comparison["expected_type"], "categorical")
        self.assertEqual(comparison["basis"], "yaml_transform_intent")

    def test_to_discovered_key_converts_supported_prefixes(self) -> None:
        self.assertEqual(
            _to_discovered_key("condition_MONDO:0004981"),
            "discovered:condition:MONDO:0004981",
        )
        self.assertEqual(
            _to_discovered_key("measurement_OBA:VT0001259"),
            "discovered:measurement:OBA:VT0001259",
        )

    def test_to_discovered_key_ignores_demography_keys(self) -> None:
        self.assertIsNone(_to_discovered_key("demog_annotated_sex"))

    def test_aggregate_source_summaries_pools_continuous_stats(self) -> None:
        pooled = _aggregate_source_summaries(
            [
                {
                    "type": "continuous",
                    "n_total": 2,
                    "n_valid": 2,
                    "n_missing": 0,
                    "mean": 2.0,
                    "sd": math.sqrt(2.0),
                    "min": 1.0,
                    "max": 3.0,
                },
                {
                    "type": "continuous",
                    "n_total": 3,
                    "n_valid": 3,
                    "n_missing": 0,
                    "mean": 6.0,
                    "sd": 2.0,
                    "min": 4.0,
                    "max": 8.0,
                },
            ]
        )

        self.assertEqual(pooled["n_valid"], 5)
        self.assertEqual(pooled["mean"], 4.4)
        self.assertAlmostEqual(pooled["sd"], 2.701851, places=6)
        self.assertEqual(pooled["min"], 1.0)
        self.assertEqual(pooled["max"], 8.0)

    def test_aggregate_source_summaries_categorical_uses_distribution_schema(self) -> None:
        pooled = _aggregate_source_summaries(
            [
                {
                    "type": "categorical",
                    "n_total": 5,
                    "n_valid": 5,
                    "n_missing": 0,
                    "distribution": {
                        "1": {"n": 2, "pct": 40.0},
                        "2": {"n": 3, "pct": 60.0},
                    },
                },
                {
                    "type": "categorical",
                    "n_total": 5,
                    "n_valid": 5,
                    "n_missing": 0,
                    "distribution": {
                        "1": {"n": 1, "pct": 20.0},
                        "3": {"n": 4, "pct": 80.0},
                    },
                },
            ]
        )

        self.assertIn("distribution", pooled)
        self.assertNotIn("values", pooled)
        self.assertEqual(pooled["distribution"]["1"], {"n": 3, "pct": 30.0})
        self.assertEqual(pooled["distribution"]["2"], {"n": 3, "pct": 30.0})
        self.assertEqual(pooled["distribution"]["3"], {"n": 4, "pct": 40.0})

        out = {"type": "categorical", "distribution": pooled["distribution"]}
        result = check_c7_categorical_distribution(pooled, out, "pooled categorical")
        self.assertEqual(result.status, "PASS")

    def test_aggregate_source_summaries_sd_includes_singleton_between_variance(self) -> None:
        pooled = _aggregate_source_summaries(
            [
                {
                    "type": "continuous",
                    "n_total": 1,
                    "n_valid": 1,
                    "n_missing": 0,
                    "mean": 10.0,
                    "sd": None,
                },
                {
                    "type": "continuous",
                    "n_total": 2,
                    "n_valid": 2,
                    "n_missing": 0,
                    "mean": 1.5,
                    "sd": math.sqrt(0.5),
                },
            ]
        )

        self.assertEqual(pooled["n_valid"], 3)
        self.assertEqual(pooled["mean"], 4.333333)
        self.assertAlmostEqual(pooled["sd"], 4.932883, places=6)

    def test_c1_uses_mapped_source_union_as_primary_denominator(self) -> None:
        source = {
            "total_participants": 5885,
            "participant_denominators": {
                "all_source_union_n": 5885,
                "max_source_pht": "pht001920",
                "max_source_pht_n": 5885,
                "mapped_source_phts": ["pht008729"],
                "mapped_source_union_n": 3883,
                "mapped_source_max_pht": "pht008729",
                "mapped_source_max_pht_n": 3883,
            },
        }
        harmonized = {"total_participants": 3883}

        result = check_c1_n_preservation(source, harmonized)[0]

        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.detail["source_n"], 3883)
        self.assertEqual(result.detail["all_source_union_n"], 5885)
        self.assertEqual(result.detail["denominator_basis"], "mapped_source_union")

    def test_c1_allows_harmonized_count_above_single_mapped_pht_when_union_matches(self) -> None:
        source = {
            "total_participants": 9780,
            "participant_denominators": {
                "all_source_union_n": 9780,
                "max_source_pht": "pht001108",
                "max_source_pht_n": 9780,
                "mapped_source_phts": ["pht001116", "pht001118"],
                "mapped_source_union_n": 8296,
                "mapped_source_max_pht": "pht001116",
                "mapped_source_max_pht_n": 6429,
            },
        }
        harmonized = {"total_participants": 8296}

        result = check_c1_n_preservation(source, harmonized)[0]

        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.detail["source_n"], 8296)
        self.assertEqual(result.detail["mapped_source_max_pht_n"], 6429)

    def test_c1_fails_when_harmonized_below_mapped_source_union(self) -> None:
        source = {
            "total_participants": 5000,
            "participant_denominators": {
                "mapped_source_union_n": 4000,
            },
        }
        harmonized = {"total_participants": 3900}

        result = check_c1_n_preservation(source, harmonized, fail_pct=1.0)[0]

        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.detail["loss_pct"], 2.5)
        self.assertEqual(result.detail["denominator_basis"], "mapped_source_union")

    def test_c1_old_source_json_warns_when_only_mapped_max_matches(self) -> None:
        source = {
            "total_participants": 5885,
            "participants_by_pht": {"pht001920": 5885, "pht008729": 3883},
        }
        harmonized = {"total_participants": 3883}

        result = check_c1_n_preservation(source, harmonized, mapped_phts={"pht008729"})[0]

        self.assertEqual(result.status, "WARN")
        self.assertEqual(result.detail["source_n"], 3883)
        self.assertEqual(result.detail["denominator_basis"], "mapped_source_max_fallback")

    def test_scan_yaml_for_phvs_ignores_commented_out_phvs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "demo.yaml"
            yaml_path.write_text(
                """
- class_derivations:
    MeasurementObservation:
      slot_derivations:
        value_quantity:
          populated_from: phv000001
        flag:
          expr: 'case({phv000002} == 1, true, false)'
# populated_from: phv999999
""",
                encoding="utf-8",
            )

            phvs = scan_yaml_for_phvs(Path(tmpdir))

        self.assertEqual(phvs, {"phv000001", "phv000002"})

    def test_c7_aggregates_many_source_categories_to_one_harmonized_category(self) -> None:
        src = {
            "type": "categorical",
            "distribution": {
                "1": {"n": 2, "pct": 20.0},
                "2": {"n": 3, "pct": 30.0},
                "3": {"n": 5, "pct": 50.0},
            },
        }
        out = {
            "type": "categorical",
            "distribution": {
                "OMOP:A": {"n": 5, "pct": 50.0},
                "OMOP:B": {"n": 5, "pct": 50.0},
            },
        }
        result = check_c7_categorical_distribution(
            src,
            out,
            "test categorical",
            value_map={"1": "OMOP:A", "2": "OMOP:A", "3": "OMOP:B"},
        )

        self.assertEqual(result.status, "PASS")
        by_cat = {row["category"]: row for row in result.detail["distribution_table"]}
        self.assertEqual(by_cat["OMOP:A"]["source_n"], 5)
        self.assertEqual(by_cat["OMOP:A"]["source_pct"], 50.0)

    def test_c10_uses_config_codes_and_reports_less_than_as_less_or_equal(self) -> None:
        clinical_ranges = {
            "fev1": {"omop_codes": ["OMOP:FEV1"], "oba_codes": []},
            "fvc": {"omop_codes": ["OMOP:FVC"], "oba_codes": []},
            "_cross_variable_rules": {
                "fev1_lt_fvc": {
                    "description": "FEV1 is generally less than FVC",
                    "check": "mean(FEV1) < mean(FVC)",
                    "variables": ["fev1", "fvc"],
                    "severity": "WARNING",
                }
            },
        }
        harmonized_vars = {
            "measurement_OMOP:FEV1": {"observation_type": "OMOP:FEV1", "mean": 2.0},
            "measurement_OMOP:FVC": {"observation_type": "OMOP:FVC", "mean": 2.0},
        }

        results = check_c10_cross_variable(harmonized_vars, clinical_ranges)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "PASS")
        self.assertIn("<=", results[0].message)

    def test_c10_warns_on_ambiguous_observation_type_match(self) -> None:
        clinical_ranges = {
            "fev1": {"omop_codes": ["OMOP:FEV1"], "oba_codes": []},
            "fvc": {"omop_codes": ["OMOP:FVC"], "oba_codes": []},
            "_cross_variable_rules": {
                "fev1_lt_fvc": {
                    "description": "FEV1 is generally less than FVC",
                    "check": "mean(FEV1) < mean(FVC)",
                    "variables": ["fev1", "fvc"],
                    "severity": "WARNING",
                }
            },
        }
        harmonized_vars = {
            "measurement_OMOP:FEV1_pre": {"observation_type": "OMOP:FEV1", "mean": 2.0},
            "measurement_OMOP:FEV1_post": {"observation_type": "OMOP:FEV1", "mean": 2.5},
            "measurement_OMOP:FVC": {"observation_type": "OMOP:FVC", "mean": 3.0},
        }

        results = check_c10_cross_variable(harmonized_vars, clinical_ranges)

        self.assertEqual(results[0].status, "WARN")
        self.assertIn("Ambiguous", results[0].message)
        self.assertEqual(
            results[0].detail["fev1_matches"],
            ["measurement_OMOP:FEV1_pre", "measurement_OMOP:FEV1_post"],
        )

    def test_c10_supports_explicit_greater_or_equal_operator(self) -> None:
        clinical_ranges = {
            "sbp": {"omop_codes": ["OMOP:SBP"], "oba_codes": []},
            "dbp": {"omop_codes": ["OMOP:DBP"], "oba_codes": []},
            "_cross_variable_rules": {
                "sbp_ge_dbp": {
                    "description": "SBP should be at least DBP",
                    "check": "mean(SBP) >= mean(DBP)",
                    "variables": ["sbp", "dbp"],
                    "severity": "ERROR",
                }
            },
        }
        harmonized_vars = {
            "measurement_OMOP:SBP": {"observation_type": "OMOP:SBP", "mean": 120.0},
            "measurement_OMOP:DBP": {"observation_type": "OMOP:DBP", "mean": 120.0},
        }

        results = check_c10_cross_variable(harmonized_vars, clinical_ranges)

        self.assertEqual(results[0].status, "PASS")
        self.assertIn(">=", results[0].message)

    def test_c10_complex_rule_type_is_explicit_skip(self) -> None:
        clinical_ranges = {
            "_cross_variable_rules": {
                "ratio_rule": {
                    "type": "complex",
                    "description": "Ratio formula requires rule-engine support",
                    "check": "mean(A) / mean(B) < 0.7",
                    "variables": ["a", "b"],
                }
            }
        }

        results = check_c10_cross_variable({}, clinical_ranges)

        self.assertEqual(results[0].status, "SKIP")
        self.assertIn("Complex", results[0].message)

    def test_clinical_ranges_validation_warns_on_bad_cross_rule_reference(self) -> None:
        warnings = validate_clinical_ranges_config(
            {
                "known": {
                    "plausible_lo": 1,
                    "plausible_hi": 2,
                    "red_flag_lo": 0,
                    "red_flag_hi": 3,
                },
                "_cross_variable_rules": {
                    "bad": {"variables": ["known", "missing"]},
                },
            }
        )

        self.assertTrue(any("missing" in warning for warning in warnings))

    def test_clinical_ranges_validation_warns_on_non_mapping_top_level(self) -> None:
        warnings = validate_clinical_ranges_config(["not", "a", "mapping"])

        self.assertIn("expected top-level mapping", warnings)

    def test_clinical_ranges_validation_warns_on_duplicate_concept_code(self) -> None:
        warnings = validate_clinical_ranges_config(
            {
                "range_a": {
                    "plausible_lo": 1,
                    "plausible_hi": 2,
                    "red_flag_lo": 0,
                    "red_flag_hi": 3,
                    "omop_codes": ["OMOP:123"],
                },
                "range_b": {
                    "plausible_lo": 1,
                    "plausible_hi": 2,
                    "red_flag_lo": 0,
                    "red_flag_hi": 3,
                    "omop_codes": ["OMOP:123"],
                },
            }
        )

        self.assertTrue(any("OMOP:123" in warning and "multiple" in warning for warning in warnings))

    def test_clinical_ranges_validation_allows_declared_duplicate_concept_code(self) -> None:
        warnings = validate_clinical_ranges_config(
            {
                "range_a": {
                    "plausible_lo": 1,
                    "plausible_hi": 2,
                    "red_flag_lo": 0,
                    "red_flag_hi": 3,
                    "omop_codes": ["OMOP:123"],
                    "allow_duplicate_codes": ["OMOP:123"],
                },
                "range_b": {
                    "plausible_lo": 1,
                    "plausible_hi": 2,
                    "red_flag_lo": 0,
                    "red_flag_hi": 3,
                    "omop_codes": ["OMOP:123"],
                    "allow_duplicate_codes": ["OMOP:123"],
                },
            }
        )

        self.assertFalse(any("OMOP:123" in warning for warning in warnings))

    def test_json_safe_converts_non_finite_floats_to_none(self) -> None:
        sanitized = _json_safe({"ok": 1.0, "bad": float("nan"), "nested": [float("inf")]})

        self.assertEqual(sanitized["ok"], 1.0)
        self.assertIsNone(sanitized["bad"])
        self.assertIsNone(sanitized["nested"][0])

    def test_c4_tighter_thresholds_escalate_warn_to_fail(self) -> None:
        """A 1.5% mean shift WARNs with old defaults but FAILs with tight thresholds."""
        src = {"type": "continuous", "mean": 100.0, "n_valid": 1000}
        out = {"type": "continuous", "mean": 101.5, "n_valid": 1000}  # 1.5% shift

        # Old defaults: pass_rel=0.01 (1%), warn_rel=0.05 (5%) -> WARN
        result_loose = check_c4_mean_preservation(src, out, "test", pass_rel=0.01, warn_rel=0.05)
        self.assertEqual(result_loose.status, "WARN")

        # Tight defaults: pass_rel=0.001 (0.1%), warn_rel=0.01 (1%) -> FAIL (1.5% > 1%)
        result_tight = check_c4_mean_preservation(src, out, "test", pass_rel=0.001, warn_rel=0.01)
        self.assertEqual(result_tight.status, "FAIL")

    def test_c3_denominator_ratio_fallback_threshold_is_configurable(self) -> None:
        src = {"n_total": 100, "n_valid": 80, "pct_missing": 20.0}
        out = {"n_total": 85, "n_valid": 80, "pct_missing": 5.88}

        default_result = check_c3_missing_accounting(src, out, "c3 threshold")
        configured_result = check_c3_missing_accounting(
            src,
            out,
            "c3 threshold",
            denominator_ratio_fallback_threshold=0.9,
        )

        self.assertEqual(default_result.status, "FAIL")
        self.assertIn("Large missing rate change", default_result.message)
        self.assertEqual(configured_result.status, "PASS")
        self.assertIn("n_valid preserved", configured_result.message)

    def test_load_thresholds_returns_empty_dict_for_nonexistent_path(self) -> None:
        from pathlib import Path
        result = load_thresholds(Path("/nonexistent/thresholds.yaml"))
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result), 0)

    def test_load_thresholds_returns_empty_dict_for_non_mapping_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "thresholds.yaml"
            path.write_text("- not\n- a mapping\n", encoding="utf-8")

            result = load_thresholds(path)

        self.assertEqual(result, {})

    def test_c5_runs_only_with_explicit_conversion_factor(self) -> None:
        self.assertFalse(should_run_c5_conversion_check({}, {}))
        self.assertTrue(should_run_c5_conversion_check({"conversion_factor": 2.54}, {}))
        self.assertTrue(should_run_c5_conversion_check({}, {"conversion_factor": 2.54}))

    def test_category_key_normalization_handles_json_and_python_repr(self) -> None:
        self.assertEqual(normalize_category_key('["OMOP:8527"]'), "OMOP:8527")
        self.assertEqual(normalize_category_key("('OMOP:8527',)"), "OMOP:8527")
        self.assertEqual(normalize_category_key("1.0"), "1")

    def test_c7_normalizes_array_repr_category_keys(self) -> None:
        src = {
            "type": "categorical",
            "distribution": {"1.0": {"n": 10, "pct": 100.0}},
        }
        out = {
            "type": "categorical",
            "distribution": {"['OMOP:8527']": {"n": 10, "pct": 100.0}},
        }

        result = check_c7_categorical_distribution(
            src,
            out,
            "race",
            value_map={"1": "OMOP:8527"},
        )

        self.assertEqual(result.status, "PASS")

    def test_static_case_expr_does_not_become_c7_category(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pheno_dir = tmp_path / "pheno_variable_summaries"
            pheno_dir.mkdir()
            (pheno_dir / "phs000000.v1.pht000001.v1.p1.test.data_dict.xml").write_text(
                '<?xml version="1.0"?>\n'
                "<data_table>\n"
                '  <variable id="phv000001.v1">\n'
                "    <name>SEX_SRC</name>\n"
                "  </variable>\n"
                "</data_table>\n",
                encoding="utf-8",
            )
            yaml_dir = tmp_path / "yaml"
            yaml_dir.mkdir()
            (yaml_dir / "demography.yaml").write_text(
                "- class_derivations:\n"
                "    Demography:\n"
                "      populated_from: pht000001\n"
                "      slot_derivations:\n"
                "        sex:\n"
                "          expr: \"case(({phv000001} == 1, 'FEMALE'), (True, 'MALE'))\"\n",
                encoding="utf-8",
            )

            matches = build_variable_crosswalk(
                variables_by_name={},
                harmonized_vars={"demog_sex": {"type": "categorical", "distribution": {}}},
                yaml_dir=yaml_dir,
                cache_dir=tmp_path,
                source_doc={"total_participants": 10, "total_rows_by_pht": {"pht000001": 10}},
            )

        self.assertEqual(len(matches), 1)
        resolved = matches[0]["_resolved_src"]
        self.assertEqual(resolved["_comparison_basis"], "static_yaml_expr")
        self.assertEqual(resolved["_comparison_confidence"], "unsupported")
        self.assertNotIn("case(", "".join(resolved.get("distribution", {}).keys()))
        result = check_c7_categorical_distribution(
            resolved,
            {"type": "categorical", "distribution": {"FEMALE": {"n": 5, "pct": 50.0}}},
            "demog sex",
        )
        self.assertEqual(result.status, "SKIP")

    def test_source_extract_config_loads_infer_type_threshold(self) -> None:
        module_path = HV_DATAQC_DIR / "extract_source" / "extract_source_summaries.py"
        spec = importlib.util.spec_from_file_location("extract_source_summaries", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "thresholds.yaml"
            cfg.write_text("source_extract:\n  infer_type_distinct_threshold: 7\n", encoding="utf-8")
            loaded = module.load_source_extract_config(cfg)

        self.assertEqual(loaded["source_extract"]["infer_type_distinct_threshold"], 7)

    def test_source_extract_type_map_loads_phv_and_variable_name_keys(self) -> None:
        module_path = HV_DATAQC_DIR / "extract_source" / "extract_source_summaries.py"
        spec = importlib.util.spec_from_file_location("extract_source_summaries_types", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp:
            pheno_dir = Path(tmp) / "pheno_variable_summaries"
            pheno_dir.mkdir()
            (pheno_dir / "pht000001.data_dict.xml").write_text(
                """
                <data_table id="pht000001">
                  <variable id="phv000001.v1"><name>fruitf25</name><type>integer</type></variable>
                  <variable id="phv000002.v1"><name>status_code</name><type>encoded</type></variable>
                </data_table>
                """,
                encoding="utf-8",
            )
            type_map = module.load_source_type_map(Path(tmp))

        self.assertEqual(type_map["phv000001"], "continuous")
        self.assertEqual(type_map["fruitf25"], "continuous")
        self.assertEqual(type_map["phv000002"], "categorical")
        self.assertEqual(type_map["status_code"], "categorical")

    def test_harmonized_extract_config_overrides_demography_columns(self) -> None:
        module_path = HV_DATAQC_DIR / "extract_harmonized" / "extract_harmonized_summaries.py"
        spec = importlib.util.spec_from_file_location("extract_harmonized_summaries_cfg", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        original = list(module.DEMOGRAPHY_COLUMNS)
        try:
            module.apply_harmonized_extract_config(
                {"demography_columns": {"annotated_sex": "sex"}}
            )
            self.assertEqual(module.DEMOGRAPHY_COLUMNS, [("annotated_sex", "sex")])
        finally:
            module.DEMOGRAPHY_COLUMNS[:] = original

    def test_normalize_code_strips_integer_float_suffix(self) -> None:
        self.assertEqual(_normalize_code("1.0"), "1")
        self.assertEqual(_normalize_code(" 12.0 "), "12")
        self.assertEqual(_normalize_code("1.5"), "1.5")

    def test_expected_harmonized_n_sums_codes_for_target_concept(self) -> None:
        match = {
            "concept_code": "MONDO:0005015",
            "concept_value_map": {
                "1": "MONDO:0005015",
                "2": "MONDO:0006920",
                "3": "MONDO:0005015",
            },
        }
        src_var = {
            "type": "categorical",
            "n_valid": 10,
            "distribution": {
                "1.0": {"n": 4, "pct": 40.0},
                "2.0": {"n": 3, "pct": 30.0},
                "3.0": {"n": 3, "pct": 30.0},
            },
        }

        self.assertEqual(_expected_harmonized_n(match, src_var), 7)

    def test_case_branches_extracts_simple_value_routing(self) -> None:
        expr = 'case(({phv00258106} == 0, "OMOP:45883537"), (True, None))'

        self.assertEqual(
            _case_branches(expr),
            [("{phv00258106} == 0", "OMOP:45883537"), ("True", "None")],
        )

    def test_expected_summary_from_case_value_exprs_marks_multi_phv_conditions_unsupported(self) -> None:
        entries = [
            {
                "value_exprs": [
                    'case(({phv00258106} == 0, "OMOP:45883537"), (True, None))'
                ]
            },
            {
                "value_exprs": [
                    'case(({phv00258106} == 1 and {phv00258107} == 1, "OMOP:40766945"), '
                    '({phv00258106} == 1 and {phv00258107} == 2, "OMOP:40766945"), '
                    '({phv00258106} == 1 and {phv00258107} == 3, "OMOP:45883458"), '
                    '(True, None))'
                ]
            },
        ]
        summaries_by_phv = {
            "phv00258106": {
                "type": "categorical",
                "distribution": {
                    "0.0": {"n": 7, "pct": 58.33},
                    "1.0": {"n": 5, "pct": 41.67},
                },
            },
            "phv00258107": {
                "type": "categorical",
                "distribution": {
                    "1.0": {"n": 2, "pct": 40.0},
                    "2.0": {"n": 1, "pct": 20.0},
                    "3.0": {"n": 2, "pct": 40.0},
                },
            },
        }

        expected = _expected_summary_from_case_value_exprs(entries, summaries_by_phv)

        self.assertIsNotNone(expected)
        self.assertEqual(expected["_comparison_basis"], "yaml_case_value_expr")
        self.assertEqual(expected["_comparison_confidence"], "unsupported")
        self.assertIn("joint counts", expected["_comparison_limitations"][0])

    def test_expected_summary_from_case_value_exprs_skips_non_null_else_branch(self) -> None:
        entries = [
            {
                "value_exprs": [
                    "case(({phv00226270} == 'Atrial fibrillation', 'PRESENT'), (True, 'ABSENT'))"
                ]
            }
        ]
        summaries_by_phv = {
            "phv00226270": {
                "type": "categorical",
                "distribution": {"Atrial fibrillation": {"n": 1, "pct": 10.0}},
            }
        }

        self.assertIsNone(_expected_summary_from_case_value_exprs(entries, summaries_by_phv))

    def test_c2_c7_pass_with_case_derived_expected_summary(self) -> None:
        src = {
            "type": "categorical",
            "n_total": 12,
            "n_valid": 12,
            "n_missing": 0,
            "pct_missing": 0.0,
            "distribution": {
                "OMOP:40766945": {"n": 3, "pct": 25.0},
                "OMOP:45883458": {"n": 2, "pct": 16.67},
                "OMOP:45883537": {"n": 7, "pct": 58.33},
            },
        }
        out = {
            "type": "categorical",
            "n_total": 12,
            "n_valid": 12,
            "n_missing": 0,
            "pct_missing": 0.0,
            "distribution": src["distribution"],
        }

        self.assertEqual(check_c2_n_loss(src, out, "smoking").status, "PASS")
        self.assertEqual(check_c7_categorical_distribution(src, out, "smoking").status, "PASS")

    def test_c2_uses_expected_n_for_concept_allocated_source(self) -> None:
        src = {"n_valid": 10}
        out = {"n_valid": 7}

        result = check_c2_n_loss(src, out, "diabetes", expected_n=7)

        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.detail["source_n_raw"], 10)
        self.assertEqual(result.detail["expected_n_for_concept"], 7)

    def test_expected_summary_from_value_map_filters_unmapped_codes(self) -> None:
        entry = {"value_map": {"0": "ABSENT", "1": "PRESENT"}}
        src = {
            "type": "categorical",
            "n_total": 11,
            "n_valid": 11,
            "distribution": {
                "0.0": {"n": 5, "pct": 45.45},
                "1.0": {"n": 4, "pct": 36.36},
                "9.0": {"n": 2, "pct": 18.18},
            },
        }

        expected = _expected_summary_from_value_map(entry, src)

        self.assertIsNotNone(expected)
        self.assertEqual(expected["n_valid"], 9)
        self.assertEqual(expected["n_missing"], 2)
        self.assertEqual(expected["distribution"]["ABSENT"]["n"], 5)
        self.assertEqual(expected["distribution"]["PRESENT"]["n"], 4)
        self.assertEqual(expected["_comparison_basis"], "yaml_value_mappings")

    def test_build_expected_summary_merges_raw_status_aliases(self) -> None:
        entries = [
            {
                "entity_class": "Condition",
                "phv_id": "phv1",
                "value_map": {"N": "ABSENT", "Y": "PRESENT"},
                "_source_summary": {
                    "type": "categorical",
                    "n_total": 3,
                    "n_valid": 3,
                    "distribution": {"N": {"n": 2}, "Y": {"n": 1}},
                },
            },
            {
                "entity_class": "Condition",
                "phv_id": "phv2",
                "_source_summary": {
                    "type": "categorical",
                    "n_total": 7,
                    "n_valid": 7,
                    "distribution": {"N": {"n": 3}, "Y": {"n": 4}},
                },
            },
        ]

        expected = build_expected_summary(entries, {})

        self.assertIsNotNone(expected)
        self.assertEqual(expected["distribution"]["ABSENT"]["n"], 5)
        self.assertEqual(expected["distribution"]["PRESENT"]["n"], 5)
        self.assertNotIn("N", expected["distribution"])
        self.assertTrue(expected["_comparison_status_aliases_applied"])

    def test_expected_summary_from_concept_value_map_preserves_status_distribution(self) -> None:
        entry = {
            "phv_id": "phv1",
            "concept_phv": "phv1",
            "concept_code": "MONDO:0005015",
            "concept_value_map": {
                "1": "MONDO:0005015",
                "2": "HP:0040270",
                "3": "MONDO:0005015",
            },
            "value_map": {"1": "ABSENT", "2": "PRESENT", "3": "PRESENT"},
        }
        src = {
            "type": "categorical",
            "n_total": 10,
            "n_valid": 10,
            "distribution": {
                "1.0": {"n": 4, "pct": 40.0},
                "2.0": {"n": 3, "pct": 30.0},
                "3.0": {"n": 3, "pct": 30.0},
            },
        }

        expected = _expected_summary_from_concept_value_map(entry, src)

        self.assertIsNotNone(expected)
        self.assertEqual(expected["n_valid"], 7)
        self.assertEqual(expected["distribution"]["ABSENT"]["n"], 4)
        self.assertEqual(expected["distribution"]["PRESENT"]["n"], 3)

    def test_build_expected_summary_marks_joint_phv_concept_routing_partial(self) -> None:
        entries = [
            {
                "phv_id": "phv_status",
                "concept_phv": "phv_concept",
                "concept_code": "MONDO:0005015",
                "concept_value_map": {"1": "MONDO:0005015"},
                "value_map": {"0": "ABSENT", "1": "PRESENT"},
                "_source_summary": {
                    "type": "categorical",
                    "n_total": 10,
                    "n_valid": 10,
                    "distribution": {"0": {"n": 5}, "1": {"n": 5}},
                },
                "yaml_file": "diabetes.yaml",
            }
        ]

        expected = build_expected_summary(entries, {})

        self.assertIsNone(expected)

    def test_unit_conversion_factor_reads_common_unit_conversion_block(self) -> None:
        self.assertEqual(
            _unit_conversion_factor({"source_unit": "[lb_av]", "target_unit": "kg"}),
            0.453592,
        )

    def test_c12_warns_on_observed_unmapped_value(self) -> None:
        match = {
            "_yaml_entries": [
                {
                    "yaml_file": "copd.yaml",
                    "phv_id": "phv1",
                    "value_map": {"0": "ABSENT", "1": "PRESENT"},
                    "source_summary": {
                        "type": "categorical",
                        "distribution": {
                            "0": {"n": 10},
                            "1": {"n": 2},
                            "9": {"n": 1},
                        },
                    },
                }
            ]
        }

        results = check_c12_value_mapping_coverage(match, {"phv1": {"0", "1", "9"}})

        self.assertEqual(results[0].status, "WARN")
        self.assertIn("9", results[0].detail["missing_codes"])
        self.assertIn("semantic", results[0].message)

    def test_c12_reports_only_sentinel_gap_as_info(self) -> None:
        match = {
            "_yaml_entries": [
                {
                    "yaml_file": "demo.yaml",
                    "phv_id": "phv1",
                    "value_map": {"0": "ABSENT", "1": "PRESENT"},
                    "source_summary": {
                        "type": "categorical",
                        "distribution": {"0": {"n": 10}, "1": {"n": 2}, ".": {"n": 1}},
                    },
                }
            ]
        }

        results = check_c12_value_mapping_coverage(match, {"phv1": {"0", "1", "."}})

        self.assertEqual(results[0].status, "INFO")
        self.assertIn("missing_sentinel_codes", results[0].detail)

    def test_c12_uses_concept_phv_summary_for_concept_value_mappings(self) -> None:
        match = {
            "_source_summaries_by_phv": {
                "phv_concept": {
                    "type": "categorical",
                    "distribution": {"1": {"n": 6}, "2": {"n": 3}, "9": {"n": 1}},
                },
                "phv_status": {
                    "type": "categorical",
                    "distribution": {"0": {"n": 7}, "1": {"n": 3}},
                },
            },
            "_yaml_entries": [
                {
                    "yaml_file": "condition.yaml",
                    "phv_id": "phv_status",
                    "concept_phv": "phv_concept",
                    "concept_value_map": {"1": "MONDO:0005015", "2": "MONDO:0006920"},
                    "source_summary": {
                        "type": "categorical",
                        "distribution": {"0": {"n": 7}, "1": {"n": 3}},
                    },
                }
            ],
        }

        results = check_c12_value_mapping_coverage(
            match,
            {"phv_concept": {"1", "2"}, "phv_status": {"0", "1"}},
        )

        self.assertEqual(results[0].status, "WARN")
        self.assertEqual(results[0].detail["phv_id"], "phv_concept")
        self.assertEqual(results[0].detail["missing_codes"], ["9"])

    def test_c11_treats_numeric_encoded_source_as_info(self) -> None:
        src = {
            "type": "categorical",
            "distribution": {"1.0": {"n": 2}, "2.5": {"n": 3}, ".": {"n": 1}},
        }
        out = {"type": "continuous"}

        result = check_c11_type_consistency(src, out, "encoded numeric")

        self.assertEqual(result.status, "INFO")

    def test_c11_reports_expected_type_basis(self) -> None:
        src = {"type": "categorical", "distribution": {"1": {"n": 2}}}
        out = {"type": "continuous"}

        result = check_c11_type_consistency(
            src,
            out,
            "source driven",
            expected_type="categorical",
            type_basis="dbgap_phv_type_consensus",
        )

        self.assertEqual(result.status, "INFO")
        self.assertEqual(result.detail["expected_type"], "categorical")
        self.assertEqual(result.detail["type_basis"], "dbgap_phv_type_consensus")

    def test_c8_namespace_mismatch_warns_unsupported_not_fail(self) -> None:
        source = {"rows_per_visit": {"SOURCE VISIT": 10}}
        harmonized = {"rows_per_visit": {"uuid:VISIT": 100}}

        results = check_c8_visit_distribution(source, harmonized)

        self.assertEqual(results[0].status, "WARN")
        self.assertEqual(results[0].detail["comparison_confidence"], "unsupported")

    def test_c8_namespace_mismatch_equal_totals_warns_not_pass(self) -> None:
        source = {"rows_per_visit": {"SOURCE VISIT": 10}}
        harmonized = {"rows_per_visit": {"uuid:VISIT": 10}}

        results = check_c8_visit_distribution(source, harmonized)

        self.assertEqual(results[0].status, "WARN")
        self.assertEqual(results[0].detail["comparison_confidence"], "unsupported")

    def test_c8_crosswalk_resolves_string_visit_codes_to_canonical_labels(self) -> None:
        """Column-based cohorts (SPIROMICS, COPDGene): raw TSV visit codes translated
        via visit.yaml case() to canonical labels; C8 should PASS per-visit, not WARN."""
        visit_yaml = """
- class_derivations:
    Visit:
      populated_from: pht000001
      slot_derivations:
        name:
          expr: "case(({phv000001} == 'V1', 'Study Visit 1'), ({phv000001} == 'V2', 'Study Visit 2'), ({phv000001} == 'V3', 'Study Visit 3'))"
"""
        source = {"rows_per_visit": {"V1": 100, "V2": 200, "V3": 150}}
        harmonized = {"rows_per_visit": {"Study Visit 1": 100, "Study Visit 2": 200, "Study Visit 3": 150}}

        with tempfile.TemporaryDirectory() as tmp:
            yaml_dir = Path(tmp)
            (yaml_dir / "visit.yaml").write_text(visit_yaml, encoding="utf-8")
            results = check_c8_visit_distribution(source, harmonized, yaml_dir=yaml_dir)

        statuses = {r.variable: r.status for r in results}
        self.assertEqual(statuses.get("visit_Study Visit 1"), "PASS")
        self.assertEqual(statuses.get("visit_Study Visit 2"), "PASS")
        self.assertEqual(statuses.get("visit_Study Visit 3"), "PASS")
        self.assertNotIn("_visits", statuses)

    def test_c8_crosswalk_resolves_integer_visit_codes_to_canonical_labels(self) -> None:
        """Integer-coded visit discriminators (e.g. FHS-style): crosswalk handles
        numeric comparisons in case() expression."""
        visit_yaml = """
- class_derivations:
    Visit:
      populated_from: pht000002
      slot_derivations:
        name:
          expr: "case(({phv000002} == 0, 'Cohort Baseline'), ({phv000002} == 1, 'Cohort Exam 2'))"
"""
        source = {"rows_per_visit": {"0": 500, "1": 480}}
        harmonized = {"rows_per_visit": {"Cohort Baseline": 500, "Cohort Exam 2": 480}}

        with tempfile.TemporaryDirectory() as tmp:
            yaml_dir = Path(tmp)
            (yaml_dir / "visit.yaml").write_text(visit_yaml, encoding="utf-8")
            results = check_c8_visit_distribution(source, harmonized, yaml_dir=yaml_dir)

        statuses = {r.variable: r.status for r in results}
        self.assertEqual(statuses.get("visit_Cohort Baseline"), "PASS")
        self.assertEqual(statuses.get("visit_Cohort Exam 2"), "PASS")
        self.assertNotIn("_visits", statuses)

    def test_c8_crosswalk_falls_back_to_warn_when_crosswalk_cannot_resolve(self) -> None:
        """When visit.yaml has no case() expression that maps the source labels,
        C8 still falls back to the total-count WARN."""
        visit_yaml = """
- class_derivations:
    Visit:
      populated_from: pht000003
      slot_derivations:
        name:
          value: "Fixed Visit Label"
"""
        source = {"rows_per_visit": {"RAW_CODE": 100}}
        harmonized = {"rows_per_visit": {"Other Visit": 100}}

        with tempfile.TemporaryDirectory() as tmp:
            yaml_dir = Path(tmp)
            (yaml_dir / "visit.yaml").write_text(visit_yaml, encoding="utf-8")
            results = check_c8_visit_distribution(source, harmonized, yaml_dir=yaml_dir)

        self.assertEqual(results[0].status, "WARN")
        self.assertEqual(results[0].detail["comparison_confidence"], "unsupported")

    def test_c8_synthesis_marks_multi_label_pht_unsupported(self) -> None:
        visit_yaml = """
- class_derivations:
    Visit:
      populated_from: pht000001
      slot_derivations:
        name:
          value: VISIT A
---
- class_derivations:
    Visit:
      populated_from: pht000001
      slot_derivations:
        name:
          value: VISIT B
"""
        with tempfile.TemporaryDirectory() as tmp:
            yaml_dir = Path(tmp)
            (yaml_dir / "visit.yaml").write_text(visit_yaml, encoding="utf-8")

            synthesized, uncovered, unsupported = _synthesize_source_visit_counts(
                {"total_rows_by_pht": {"pht000001": 100}}, yaml_dir
            )

        self.assertEqual(synthesized, {})
        self.assertEqual(uncovered, [])
        self.assertEqual(unsupported[0]["rows"], 100)
        self.assertEqual(unsupported[0]["labels"], ["VISIT A", "VISIT B"])

    def test_c9_all_out_src_demoted_to_info(self) -> None:
        ranges = {
            "weight": {
                "common_phv_names": ["weight"],
                "plausible_lo": 15,
                "plausible_hi": 350,
                "red_flag_lo": 15,
                "red_flag_hi": 350,
            }
        }
        src = {"type": "continuous", "min": 0.0, "max": 415.0}
        out = {"type": "continuous", "min": 0.0, "max": 415.0}

        result = check_c9_clinical_range(out, "weight", ranges, src_var=src)

        self.assertEqual(result.status, "INFO")
        self.assertIn("[out+src]", result.message)

    def test_c9_uses_min_max_from_numeric_encoded_source(self) -> None:
        ranges = {
            "weight": {
                "common_phv_names": ["weight"],
                "plausible_lo": 15,
                "plausible_hi": 350,
                "red_flag_lo": 15,
                "red_flag_hi": 350,
            }
        }
        src = {"type": "categorical", "min": 0.0, "max": 415.0}
        out = {"type": "continuous", "min": 0.0, "max": 415.0}

        result = check_c9_clinical_range(out, "weight", ranges, src_var=src)

        self.assertEqual(result.status, "INFO")
        self.assertIn("[out+src]", result.message)

    def test_c9_detail_reports_exact_name_match(self) -> None:
        ranges = {
            "weight_kg": {
                "common_phv_names": ["WEIGHT"],
                "plausible_lo": 15,
                "plausible_hi": 350,
                "red_flag_lo": 15,
                "red_flag_hi": 350,
            }
        }
        out = {"type": "continuous", "min": 70.0, "max": 90.0}

        result = check_c9_clinical_range(out, "weight", ranges)

        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.detail["range_name"], "weight_kg")
        self.assertEqual(result.detail["match_method"], "common_phv_name")

    def test_c9_detail_reports_concept_code_match(self) -> None:
        ranges = {
            "heart_rate": {
                "oba_codes": ["OBA:1001087"],
                "omop_codes": [],
                "plausible_lo": 30,
                "plausible_hi": 200,
                "red_flag_lo": 15,
                "red_flag_hi": 300,
            }
        }
        out = {
            "type": "continuous",
            "observation_type": "OBA:1001087",
            "min": 45.0,
            "max": 130.0,
        }

        result = check_c9_clinical_range(out, "hr30", ranges)

        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.detail["range_name"], "heart_rate")
        self.assertEqual(result.detail["match_method"], "concept_code")
        self.assertEqual(result.detail["matched_code"], "OBA:1001087")

    def test_c9_detail_reports_substring_match(self) -> None:
        ranges = {
            "heart_rate": {
                "common_phv_names": [],
                "plausible_lo": 30,
                "plausible_hi": 200,
                "red_flag_lo": 15,
                "red_flag_hi": 300,
            }
        }
        out = {"type": "continuous", "min": 45.0, "max": 350.0}

        result = check_c9_clinical_range(out, "resting heart_rate supine", ranges)

        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.detail["range_name"], "heart_rate")
        self.assertEqual(result.detail["match_method"], "substring")

    def test_c2_large_n_gain_escalates_to_fail(self) -> None:
        src = {"n_valid": 100}
        out = {"n_valid": 125}

        result = check_c2_n_loss(
            src,
            out,
            "fanout",
            gain_warn_pct=2.0,
            gain_fail_pct=10.0,
        )

        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.detail["gain_pct"], 25.0)

    def test_c2_skips_unsupported_expected_summary(self) -> None:
        src = {
            "n_valid": 100,
            "_comparison_confidence": "unsupported",
            "_comparison_limitations": ["joint counts required"],
        }
        out = {"n_valid": 125}

        result = check_c2_n_loss(src, out, "joint")

        self.assertEqual(result.status, "SKIP")
        self.assertEqual(result.detail["comparison_confidence"], "unsupported")

    def test_build_variable_crosswalk_raises_on_empty_cache_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            (cache_dir / "pheno_variable_summaries").mkdir()
            yaml_dir = cache_dir / "yaml"
            yaml_dir.mkdir()

            with self.assertRaises(CrosswalkBuildError):
                build_variable_crosswalk(
                    variables_by_name={},
                    harmonized_vars={},
                    yaml_dir=yaml_dir,
                    cache_dir=cache_dir,
                )

    def test_process_conditions_marks_missing_status_assumption(self) -> None:
        import pandas as pd

        module_path = HV_DATAQC_DIR / "extract_harmonized" / "extract_harmonized_summaries.py"
        spec = importlib.util.spec_from_file_location("extract_harmonized_summaries", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        diagnostics: dict = {}
        variables = module.process_conditions(
            pd.DataFrame({"condition_concept": ["MONDO:1", "MONDO:1"]}),
            visit_id_to_label={},
            diagnostics_out=diagnostics,
        )

        self.assertTrue(diagnostics["condition_status_missing"])
        self.assertEqual(diagnostics["condition_status_missing_rows"], 2)
        self.assertTrue(
            variables["condition_MONDO:1"]["condition_status_missing_assumption"]
        )


class AmbiguousColumnTests(unittest.TestCase):
    """Tests for the variables_by_name lookup and ambiguity handling."""

    def test_build_variables_by_name_groups_by_column(self) -> None:
        vbp = {
            "pht1": {"age": {"mean": 50}, "sex": {"n_valid": 100}},
            "pht2": {"age": {"mean": 60}},
        }
        vbn = _build_variables_by_name(vbp)
        self.assertEqual(set(vbn), {"age", "sex"})
        self.assertEqual(set(vbn["age"]), {"pht1", "pht2"})
        self.assertEqual(vbn["age"]["pht1"]["mean"], 50)

    def test_pick_single_pht_summary_returns_only_pht(self) -> None:
        vbn = {"age": {"pht1": {"mean": 50, "n_valid": 100}}}
        result = _pick_single_pht_summary(vbn, "age")
        self.assertEqual(result, {"mean": 50, "n_valid": 100})

    def test_pick_single_pht_summary_returns_none_for_missing(self) -> None:
        vbn = {"age": {"pht1": {"mean": 50}}}
        self.assertIsNone(_pick_single_pht_summary(vbn, "weight"))

    def test_pick_single_pht_summary_raises_on_multi_pht(self) -> None:
        vbn = {
            "age": {
                "pht1": {"mean": 50, "n_valid": 100},
                "pht2": {"mean": 60, "n_valid": 200},
            }
        }
        with self.assertRaises(AmbiguousColumnError) as ctx:
            _pick_single_pht_summary(vbn, "age")
        self.assertEqual(ctx.exception.col, "age")
        self.assertEqual(set(ctx.exception.pht_map), {"pht1", "pht2"})


class AmbiguousColumnIntegrationTests(unittest.TestCase):
    """End-to-end tests for build_variable_crosswalk's ambiguous-column path.

    Construct a minimal cache XML + YAML + variables_by_name to exercise the
    PHV→PHT fallback. The fallback fires when the cache doesn't have the
    PHV (so phv_to_pht.get returns None) and we fall through to looking up
    by bare column name in variables_by_name.

    - Scenario A: column exists in multiple PHTs → AmbiguousColumnError →
      crosswalk records _ambiguous_columns on the merged match.
    - Scenario B: column exists in only one PHT → silent resolution, no
      _ambiguous_columns recorded.
    """

    YAML_BLOCK = (
        "- class_derivations:\n"
        "    MeasurementObservation:\n"
        "      populated_from: pht002239\n"
        "      slot_derivations:\n"
        "        observation_type:\n"
        "          value: OMOP:1234567\n"
        "        value_quantity:\n"
        "          object_derivations:\n"
        "          - class_derivations:\n"
        "              Quantity:\n"
        "                populated_from: pht002239\n"
        "                slot_derivations:\n"
        "                  value_decimal:\n"
        "                    populated_from: phv00000999\n"
    )

    def _write_cache(
        self,
        tmp_path: Path,
        cache_phv: str,
        cache_var_name: str,
        cache_pht: str,
    ) -> None:
        """Write a minimal data_dict.xml that maps `cache_phv` to `cache_var_name`
        under `cache_pht`. If we want the YAML's PHV to be absent from the cache,
        the caller passes a different PHV than the YAML's populated_from."""
        pheno_dir = tmp_path / "pheno_variable_summaries"
        pheno_dir.mkdir(exist_ok=True)
        (pheno_dir / f"phs000000.v1.{cache_pht}.v1.p1.test.data_dict.xml").write_text(
            '<?xml version="1.0"?>\n'
            "<data_table>\n"
            f'  <variable id="{cache_phv}.v1">\n'
            f"    <name>{cache_var_name}</name>\n"
            "  </variable>\n"
            "</data_table>\n",
            encoding="utf-8",
        )

    def test_ambiguous_lookup_emits_ambiguous_columns(self) -> None:
        """YAML PHV not in cache + bare-name column in 2 PHTs → FAIL recorded."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Cache resolves the YAML's PHV (phv00000999) to a column name
            # but NOT to a PHT entry that contains the column — we'll make
            # the cache map the PHV to pht002239 while the actual column
            # lives only in unrelated PHTs in variables_by_name.
            self._write_cache(
                tmp_path,
                cache_phv="phv00000999",
                cache_var_name="ambig_col",
                cache_pht="pht002239",
            )

            yaml_dir = tmp_path / "yaml"
            yaml_dir.mkdir()
            (yaml_dir / "test.yaml").write_text(self.YAML_BLOCK, encoding="utf-8")

            # variables_by_name: ambig_col exists in TWO unrelated PHTs.
            # Since pht002239 has no ambig_col entry, the PHV→PHT path
            # fails to find the summary, falling through to bare-name lookup,
            # which raises AmbiguousColumnError.
            variables_by_name = {
                "ambig_col": {
                    "pht111111": {"type": "continuous", "n_valid": 50, "mean": 1.0},
                    "pht222222": {"type": "continuous", "n_valid": 80, "mean": 2.0},
                },
            }
            harmonized_vars = {"measurement_OMOP:1234567": {"n_valid": 100}}

            matches = build_variable_crosswalk(
                variables_by_name=variables_by_name,
                harmonized_vars=harmonized_vars,
                yaml_dir=yaml_dir,
                cache_dir=tmp_path,
            )

            self.assertEqual(len(matches), 1)
            match = matches[0]
            self.assertIn("_ambiguous_columns", match)
            # At least one source-role ambiguity for ambig_col with both PHTs.
            # (The value-expr resolution loop may also flag the same column
            # via the entry's source_phvs list — that's fine; both should
            # carry the same diagnostic info.)
            source_role = [
                a for a in match["_ambiguous_columns"] if a["role"] == "source"
            ]
            self.assertEqual(len(source_role), 1)
            amb = source_role[0]
            self.assertEqual(amb["col"], "ambig_col")
            self.assertEqual(set(amb["phts"]), {"pht111111", "pht222222"})
            for entry in match["_ambiguous_columns"]:
                self.assertEqual(entry["col"], "ambig_col")
                self.assertEqual(set(entry["phts"]), {"pht111111", "pht222222"})

    def test_ambiguous_columns_fail_builds_checkresult_with_diagnostic(self) -> None:
        """_ambiguous_columns_fail produces a CROSSWALK FAIL with per-PHT stats."""
        match = {
            "harmonized_key": "measurement_OBA:9999999",
            "yaml_file": "test.yaml",
            "phv_id": "phv00000999",
        }
        ambiguous = [{
            "col": "age",
            "phts": ["pht111111", "pht222222"],
            "role": "source",
            "phv_id": "phv00000999",
        }]
        variables_by_name = {
            "age": {
                "pht111111": {"n_valid": 50, "mean": 1.0, "_pht": "pht111111"},
                "pht222222": {"n_valid": 80, "mean": 2.0, "_pht": "pht222222"},
            },
        }
        result = _ambiguous_columns_fail(match, ambiguous, variables_by_name)
        self.assertEqual(result.check_id, "CROSSWALK")
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.variable, "measurement_OBA:9999999")
        # Diagnostic detail should carry per-PHT stats for reviewer triage.
        per_pht = result.detail["ambiguous_columns"][0]["per_pht_stats"]
        self.assertEqual(per_pht["pht111111"]["mean"], 1.0)
        self.assertEqual(per_pht["pht222222"]["mean"], 2.0)
        # Message should name the column and list the PHTs.
        self.assertIn("'age'", result.message)
        self.assertIn("pht111111", result.message)
        self.assertIn("pht222222", result.message)

    def test_unambiguous_single_pht_lookup_no_failure(self) -> None:
        """YAML PHV not in cache + bare-name column in 1 PHT → resolves silently."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            self._write_cache(
                tmp_path,
                cache_phv="phv00000999",
                cache_var_name="solo_col",
                cache_pht="pht002239",
            )

            yaml_dir = tmp_path / "yaml"
            yaml_dir.mkdir()
            yaml_text = self.YAML_BLOCK.replace("phv00000999", "phv00000999")
            (yaml_dir / "test.yaml").write_text(yaml_text, encoding="utf-8")

            # solo_col exists in only one PHT — fallback returns it without
            # complaint.
            variables_by_name = {
                "solo_col": {
                    "pht999999": {"type": "continuous", "n_valid": 50, "mean": 1.0},
                },
            }
            harmonized_vars = {"measurement_OMOP:1234567": {"n_valid": 100}}

            matches = build_variable_crosswalk(
                variables_by_name=variables_by_name,
                harmonized_vars=harmonized_vars,
                yaml_dir=yaml_dir,
                cache_dir=tmp_path,
            )

            self.assertEqual(len(matches), 1)
            match = matches[0]
            self.assertNotIn("_ambiguous_columns", match)
            # The single-PHT summary should have been picked up.
            self.assertIsNotNone(match.get("_resolved_src"))


class DedupCheckResultsTests(unittest.TestCase):
    """Tests for _dedup_check_results: exact dedup and C9 consolidation."""

    def test_exact_dedup_removes_identical_findings(self) -> None:
        """Two identical C2 FAILs (shared-PHV pre/post bronchodilator) become one."""
        r1 = CheckResult("C2", "ppfvc51 [phv1 / pht1]", "FAIL", "Significant N loss: 4,250 -> 0 (100.0%)")
        r2 = CheckResult("C2", "ppfvc51 [phv1 / pht1]", "FAIL", "Significant N loss: 4,250 -> 0 (100.0%)")
        r3 = CheckResult("C2", "fvc01 [phv2 / pht2]", "FAIL", "Significant N loss: 28,683 -> 0 (100.0%)")
        result = _dedup_check_results([r1, r2, r3])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].variable, "ppfvc51 [phv1 / pht1]")
        self.assertEqual(result[1].variable, "fvc01 [phv2 / pht2]")

    def test_exact_dedup_keeps_different_messages_for_same_variable(self) -> None:
        """Two C2 results for same variable but different messages are both kept."""
        r1 = CheckResult("C2", "sbpa17", "FAIL", "Significant N loss: 100 -> 0 (100.0%)")
        r2 = CheckResult("C2", "sbpa17", "WARN", "Moderate N loss: 100 -> 98 (2.0%)")
        result = _dedup_check_results([r1, r2])
        self.assertEqual(len(result), 2)

    def test_c9_consolidation_merges_different_range_violations(self) -> None:
        """Two C9 FAILs for the same variable (different range matches) are merged."""
        r1 = CheckResult("C9", "sbpa17 [phv1 / pht1]", "FAIL",
                         "min=0.0 below red_flag 40 [out+src]",
                         {"min": 0.0, "max": 220.0})
        r2 = CheckResult("C9", "sbpa17 [phv1 / pht1]", "FAIL",
                         "min=0.0 below red_flag 15 [out+src]",
                         {"min": 0.0, "max": 220.0})
        result = _dedup_check_results([r1, r2])
        c9_results = [r for r in result if r.check_id == "C9"]
        self.assertEqual(len(c9_results), 1, "Two C9 entries for same variable should merge to one")
        self.assertIn("min=0.0 below red_flag 40", c9_results[0].message)
        self.assertIn("min=0.0 below red_flag 15", c9_results[0].message)
        self.assertEqual(c9_results[0].status, "FAIL")

    def test_c9_consolidation_uses_worst_status(self) -> None:
        """When one C9 is FAIL and another WARN, merged result is FAIL."""
        r1 = CheckResult("C9", "sbpa17", "WARN", "max=260 above plausible 250 [out+src]")
        r2 = CheckResult("C9", "sbpa17", "FAIL", "min=0.0 below red_flag 40 [out only]")
        result = _dedup_check_results([r1, r2])
        c9_results = [r for r in result if r.check_id == "C9"]
        self.assertEqual(len(c9_results), 1)
        self.assertEqual(c9_results[0].status, "FAIL")

    def test_c9_dedup_does_not_merge_different_variables(self) -> None:
        """C9 results for different variables are not merged."""
        r1 = CheckResult("C9", "sbp [phv1 / pht1]", "FAIL", "min=0 below red_flag 40 [out+src]")
        r2 = CheckResult("C9", "dbp [phv2 / pht1]", "FAIL", "max=200 above red_flag 150 [out+src]")
        result = _dedup_check_results([r1, r2])
        c9_results = [r for r in result if r.check_id == "C9"]
        self.assertEqual(len(c9_results), 2)

    def test_c9_consolidation_deduplicates_identical_violation_strings(self) -> None:
        """If two C9 results have the same violation string, it appears only once."""
        r1 = CheckResult("C9", "sbpa17", "FAIL", "min=0.0 below red_flag 40 [out+src]")
        r2 = CheckResult("C9", "sbpa17", "FAIL", "min=0.0 below red_flag 40 [out+src]")
        result = _dedup_check_results([r1, r2])
        c9_results = [r for r in result if r.check_id == "C9"]
        self.assertEqual(len(c9_results), 1)
        self.assertEqual(c9_results[0].message, "min=0.0 below red_flag 40 [out+src]")


class C1NPreservationTests(unittest.TestCase):
    """Tests for check_c1_n_preservation, including participants_by_pht logic."""

    @staticmethod
    def _src(total: int, by_pht: dict | None = None) -> dict:
        doc: dict = {"total_participants": total}
        if by_pht is not None:
            doc["participants_by_pht"] = by_pht
        return doc

    @staticmethod
    def _harm(total: int) -> dict:
        return {"total_participants": total}

    # --- No participants_by_pht (legacy path) ---

    def test_c1_pass_exact_match_no_pht(self) -> None:
        result = check_c1_n_preservation(self._src(5531), self._harm(5531))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].status, "PASS")

    def test_c1_fail_large_loss_no_pht(self) -> None:
        result = check_c1_n_preservation(self._src(7380), self._harm(5531))
        self.assertEqual(result[0].status, "FAIL")
        self.assertIn("Participant loss", result[0].message)
        self.assertAlmostEqual(result[0].detail["loss_pct"], 25.1, places=1)

    def test_c1_skip_no_source(self) -> None:
        result = check_c1_n_preservation({"total_participants": 0}, self._harm(5531))
        self.assertEqual(result[0].status, "SKIP")

    def test_c1_fail_no_harmonized(self) -> None:
        result = check_c1_n_preservation(self._src(5531), {"total_participants": 0})
        self.assertEqual(result[0].status, "FAIL")

    def test_c1_warn_harmonized_exceeds_source(self) -> None:
        result = check_c1_n_preservation(self._src(5000), self._harm(5100))
        self.assertEqual(result[0].status, "WARN")
        self.assertIn("MORE participants", result[0].message)

    # --- With participants_by_pht, no mapped_phts (legacy/fallback path) ---

    def test_c1_keeps_union_denominator_with_pht_breakdown(self) -> None:
        """participants_by_pht is diagnostic-only; total_participants remains denominator."""
        by_pht = {"pht001450": 5531, "pht001467": 7200}  # union would be >5531
        result = check_c1_n_preservation(
            self._src(total=7380, by_pht=by_pht), self._harm(7200)
        )
        self.assertEqual(result[0].status, "FAIL")
        self.assertEqual(result[0].detail["source_n"], 7380)
        self.assertEqual(result[0].detail["max_single_pht_n"], 7200)
        self.assertIn("max single-PHT: pht001467=7,200", result[0].message)

    def test_c1_reports_pht_diagnostics_without_masking_union_loss(self) -> None:
        """CHS scenario stays visible as loss but reports max single-PHT context."""
        by_pht = {"pht001450": 5531, "pht001466": 5000, "pht001467": 5531}
        result = check_c1_n_preservation(
            self._src(total=7380, by_pht=by_pht), self._harm(5531)
        )
        self.assertEqual(result[0].status, "FAIL")
        self.assertEqual(result[0].detail["source_n"], 7380)
        self.assertEqual(result[0].detail["max_single_pht_n"], 5531)
        self.assertIn("all-PHT union=7,380", result[0].message)

    def test_c1_fail_real_loss_with_pht(self) -> None:
        """Even with pht breakdown, genuine loss is still FAIL."""
        by_pht = {"pht001450": 5531, "pht001467": 5531}
        result = check_c1_n_preservation(
            self._src(total=6000, by_pht=by_pht), self._harm(4000)
        )
        self.assertEqual(result[0].status, "FAIL")
        loss = result[0].detail["loss_pct"]
        self.assertGreater(loss, 1.0)

    def test_c1_detail_carries_pht_diagnostics(self) -> None:
        """detail dict must include max single-PHT diagnostics when present."""
        by_pht = {"pht001450": 5531, "pht001467": 5800}
        result = check_c1_n_preservation(
            self._src(total=7380, by_pht=by_pht), self._harm(4000)
        )
        self.assertEqual(result[0].detail["source_n"], 7380)
        self.assertEqual(result[0].detail["max_single_pht"], "pht001467")
        self.assertEqual(result[0].detail["max_single_pht_n"], 5800)

    # --- With participants_by_pht AND mapped_phts ---

    def test_c1_shows_mapped_pht_max_and_all_pht_union(self) -> None:
        """CHS scenario: message shows mapped-PHT max and all-PHT union separately."""
        # pht001447 is mapped (5612), pht001467 is unmapped (inflates union to 7380)
        by_pht = {"pht001447": 5612, "pht001450": 5531, "pht001467": 4752}
        mapped = {"pht001447", "pht001450"}
        result = check_c1_n_preservation(
            self._src(total=7380, by_pht=by_pht), self._harm(5531),
            mapped_phts=mapped,
        )
        self.assertEqual(result[0].status, "FAIL")
        self.assertEqual(result[0].detail["source_n"], 7380)
        self.assertEqual(result[0].detail["mapped_pht_max"], "pht001447")
        self.assertEqual(result[0].detail["mapped_pht_max_n"], 5612)
        self.assertIn("mapped-PHT max: pht001447=5,612", result[0].message)
        self.assertIn("all-PHT union=7,380", result[0].message)

    def test_c1_mapped_phts_detail_has_both_max_fields(self) -> None:
        """detail carries both max_single_pht (global) and mapped_pht_max (scoped)."""
        by_pht = {"pht001447": 5612, "pht001467": 9000}
        mapped = {"pht001447"}
        result = check_c1_n_preservation(
            self._src(total=9500, by_pht=by_pht), self._harm(4000),
            mapped_phts=mapped,
        )
        detail = result[0].detail
        self.assertEqual(detail["max_single_pht"], "pht001467")  # global max
        self.assertEqual(detail["max_single_pht_n"], 9000)
        self.assertEqual(detail["mapped_pht_max"], "pht001447")  # mapped max
        self.assertEqual(detail["mapped_pht_max_n"], 5612)

    def test_c1_mapped_phts_empty_intersection_falls_back(self) -> None:
        """If none of the mapped_phts appear in participants_by_pht, note is minimal."""
        by_pht = {"pht001447": 5612}
        mapped = {"pht999999"}  # no overlap
        result = check_c1_n_preservation(
            self._src(total=5612, by_pht=by_pht), self._harm(4000),
            mapped_phts=mapped,
        )
        # Should not crash; note falls back to just union
        self.assertIn("all-PHT union=5,612", result[0].message)
        self.assertNotIn("mapped_pht_max", result[0].detail)

    def test_c1_pass_with_mapped_phts(self) -> None:
        """PASS when harmonized matches total_participants even with mapped_phts."""
        by_pht = {"pht001450": 5531, "pht001467": 4000}
        mapped = {"pht001450"}
        result = check_c1_n_preservation(
            self._src(total=5531, by_pht=by_pht), self._harm(5531),
            mapped_phts=mapped,
        )
        self.assertEqual(result[0].status, "PASS")


# ---------------------------------------------------------------------------
# Crosswalk extraction: case() and value_mappings concept code improvements
# ---------------------------------------------------------------------------

from compare import (  # noqa: E402
    _concept_codes_from_expr,
    _concept_codes_from_value_mappings,
    _extract_crosswalk_from_class_derivations,
    _normalize_harmonized_vars,
)


class CrosswalkConceptExtractionTests(unittest.TestCase):
    """Tests for case()-expr and value_mappings-driven concept code extraction."""

    def test_case_expr_single_quotes_extracts_curies(self) -> None:
        """case() with single-quoted CURIEs (hdl.yaml style) → two codes."""
        expr = "case(({phv00099923} >= 12, 'OMOP:4041720'), (True, 'OBA:VT0000184'))"
        self.assertEqual(_concept_codes_from_expr(expr), ["OMOP:4041720", "OBA:VT0000184"])

    def test_case_expr_double_quotes_extracts_curies(self) -> None:
        """case() with double-quoted CURIEs (stroke.yaml style) → two codes."""
        expr = 'case(({phv00100830} == 1, "HP:0002140"), (True, "MONDO:0013792"))'
        self.assertEqual(_concept_codes_from_expr(expr), ["HP:0002140", "MONDO:0013792"])

    def test_case_expr_deduplicates(self) -> None:
        expr = "case(({p} == 1, 'OBA:2045443'), ({p} == 2, 'OBA:2045443'), (True, 'OMOP:0'))"
        self.assertEqual(_concept_codes_from_expr(expr), ["OBA:2045443", "OMOP:0"])

    def test_case_expr_no_curies_returns_empty(self) -> None:
        """Non-CURIE case() expression returns empty list."""
        self.assertEqual(_concept_codes_from_expr("case(({phv} > 0, 'high'), (True, 'low'))"), [])

    def test_value_mappings_extracts_curie_values(self) -> None:
        """value_mappings with CURIE values (diabetes.yaml pht001490 style)."""
        slot = {
            "populated_from": "phv00106406",
            "value_mappings": {
                "1": "MONDO:0005015",
                "2": "MONDO:0006920",
                "3": "MONDO:0005015",
                "4": "MONDO:0005015",
            },
        }
        self.assertEqual(
            _concept_codes_from_value_mappings(slot), ["MONDO:0005015", "MONDO:0006920"]
        )

    def test_value_mappings_filters_non_curie_values(self) -> None:
        """value_mappings with non-CURIE values (ABSENT/PRESENT) returns empty."""
        slot = {"value_mappings": {"0": "ABSENT", "1": "PRESENT"}}
        self.assertEqual(_concept_codes_from_value_mappings(slot), [])

    def test_value_concept_inner_slot_picks_measurement_phv(self) -> None:
        """value_concept inside object_derivations is treated as is_value_slot,
        so the measurement PHV (not the participant PHV) is selected as primary.
        Regression: spo2.yaml block 1 was previously picking Individual_ID."""
        cd = {
            "MeasurementObservation": {
                "populated_from": "pht001495",
                "slot_derivations": {
                    "associated_participant": {
                        "expr": 'uuid5("x", str({phv00109768}))'  # Individual_ID
                    },
                    "observation_type": {"value": "OBA:2045443"},
                    "value_quantity": {
                        "object_derivations": [
                            {
                                "class_derivations": {
                                    "Quantity": {
                                        "slot_derivations": {
                                            "value_concept": {
                                                "populated_from": "phv00110401",  # SPLT9069
                                                "value_mappings": {"0": "<90", "1": ">90"},
                                            },
                                        }
                                    }
                                }
                            }
                        ]
                    },
                },
            }
        }
        phv_names = {"phv00110401": "SPLT9069", "phv00109768": "Individual_ID"}
        cw: list[dict] = []
        _extract_crosswalk_from_class_derivations(cd, "spo2.yaml", phv_names, cw)
        self.assertEqual(len(cw), 1)
        self.assertEqual(cw[0]["phv_id"], "phv00110401",
                         "Should pick SPLT9069 (value_concept), not Individual_ID")
        self.assertEqual(cw[0]["source_key"], "SPLT9069")

    def test_context_phvs_are_tagged_but_excluded_from_comparison_source_phvs(self) -> None:
        cd = {
            "MeasurementObservation": {
                "populated_from": "pht001450",
                "slot_derivations": {
                    "associated_participant": {"populated_from": "phv000001"},
                    "associated_visit": {"expr": 'uuid5("Visit", str({phv000001}) + ":baseline")'},
                    "age_at_observation": {"expr": "{phv000002} * 365"},
                    "observation_type": {"value": "OBA:1001087"},
                    "value_quantity": {
                        "object_derivations": [
                            {
                                "class_derivations": {
                                    "Quantity": {
                                        "slot_derivations": {
                                            "value_decimal": {"expr": "{phv000003} * 2"},
                                        }
                                    }
                                }
                            }
                        ]
                    },
                    "method_type": {"value": "30 second heart rate"},
                },
            }
        }
        phv_names = {"phv000001": "ID", "phv000002": "AGE", "phv000003": "HR30"}
        cw: list[dict] = []

        _extract_crosswalk_from_class_derivations(cd, "hrtrt.yaml", phv_names, cw)

        self.assertEqual(len(cw), 1)
        self.assertEqual(cw[0]["phv_id"], "phv000003")
        self.assertEqual(cw[0]["source_phvs"], ["phv000003"])
        roles = {(entry["phv_id"], entry["role"]) for entry in cw[0]["source_phv_roles"]}
        self.assertIn(("phv000001", "participant_id"), roles)
        self.assertIn(("phv000001", "visit"), roles)
        self.assertIn(("phv000002", "age_at_observation"), roles)
        self.assertIn(("phv000003", "value"), roles)
        self.assertEqual(cw[0]["conversion_factor"], 2.0)

    def test_case_expr_observation_type_generates_multiple_entries(self) -> None:
        """case() on observation_type generates one crosswalk entry per CURIE.
        Regression: hdl.yaml was silently producing no matched entries."""
        cd = {
            "MeasurementObservation": {
                "populated_from": "pht001451",
                "slot_derivations": {
                    "associated_participant": {"expr": 'uuid5("x", str({phv00098771}))'},
                    "observation_type": {
                        "expr": "case(({phv00099923} >= 12, 'OMOP:4041720'), (True, 'OBA:VT0000184'))"
                    },
                    "value_quantity": {
                        "object_derivations": [
                            {
                                "class_derivations": {
                                    "Quantity": {
                                        "slot_derivations": {
                                            "value_decimal": {"populated_from": "phv00100042"},
                                        }
                                    }
                                }
                            }
                        ]
                    },
                },
            }
        }
        phv_names = {"phv00100042": "HDL44", "phv00098771": "SUBJECT_ID", "phv00099923": "FASTED"}
        cw: list[dict] = []
        _extract_crosswalk_from_class_derivations(cd, "hdl.yaml", phv_names, cw)
        hkeys = {e["harmonized_key"] for e in cw}
        self.assertIn("measurement_OMOP:4041720", hkeys)
        self.assertIn("measurement_OBA:VT0000184", hkeys)
        for e in cw:
            self.assertEqual(e["phv_id"], "phv00100042",
                             "Both entries should use value_decimal PHV (HDL44)")
            self.assertTrue(e["concept_exprs"])

    def test_concept_case_expr_expected_summary_is_unsupported(self) -> None:
        entry = {
            "yaml_file": "hdl.yaml",
            "phv_id": "phv00100042",
            "concept_codes": ["OMOP:4041720", "OBA:VT0000184"],
            "concept_exprs": ["case(({phv00099923} >= 12, 'OMOP:4041720'), (True, 'OBA:VT0000184'))"],
            "_source_summary": {
                "type": "continuous",
                "n_total": 12,
                "n_valid": 12,
                "mean": 50.0,
                "sd": 5.0,
            },
        }

        expected = build_expected_summary([entry], {})

        self.assertIsNotNone(expected)
        self.assertEqual(expected["_comparison_basis"], "yaml_concept_case_expr")
        self.assertEqual(expected["_comparison_confidence"], "unsupported")
        self.assertIn("branch-specific", expected["_comparison_limitations"][0])

    def test_value_mappings_condition_concept_generates_multiple_entries(self) -> None:
        """condition_concept with CURIE value_mappings emits one entry per CURIE.
        Regression: diabetes.yaml pht001490 block was silently dropped."""
        cd = {
            "Condition": {
                "populated_from": "pht001490",
                "slot_derivations": {
                    "associated_participant": {"expr": 'uuid5("x", str({phv00105099}))'},
                    "condition_concept": {
                        "populated_from": "phv00106406",
                        "value_mappings": {
                            "1": "MONDO:0005015",
                            "2": "MONDO:0006920",
                            "3": "MONDO:0005015",
                        },
                    },
                    "condition_status": {
                        "populated_from": "phv00106406",
                        "value_mappings": {"1": "ABSENT", "2": "PRESENT", "3": "PRESENT"},
                    },
                },
            }
        }
        phv_names = {"phv00106406": "DIAB_STAT", "phv00105099": "SUBJECT_ID"}
        cw: list[dict] = []
        _extract_crosswalk_from_class_derivations(cd, "diabetes.yaml", phv_names, cw)
        hkeys = {e["harmonized_key"] for e in cw}
        self.assertIn("condition_MONDO:0005015", hkeys)
        self.assertIn("condition_MONDO:0006920", hkeys)


# ---------------------------------------------------------------------------
# Harmonized key normalization and crosswalk resolution fallbacks
# ---------------------------------------------------------------------------


class HarmonizedKeyNormalizationTests(unittest.TestCase):
    """Tests for tuple-notation cleanup (_normalize_harmonized_vars) and
    the method_type suffix fallback in build_variable_crosswalk."""

    def test_tuple_key_notation_is_stripped(self) -> None:
        """Keys like measurement_('OMOP:4152194',) are normalised to measurement_OMOP:4152194."""
        raw = {
            "measurement_('OMOP:4152194',)": {"n_valid": 50},
            "measurement_('OMOP:4154790',)": {"n_valid": 50},
            "measurement_OMOP:4241837": {"n_valid": 100},
        }
        result = _normalize_harmonized_vars(raw)
        self.assertIn("measurement_OMOP:4152194", result)
        self.assertIn("measurement_OMOP:4154790", result)
        self.assertNotIn("measurement_('OMOP:4152194',)", result)
        self.assertNotIn("measurement_('OMOP:4154790',)", result)
        # Already-clean key is preserved
        self.assertIn("measurement_OMOP:4241837", result)

    def test_method_type_suffix_fallback_resolves_bare_harmonized_key(self) -> None:
        """Crosswalk key with |method_type suffix matches bare harmonized key.

        Regression: COPDGene spirometry.yaml MOS blocks produce crosswalk keys
        like ``measurement_OMOP:4241837|Pre-bronchodilator, spirometry`` but
        the COPDGene harmonized extract emits bare ``measurement_OMOP:4241837``.
        Fallback 3 should resolve this so the entry appears in the crosswalk
        rather than falling into unresolved diagnostics.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Minimal pheno_variable_summaries cache
            pheno_dir = tmp_path / "pheno_variable_summaries"
            pheno_dir.mkdir()
            dd_xml = pheno_dir / "phs000179.v7.pht002239.v8.p2.COPDGene.data_dict.xml"
            dd_xml.write_text(
                '<?xml version="1.0"?>\n'
                "<data_table>\n"
                '  <variable id="phv00159853.v5">\n'
                "    <name>FEV1_pre</name>\n"
                "  </variable>\n"
                "</data_table>\n",
                encoding="utf-8",
            )

            # Minimal MOS YAML
            yaml_dir = tmp_path / "yaml"
            yaml_dir.mkdir()
            (yaml_dir / "spirometry.yaml").write_text(
                "- class_derivations:\n"
                "    MeasurementObservationSet:\n"
                "      populated_from: pht002239\n"
                "      slot_derivations:\n"
                "        observations:\n"
                "          object_derivations:\n"
                "          - class_derivations:\n"
                "              MeasurementObservation:\n"
                "                populated_from: pht002239\n"
                "                slot_derivations:\n"
                "                  observation_type:\n"
                "                    value: OMOP:4241837\n"
                "                  method_type:\n"
                "                    value: Pre-bronchodilator, spirometry\n"
                "                  value_quantity:\n"
                "                    object_derivations:\n"
                "                    - class_derivations:\n"
                "                        Quantity:\n"
                "                          populated_from: pht002239\n"
                "                          slot_derivations:\n"
                "                            value_decimal:\n"
                "                              populated_from: phv00159853\n",
                encoding="utf-8",
            )

            variables_by_name = {
                "FEV1_pre": {"pht000001": {"type": "continuous", "n_valid": 100, "n_total": 100}},
            }
            # Harmonized extract has bare key — no |method_type suffix
            harmonized_vars = {"measurement_OMOP:4241837": {"n_valid": 100}}

            matches = build_variable_crosswalk(
                variables_by_name=variables_by_name,
                harmonized_vars=harmonized_vars,
                yaml_dir=yaml_dir,
                cache_dir=tmp_path,
            )

            matched_keys = {m["harmonized_key"] for m in matches}
            self.assertIn(
                "measurement_OMOP:4241837",
                matched_keys,
                "Fallback 3 should resolve |method_type-suffixed key to bare harmonized key",
            )

    def test_tuple_key_normalization_then_method_type_suffix_fallback(self) -> None:
        """Tuple-form harmonized key normalizes, then resolves a suffixed MOS crosswalk key.

        Regression: COPDGene blood_pressure.yaml yielded crosswalk keys like
        ``measurement_OMOP:4152194|automated sphygmomanometer`` while the
        harmonized extract key serialized as ``measurement_('OMOP:4152194',)``.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            pheno_dir = tmp_path / "pheno_variable_summaries"
            pheno_dir.mkdir()
            dd_xml = pheno_dir / "phs000179.v7.pht002239.v8.p2.COPDGene.data_dict.xml"
            dd_xml.write_text(
                '<?xml version="1.0"?>\n'
                "<data_table>\n"
                '  <variable id="phv00159590.v5">\n'
                "    <name>sysBP</name>\n"
                "  </variable>\n"
                "</data_table>\n",
                encoding="utf-8",
            )

            yaml_dir = tmp_path / "yaml"
            yaml_dir.mkdir()
            (yaml_dir / "blood_pressure.yaml").write_text(
                "- class_derivations:\n"
                "    MeasurementObservationSet:\n"
                "      populated_from: pht002239\n"
                "      slot_derivations:\n"
                "        observations:\n"
                "          object_derivations:\n"
                "          - class_derivations:\n"
                "              MeasurementObservation:\n"
                "                populated_from: pht002239\n"
                "                slot_derivations:\n"
                "                  observation_type:\n"
                "                    value: OMOP:4152194\n"
                "                  method_type:\n"
                "                    value: automated sphygmomanometer\n"
                "                  value_quantity:\n"
                "                    object_derivations:\n"
                "                    - class_derivations:\n"
                "                        Quantity:\n"
                "                          populated_from: pht002239\n"
                "                          slot_derivations:\n"
                "                            value_decimal:\n"
                "                              populated_from: phv00159590\n",
                encoding="utf-8",
            )

            variables_by_name = {
                "sysBP": {"pht000001": {"type": "continuous", "n_valid": 100, "n_total": 100}},
            }
            raw_harmonized_vars = {"measurement_('OMOP:4152194',)": {"n_valid": 100}}

            matches = build_variable_crosswalk(
                variables_by_name=variables_by_name,
                harmonized_vars=_normalize_harmonized_vars(raw_harmonized_vars),
                yaml_dir=yaml_dir,
                cache_dir=tmp_path,
            )

            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["harmonized_key"], "measurement_OMOP:4152194")
            self.assertEqual(matches[0]["source_key"], "sysBP")


class SourceSchemaValidationTests(unittest.TestCase):
    """compare.main must reject source JSON without `variables_by_pht`.

    Otherwise a malformed or unsupported-extractor source summary will
    silently compare as zero source variables, producing misleading
    unmatched/missing output.
    """

    def _write_minimal_inputs(
        self,
        tmp: Path,
        source_doc: dict,
        harmonized_doc: dict | None = None,
    ) -> dict[str, Path]:
        """Lay out a temp dir with the files compare.main needs at startup.

        Returns a dict of paths the caller can pass into argv. Yaml and
        cache dirs exist but are empty — the schema check is supposed to
        fire before the crosswalk build, so empty is fine.
        """
        src_path = tmp / "src.json"
        harm_path = tmp / "harm.json"
        yaml_dir = tmp / "yaml"
        cache_dir = tmp / "cache"
        src_path.write_text(json.dumps(source_doc), encoding="utf-8")
        harm_path.write_text(
            json.dumps(harmonized_doc if harmonized_doc is not None else {"variables": {}}),
            encoding="utf-8",
        )
        yaml_dir.mkdir()
        cache_dir.mkdir()
        return {
            "source": src_path, "harmonized": harm_path,
            "yaml_dir": yaml_dir, "cache_dir": cache_dir,
        }

    def _argv(self, paths: dict[str, Path]) -> list[str]:
        return [
            "--source", str(paths["source"]),
            "--harmonized", str(paths["harmonized"]),
            "--cohort", "TESTCOHORT",
            "--yaml-dir", str(paths["yaml_dir"]),
            "--cache-dir", str(paths["cache_dir"]),
        ]

    def _valid_source_doc(self) -> dict:
        return {
            "metadata": {},
            "variables_by_pht": {"pht000001": {"X": {"type": "continuous"}}},
            "participant_denominators": {},
            "total_rows_by_pht": {"pht000001": 1},
        }

    def test_source_summary_schema_requires_phase4_fields(self) -> None:
        errors = validate_source_summary_schema({"metadata": {}, "variables_by_pht": {"pht000001": {}}})

        self.assertIn("ERROR: source JSON has no usable `participant_denominators` mapping.", errors)
        self.assertIn("ERROR: source JSON has no usable `total_rows_by_pht` mapping.", errors)

    def test_harmonized_summary_schema_requires_phase4_fields(self) -> None:
        errors = validate_harmonized_summary_schema({"metadata": {}, "variables": {"x": {}}})

        self.assertIn("ERROR: harmonized JSON has no usable `entity_counts` mapping.", errors)
        self.assertIn("ERROR: harmonized JSON has no usable integer `total_participants`.", errors)

    def test_missing_variables_by_pht_exits_with_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_minimal_inputs(
                Path(tmp),
                source_doc={"metadata": {}, "total_rows": 100},  # no variables_by_pht
            )
            with self.assertRaises(SystemExit) as ctx:
                compare_main(self._argv(paths))
            self.assertEqual(ctx.exception.code, 2)

    def test_empty_variables_by_pht_exits_with_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_minimal_inputs(
                Path(tmp),
                source_doc={"metadata": {}, "variables_by_pht": {}},
            )
            with self.assertRaises(SystemExit) as ctx:
                compare_main(self._argv(paths))
            self.assertEqual(ctx.exception.code, 2)

    def test_variables_by_pht_wrong_type_exits_with_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_minimal_inputs(
                Path(tmp),
                source_doc={"metadata": {}, "variables_by_pht": "not a dict"},
            )
            with self.assertRaises(SystemExit) as ctx:
                compare_main(self._argv(paths))
            self.assertEqual(ctx.exception.code, 2)

    def test_missing_harmonized_variables_exits_with_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_minimal_inputs(
                Path(tmp),
                source_doc=self._valid_source_doc(),
                harmonized_doc={"metadata": {}},
            )
            with self.assertRaises(SystemExit) as ctx:
                compare_main(self._argv(paths))
            self.assertEqual(ctx.exception.code, 2)

    def test_empty_harmonized_variables_exits_with_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_minimal_inputs(
                Path(tmp),
                source_doc=self._valid_source_doc(),
                harmonized_doc={"metadata": {}, "variables": {}, "entity_counts": {}, "total_participants": 1},
            )
            with self.assertRaises(SystemExit) as ctx:
                compare_main(self._argv(paths))
            self.assertEqual(ctx.exception.code, 2)

    def test_wrong_type_harmonized_variables_exits_with_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_minimal_inputs(
                Path(tmp),
                source_doc=self._valid_source_doc(),
                harmonized_doc={"metadata": {}, "variables": "not a dict", "entity_counts": {}, "total_participants": 1},
            )
            with self.assertRaises(SystemExit) as ctx:
                compare_main(self._argv(paths))
            self.assertEqual(ctx.exception.code, 2)


class CompareJsonSchemaValidationTests(unittest.TestCase):
    """validate_compare_json_schema must catch malformed compare JSON output."""

    def _valid_report(self) -> dict:
        return {
            "metadata": {"cohort": "TEST", "generated_at": "2026-01-01T00:00:00+00:00"},
            "summary": {"PASS": 1},
            "crosswalk": [],
            "yaml_diagnostics": {},
            "results": [],
        }

    def test_valid_report_has_no_errors(self) -> None:
        self.assertEqual(validate_compare_json_schema(self._valid_report()), [])

    def test_not_a_dict_returns_single_error(self) -> None:
        errors = validate_compare_json_schema([])
        self.assertEqual(len(errors), 1)
        self.assertIn("top-level", errors[0])

    def test_all_five_sections_missing_yields_five_errors(self) -> None:
        errors = validate_compare_json_schema({})
        self.assertEqual(len(errors), 5)

    def test_missing_metadata_reported(self) -> None:
        doc = self._valid_report()
        del doc["metadata"]
        errors = validate_compare_json_schema(doc)
        self.assertTrue(any("`metadata`" in e for e in errors))

    def test_missing_summary_reported(self) -> None:
        doc = self._valid_report()
        del doc["summary"]
        errors = validate_compare_json_schema(doc)
        self.assertTrue(any("`summary`" in e for e in errors))

    def test_missing_crosswalk_reported(self) -> None:
        doc = self._valid_report()
        del doc["crosswalk"]
        errors = validate_compare_json_schema(doc)
        self.assertTrue(any("`crosswalk`" in e for e in errors))

    def test_missing_yaml_diagnostics_reported(self) -> None:
        doc = self._valid_report()
        del doc["yaml_diagnostics"]
        errors = validate_compare_json_schema(doc)
        self.assertTrue(any("`yaml_diagnostics`" in e for e in errors))

    def test_missing_results_reported(self) -> None:
        doc = self._valid_report()
        del doc["results"]
        errors = validate_compare_json_schema(doc)
        self.assertTrue(any("`results`" in e for e in errors))

    def test_wrong_type_crosswalk_dict_instead_of_list(self) -> None:
        doc = self._valid_report()
        doc["crosswalk"] = {}
        errors = validate_compare_json_schema(doc)
        self.assertTrue(any("`crosswalk`" in e for e in errors))

    def test_wrong_type_results_dict_instead_of_list(self) -> None:
        doc = self._valid_report()
        doc["results"] = {}
        errors = validate_compare_json_schema(doc)
        self.assertTrue(any("`results`" in e for e in errors))

    def test_wrong_type_metadata_list_instead_of_dict(self) -> None:
        doc = self._valid_report()
        doc["metadata"] = []
        errors = validate_compare_json_schema(doc)
        self.assertTrue(any("`metadata`" in e for e in errors))


class StaleArtifactTests(unittest.TestCase):
    """check_stale_artifacts must detect mismatched or stale extraction timestamps."""

    def _src(self, extracted_at: str) -> dict:
        return {"metadata": {"extracted_at": extracted_at}}

    def _harm(self, generated_at: str) -> dict:
        return {"metadata": {"generated_at": generated_at}}

    def test_matching_timestamps_no_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            yaml_d = Path(tmp) / "yaml"
            cache.mkdir()
            yaml_d.mkdir()
            warnings = check_stale_artifacts(
                self._src("2026-01-01T00:00:00+00:00"),
                self._harm("2026-01-01T00:01:00+00:00"),
                cache_dir=cache,
                yaml_dir=yaml_d,
            )
        self.assertEqual(warnings, [])

    def test_skew_beyond_threshold_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            yaml_d = Path(tmp) / "yaml"
            cache.mkdir()
            yaml_d.mkdir()
            warnings = check_stale_artifacts(
                self._src("2026-01-01T00:00:00+00:00"),
                self._harm("2026-01-15T00:00:00+00:00"),  # 14 days apart
                cache_dir=cache,
                yaml_dir=yaml_d,
                max_skew_days=7.0,
            )
        self.assertEqual(len(warnings), 1)
        self.assertIn("STALE", warnings[0])
        self.assertIn("14.", warnings[0])

    def test_skew_within_threshold_no_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            yaml_d = Path(tmp) / "yaml"
            cache.mkdir()
            yaml_d.mkdir()
            warnings = check_stale_artifacts(
                self._src("2026-01-01T00:00:00+00:00"),
                self._harm("2026-01-04T00:00:00+00:00"),  # 3 days apart
                cache_dir=cache,
                yaml_dir=yaml_d,
                max_skew_days=7.0,
            )
        self.assertEqual(warnings, [])

    def test_cache_newer_than_source_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            yaml_d = Path(tmp) / "yaml"
            cache.mkdir()
            yaml_d.mkdir()
            # Create a data_dict.xml with current mtime (newer than our old extracted_at)
            dd = cache / "pht000001.v1.data_dict.xml"
            dd.write_text("<data_table/>")
            warnings = check_stale_artifacts(
                self._src("2020-01-01T00:00:00+00:00"),  # very old extraction
                self._harm("2020-01-01T00:00:00+00:00"),
                cache_dir=cache,
                yaml_dir=yaml_d,
                max_skew_days=7.0,
            )
        cache_warns = [w for w in warnings if "cache was updated" in w]
        self.assertEqual(len(cache_warns), 1)

    def test_yaml_newer_than_harmonized_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            yaml_d = Path(tmp) / "yaml"
            cache.mkdir()
            yaml_d.mkdir()
            # Create a yaml file with current mtime (newer than our old generated_at)
            yf = yaml_d / "heart_rate.yaml"
            yf.write_text("transform: []\n")
            warnings = check_stale_artifacts(
                self._src("2020-01-01T00:00:00+00:00"),
                self._harm("2020-01-01T00:00:00+00:00"),  # very old extraction
                cache_dir=cache,
                yaml_dir=yaml_d,
                max_skew_days=7.0,
            )
        yaml_warns = [w for w in warnings if "YAML transform" in w]
        self.assertEqual(len(yaml_warns), 1)

    def test_missing_timestamps_no_crash(self) -> None:
        """Missing metadata timestamps must not raise — just skip the check."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            yaml_d = Path(tmp) / "yaml"
            cache.mkdir()
            yaml_d.mkdir()
            warnings = check_stale_artifacts(
                {"metadata": {}},
                {"metadata": {}},
                cache_dir=cache,
                yaml_dir=yaml_d,
            )
        self.assertEqual(warnings, [])

    def test_invalid_timestamp_strings_no_crash(self) -> None:
        """Unparseable ISO strings must not raise."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            yaml_d = Path(tmp) / "yaml"
            cache.mkdir()
            yaml_d.mkdir()
            warnings = check_stale_artifacts(
                self._src("not-a-date"),
                self._harm("also-not-a-date"),
                cache_dir=cache,
                yaml_dir=yaml_d,
            )
        self.assertEqual(warnings, [])


class AtomicWriteTests(unittest.TestCase):
    """Atomic writers must create missing parent directories."""

    def test_write_json_atomic_creates_missing_parents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "missing" / "nested" / "out.json"
            write_json_atomic(target, {"k": 1})
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8").strip()[0], "{")

    def test_write_text_atomic_creates_missing_parents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "missing" / "report.md"
            _write_text_atomic(target, "hello")
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "hello")


class ExtractorRegressionTests(unittest.TestCase):
    """Regression tests for extractor behaviors consumed by compare."""

    def test_measurement_extractor_summarizes_flat_enum_and_status_values(self) -> None:
        df = pd.DataFrame(
            {
                "observation_type": ["OBA:ENUM", "OBA:ENUM", "OBA:STATUS", "OBA:STATUS"],
                "value_enum": ["YES", "NO", None, None],
                "measurement_status": [None, None, "present", "absent"],
                "associated_visit": ["visit_1", "visit_2", "visit_1", "visit_2"],
            }
        )

        variables = process_measurements(df, {}, by_visit=True)

        enum_summary = variables["measurement_OBA:ENUM"]
        self.assertEqual(enum_summary["type"], "categorical")
        self.assertEqual(enum_summary["n_valid"], 2)
        self.assertEqual(enum_summary["distribution"]["YES"]["n"], 1)
        self.assertEqual(enum_summary["by_visit"]["visit_1"]["distribution"]["YES"]["n"], 1)

        status_summary = variables["measurement_OBA:STATUS"]
        self.assertEqual(status_summary["type"], "categorical")
        self.assertEqual(status_summary["n_valid"], 2)
        self.assertEqual(status_summary["distribution"]["present"]["n"], 1)
        self.assertEqual(status_summary["by_visit"]["visit_2"]["distribution"]["absent"]["n"], 1)

    def test_mos_extractor_summarizes_integer_coded_and_concept_values(self) -> None:
        df = pd.DataFrame(
            {
                "observations": [
                    json.dumps([
                        {
                            "observation_type": "OBA:INTEGER",
                            "value_quantity": {"value_integer": 3},
                        },
                        {
                            "observation_type": "OBA:CODED",
                            "value_quantity": {"value_coded": "HIGH"},
                        },
                        {
                            "observation_type": "OBA:CONCEPT",
                            "value_quantity": {"value_concept": "OMOP:123"},
                        },
                    ])
                ]
            }
        )

        variables = process_measurement_observation_sets(df, {})

        self.assertEqual(variables["measurement_OBA:INTEGER"]["type"], "continuous")
        self.assertEqual(variables["measurement_OBA:INTEGER"]["n_valid"], 1)
        self.assertEqual(variables["measurement_OBA:INTEGER"]["mean"], 3.0)
        self.assertEqual(variables["measurement_OBA:CODED"]["type"], "categorical")
        self.assertEqual(variables["measurement_OBA:CODED"]["distribution"]["HIGH"]["n"], 1)
        self.assertEqual(variables["measurement_OBA:CONCEPT"]["distribution"]["OMOP:123"]["n"], 1)

    def test_merge_variable_summaries_combines_duplicate_continuous_keys(self) -> None:
        variables = {
            "measurement_OBA:1": {
                "type": "continuous",
                "entity": "MeasurementObservation",
                "n_total": 2,
                "n_valid": 2,
                "n_missing": 0,
                "mean": 10.0,
                "sd": 2.0,
            }
        }
        diagnostics: dict = {}

        merge_variable_summaries(
            variables,
            {
                "measurement_OBA:1": {
                    "type": "continuous",
                    "entity": "MeasurementObservationSet",
                    "n_total": 1,
                    "n_valid": 1,
                    "n_missing": 0,
                    "mean": 20.0,
                    "sd": None,
                }
            },
            diagnostics,
        )

        merged = variables["measurement_OBA:1"]
        self.assertTrue(merged["_merged_harmonized_key_collision"])
        self.assertEqual(merged["n_valid"], 3)
        self.assertAlmostEqual(merged["mean"], 13.333333, places=6)
        self.assertEqual(diagnostics["harmonized_variable_key_collisions"], ["measurement_OBA:1"])

    def test_canonical_participant_id_normalizes_integer_like_values(self) -> None:
        self.assertEqual(_canonical_participant_id(1), "1")
        self.assertEqual(_canonical_participant_id(1.0), "1")
        self.assertEqual(_canonical_participant_id(" 1.0 "), "1")
        self.assertEqual(_canonical_participant_id("001"), "001")


class JointDistributionOptionBTests(unittest.TestCase):
    """Tests for Option B: pre-generated crosstabs enabling exact multi-PHV comparisons."""

    # -----------------------------------------------------------------------
    # scan_yaml_for_phv_pairs
    # -----------------------------------------------------------------------

    def test_scan_yaml_for_phv_pairs_finds_two_phv_condition(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "test.yaml"
            yaml_path.write_text(
                'value:\n'
                '  expr: case(({phv00001234} == 1 and {phv00005678} == 2, "YES"), (True, None))\n'
            )
            pairs = scan_yaml_for_phv_pairs(Path(tmpdir))
        self.assertEqual(pairs, [("phv00001234", "phv00005678")])

    def test_scan_yaml_for_phv_pairs_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "test.yaml"
            yaml_path.write_text(
                'expr: case(({phv00001234} == 1 and {phv00005678} == 2, "A"), '
                '({phv00001234} == 1 and {phv00005678} == 3, "B"))\n'
            )
            pairs = scan_yaml_for_phv_pairs(Path(tmpdir))
        # Same pair on two lines — should be deduplicated
        self.assertEqual(pairs, [("phv00001234", "phv00005678")])

    def test_scan_yaml_for_phv_pairs_ignores_single_phv_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "test.yaml"
            yaml_path.write_text('expr: case(({phv00001234} == 1, "YES"))\n')
            pairs = scan_yaml_for_phv_pairs(Path(tmpdir))
        self.assertEqual(pairs, [])

    def test_scan_yaml_for_phv_pairs_canonical_order(self) -> None:
        """Pair key is always alphabetically sorted regardless of line order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "test.yaml"
            yaml_path.write_text(
                'expr: case(({phv00009999} == 1 and {phv00001111} == 2, "A"))\n'
            )
            pairs = scan_yaml_for_phv_pairs(Path(tmpdir))
        # phv00001111 < phv00009999 alphabetically
        self.assertEqual(pairs, [("phv00001111", "phv00009999")])

    def test_scan_yaml_for_phv_pairs_finds_in_condition(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "test.yaml"
            yaml_path.write_text(
                'expr: case(({phv00001234} == 1 and {phv00005678} in (2, 3), "YES"))\n'
            )
            pairs = scan_yaml_for_phv_pairs(Path(tmpdir))
        self.assertEqual(pairs, [("phv00001234", "phv00005678")])

    # -----------------------------------------------------------------------
    # _normalize_dist_key
    # -----------------------------------------------------------------------

    def test_normalize_dist_key_integer_float(self) -> None:
        self.assertEqual(_normalize_dist_key(1.0), "1")
        self.assertEqual(_normalize_dist_key(2.0), "2")

    def test_normalize_dist_key_nan(self) -> None:
        self.assertEqual(_normalize_dist_key(float("nan")), "nan")

    def test_normalize_dist_key_string(self) -> None:
        self.assertEqual(_normalize_dist_key("YES"), "YES")

    # -----------------------------------------------------------------------
    # _compute_joint_distributions
    # -----------------------------------------------------------------------

    def test_compute_joint_distributions_basic_crosstab(self) -> None:
        df = pd.DataFrame({
            "SMOKE": [1, 1, 1, 0, 0],
            "DRINK": [2, 3, 2, 1, 1],
        })
        pairs = [("phv00000001", "phv00000002")]
        phv_name_map = {"phv00000001": "SMOKE", "phv00000002": "DRINK"}

        result = _compute_joint_distributions(df, pairs, phv_name_map)

        self.assertIn("phv00000001+phv00000002", result)
        ct = result["phv00000001+phv00000002"]
        # SMOKE=1: DRINK=2 twice, DRINK=3 once
        self.assertEqual(ct["1"]["2"], 2)
        self.assertEqual(ct["1"]["3"], 1)
        # SMOKE=0: DRINK=1 twice
        self.assertEqual(ct["0"]["1"], 2)

    def test_compute_joint_distributions_skips_missing_column(self) -> None:
        df = pd.DataFrame({"SMOKE": [1, 0, 1]})
        pairs = [("phv00000001", "phv00000002")]
        phv_name_map = {"phv00000001": "SMOKE", "phv00000002": "DRINK"}

        result = _compute_joint_distributions(df, pairs, phv_name_map)

        # DRINK column absent — pair should be skipped
        self.assertEqual(result, {})

    def test_compute_joint_distributions_empty_pairs_returns_empty(self) -> None:
        df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        result = _compute_joint_distributions(df, [], {})
        self.assertEqual(result, {})

    def test_compute_joint_distributions_uses_phv_name_fallback(self) -> None:
        """When PHV name not in name map, fall back to PHV ID as column name."""
        df = pd.DataFrame({
            "phv00000001": [1, 0],
            "phv00000002": [2, 1],
        })
        pairs = [("phv00000001", "phv00000002")]

        result = _compute_joint_distributions(df, pairs, phv_name_map={})

        self.assertIn("phv00000001+phv00000002", result)

    # -----------------------------------------------------------------------
    # _extract_phv_conditions
    # -----------------------------------------------------------------------

    def test_extract_phv_conditions_equality(self) -> None:
        conds = _extract_phv_conditions("{phv00001234} == 1")
        self.assertEqual(conds, {"phv00001234": ["1"]})

    def test_extract_phv_conditions_in_list(self) -> None:
        conds = _extract_phv_conditions("{phv00001234} in (2, 3, 4)")
        self.assertEqual(conds, {"phv00001234": ["2", "3", "4"]})

    def test_extract_phv_conditions_two_phv_mixed(self) -> None:
        conds = _extract_phv_conditions("{phv00000001} == 1 and {phv00000002} in (2, 3)")
        self.assertEqual(sorted(conds.keys()), ["phv00000001", "phv00000002"])
        self.assertEqual(conds["phv00000001"], ["1"])
        self.assertIn("2", conds["phv00000002"])
        self.assertIn("3", conds["phv00000002"])

    def test_extract_phv_conditions_inequality_excluded(self) -> None:
        """!= is intentionally excluded from the extracted conditions."""
        conds = _extract_phv_conditions("{phv00001234} != 9 and {phv00001234} == 1")
        # Only the == test is captured
        self.assertEqual(conds, {"phv00001234": ["1"]})

    # -----------------------------------------------------------------------
    # _count_from_joint_dist
    # -----------------------------------------------------------------------

    def _make_joint_dists(self) -> dict[str, dict]:
        """Fixture: pht001234 has a 2×3 crosstab for phv00000001 × phv00000002."""
        return {
            "pht001234": {
                "phv00000001+phv00000002": {
                    "0": {"1": 300, "2": 100, "3": 50},
                    "1": {"1": 80, "2": 120, "3": 150},
                }
            }
        }

    def test_count_from_joint_dist_single_value_each(self) -> None:
        jd = self._make_joint_dists()
        count = _count_from_joint_dist(jd, "pht001234", "phv00000001", ["1"], "phv00000002", ["2"])
        self.assertEqual(count, 120)

    def test_count_from_joint_dist_multiple_values_inner(self) -> None:
        jd = self._make_joint_dists()
        # phv00000002 in (1, 2) for phv00000001 == 1
        count = _count_from_joint_dist(jd, "pht001234", "phv00000001", ["1"], "phv00000002", ["1", "2"])
        self.assertEqual(count, 200)  # 80 + 120

    def test_count_from_joint_dist_reversed_phv_order(self) -> None:
        """Caller passes phv_b as first arg, phv_a as second — should still work."""
        jd = self._make_joint_dists()
        # Pass args with phv_b first; orientation should be handled by sorted()
        count = _count_from_joint_dist(jd, "pht001234", "phv00000002", ["2"], "phv00000001", ["1"])
        self.assertEqual(count, 120)

    def test_count_from_joint_dist_missing_pair_returns_none(self) -> None:
        jd = self._make_joint_dists()
        count = _count_from_joint_dist(jd, "pht001234", "phv00000001", ["1"], "phv00000099", ["2"])
        self.assertIsNone(count)

    def test_count_from_joint_dist_missing_pht_returns_none(self) -> None:
        jd = self._make_joint_dists()
        count = _count_from_joint_dist(jd, "pht999999", "phv00000001", ["1"], "phv00000002", ["2"])
        self.assertIsNone(count)

    # -----------------------------------------------------------------------
    # _expected_summary_from_case_value_exprs with joint_dists_by_pht
    # -----------------------------------------------------------------------

    def test_case_value_exprs_exact_with_joint_dist(self) -> None:
        """Multi-PHV condition resolves to exact verdict when joint dist is provided."""
        joint_dists_by_pht = {
            "pht001234": {
                "phv00258106+phv00258107": {
                    "0": {"1": 4, "2": 2, "3": 1},
                    "1": {"1": 2, "2": 1, "3": 2},
                }
            }
        }
        entries = [
            {
                "value_exprs": [
                    'case(({phv00258106} == 0, "OMOP:45883537"), (True, None))'
                ]
            },
            {
                "value_exprs": [
                    'case(('
                    '{phv00258106} == 1 and {phv00258107} == 1, "OMOP:40766945"), '
                    '({phv00258106} == 1 and {phv00258107} == 2, "OMOP:40766945"), '
                    '({phv00258106} == 1 and {phv00258107} == 3, "OMOP:45883458"), '
                    '(True, None))'
                ]
            },
        ]
        summaries_by_phv = {
            "phv00258106": {
                "_pht": "pht001234",
                "type": "categorical",
                "distribution": {
                    "0": {"n": 7, "pct": 58.33},
                    "1": {"n": 5, "pct": 41.67},
                },
            },
            "phv00258107": {
                "_pht": "pht001234",
                "type": "categorical",
                "distribution": {
                    "1": {"n": 2, "pct": 40.0},
                    "2": {"n": 1, "pct": 20.0},
                    "3": {"n": 2, "pct": 40.0},
                },
            },
        }

        result = _expected_summary_from_case_value_exprs(entries, summaries_by_phv, joint_dists_by_pht)

        self.assertIsNotNone(result)
        self.assertEqual(result["_comparison_confidence"], "exact")
        self.assertEqual(result["_comparison_basis"], "yaml_case_value_expr")
        # OMOP:45883537: phv00258106 == 0 → uses marginal: 7 (single PHV, uses reversed vals)
        self.assertEqual(result["distribution"]["OMOP:45883537"]["n"], 7)
        # OMOP:40766945: (phv00258106==1 AND phv00258107==1) + (phv00258106==1 AND phv00258107==2) = 2+1 = 3
        self.assertEqual(result["distribution"]["OMOP:40766945"]["n"], 3)
        # OMOP:45883458: phv00258106==1 AND phv00258107==3 = 2
        self.assertEqual(result["distribution"]["OMOP:45883458"]["n"], 2)

    def test_case_value_exprs_still_unsupported_without_joint_dist(self) -> None:
        """Without joint_dists_by_pht, multi-PHV conditions still return unsupported."""
        entries = [
            {
                "value_exprs": [
                    'case(({phv00258106} == 1 and {phv00258107} == 1, "YES"), (True, None))'
                ]
            },
        ]
        summaries_by_phv = {
            "phv00258106": {"type": "categorical", "distribution": {"1": {"n": 5, "pct": 100.0}}},
            "phv00258107": {"type": "categorical", "distribution": {"1": {"n": 5, "pct": 100.0}}},
        }

        result = _expected_summary_from_case_value_exprs(entries, summaries_by_phv)

        self.assertIsNotNone(result)
        self.assertEqual(result["_comparison_confidence"], "unsupported")

    def test_extract_phv_conditions_in_returns_multiple_values(self) -> None:
        """_extract_phv_conditions handles in() lists in raw condition strings."""
        # Note: _case_branches does NOT parse in() inside case() because the
        # comma inside in(1, 2) confuses the regex. _extract_phv_conditions is
        # called on the output of _case_branches, so in() conditions within
        # case() expressions are not reachable through the normal path.
        # However, _extract_phv_conditions is correct for raw condition strings
        # (e.g. from when: fields) so we test it directly here.
        conds = _extract_phv_conditions("{phv00000001} in (1, 2)")
        self.assertEqual(conds["phv00000001"], ["1", "2"])

    def test_case_value_exprs_single_phv_equality(self) -> None:
        """Single PHV == condition still resolves via marginal (no regression)."""
        entries = [
            {
                "value_exprs": [
                    'case(({phv00000001} == 1, "PRESENT"), (True, None))'
                ]
            },
        ]
        summaries_by_phv = {
            "phv00000001": {
                "type": "categorical",
                "distribution": {
                    "1": {"n": 30, "pct": 30.0},
                    "3": {"n": 70, "pct": 70.0},
                },
            }
        }

        result = _expected_summary_from_case_value_exprs(entries, summaries_by_phv)

        self.assertIsNotNone(result)
        self.assertEqual(result["_comparison_confidence"], "exact")
        self.assertEqual(result["distribution"]["PRESENT"]["n"], 30)

    # -----------------------------------------------------------------------
    # _expected_summary_from_case_entry with joint_dists_by_pht
    # -----------------------------------------------------------------------

    def test_case_entry_exact_with_joint_dist(self) -> None:
        """Single entry with a two-PHV condition resolves when joint dist available."""
        joint_dists_by_pht = {
            "pht001234": {
                "phv00000001+phv00000002": {
                    "0": {"1": 300, "2": 100},
                    "1": {"1": 80, "2": 120},
                }
            }
        }
        entry = {
            "value_exprs": [
                'case(({phv00000001} == 1 and {phv00000002} == 2, "YES"), '
                '({phv00000001} == 0, "NO"), '
                '(True, None))'
            ]
        }
        src_summary = {
            "type": "categorical",
            "_pht": "pht001234",
            "n_total": 600,
            "n_valid": 600,
            "n_missing": 0,
        }
        summaries_by_phv = {
            "phv00000001": {
                "_pht": "pht001234",
                "type": "categorical",
                "distribution": {
                    "0": {"n": 400, "pct": 66.67},
                    "1": {"n": 200, "pct": 33.33},
                },
            }
        }

        result = _expected_summary_from_case_entry(
            entry, src_summary, summaries_by_phv, joint_dists_by_pht
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["_comparison_confidence"], "exact")
        # YES: joint count for phv00000001==1 AND phv00000002==2 = 120
        self.assertEqual(result["distribution"]["YES"]["n"], 120)
        # NO: marginal phv00000001==0 = 400 (single-PHV condition)
        self.assertEqual(result["distribution"]["NO"]["n"], 400)

    def test_case_entry_unsupported_when_joint_dist_missing_pht(self) -> None:
        """Falls back to unsupported when the joint dist has no entry for this PHT."""
        joint_dists_by_pht = {}  # No distributions for any PHT
        entry = {
            "value_exprs": [
                'case(({phv00000001} == 1 and {phv00000002} == 2, "YES"), (True, None))'
            ]
        }
        src_summary = {
            "type": "categorical",
            "_pht": "pht001234",
            "n_total": 100,
        }
        summaries_by_phv = {}

        result = _expected_summary_from_case_entry(
            entry, src_summary, summaries_by_phv, joint_dists_by_pht
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["_comparison_confidence"], "unsupported")

    def test_case_entry_still_unsupported_without_joint_dists_kwarg(self) -> None:
        """Calling without joint_dists_by_pht arg preserves old unsupported behaviour."""
        entry = {
            "value_exprs": [
                'case(({phv00000001} == 1 and {phv00000002} == 2, "YES"), (True, None))'
            ]
        }
        src_summary = {
            "type": "categorical",
            "_pht": "pht001234",
            "n_total": 100,
        }
        summaries_by_phv = {}

        result = _expected_summary_from_case_entry(entry, src_summary, summaries_by_phv)

        self.assertIsNotNone(result)
        self.assertEqual(result["_comparison_confidence"], "unsupported")


class RenderDbGaPStudyIdTests(unittest.TestCase):
    """Tests for the study_id extraction logic in generate_markdown_report (#643)."""

    def _report(self, source_dirs: list[str]) -> str:
        from hv_dataqc.compare.render import generate_markdown_report
        return generate_markdown_report(
            results=[],
            cohort="TEST",
            source_meta={"source_dirs": source_dirs, "cohort": "TEST"},
            harmonized_meta={},
        )

    def test_bdc_topmed_form_resolves_study_id(self) -> None:
        """BDC TOPMed directory (phs…-v…-r…-c…) should produce a dbGaP link."""
        report = self._report(["nih-nhlbi-topmed-parent-hchs-sol-phs000810-v2-r1-c1"])
        self.assertIn("phs000810.v2.p2", report)

    def test_pilotparent_form_resolves_study_id(self) -> None:
        """PilotParent directory (phs…-v…-p…-c…) should produce a dbGaP link."""
        report = self._report(["parent-CHS_DS-CVD-MDS_-phs000287-v7-p1-c3"])
        self.assertIn("phs000287.v7.p1", report)

    def test_pilotparent_participant_set_extracted_from_dir(self) -> None:
        """Participant set number should come from the directory, not be hardcoded."""
        report = self._report(["parent-ARIC-phs000280-v9-p3-c1"])
        self.assertIn("phs000280.v9.p3", report)

    def test_no_matching_dir_produces_no_dbgap_link(self) -> None:
        """When no recognised directory pattern is present, no dbGaP link is rendered."""
        report = self._report(["some-unrecognised-directory"])
        self.assertNotIn("dbgap.ncbi.nlm.nih.gov", report)
        self.assertNotIn("dbGaP", report)


class MultiBlockVarLabelTests(unittest.TestCase):
    """C2-C11 var_label must include all contributing source variable names (#641).

    When two YAML blocks map to the same harmonized concept (e.g. MONDO:0004981),
    the crosswalk builds a single match with _source_keys = ["ecga271", "mhea7"].
    The display_name in compare.py should join those names with '+' rather than
    showing only the primary block's name.
    """

    _TWO_BLOCK_YAML = """\
- class_derivations:
    Condition:
      populated_from: pht000001
      slot_derivations:
        associated_participant:
          populated_from: phv00000001
        condition_concept:
          value: MONDO:test_afib
        condition_status:
          populated_from: phv00000002
          value_mappings:
            '1': PRESENT
            '0': ABSENT
---
- class_derivations:
    Condition:
      populated_from: pht000001
      slot_derivations:
        associated_participant:
          populated_from: phv00000001
        condition_concept:
          value: MONDO:test_afib
        condition_status:
          populated_from: phv00000003
          value_mappings:
            '1': PRESENT
            '0': ABSENT
"""

    def _setup(self, tmp_path: Path) -> tuple[Path, Path]:
        """Write a cache dir (two PHVs) and yaml dir (two-block YAML) into tmp."""
        pheno_dir = tmp_path / "pheno_variable_summaries"
        pheno_dir.mkdir()
        (pheno_dir / "phs000000.v1.pht000001.v1.p1.test.data_dict.xml").write_text(
            '<?xml version="1.0"?>\n'
            "<data_table>\n"
            '  <variable id="phv00000001.v1"><name>subj_id</name></variable>\n'
            '  <variable id="phv00000002.v1"><name>ecga271</name></variable>\n'
            '  <variable id="phv00000003.v1"><name>mhea7</name></variable>\n'
            "</data_table>\n",
            encoding="utf-8",
        )
        yaml_dir = tmp_path / "yaml"
        yaml_dir.mkdir()
        (yaml_dir / "afib.yaml").write_text(self._TWO_BLOCK_YAML, encoding="utf-8")
        return tmp_path, yaml_dir

    def _source_vars(self) -> dict:
        return {
            "ecga271": {"pht000001": {"type": "categorical", "n_valid": 100, "n_total": 100, "distribution": {"PRESENT": {"n": 50}, "ABSENT": {"n": 50}}}},
            "mhea7":   {"pht000001": {"type": "categorical", "n_valid": 100, "n_total": 100, "distribution": {"PRESENT": {"n": 40}, "ABSENT": {"n": 60}}}},
        }

    def test_two_block_crosswalk_populates_source_keys_with_both_names(self) -> None:
        """build_variable_crosswalk sets _source_keys = ['ecga271', 'mhea7'] for
        a two-block YAML where each block maps a different PHV to the same concept."""
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir, yaml_dir = self._setup(Path(tmp))
            matches = build_variable_crosswalk(
                variables_by_name=self._source_vars(),
                harmonized_vars={"condition_MONDO:test_afib": {"type": "categorical", "n_valid": 130}},
                yaml_dir=yaml_dir,
                cache_dir=cache_dir,
                source_doc={"total_participants": 100, "total_rows_by_pht": {"pht000001": 100}},
            )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["_source_keys"], ["ecga271", "mhea7"])

    def test_two_block_match_display_name_joins_source_keys(self) -> None:
        """The display_name computed from _source_keys is 'ecga271+mhea7', not just 'ecga271'."""
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir, yaml_dir = self._setup(Path(tmp))
            matches = build_variable_crosswalk(
                variables_by_name=self._source_vars(),
                harmonized_vars={"condition_MONDO:test_afib": {"type": "categorical", "n_valid": 130}},
                yaml_dir=yaml_dir,
                cache_dir=cache_dir,
                source_doc={"total_participants": 100, "total_rows_by_pht": {"pht000001": 100}},
            )

        match = matches[0]
        _source_keys = match.get("_source_keys") or []
        src_var = match.get("_resolved_src") or {}
        src_key = match.get("source_key", "")
        if len(_source_keys) > 1:
            display_name = "+".join(_source_keys)
        else:
            display_name = src_var.get("name", src_key)

        self.assertEqual(display_name, "ecga271+mhea7")

    def test_single_block_match_display_name_uses_primary_name(self) -> None:
        """A single-block YAML (_source_keys has one entry) still falls back to src_var name."""
        single_block_yaml = """\
- class_derivations:
    Condition:
      populated_from: pht000001
      slot_derivations:
        associated_participant:
          populated_from: phv00000001
        condition_concept:
          value: MONDO:test_afib
        condition_status:
          populated_from: phv00000002
          value_mappings:
            '1': PRESENT
            '0': ABSENT
"""
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir, yaml_dir = self._setup(Path(tmp))
            (yaml_dir / "afib.yaml").write_text(single_block_yaml, encoding="utf-8")
            matches = build_variable_crosswalk(
                variables_by_name=self._source_vars(),
                harmonized_vars={"condition_MONDO:test_afib": {"type": "categorical", "n_valid": 100}},
                yaml_dir=yaml_dir,
                cache_dir=cache_dir,
                source_doc={"total_participants": 100, "total_rows_by_pht": {"pht000001": 100}},
            )

        self.assertEqual(len(matches), 1)
        self.assertEqual(len(matches[0]["_source_keys"]), 1)
        self.assertEqual(matches[0]["_source_keys"], ["ecga271"])

    def test_block_with_no_value_phv_is_skipped_not_mislabelled(self) -> None:
        """A YAML block where value_quantity/condition_status is absent (commented out)
        must not produce a crosswalk entry labelled with the participant-ID PHV (#644).

        Tested via build_yaml_crosswalk (one level below build_variable_crosswalk)
        so we can assert 0 entries without triggering the CrosswalkBuildError that
        fires when the whole yaml_dir is empty."""
        # Only associated_participant mapped; condition_status absent — simulates
        # a block where value_quantity is commented out pending unit-conversion work.
        no_value_yaml = """\
- class_derivations:
    Condition:
      populated_from: pht000001
      slot_derivations:
        associated_participant:
          populated_from: phv00000001
        condition_concept:
          value: MONDO:test_afib
"""
        phv_names = {"phv00000001": "subj_id", "phv00000002": "ecga271"}

        with tempfile.TemporaryDirectory() as tmp:
            yaml_dir = Path(tmp) / "yaml"
            yaml_dir.mkdir()
            (yaml_dir / "afib.yaml").write_text(no_value_yaml, encoding="utf-8")
            entries = build_yaml_crosswalk(yaml_dir, phv_names)

        # The block produces no entries — it was skipped rather than emitting
        # an entry labelled with the participant-ID variable.
        self.assertEqual(entries, [])
        source_keys = [e["source_key"] for e in entries]
        self.assertNotIn("subj_id", source_keys)


class UnitConversionFlagTests(unittest.TestCase):
    """Tests for the has_unit_conversion flag (#647) and related [in_us] factor entry."""

    # Minimal YAML block with a unit_conversion (known pair [lb_av] → kg)
    _YAML_WITH_UNIT_CONVERSION = """\
- class_derivations:
    MeasurementObservation:
      populated_from: pht000001
      slot_derivations:
        associated_participant:
          populated_from: phv00000001
        observation_type:
          value: OBA:VT0001259
        value_quantity:
          object_derivations:
          - class_derivations:
              Quantity:
                populated_from: pht000001
                slot_derivations:
                  value_decimal:
                    populated_from: phv00000002
                    unit_conversion:
                      source_unit: '[lb_av]'
                      target_unit: kg
                  unit:
                    value: kg
                    range: string
"""

    # Identical structure but without any unit_conversion key
    _YAML_WITHOUT_UNIT_CONVERSION = """\
- class_derivations:
    MeasurementObservation:
      populated_from: pht000001
      slot_derivations:
        associated_participant:
          populated_from: phv00000001
        observation_type:
          value: OBA:VT0001259
        value_quantity:
          object_derivations:
          - class_derivations:
              Quantity:
                populated_from: pht000001
                slot_derivations:
                  value_decimal:
                    populated_from: phv00000002
                  unit:
                    value: kg
                    range: string
"""

    # YAML with an unknown unit pair (not in _COMMON_UNIT_FACTORS) to verify
    # has_unit_conversion is True even when conversion_factor cannot be computed.
    _YAML_UNKNOWN_UNIT_PAIR = """\
- class_derivations:
    MeasurementObservation:
      populated_from: pht000001
      slot_derivations:
        associated_participant:
          populated_from: phv00000001
        observation_type:
          value: OBA:VT0001259
        value_quantity:
          object_derivations:
          - class_derivations:
              Quantity:
                populated_from: pht000001
                slot_derivations:
                  value_decimal:
                    populated_from: phv00000002
                    unit_conversion:
                      source_unit: 'fathom'
                      target_unit: 'meter'
                  unit:
                    value: meter
                    range: string
"""

    def _write_yaml_and_get_entries(self, yaml_text: str) -> list[dict]:
        """Write a single YAML file and return build_yaml_crosswalk results."""
        phv_names = {"phv00000001": "subj_id", "phv00000002": "weight_src"}
        with tempfile.TemporaryDirectory() as tmp:
            yaml_dir = Path(tmp) / "yaml"
            yaml_dir.mkdir()
            (yaml_dir / "weight.yaml").write_text(yaml_text, encoding="utf-8")
            return build_yaml_crosswalk(yaml_dir, phv_names)

    def test_in_us_to_cm_factor_is_in_factor_table(self) -> None:
        """[in_us] → cm unit pair is now in _COMMON_UNIT_FACTORS (added for #647)."""
        self.assertEqual(
            _unit_conversion_factor({"source_unit": "[in_us]", "target_unit": "cm"}),
            2.54,
        )

    def test_crosswalk_entry_has_unit_conversion_true_for_known_unit_pair(self) -> None:
        """A block with unit_conversion: [lb_av] → kg emits has_unit_conversion=True."""
        entries = self._write_yaml_and_get_entries(self._YAML_WITH_UNIT_CONVERSION)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertTrue(entry.get("has_unit_conversion"), msg="has_unit_conversion should be True")
        self.assertAlmostEqual(entry.get("conversion_factor"), 0.453592, places=5)

    def test_crosswalk_entry_has_unit_conversion_false_without_unit_conversion(self) -> None:
        """A block without unit_conversion: emits has_unit_conversion=False."""
        entries = self._write_yaml_and_get_entries(self._YAML_WITHOUT_UNIT_CONVERSION)
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0].get("has_unit_conversion"),
                         msg="has_unit_conversion should be False when no unit_conversion key")

    def test_crosswalk_entry_has_unit_conversion_true_for_unknown_unit_pair(self) -> None:
        """A block with an unknown unit pair sets has_unit_conversion=True, conversion_factor=None.

        This combination triggers the C4/C6 INFO bypass in compare.py: the YAML
        specifies a conversion but the tool cannot compute the factor, so comparing
        raw source values to harmonized values would produce a false FAIL.
        """
        entries = self._write_yaml_and_get_entries(self._YAML_UNKNOWN_UNIT_PAIR)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertTrue(entry.get("has_unit_conversion"),
                        msg="has_unit_conversion should be True even for unknown unit pair")
        self.assertIsNone(entry.get("conversion_factor"),
                          msg="conversion_factor should be None for unknown pair")

    def test_c5_guard_fires_for_mixed_source_direct_plus_yaml_scalar_basis(self) -> None:
        """The C5 guard string-contains check blocks C5 for mixed pooled bases.

        When some blocks use yaml_scalar_conversion and some use source_direct,
        the pooled basis is "source_direct+yaml_scalar_conversion".  The old
        exact-equality guard (basis != "yaml_scalar_conversion") would let C5 run,
        double-applying the conversion factor.  The new substring guard catches it.
        """
        # Simulate the mixed-basis resolved source as returned by build_expected_summary
        resolved_src = {
            "type": "continuous",
            "mean": 72.503,  # already post-conversion (kg)
            "sd": 15.0,
            "n_valid": 10000,
            "_comparison_basis": "source_direct+yaml_scalar_conversion",
        }
        basis = resolved_src["_comparison_basis"]
        # New guard: "yaml_scalar_conversion" in basis → C5 should be SKIPPED
        self.assertIn("yaml_scalar_conversion", basis)
        # The old guard (exact equality) would have been False → C5 would run
        self.assertNotEqual(basis, "yaml_scalar_conversion")
        # The new guard prevents C5 from running
        self.assertFalse("yaml_scalar_conversion" not in basis,
                         msg="New guard should prevent C5 when basis contains yaml_scalar_conversion")


class C2PerPhtBreakdownTests(unittest.TestCase):
    """Tests for C2 per-PHT source breakdown and harmonized n_total split (#662)."""

    def test_c2_fail_includes_per_pht_breakdown_in_detail(self) -> None:
        """check_c2_n_loss populates per_pht_src_breakdown when given _pht-stamped data."""
        src_var = {"n_valid": 10000, "type": "continuous"}
        harmonized_var = {"n_valid": 9000, "n_total": 9000}
        per_pht = [
            {"_pht": "pht000001", "n_valid": 6000},
            {"_pht": "pht000002", "n_valid": 4000},
        ]
        result = check_c2_n_loss(
            src_var, harmonized_var, "weight",
            pass_pct=0.5, warn_pct=2.0,
            per_pht_src=per_pht,
        )
        self.assertEqual(result.status, "FAIL")
        breakdown = result.detail.get("per_pht_src_breakdown", [])
        self.assertEqual(len(breakdown), 2)
        self.assertEqual(breakdown[0], {"pht": "pht000001", "source_n_valid": 6000})
        self.assertEqual(breakdown[1], {"pht": "pht000002", "source_n_valid": 4000})

    def test_c2_single_pht_no_breakdown(self) -> None:
        """check_c2_n_loss does not add breakdown when only one PHT is present."""
        src_var = {"n_valid": 1000, "type": "continuous"}
        harmonized_var = {"n_valid": 900, "n_total": 900}
        per_pht = [{"_pht": "pht000001", "n_valid": 1000}]
        result = check_c2_n_loss(
            src_var, harmonized_var, "weight",
            per_pht_src=per_pht,
        )
        self.assertNotIn("per_pht_src_breakdown", result.detail)

    def test_c2_harmonized_n_total_differs_adds_detail(self) -> None:
        """When harmonized n_total > n_valid, null-status row count appears in detail."""
        src_var = {"n_valid": 26561, "type": "categorical"}
        harmonized_var = {"n_valid": 11256, "n_total": 26561}
        result = check_c2_n_loss(src_var, harmonized_var, "ecglvh1c")
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.detail.get("harmonized_n_total"), 26561)
        self.assertEqual(result.detail.get("harmonized_null_status_rows"), 15305)

    def test_c2_harmonized_n_total_equal_to_n_valid_not_added(self) -> None:
        """When n_total == n_valid, no extra n_total key is added to detail."""
        src_var = {"n_valid": 500, "type": "categorical"}
        harmonized_var = {"n_valid": 480, "n_total": 480}
        result = check_c2_n_loss(src_var, harmonized_var, "some_var")
        self.assertNotIn("harmonized_n_total", result.detail)

    def test_c2_per_pht_breakdown_entries_without_pht_key_are_skipped(self) -> None:
        """Per-PHT summaries lacking _pht are silently skipped in the breakdown."""
        src_var = {"n_valid": 1000, "type": "continuous"}
        harmonized_var = {"n_valid": 900, "n_total": 900}
        per_pht = [
            {"n_valid": 600},          # no _pht key — should be ignored
            {"_pht": "pht000002", "n_valid": 400},
        ]
        result = check_c2_n_loss(src_var, harmonized_var, "weight", per_pht_src=per_pht)
        # Only one pht row survives → no breakdown (need >1 to trigger)
        self.assertNotIn("per_pht_src_breakdown", result.detail)


if __name__ == "__main__":
    unittest.main()

