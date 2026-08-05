"""Tests for C15: Entity Column Schema Consistency.

All fixtures are synthetic aggregate metadata only; no participant-level rows
or identifiers are embedded here.
"""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from hv_dataqc.compare.checks.column_coverage import (
    build_expected_columns_from_yaml,
    check_c15_column_coverage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cg_status(
    *,
    groups: dict[str, dict[str, list[str] | None]],
) -> dict:
    """Build a minimal harmonized dict with consent_group_file_status.

    Args:
        groups: {cg_label: {entity_name: columns_list_or_None}}
            columns_list_or_None=None means status="missing"; a list means
            status="loaded" with those columns.
    """
    cg_status: dict[str, dict] = {}
    for cg_label, entity_map in groups.items():
        cg_status[cg_label] = {}
        for entity, cols in entity_map.items():
            if cols is None:
                cg_status[cg_label][entity] = {"status": "missing"}
            else:
                cg_status[cg_label][entity] = {
                    "status": "loaded",
                    "rows": len(cols),
                    "columns": cols,
                }
    return {"consent_group_file_status": cg_status}


def _write_yaml(yaml_dir: Path, entity: str, slots: list[str], filename: str = "test.yaml") -> None:
    """Write a minimal cohort YAML file defining the given slots for an entity."""
    lines = [
        "- class_derivations:",
        f"    {entity}:",
        "      populated_from: pht000001",
        "      slot_derivations:",
    ]
    for slot in slots:
        lines.append(f"        {slot}:")
        lines.append("          value: test")
    (yaml_dir / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# SKIP cases
# ---------------------------------------------------------------------------

class TestC15Skip(unittest.TestCase):
    def test_skip_when_no_consent_group_file_status(self) -> None:
        results = check_c15_column_coverage({})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "SKIP")

    def test_skip_when_no_loaded_entities(self) -> None:
        harmonized = _cg_status(groups={
            "c1": {"Condition": None},
            "c2": {"Condition": None},
        })
        results = check_c15_column_coverage(harmonized)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "SKIP")

    def test_skip_when_columns_field_absent_from_all_loaded_entries(self) -> None:
        """Older JSON artifacts have loaded status but no columns field."""
        harmonized = {
            "consent_group_file_status": {
                "c1": {
                    "Condition": {"status": "loaded", "rows": 100},
                },
            }
        }
        results = check_c15_column_coverage(harmonized)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "SKIP")

    def test_subcheck2_skipped_when_yaml_dir_is_none(self) -> None:
        """Sub-check 2 does not fire when yaml_dir is not provided."""
        cols = ["id", "associated_participant"]
        harmonized = _cg_status(groups={"c1": {"Condition": cols}})
        results = check_c15_column_coverage(harmonized, yaml_dir=None)
        # Sub-check 1 passes (only one group); sub-check 2 is skipped. -> PASS
        self.assertTrue(any(r.status == "PASS" for r in results))
        self.assertFalse(any(r.status == "FAIL" for r in results))


# ---------------------------------------------------------------------------
# build_expected_columns_from_yaml unit tests
# ---------------------------------------------------------------------------

class TestBuildExpectedColumns(unittest.TestCase):
    def test_parses_slot_derivations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_yaml(d, "Condition", ["condition_concept", "associated_participant"])
            result = build_expected_columns_from_yaml(d)
        self.assertIn("Condition", result)
        self.assertIn("condition_concept", result["Condition"])
        self.assertIn("associated_participant", result["Condition"])
        # 'id' is NOT auto-added — it is only expected when the YAML explicitly
        # derives it (e.g. visit.yaml). See fix e15c71cd, which removed the
        # unconditional id injection that false-flagged non-Visit entities.
        self.assertNotIn("id", result["Condition"])

    def test_aggregates_across_multiple_yaml_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_yaml(d, "Condition", ["condition_concept", "associated_participant"], "a.yaml")
            _write_yaml(d, "Condition", ["condition_status", "associated_visit"], "b.yaml")
            result = build_expected_columns_from_yaml(d)
        self.assertIn("condition_concept", result["Condition"])
        self.assertIn("condition_status", result["Condition"])
        self.assertIn("associated_visit", result["Condition"])

    def test_aggregates_multiple_entity_classes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            content = textwrap.dedent("""\
                - class_derivations:
                    Condition:
                      populated_from: pht000001
                      slot_derivations:
                        condition_concept:
                          value: MONDO:0000001
                        associated_participant:
                          expr: 'uuid5("x", "y")'
                - class_derivations:
                    Observation:
                      populated_from: pht000002
                      slot_derivations:
                        observation_type:
                          value: OMOP:1234567
                        associated_participant:
                          expr: 'uuid5("x", "y")'
            """)
            (d / "multi.yaml").write_text(content, encoding="utf-8")
            result = build_expected_columns_from_yaml(d)
        self.assertIn("Condition", result)
        self.assertIn("Observation", result)
        self.assertIn("observation_type", result["Observation"])

    def test_empty_dir_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = build_expected_columns_from_yaml(Path(tmp))
        self.assertEqual(result, {})

    def test_malformed_yaml_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "bad.yaml").write_text("{ unclosed: [bracket", encoding="utf-8")
            _write_yaml(d, "Condition", ["condition_concept"], "good.yaml")
            result = build_expected_columns_from_yaml(d)
        self.assertIn("Condition", result)  # good file still parsed


# ---------------------------------------------------------------------------
# PASS cases
# ---------------------------------------------------------------------------

class TestC15Pass(unittest.TestCase):
    def test_pass_single_group_yaml_columns_all_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_yaml(d, "Condition", ["condition_concept", "associated_participant"])
            cols = ["id", "condition_concept", "associated_participant", "condition_status"]
            harmonized = _cg_status(groups={"c1": {"Condition": cols}})
            results = check_c15_column_coverage(harmonized, yaml_dir=d)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "PASS")

    def test_pass_two_groups_identical_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_yaml(d, "Condition", ["condition_concept", "associated_participant"])
            cols = ["id", "condition_concept", "associated_participant"]
            harmonized = _cg_status(groups={
                "c1": {"Condition": cols},
                "c2": {"Condition": cols},
            })
            results = check_c15_column_coverage(harmonized, yaml_dir=d)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "PASS")

    def test_pass_entity_not_in_yaml_spec(self) -> None:
        """Entity in TSV but not in YAML (e.g. pipeline-generated) -- no FAIL."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            # YAML only defines Condition; TSV has UnknownEntity
            _write_yaml(d, "Condition", ["condition_concept", "associated_participant"])
            cols = ["id", "some_column", "associated_participant"]
            harmonized = _cg_status(groups={"c1": {"UnknownEntity": cols}})
            results = check_c15_column_coverage(harmonized, yaml_dir=d)
        self.assertTrue(any(r.status == "PASS" for r in results))
        self.assertFalse(any(r.status == "FAIL" for r in results))

    def test_pass_missing_entity_in_one_group_is_ignored(self) -> None:
        """Missing/empty status in one group does not trigger C15; that is C0's job."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_yaml(d, "Condition", ["condition_concept", "associated_participant"])
            cols = ["id", "condition_concept", "associated_participant"]
            harmonized = _cg_status(groups={
                "c1": {"Condition": cols},
                "c2": {"Condition": None},  # missing status -- C0 catches this
            })
            results = check_c15_column_coverage(harmonized, yaml_dir=d)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "PASS")

    def test_pass_extra_tsv_columns_not_in_yaml_are_fine(self) -> None:
        """TSV may have more columns than YAML spec -- that is fine."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_yaml(d, "Condition", ["condition_concept", "associated_participant"])
            cols = ["id", "condition_concept", "associated_participant", "extra_col", "another_col"]
            harmonized = _cg_status(groups={"c1": {"Condition": cols}})
            results = check_c15_column_coverage(harmonized, yaml_dir=d)
        self.assertFalse(any(r.status == "FAIL" for r in results))


# ---------------------------------------------------------------------------
# FAIL: cross-consent-group column mismatch  (sub-check 1, no yaml_dir needed)
# ---------------------------------------------------------------------------

class TestC15ConsistencyFail(unittest.TestCase):
    def test_fail_one_column_missing_in_c2(self) -> None:
        c1_cols = ["id", "condition_concept", "associated_participant", "condition_status"]
        c2_cols = ["id", "condition_concept", "associated_participant"]
        harmonized = _cg_status(groups={
            "c1": {"Condition": c1_cols},
            "c2": {"Condition": c2_cols},
        })
        results = check_c15_column_coverage(harmonized)
        fail_results = [r for r in results if r.status == "FAIL"]
        self.assertGreaterEqual(len(fail_results), 1)
        fail = fail_results[0]
        self.assertEqual(fail.check_id, "C15")
        self.assertIn("condition_status", fail.detail["missing_in_differing"])
        self.assertEqual(fail.detail["entity"], "Condition")
        self.assertEqual(fail.detail["reference_group"], "c1")
        self.assertEqual(fail.detail["differing_group"], "c2")

    def test_fail_extra_column_in_c2(self) -> None:
        c1_cols = ["id", "condition_concept", "associated_participant"]
        c2_cols = ["id", "condition_concept", "associated_participant", "unexpected_col"]
        harmonized = _cg_status(groups={
            "c1": {"Condition": c1_cols},
            "c2": {"Condition": c2_cols},
        })
        results = check_c15_column_coverage(harmonized)
        fail_results = [r for r in results if r.status == "FAIL"]
        self.assertGreaterEqual(len(fail_results), 1)
        self.assertIn("unexpected_col", fail_results[0].detail["extra_in_differing"])

    def test_fail_multiple_entities_with_mismatches(self) -> None:
        harmonized = _cg_status(groups={
            "c1": {
                "Condition": ["id", "condition_concept", "associated_participant", "condition_status"],
                "Observation": ["id", "observation_type", "associated_participant", "value_enum"],
            },
            "c2": {
                "Condition": ["id", "condition_concept", "associated_participant"],
                "Observation": ["id", "observation_type", "associated_participant"],
            },
        })
        results = check_c15_column_coverage(harmonized)
        fail_results = [r for r in results if r.status == "FAIL"]
        entity_names = {r.detail["entity"] for r in fail_results}
        self.assertIn("Condition", entity_names)
        self.assertIn("Observation", entity_names)


# ---------------------------------------------------------------------------
# FAIL: YAML-driven column presence  (sub-check 2, yaml_dir required)
# ---------------------------------------------------------------------------

class TestC15YamlColumnsFail(unittest.TestCase):
    def test_fail_yaml_slot_missing_from_tsv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_yaml(d, "Condition", ["condition_concept", "associated_participant", "condition_status"])
            # TSV missing condition_concept
            cols = ["id", "associated_participant", "condition_status"]
            harmonized = _cg_status(groups={"c1": {"Condition": cols}})
            results = check_c15_column_coverage(harmonized, yaml_dir=d)
        fail_results = [r for r in results if r.status == "FAIL"]
        self.assertGreaterEqual(len(fail_results), 1)
        fail = next(r for r in fail_results if "required_columns" in r.variable)
        self.assertIn("condition_concept", fail.detail["missing_yaml_columns"])

    def test_fail_yaml_derived_id_missing_from_tsv(self) -> None:
        """When the YAML explicitly derives 'id' (e.g. visit.yaml), a TSV missing
        it is a hard FAIL. Entities whose YAML does not derive 'id' are not
        flagged — 'id' is no longer injected unconditionally (fix e15c71cd)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_yaml(d, "Visit", ["id", "visit_category"])
            cols = ["visit_category", "associated_participant"]  # no id
            harmonized = _cg_status(groups={"c1": {"Visit": cols}})
            results = check_c15_column_coverage(harmonized, yaml_dir=d)
        fail_results = [r for r in results if r.status == "FAIL"]
        self.assertTrue(any("id" in r.detail.get("missing_yaml_columns", []) for r in fail_results))

    def test_fail_multiple_slots_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_yaml(d, "Participant", ["identity", "member_of_research_study", "associated_person"])
            cols = ["id"]  # missing everything else
            harmonized = _cg_status(groups={"c1": {"Participant": cols}})
            results = check_c15_column_coverage(harmonized, yaml_dir=d)
        fail_results = [r for r in results if r.status == "FAIL"]
        missing = fail_results[0].detail["missing_yaml_columns"]
        self.assertIn("identity", missing)
        self.assertIn("member_of_research_study", missing)

    def test_fail_consistency_and_yaml_fire_independently(self) -> None:
        """Both sub-checks can fire in the same call."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_yaml(d, "Observation", ["observation_type", "associated_participant", "value_enum"])
            c1_cols = ["id", "observation_type", "associated_participant", "value_enum"]
            c2_cols = ["id", "associated_participant", "value_enum"]  # c2 missing observation_type
            harmonized = _cg_status(groups={
                "c1": {"Observation": c1_cols},
                "c2": {"Observation": c2_cols},
            })
            results = check_c15_column_coverage(harmonized, yaml_dir=d)
        # Sub-check 1: c2 missing observation_type vs c1
        consistency_fails = [r for r in results if "consistency" in r.variable]
        self.assertGreaterEqual(len(consistency_fails), 1)


if __name__ == "__main__":
    unittest.main()
