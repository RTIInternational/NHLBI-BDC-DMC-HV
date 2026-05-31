"""Focused tests for YAML crosswalk expected-summary modes.

All fixtures are synthetic aggregate summaries only; no participant-level rows
or identifiers are embedded here.
"""

from __future__ import annotations

import unittest

from hv_dataqc.compare.crosswalk import build_expected_summary


class CompareCrosswalkModeTests(unittest.TestCase):
    def _categorical_summary(self) -> dict:
        return {
            "type": "categorical",
            "n_total": 10,
            "n_valid": 10,
            "n_missing": 0,
            "distribution": {
                "0": {"n": 4, "pct": 40.0},
                "1": {"n": 3, "pct": 30.0},
                "9": {"n": 3, "pct": 30.0},
            },
        }

    def test_direct_source_summary_is_exact_source_direct(self) -> None:
        source_summary = {
            "type": "continuous",
            "n_total": 5,
            "n_valid": 5,
            "n_missing": 0,
            "mean": 80.0,
            "sd": 10.0,
            "min": 60.0,
            "max": 100.0,
        }
        entry = {"yaml_file": "heart_rate.yaml", "phv_id": "phv000001", "_source_summary": source_summary}

        expected = build_expected_summary([entry], {})

        self.assertIsNotNone(expected)
        self.assertEqual(expected["_comparison_basis"], "source_direct")
        self.assertEqual(expected["_comparison_confidence"], "exact")
        self.assertEqual(expected["mean"], 80.0)
        self.assertEqual(expected["n_valid"], 5)

    def test_scalar_conversion_marks_yaml_scalar_conversion(self) -> None:
        source_summary = {
            "type": "continuous",
            "n_total": 5,
            "n_valid": 5,
            "n_missing": 0,
            "mean": 2.0,
            "sd": 0.5,
            "min": 1.0,
            "max": 3.0,
        }
        entry = {
            "yaml_file": "duration.yaml",
            "phv_id": "phv000002",
            "conversion_factor": 7.0,
            "_source_summary": source_summary,
        }

        expected = build_expected_summary([entry], {})

        self.assertIsNotNone(expected)
        self.assertEqual(expected["_comparison_basis"], "yaml_scalar_conversion")
        self.assertEqual(expected["_comparison_confidence"], "exact")
        self.assertEqual(expected["mean"], 14.0)
        self.assertEqual(expected["sd"], 3.5)
        self.assertEqual(expected["min"], 7.0)
        self.assertEqual(expected["max"], 21.0)

    def test_value_mappings_filter_unmapped_source_codes(self) -> None:
        entry = {
            "yaml_file": "condition.yaml",
            "phv_id": "phv000003",
            "value_map": {"0": "ABSENT", "1": "PRESENT"},
            "_source_summary": self._categorical_summary(),
        }

        expected = build_expected_summary([entry], {})

        self.assertIsNotNone(expected)
        self.assertEqual(expected["_comparison_basis"], "yaml_value_mappings")
        self.assertEqual(expected["_comparison_confidence"], "exact")
        self.assertEqual(expected["n_valid"], 7)
        self.assertEqual(expected["n_missing"], 3)
        self.assertEqual(expected["distribution"], {
            "ABSENT": {"n": 4, "pct": 57.14},
            "PRESENT": {"n": 3, "pct": 42.86},
        })

    def test_value_case_expression_with_default_branch_is_exact(self) -> None:
        entry = {
            "yaml_file": "case_status.yaml",
            "phv_id": "phv000004",
            "value_exprs": ["case(({phv000004} == 1, 'PRESENT'), (True, 'ABSENT'))"],
            "_source_summary": self._categorical_summary(),
        }

        expected = build_expected_summary([entry], {"phv000004": entry["_source_summary"]})

        self.assertIsNotNone(expected)
        self.assertEqual(expected["_comparison_basis"], "yaml_case_value_expr")
        self.assertEqual(expected["_comparison_confidence"], "exact")
        self.assertEqual(expected["distribution"]["PRESENT"]["n"], 3)
        self.assertEqual(expected["distribution"]["ABSENT"]["n"], 7)

    def test_joint_phv_case_expression_without_joint_distribution_is_unsupported(self) -> None:
        source_summary = self._categorical_summary() | {"_pht": "pht000001"}
        entry = {
            "yaml_file": "joint_case.yaml",
            "phv_id": "phv000005",
            "value_exprs": [
                "case(({phv000005} == 1 and {phv000006} == 1, 'PRESENT'))"
            ],
            "_source_summary": source_summary,
        }

        expected = build_expected_summary(
            [entry],
            {
                "phv000005": source_summary,
                "phv000006": self._categorical_summary() | {"_pht": "pht000001"},
            },
        )

        self.assertIsNotNone(expected)
        self.assertEqual(expected["_comparison_basis"], "yaml_case_value_expr")
        self.assertEqual(expected["_comparison_confidence"], "unsupported")
        self.assertIn("multiple PHVs", expected["_comparison_limitations"][0])

    def test_concept_value_mappings_filter_rows_for_matching_concept(self) -> None:
        entry = {
            "yaml_file": "diabetes.yaml",
            "phv_id": "phv000007",
            "concept_phv": "phv000007",
            "concept_code": "MONDO:0005015",
            "concept_value_map": {
                "0": "MONDO:0005015",
                "1": "MONDO:0006920",
                "9": "MONDO:0005015",
            },
            "value_map": {"0": "ABSENT", "1": "PRESENT", "9": "UNKNOWN"},
            "_source_summary": self._categorical_summary(),
        }

        expected = build_expected_summary([entry], {})

        self.assertIsNotNone(expected)
        self.assertEqual(expected["_comparison_basis"], "yaml_concept_value_mappings")
        self.assertEqual(expected["_comparison_confidence"], "exact")
        self.assertEqual(expected["n_valid"], 7)
        self.assertEqual(expected["distribution"]["ABSENT"]["n"], 4)
        self.assertEqual(expected["distribution"]["UNKNOWN"]["n"], 3)

    def test_separate_concept_and_value_phvs_are_not_summarized_as_one_source(self) -> None:
        entry = {
            "yaml_file": "joint_diabetes.yaml",
            "phv_id": "phv000008",
            "concept_phv": "phv000009",
            "concept_code": "MONDO:0005015",
            "concept_value_map": {"1": "MONDO:0005015"},
            "value_map": {"0": "ABSENT", "1": "PRESENT"},
            "_source_summary": self._categorical_summary(),
        }

        expected = build_expected_summary([entry], {})

        self.assertIsNone(expected)


if __name__ == "__main__":
    unittest.main()