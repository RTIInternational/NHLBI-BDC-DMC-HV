"""Tests for C0: Entity File Coverage.

All fixtures are synthetic aggregate metadata only; no participant-level rows
or identifiers are embedded here.
"""

from __future__ import annotations

import unittest

from hv_dataqc.compare.checks.entity_completeness import check_c0_entity_file_coverage


class TestC0EntityFileCoverage(unittest.TestCase):
    def test_absent_field_returns_no_results(self) -> None:
        self.assertEqual(check_c0_entity_file_coverage({}), [])

    def test_pass_when_all_entities_loaded_in_all_groups(self) -> None:
        harmonized = {
            "consent_group_file_status": {
                "c1": {"MeasurementObservation": {"status": "loaded", "rows": 100}},
                "c2": {"MeasurementObservation": {"status": "loaded", "rows": 120}},
            }
        }
        results = check_c0_entity_file_coverage(harmonized)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "PASS")

    def test_unrecognized_status_in_some_groups_fails_not_passes(self) -> None:
        """An unrecognized/absent status literal must count as a problem group,
        not silently drop and let a broken run read as PASS."""
        harmonized = {
            "consent_group_file_status": {
                "c1": {"Observation": {"status": "loaded", "rows": 100}},
                "c2": {"Observation": {"status": "corrupted"}},  # unknown status
            }
        }
        results = check_c0_entity_file_coverage(harmonized)
        self.assertFalse(any(r.status == "PASS" for r in results))
        fails = [r for r in results if r.status == "FAIL"]
        self.assertEqual(len(fails), 1)
        self.assertEqual(fails[0].detail["entity"], "Observation")

    def test_unrecognized_status_in_all_groups_is_not_a_pass(self) -> None:
        harmonized = {
            "consent_group_file_status": {
                "c1": {"Observation": {"status": "weird"}},
                "c2": {"Observation": {"status": "weird"}},
            }
        }
        results = check_c0_entity_file_coverage(harmonized)
        self.assertFalse(any(r.status == "PASS" for r in results))
        self.assertGreaterEqual(len(results), 1)

    def test_empty_coverage_map_skips_instead_of_passing(self) -> None:
        """consent_group_file_status present but no entities recorded anywhere:
        a total-absence signature must SKIP, never read as 'all loaded'."""
        harmonized = {"consent_group_file_status": {"c1": {}, "c2": {}}}
        results = check_c0_entity_file_coverage(harmonized)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "SKIP")

    def test_missing_in_all_groups_is_info_not_fail(self) -> None:
        """An optional entity genuinely missing in every group stays INFO."""
        harmonized = {
            "consent_group_file_status": {
                "c1": {"DrugExposure": {"status": "missing"}},
                "c2": {"DrugExposure": {"status": "missing"}},
            }
        }
        results = check_c0_entity_file_coverage(harmonized)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "INFO")

    def test_zero_rows_in_one_group_fails_when_other_group_has_rows(self) -> None:
        """A header-only TSV (parses fine, 0 rows) must not read as PASS when
        the same entity produced real rows in a sibling consent group."""
        harmonized = {
            "consent_group_file_status": {
                "c1": {"Condition": {"status": "loaded", "rows": 0}},
                "c2": {"Condition": {"status": "loaded", "rows": 500}},
            }
        }
        results = check_c0_entity_file_coverage(harmonized)
        self.assertFalse(any(r.status == "PASS" for r in results))
        fails = [r for r in results if r.status == "FAIL"]
        self.assertEqual(len(fails), 1)
        self.assertEqual(fails[0].detail["entity"], "Condition")

    def test_zero_rows_in_all_groups_is_info_not_fail(self) -> None:
        """A consistently 0-row entity across every group is not an anomaly --
        same INFO treatment as an entity missing everywhere."""
        harmonized = {
            "consent_group_file_status": {
                "c1": {"Procedure": {"status": "loaded", "rows": 0}},
                "c2": {"Procedure": {"status": "loaded", "rows": 0}},
            }
        }
        results = check_c0_entity_file_coverage(harmonized)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "INFO")


if __name__ == "__main__":
    unittest.main()
