"""Tests for C13 UUID format validation and C14 duplicate row detection.

All fixtures are synthetic aggregate summaries only; no participant-level
rows or identifiers are embedded here.
"""

from __future__ import annotations

import unittest

from hv_dataqc.compare.checks.uuid_validation import check_c13_uuid_format
from hv_dataqc.compare.checks.duplicate_rows import check_c14_duplicate_rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_UUID = "a1b2c3d4-e5f6-5000-8000-000000000001"
_INVALID_UUID_STR = "https://w3id.org/bdchm/ParticipantNone:MESA"
_INVALID_UUID_NONE = "None"


def _uuid_stats(
    entity: str,
    n_total: int = 100,
    n_bad_participant: int = 0,
    n_bad_visit: int = 0,
    samples_participant: list | None = None,
    samples_visit: list | None = None,
) -> dict:
    return {
        "entity": entity,
        "n_total_rows": n_total,
        "n_invalid_participant_uuid": n_bad_participant,
        "n_invalid_visit_uuid": n_bad_visit,
        "sample_invalid_participant": samples_participant or [],
        "sample_invalid_visit": samples_visit or [],
    }


def _dup_stats(
    entity: str,
    n_total: int = 100,
    n_dup: int = 0,
    n_groups: int = 0,
    pct: float = 0.0,
) -> dict:
    return {
        "entity": entity,
        "n_total_rows": n_total,
        "n_duplicate_rows": n_dup,
        "n_duplicate_groups": n_groups,
        "pct_duplicated": pct,
    }


# ---------------------------------------------------------------------------
# C13: UUID format validation
# ---------------------------------------------------------------------------

class TestC13UuidFormat(unittest.TestCase):

    def test_skip_when_uuid_validation_absent(self) -> None:
        results = check_c13_uuid_format({})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "SKIP")
        self.assertEqual(results[0].check_id, "C13")

    def test_pass_when_all_uuids_valid(self) -> None:
        harmonized = {
            "uuid_validation": {
                "Condition": _uuid_stats("Condition", n_total=500),
                "MeasurementObservation": _uuid_stats("MeasurementObservation", n_total=300),
            }
        }
        results = check_c13_uuid_format(harmonized)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.check_id, "C13")
        self.assertEqual(r.status, "PASS")
        self.assertIn("Condition", r.message)
        self.assertIn("MeasurementObservation", r.message)

    def test_skip_when_no_rows_to_validate(self) -> None:
        """uuid_validation present but every entity has 0 rows -> SKIP, not a
        false 'all valid' PASS on zero validated values."""
        harmonized = {
            "uuid_validation": {
                "Condition": _uuid_stats("Condition", n_total=0),
                "MeasurementObservation": _uuid_stats("MeasurementObservation", n_total=0),
            }
        }
        results = check_c13_uuid_format(harmonized)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.check_id, "C13")
        self.assertEqual(r.status, "SKIP")
        self.assertIn("0 total rows", r.message)

    def test_pass_when_some_rows_present_even_if_one_entity_empty(self) -> None:
        """A zero-row entity alongside a populated, clean entity still PASSes —
        the guard only blocks the all-empty case."""
        harmonized = {
            "uuid_validation": {
                "Condition": _uuid_stats("Condition", n_total=0),
                "MeasurementObservation": _uuid_stats("MeasurementObservation", n_total=300),
            }
        }
        results = check_c13_uuid_format(harmonized)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "PASS")

    def test_fail_on_invalid_participant_uuid(self) -> None:
        harmonized = {
            "uuid_validation": {
                "Condition": _uuid_stats(
                    "Condition",
                    n_total=200,
                    n_bad_participant=5,
                    samples_participant=[_INVALID_UUID_NONE],
                ),
            }
        }
        results = check_c13_uuid_format(harmonized)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.check_id, "C13")
        self.assertEqual(r.status, "FAIL")
        self.assertIn("associated_participant", r.message)
        self.assertIn("5", r.message)
        self.assertEqual(r.detail["n_invalid_participant_uuid"], 5)

    def test_fail_on_invalid_visit_uuid(self) -> None:
        harmonized = {
            "uuid_validation": {
                "MeasurementObservation": _uuid_stats(
                    "MeasurementObservation",
                    n_total=150,
                    n_bad_visit=3,
                    samples_visit=[_INVALID_UUID_STR],
                ),
            }
        }
        results = check_c13_uuid_format(harmonized)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.status, "FAIL")
        self.assertIn("associated_visit", r.message)
        self.assertEqual(r.detail["n_invalid_visit_uuid"], 3)

    def test_fail_on_both_columns_invalid(self) -> None:
        harmonized = {
            "uuid_validation": {
                "Condition": _uuid_stats(
                    "Condition",
                    n_total=100,
                    n_bad_participant=2,
                    n_bad_visit=1,
                ),
            }
        }
        results = check_c13_uuid_format(harmonized)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.status, "FAIL")
        self.assertIn("associated_participant", r.message)
        self.assertIn("associated_visit", r.message)

    def test_fail_only_for_affected_entity(self) -> None:
        harmonized = {
            "uuid_validation": {
                "Condition": _uuid_stats("Condition", n_total=100, n_bad_participant=4),
                "Demography": _uuid_stats("Demography", n_total=5000),
            }
        }
        results = check_c13_uuid_format(harmonized)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.status, "FAIL")
        self.assertIn("Condition", r.variable)

    def test_variable_key_uses_entity_name(self) -> None:
        harmonized = {
            "uuid_validation": {
                "MeasurementObservationSet": _uuid_stats(
                    "MeasurementObservationSet", n_bad_participant=1
                ),
            }
        }
        results = check_c13_uuid_format(harmonized)
        self.assertEqual(results[0].variable, "MeasurementObservationSet_uuid_format")


# ---------------------------------------------------------------------------
# C14: Duplicate row detection
# ---------------------------------------------------------------------------

class TestC14DuplicateRows(unittest.TestCase):

    def test_skip_when_duplicate_stats_absent(self) -> None:
        results = check_c14_duplicate_rows({})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "SKIP")
        self.assertEqual(results[0].check_id, "C14")

    def test_pass_when_no_duplicates(self) -> None:
        harmonized = {
            "duplicate_stats": {
                "Condition": _dup_stats("Condition", n_total=1000),
                "MeasurementObservation": _dup_stats("MeasurementObservation", n_total=500),
            }
        }
        results = check_c14_duplicate_rows(harmonized)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.check_id, "C14")
        self.assertEqual(r.status, "PASS")
        self.assertIn("Condition", r.message)
        self.assertIn("MeasurementObservation", r.message)

    def test_warn_on_duplicate_rows(self) -> None:
        harmonized = {
            "duplicate_stats": {
                "Condition": _dup_stats(
                    "Condition",
                    n_total=200,
                    n_dup=10,
                    n_groups=5,
                    pct=5.0,
                ),
            }
        }
        results = check_c14_duplicate_rows(harmonized)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.check_id, "C14")
        self.assertEqual(r.status, "WARN")
        self.assertIn("10", r.message)
        self.assertIn("5 duplicate group", r.message)
        self.assertEqual(r.detail["n_duplicate_rows"], 10)
        self.assertEqual(r.detail["n_duplicate_groups"], 5)
        self.assertAlmostEqual(r.detail["pct_duplicated"], 5.0)

    def test_warn_only_for_affected_entity(self) -> None:
        harmonized = {
            "duplicate_stats": {
                "Condition": _dup_stats("Condition", n_total=100, n_dup=4, n_groups=2, pct=4.0),
                "Demography": _dup_stats("Demography", n_total=5000),
            }
        }
        results = check_c14_duplicate_rows(harmonized)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.status, "WARN")
        self.assertIn("Condition", r.variable)

    def test_variable_key_uses_entity_name(self) -> None:
        harmonized = {
            "duplicate_stats": {
                "MeasurementObservationSet": _dup_stats(
                    "MeasurementObservationSet", n_dup=2, n_groups=1, pct=1.0
                ),
            }
        }
        results = check_c14_duplicate_rows(harmonized)
        self.assertEqual(results[0].variable, "MeasurementObservationSet_duplicates")

    def test_multiple_entities_with_duplicates(self) -> None:
        harmonized = {
            "duplicate_stats": {
                "Condition": _dup_stats("Condition", n_dup=6, n_groups=3, pct=3.0),
                "MeasurementObservation": _dup_stats("MeasurementObservation", n_dup=2, n_groups=1, pct=1.0),
            }
        }
        results = check_c14_duplicate_rows(harmonized)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.status == "WARN" for r in results))


if __name__ == "__main__":
    unittest.main()
