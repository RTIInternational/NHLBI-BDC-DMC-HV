"""Focused tests for YAML crosswalk expected-summary modes.

All fixtures are synthetic aggregate summaries only; no participant-level rows
or identifiers are embedded here.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hv_dataqc.compare.crosswalk import (
    _infer_match_mode,
    _promote_comparison_metadata,
    _source_phv_details_for_entries,
    build_expected_summary,
    build_variable_crosswalk,
)


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

    def test_condition_block_with_coded_concept_and_fixed_status_is_crosswalked(self) -> None:
        """Condition blocks where condition_status is a fixed value but
        condition_concept is a coded PHV (e.g. PADDX, STROKEDX) should
        produce crosswalk entries — one per concept code — using the concept
        PHV as primary.  Previously these were silently skipped, producing
        the 'no YAML block proposed this concept' false positive (#670)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pheno_dir = tmp_path / "pheno_variable_summaries"
            pheno_dir.mkdir()
            (pheno_dir / "synthetic.pht003405.data_dict.xml").write_text(
                '<?xml version="1.0"?>\n'
                "<data_table>\n"
                '  <variable id="phv000090.v1"><name>SUBJID</name></variable>\n'
                '  <variable id="phv000091.v1"><name>PADDX</name></variable>\n'
                "</data_table>\n",
                encoding="utf-8",
            )
            yaml_dir = tmp_path / "yaml"
            yaml_dir.mkdir()
            (yaml_dir / "pad.yaml").write_text(
                "- class_derivations:\n"
                "    Condition:\n"
                "      populated_from: pht003405\n"
                "      slot_derivations:\n"
                "        associated_participant:\n"
                "          expr: 'uuid5(\"P\", str({phv000090}) + \":WHI\")'\n"
                "        condition_concept:\n"
                "          populated_from: phv000091\n"
                "          value_mappings:\n"
                "            '1': HP:0004417\n"
                "            '2': HP:0002621\n"
                "        condition_status:\n"
                "          value: PRESENT\n",
                encoding="utf-8",
            )
            paddx_summary = {
                "type": "categorical",
                "n_total": 100,
                "n_valid": 10,
                "n_missing": 90,
                "distribution": {
                    "1": {"n": 6, "pct": 6.0},
                    "2": {"n": 4, "pct": 4.0},
                },
            }
            matches = build_variable_crosswalk(
                variables_by_name={"PADDX": {"pht003405": paddx_summary}},
                harmonized_vars={
                    "condition_HP:0004417": {"type": "categorical"},
                    "condition_HP:0002621": {"type": "categorical"},
                },
                yaml_dir=yaml_dir,
                cache_dir=tmp_path,
                source_doc={"variables_by_pht": {"pht003405": {"PADDX": paddx_summary}}},
            )

        matched_keys = {m["harmonized_key"] for m in matches}
        self.assertIn("condition_HP:0004417", matched_keys)
        self.assertIn("condition_HP:0002621", matched_keys)
        # The concept PHV is used as the primary PHV (concept_phv == phv_id)
        for m in matches:
            entries = m.get("_yaml_entries", [])
            self.assertTrue(
                any(e.get("phv_id") == "phv000091" for e in entries),
                f"Expected phv000091 as primary PHV in {m['harmonized_key']}",
            )

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

    def test_match_mode_labels_supported_modes(self) -> None:
        exact = {"_comparison_confidence": "exact"}

        self.assertEqual(_infer_match_mode([{}], exact, [{}]), "direct")
        self.assertEqual(_infer_match_mode([{}, {}], exact, [{}, {}]), "pooled_blocks")
        self.assertEqual(_infer_match_mode([{"value_map": {"0": "ABSENT"}}], exact, [{}]), "value_mapping")
        self.assertEqual(_infer_match_mode([{"concept_value_map": {"1": "MONDO:1"}}], exact, [{}]), "concept_routing")
        self.assertEqual(_infer_match_mode([{"value_exprs": ["case((True, 'Y'))"]}], exact, [{}]), "case_expr")
        self.assertEqual(_infer_match_mode([{"conversion_factor": 2.0}], exact, [{}]), "scalar_conversion")
        self.assertEqual(_infer_match_mode([{"is_static": True}], exact, [{}]), "static_value")
        self.assertEqual(
            _infer_match_mode([{"value_exprs": ["case((True, 'Y'))"]}], {"_comparison_confidence": "unsupported"}, [{}]),
            "unsupported_complex",
        )

    def test_build_variable_crosswalk_exposes_match_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pheno_dir = tmp_path / "pheno_variable_summaries"
            pheno_dir.mkdir()
            (pheno_dir / "synthetic.pht000001.data_dict.xml").write_text(
                '<?xml version="1.0"?>\n'
                "<data_table>\n"
                '  <variable id="phv000001.v1">\n'
                "    <name>HR</name>\n"
                "  </variable>\n"
                "</data_table>\n",
                encoding="utf-8",
            )
            yaml_dir = tmp_path / "yaml"
            yaml_dir.mkdir()
            (yaml_dir / "heart_rate.yaml").write_text(
                "- class_derivations:\n"
                "    MeasurementObservation:\n"
                "      populated_from: pht000001\n"
                "      slot_derivations:\n"
                "        observation_type:\n"
                "          value: OBA:HEART_RATE\n"
                "        value_quantity:\n"
                "          object_derivations:\n"
                "            - class_derivations:\n"
                "                Quantity:\n"
                "                  slot_derivations:\n"
                "                    value_decimal:\n"
                "                      populated_from: phv000001\n",
                encoding="utf-8",
            )
            source_summary = {
                "type": "continuous",
                "n_total": 2,
                "n_valid": 2,
                "n_missing": 0,
                "mean": 80.0,
                "sd": 5.0,
            }

            matches = build_variable_crosswalk(
                variables_by_name={"HR": {"pht000001": source_summary}},
                harmonized_vars={"measurement_OBA:HEART_RATE": {"type": "continuous"}},
                yaml_dir=yaml_dir,
                cache_dir=tmp_path,
                source_doc={"variables_by_pht": {"pht000001": {"HR": source_summary}}},
            )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["match_mode"], "direct")
        self.assertEqual(matches[0]["comparison_basis"], "source_direct")
        self.assertEqual(matches[0]["comparison_confidence"], "exact")
        self.assertEqual(matches[0]["comparison_limitations"], [])
        self.assertEqual(matches[0]["source_phts"], ["pht000001"])
        self.assertEqual(matches[0]["source_phvs"], ["phv000001"])
        self.assertEqual(matches[0]["_yaml_entries"][0]["match_mode"], "direct")

    def test_promote_comparison_metadata_uses_resolved_src_fields(self) -> None:
        match = {
            "_resolved_src": {
                "_comparison_basis": "yaml_case_value_expr",
                "_comparison_confidence": "unsupported",
                "_comparison_limitations": ["aggregate summaries cannot compute joint counts"],
            },
            "_source_phts": ["pht000001"],
            "_source_phvs": ["phv000010", "phv000011"],
        }

        _promote_comparison_metadata(match)

        self.assertEqual(match["comparison_basis"], "yaml_case_value_expr")
        self.assertEqual(match["comparison_confidence"], "unsupported")
        self.assertEqual(
            match["comparison_limitations"],
            ["aggregate summaries cannot compute joint counts"],
        )
        self.assertEqual(match["source_phts"], ["pht000001"])
        self.assertEqual(match["source_phvs"], ["phv000010", "phv000011"])

    def test_promote_comparison_metadata_defaults_direct_fields(self) -> None:
        match = {"_resolved_src": {"type": "continuous"}, "_phv_ids": ["phv000030"]}

        _promote_comparison_metadata(match)

        self.assertEqual(match["comparison_basis"], "source_direct")
        self.assertEqual(match["comparison_confidence"], "exact")
        self.assertEqual(match["comparison_limitations"], [])
        self.assertEqual(match["source_phts"], [])
        self.assertEqual(match["source_phvs"], ["phv000030"])

    def test_build_variable_crosswalk_exposes_source_phv_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pheno_dir = tmp_path / "pheno_variable_summaries"
            pheno_dir.mkdir()
            (pheno_dir / "synthetic.pht000001.data_dict.xml").write_text(
                '<?xml version="1.0"?>\n'
                "<data_table>\n"
                '  <variable id="phv000010.v1"><name>PERSON_KEY</name></variable>\n'
                '  <variable id="phv000011.v1"><name>AGE_DAYS</name></variable>\n'
                '  <variable id="phv000012.v1"><name>HEART_RATE</name></variable>\n'
                "</data_table>\n",
                encoding="utf-8",
            )
            yaml_dir = tmp_path / "yaml"
            yaml_dir.mkdir()
            (yaml_dir / "heart_rate.yaml").write_text(
                "- class_derivations:\n"
                "    MeasurementObservation:\n"
                "      populated_from: pht000001\n"
                "      slot_derivations:\n"
                "        associated_participant:\n"
                "          populated_from: phv000010\n"
                "        associated_visit:\n"
                "          expr: 'uuid5(\"Visit\", str({phv000010}) + \":baseline\")'\n"
                "        age_at_observation:\n"
                "          expr: '{phv000011} * 365'\n"
                "        observation_type:\n"
                "          value: OBA:HEART_RATE\n"
                "        value_quantity:\n"
                "          object_derivations:\n"
                "            - class_derivations:\n"
                "                Quantity:\n"
                "                  slot_derivations:\n"
                "                    value_decimal:\n"
                "                      populated_from: phv000012\n",
                encoding="utf-8",
            )
            source_summary = {
                "type": "continuous",
                "n_total": 2,
                "n_valid": 2,
                "n_missing": 0,
                "mean": 80.0,
                "sd": 5.0,
            }

            matches = build_variable_crosswalk(
                variables_by_name={"HEART_RATE": {"pht000001": source_summary}},
                harmonized_vars={"measurement_OBA:HEART_RATE": {"type": "continuous"}},
                yaml_dir=yaml_dir,
                cache_dir=tmp_path,
                source_doc={"variables_by_pht": {"pht000001": {"HEART_RATE": source_summary}}},
            )

        details = matches[0]["source_phv_details"]
        detail_by_role = {(detail["phv_id"], detail["role"]): detail for detail in details}

        self.assertEqual(detail_by_role[("phv000010", "participant_id")]["source_column"], "PERSON_KEY")
        self.assertEqual(detail_by_role[("phv000010", "visit")]["slot"], "associated_visit")
        self.assertEqual(detail_by_role[("phv000011", "age_at_observation")]["pht_id"], "pht000001")
        self.assertEqual(detail_by_role[("phv000012", "value")]["source_column"], "HEART_RATE")
        self.assertEqual(detail_by_role[("phv000012", "value")]["yaml_file"], "heart_rate.yaml")
        self.assertEqual(matches[0]["_yaml_entries"][0]["source_phv_details"], details)

    def test_value_map_none_rows_excluded_from_expected_distribution(self) -> None:
        """Source codes mapped to None (null sentinel = drop row) produce a
        'None' category in the expected distribution.  C7 must downgrade this
        from FAIL to INFO so the drop count is visible for review but is not
        confused with a genuine mapping error.  The expected_summary function
        still includes 'None' so reviewers see the drop in the distribution
        table; distributions.py separates it from real missing categories."""
        entry = {
            "yaml_file": "lvh.yaml",
            "phv_id": "phv000050",
            "value_map": {
                "0": "ABSENT",
                "1": "PRESENT",
                "4": None,     # explicit drop sentinel → 'None' category
                "6": "UNKNOWN",
            },
            "_source_summary": {
                "type": "categorical",
                "n_total": 100,
                "n_valid": 100,
                "n_missing": 0,
                "distribution": {
                    "0": {"n": 50, "pct": 50.0},
                    "1": {"n": 20, "pct": 20.0},
                    "4": {"n": 10, "pct": 10.0},
                    "6": {"n": 20, "pct": 20.0},
                },
            },
        }

        expected = build_expected_summary([entry], {})

        self.assertIsNotNone(expected)
        dist = expected.get("distribution", {})
        # 'None' IS present in expected (visible for review in distribution table)
        self.assertIn("None", dist)
        self.assertEqual(dist["None"]["n"], 10)
        # Real categories are also present
        self.assertIn("ABSENT", dist)
        self.assertIn("UNKNOWN", dist)

    def test_c7_none_drop_produces_info_not_fail(self) -> None:
        """C7 must emit INFO (not FAIL) when the only missing category is 'None'.
        The 'None' category represents rows explicitly excluded via None
        value_mapping — intentional behavior that should be visible but not
        treated as a mapping error."""
        from hv_dataqc.compare.checks.distributions import check_c7_categorical_distribution

        # Use percentages already relative to the non-None denominator (90),
        # so the real categories ABSENT/PRESENT match exactly and only 'None'
        # is missing — isolating the None-drop INFO path.
        src_var = {
            "type": "categorical",
            "n_valid": 100,
            "distribution": {
                "ABSENT": {"n": 50, "pct": 55.6},
                "PRESENT": {"n": 40, "pct": 44.4},
                "None": {"n": 10, "pct": 10.0},   # drop sentinel
            },
        }
        harmonized_var = {
            "type": "categorical",
            "n_valid": 90,
            "distribution": {
                "ABSENT": {"n": 50, "pct": 55.6},
                "PRESENT": {"n": 40, "pct": 44.4},
            },
        }

        result = check_c7_categorical_distribution(src_var, harmonized_var, "lvh_minn")

        self.assertEqual(result.status, "INFO",
                         f"Expected INFO for None-only drop, got {result.status}: {result.message}")
        self.assertIn("none", result.message.lower())
        self.assertIn("10", result.message)  # drop count visible

    def test_cross_phv_cascade_case_returns_unsupported(self) -> None:
        """_expected_summary_from_case_entry must return unsupported when branch 2+
        introduces a different PHV than branch 1.  Mixing marginals from different
        PHVs without conditioning inflates the expected count (HCHS asthma issue #673).
        E.g. case(({phv_a}==0,'ABSENT'),({phv_b}==0,'HISTORICAL'),(True,'PRESENT'))
        — N(phv_b=0) overcounts because it includes rows already counted as ABSENT."""
        from hv_dataqc.compare.expected_summary import _expected_summary_from_case_entry

        entry = {
            "phv_id": "phv00001",
            "value_exprs": [
                "case(({phv00001} == 0, 'ABSENT'), ({phv00002} == 0, 'HISTORICAL'), (True, 'PRESENT'))"
            ],
        }
        summaries_by_phv = {
            "phv00001": {
                "type": "categorical", "n_total": 1000, "n_valid": 1000,
                "_pht": "pht001",
                "distribution": {"0": {"n": 800}, "1": {"n": 200}},
            },
            "phv00002": {
                "type": "categorical", "n_total": 1000, "n_valid": 1000,
                "_pht": "pht001",
                "distribution": {"0": {"n": 950}, "1": {"n": 50}},
            },
        }
        src_summary = summaries_by_phv["phv00001"]
        result = _expected_summary_from_case_entry(entry, src_summary, summaries_by_phv)

        self.assertIsNotNone(result, "Should return a summary, not None")
        self.assertEqual(result.get("_comparison_confidence"), "unsupported",
                         f"Expected unsupported confidence for cross-PHV cascade, got: {result}")
        # The n_valid in the unsupported summary should equal the source PHV's n,
        # not the overcounted marginal sum (800 + 950 = 1750).
        self.assertLessEqual(result.get("n_valid", 0), 1000,
                             "Unsupported summary n_valid must not exceed source table total")

    def test_single_phv_case_with_true_arm_not_affected(self) -> None:
        """Single-PHV case() with True catch-all should still work correctly —
        the cross-PHV guard must not fire when all explicit branches use the same PHV."""
        from hv_dataqc.compare.expected_summary import _expected_summary_from_case_entry

        entry = {
            "phv_id": "phv00010",
            "value_exprs": [
                "case(({phv00010} == 0, 'ABSENT'), ({phv00010} == 1, 'PRESENT'), (True, 'UNKNOWN'))"
            ],
        }
        src_summary = {
            "type": "categorical", "n_total": 500, "n_valid": 480,
            "_pht": "pht002",
            "distribution": {"0": {"n": 300}, "1": {"n": 160}, "9": {"n": 20}},
        }
        summaries_by_phv = {"phv00010": src_summary}
        result = _expected_summary_from_case_entry(entry, src_summary, summaries_by_phv)

        self.assertIsNotNone(result, "Single-PHV case() should return a summary")
        self.assertNotEqual(result.get("_comparison_confidence"), "unsupported",
                            "Single-PHV case() should not be classified as unsupported")
        dist = result.get("distribution", {})
        self.assertEqual(dist.get("ABSENT", {}).get("n"), 300)
        self.assertEqual(dist.get("PRESENT", {}).get("n"), 160)
        # UNKNOWN = 500 - 300 - 160 = 40 (True arm uses table_total=500, not n_valid=480)
        self.assertEqual(dist.get("UNKNOWN", {}).get("n"), 40)

    def test_c7_skipped_for_concept_value_map_routing_entries(self) -> None:
        """Concept_value_map routing entries must produce _comparison_basis ==
        'yaml_concept_value_mappings', which gates the C7 INFO/skip in
        compare.py.  The source distribution contains concept CURIEs; the
        harmonized distribution contains condition_status values — orthogonal
        axes where a category comparison is meaningless."""
        entry = {
            "yaml_file": "pad.yaml",
            "phv_id": "phv000091",
            "concept_phv": "phv000091",   # concept_phv == phv_id (promoted primary)
            "concept_code": "HP:0004417",
            "concept_value_map": {"1": "HP:0004417", "2": "HP:0002621"},
            "_source_summary": {
                "type": "categorical",
                "n_total": 100,
                "n_valid": 10,
                "n_missing": 90,
                "distribution": {"1": {"n": 10, "pct": 100.0}},
            },
        }

        expected = build_expected_summary([entry], {})

        self.assertIsNotNone(expected)
        # The basis must be 'yaml_concept_value_mappings' so compare.py
        # emits C7 INFO (skip) instead of calling check_c7_categorical_distribution.
        self.assertEqual(expected["_comparison_basis"], "yaml_concept_value_mappings")
        # Distribution is keyed by concept CURIE, NOT by condition_status value —
        # this confirms the C7 mismatch that the skip guards against.
        self.assertIn("HP:0004417", expected.get("distribution", {}))

    def test_source_phv_details_falls_back_to_primary_phv(self) -> None:
        details = _source_phv_details_for_entries(
            [{"yaml_file": "demography.yaml", "phv_id": "phv000020"}],
            {"phv000020": "SEX"},
            {"phv000020": "pht000002"},
        )

        self.assertEqual(
            details,
            [
                {
                    "phv_id": "phv000020",
                    "pht_id": "pht000002",
                    "source_column": "SEX",
                    "role": "value",
                    "slot": "",
                    "yaml_file": "demography.yaml",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()