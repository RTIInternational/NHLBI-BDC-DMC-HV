"""Unit tests for HV-DataQC compare helpers.

All fixtures are aggregate metadata only; no participant-level rows are used.
"""

from __future__ import annotations

import sys
import unittest
import math
from pathlib import Path


COMPARE_DIR = Path(__file__).resolve().parents[1] / "compare"
sys.path.insert(0, str(COMPARE_DIR))

from compare_source_harmonized import (  # noqa: E402
    _aggregate_source_summaries,
    _json_safe,
    _to_discovered_key,
    check_c1_n_preservation,
    check_c4_mean_preservation,
    check_c10_cross_variable,
    check_c7_categorical_distribution,
    load_thresholds,
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

    # --- With participants_by_pht ---

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


if __name__ == "__main__":
    unittest.main()
