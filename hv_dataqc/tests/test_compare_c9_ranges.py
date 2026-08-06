"""Focused tests for C9 clinical range matching and diagnostics.

All fixtures are synthetic aggregate summaries only; no participant-level rows
or identifiers are embedded here.
"""

from __future__ import annotations

import unittest

from hv_dataqc.compare.checks.clinical_ranges import check_c9_clinical_range
from hv_dataqc.compare.compare import validate_clinical_ranges_config


class CompareC9RangeTests(unittest.TestCase):
    def _range(
        self,
        *,
        common_phv_names: list[str] | None = None,
        oba_codes: list[str] | None = None,
        omop_codes: list[str] | None = None,
    ) -> dict:
        return {
            "common_phv_names": common_phv_names or [],
            "oba_codes": oba_codes or [],
            "omop_codes": omop_codes or [],
            "plausible_lo": 30,
            "plausible_hi": 200,
            "red_flag_lo": 15,
            "red_flag_hi": 300,
        }

    def test_exact_common_name_match_reports_detail(self) -> None:
        result = check_c9_clinical_range(
            {"type": "continuous", "min": 60.0, "max": 90.0},
            "heart_rate",
            {"heart_rate": self._range(common_phv_names=["HEART_RATE"])},
        )

        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.detail["range_name"], "heart_rate")
        self.assertEqual(result.detail["match_method"], "common_phv_name")

    def test_concept_code_match_reports_matched_code(self) -> None:
        result = check_c9_clinical_range(
            {
                "type": "continuous",
                "observation_type": "OBA:1001087",
                "min": 60.0,
                "max": 90.0,
            },
            "hr30",
            {"heart_rate": self._range(oba_codes=["OBA:1001087"])},
        )

        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.detail["range_name"], "heart_rate")
        self.assertEqual(result.detail["match_method"], "concept_code")
        self.assertEqual(result.detail["matched_code"], "OBA:1001087")

    def test_substring_match_reports_detail(self) -> None:
        result = check_c9_clinical_range(
            {"type": "continuous", "min": 60.0, "max": 350.0},
            "resting heart_rate supine",
            {"heart_rate": self._range()},
        )

        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.detail["range_name"], "heart_rate")
        self.assertEqual(result.detail["match_method"], "substring")

    def test_no_match_is_explicit_skip_with_none_detail(self) -> None:
        result = check_c9_clinical_range(
            {"type": "continuous", "min": 60.0, "max": 90.0},
            "unknown_measurement",
            {"heart_rate": self._range()},
        )

        self.assertEqual(result.status, "SKIP")
        self.assertEqual(result.detail["range_name"], None)
        self.assertEqual(result.detail["match_method"], "none")

    def test_non_continuous_is_not_applicable_skip(self) -> None:
        result = check_c9_clinical_range(
            {"type": "categorical"},
            "heart_rate",
            {"heart_rate": self._range(common_phv_names=["heart_rate"])},
        )

        self.assertEqual(result.status, "SKIP")
        self.assertEqual(result.detail["match_method"], "not_applicable")

    def test_missing_min_max_preserves_match_detail(self) -> None:
        result = check_c9_clinical_range(
            {"type": "continuous", "min": None, "max": None},
            "heart_rate",
            {"heart_rate": self._range(common_phv_names=["heart_rate"])},
        )

        self.assertEqual(result.status, "SKIP")
        self.assertEqual(result.detail["range_name"], "heart_rate")
        self.assertEqual(result.detail["match_method"], "common_phv_name")

    def test_source_carried_red_flag_warns_not_fails(self) -> None:
        result = check_c9_clinical_range(
            {"type": "continuous", "min": 0.0, "max": 350.0},
            "heart_rate",
            {"heart_rate": self._range(common_phv_names=["heart_rate"])},
            src_var={"type": "continuous", "min": 0.0, "max": 350.0},
        )

        self.assertEqual(result.status, "WARN")
        self.assertIn("[out+src]", result.message)
        self.assertEqual(result.detail["range_name"], "heart_rate")

    def test_duplicate_concept_code_validation_can_be_allowed(self) -> None:
        ranges = {
            "range_a": {
                **self._range(omop_codes=["OMOP:123"]),
                "allow_duplicate_codes": ["OMOP:123"],
            },
            "range_b": {
                **self._range(omop_codes=["OMOP:123"]),
                "allow_duplicate_codes": ["OMOP:123"],
            },
        }

        warnings = validate_clinical_ranges_config(ranges)

        self.assertFalse(any("OMOP:123" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()