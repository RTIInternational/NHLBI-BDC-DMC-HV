"""Unit tests for HV-DataQC compare helpers.

All fixtures are aggregate metadata only; no participant-level rows are used.
"""

from __future__ import annotations

import sys
import unittest
import math
import tempfile
import importlib.util
from pathlib import Path


HV_DATAQC_DIR = Path(__file__).resolve().parents[1]
COMPARE_DIR = HV_DATAQC_DIR / "compare"
sys.path.insert(0, str(HV_DATAQC_DIR))
sys.path.insert(0, str(COMPARE_DIR))

from hv_dataqc_common import normalize_category_key  # noqa: E402

from compare_source_harmonized import (  # noqa: E402
    CrosswalkBuildError,
    _aggregate_source_summaries,
    _expected_harmonized_n,
    _json_safe,
    _normalize_code,
    _to_discovered_key,
    build_variable_crosswalk,
    check_c1_n_preservation,
    check_c2_n_loss,
    check_c4_mean_preservation,
    check_c10_cross_variable,
    check_c7_categorical_distribution,
    load_thresholds,
    should_run_c5_conversion_check,
    validate_clinical_ranges_config,
)


class CompareSourceHarmonizedTests(unittest.TestCase):
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

    def test_load_thresholds_returns_empty_dict_for_nonexistent_path(self) -> None:
        from pathlib import Path
        result = load_thresholds(Path("/nonexistent/thresholds.yaml"))
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result), 0)

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

    def test_source_extract_config_loads_infer_type_threshold(self) -> None:
        module_path = HV_DATAQC_DIR / "extract-source" / "extract_source_summaries.py"
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

    def test_harmonized_extract_config_overrides_demography_columns(self) -> None:
        module_path = HV_DATAQC_DIR / "extract-harmonized" / "extract_harmonized_summaries.py"
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

    def test_c2_uses_expected_n_for_concept_allocated_source(self) -> None:
        src = {"n_valid": 10}
        out = {"n_valid": 7}

        result = check_c2_n_loss(src, out, "diabetes", expected_n=7)

        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.detail["source_n_raw"], 10)
        self.assertEqual(result.detail["expected_n_for_concept"], 7)

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

    def test_build_variable_crosswalk_raises_on_empty_cache_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            (cache_dir / "pheno_variable_summaries").mkdir()
            yaml_dir = cache_dir / "yaml"
            yaml_dir.mkdir()

            with self.assertRaises(CrosswalkBuildError):
                build_variable_crosswalk(
                    source_vars={},
                    harmonized_vars={},
                    yaml_dir=yaml_dir,
                    cache_dir=cache_dir,
                )

    def test_process_conditions_marks_missing_status_assumption(self) -> None:
        import pandas as pd

        module_path = HV_DATAQC_DIR / "extract-harmonized" / "extract_harmonized_summaries.py"
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
        self.assertIn("pht001467=7200", result[0].message)

    def test_c1_reports_pht_diagnostics_without_masking_union_loss(self) -> None:
        """CHS scenario stays visible as loss but reports max single-PHT context."""
        by_pht = {"pht001450": 5531, "pht001466": 5000, "pht001467": 5531}
        result = check_c1_n_preservation(
            self._src(total=7380, by_pht=by_pht), self._harm(5531)
        )
        self.assertEqual(result[0].status, "FAIL")
        self.assertEqual(result[0].detail["source_n"], 7380)
        self.assertEqual(result[0].detail["max_single_pht_n"], 5531)
        self.assertIn("cross-PHT union=7380", result[0].message)

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
        self.assertIn("mapped-PHT max: pht001447=5612", result[0].message)
        self.assertIn("all-PHT union=7380", result[0].message)

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
        self.assertIn("cross-PHT union=5612", result[0].message)
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

from compare_source_harmonized import (  # noqa: E402
    _concept_codes_from_expr,
    _concept_codes_from_value_mappings,
    _extract_crosswalk_from_class_derivations,
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


if __name__ == "__main__":
    unittest.main()
