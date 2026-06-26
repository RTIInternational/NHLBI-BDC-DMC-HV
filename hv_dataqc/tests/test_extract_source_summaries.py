"""Focused tests for source TSV summary extraction.

Fixtures are tiny synthetic tables used only to verify aggregate behavior; they
do not contain real participant records or study data.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from hv_dataqc.extract_source.extract_source_summaries import (
    _compute_joint_distributions,
    compute_variable_summary,
    count_rows_per_visit,
    infer_variable_type,
    is_system_column,
    load_source_data,
    load_source_type_map,
    scope_columns_to_yaml_phvs,
)


class ExtractSourceSummaryTests(unittest.TestCase):
    def test_load_source_data_groups_pht_and_deduplicates_multi_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            c1 = root / "consent_c1"
            c2 = root / "consent_c2"
            c1.mkdir()
            c2.mkdir()
            (c1 / "synthetic.pht000001.MULTI.txt").write_text(
                " synthetic_key \t VALUE \n"
                "A\t10\n"
                "B\t20\n",
                encoding="utf-8",
            )
            (c2 / "synthetic.pht000001.MULTI.txt").write_text(
                " synthetic_key \t VALUE \n"
                "B\t20\n"
                "C\t30\n",
                encoding="utf-8",
            )

            loaded = list(load_source_data([c1, c2], participant_col="synthetic_key"))

        self.assertEqual(len(loaded), 1)
        pht_id, df = loaded[0]
        self.assertEqual(pht_id, "pht000001")
        self.assertEqual(list(df.columns[:2]), ["synthetic_key", "VALUE"])
        self.assertEqual(len(df), 3)
        self.assertEqual(sorted(df["VALUE"].astype(int).tolist()), [10, 20, 30])
        self.assertEqual(set(df["_consent_group"]), {"consent_c1", "consent_c2"})

    def test_system_columns_are_excluded_by_exact_and_pattern_rules(self) -> None:
        self.assertTrue(is_system_column("dbgap_subject_id"))
        self.assertTrue(is_system_column("sample.id"))
        self.assertTrue(is_system_column("_internal_flag"))
        self.assertTrue(is_system_column("topmed_flag_status"))
        self.assertFalse(is_system_column("blood_pressure"))

    def test_infer_variable_type_uses_dtype_and_distinct_threshold(self) -> None:
        self.assertEqual(infer_variable_type(pd.Series(["Y", "N", "Y"])), "categorical")
        self.assertEqual(infer_variable_type(pd.Series([0, 1, 1]), n_distinct_threshold=2), "categorical")
        self.assertEqual(infer_variable_type(pd.Series([1, 2, 3, 4]), n_distinct_threshold=2), "continuous")

    def test_compute_variable_summary_respects_forced_dbgap_type(self) -> None:
        summary = compute_variable_summary(pd.Series([1, 2, 3, 4]), forced_type="categorical")

        self.assertEqual(summary["type"], "categorical")
        self.assertEqual(summary["n_valid"], 4)
        self.assertEqual(summary["distribution"]["1"]["n"], 1)

    def test_load_source_type_map_indexes_phv_and_variable_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pheno_dir = Path(tmp) / "pheno_variable_summaries"
            pheno_dir.mkdir()
            (pheno_dir / "synthetic_pht000001.data_dict.xml").write_text(
                '<?xml version="1.0"?>\n'
                "<data_table>\n"
                '  <variable id="phv000001.v1">\n'
                "    <name>NUMERIC_VAR</name>\n"
                "    <type>continuous integer</type>\n"
                "  </variable>\n"
                '  <variable id="phv000002.v1">\n'
                "    <name>CODE_VAR</name>\n"
                "    <type>encoded value</type>\n"
                "  </variable>\n"
                "</data_table>\n",
                encoding="utf-8",
            )

            type_map = load_source_type_map(Path(tmp))

        self.assertEqual(type_map["phv000001"], "continuous")
        self.assertEqual(type_map["numeric_var"], "continuous")
        self.assertEqual(type_map["phv000002"], "categorical")
        self.assertEqual(type_map["code_var"], "categorical")

    def test_count_rows_per_visit_returns_sorted_string_keys(self) -> None:
        df = pd.DataFrame({"visit": ["year_2", "baseline", "baseline"]})

        self.assertEqual(count_rows_per_visit(df, "visit"), {"baseline": 2, "year_2": 1})
        self.assertEqual(count_rows_per_visit(df, "missing_visit"), {})

    def test_compute_joint_distributions_uses_phv_name_map_and_normalized_keys(self) -> None:
        df = pd.DataFrame(
            {
                "STATUS": [1, 1, 0],
                "FLAG": ["Y", "Y", "N"],
            }
        )

        joint = _compute_joint_distributions(
            df,
            [("phv000001", "phv000002")],
            {"phv000001": "STATUS", "phv000002": "FLAG"},
        )

        self.assertEqual(
            joint,
            {
                "phv000001+phv000002": {
                    "0": {"N": 1},
                    "1": {"Y": 2},
                }
            },
        )


    def test_scope_columns_to_yaml_phvs_resolves_and_lowercases(self) -> None:
        yaml_phvs = {"phv00007567", "phv00172165", "phv99999999"}
        name_map = {"phv00007567": "A40", "phv00172165": "AST"}
        scoped = scope_columns_to_yaml_phvs(yaml_phvs, name_map)
        # Resolved names are lowercased; the unresolved PHV falls back to its id.
        self.assertEqual(scoped, {"a40", "ast", "phv99999999"})


if __name__ == "__main__":
    unittest.main()