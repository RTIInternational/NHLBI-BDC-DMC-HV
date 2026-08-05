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
    apply_quasi_identifier_suppression,
    compute_variable_summary,
    count_rows_per_visit,
    infer_variable_type,
    is_join_unsafe_column,
    is_quasi_identifier_column,
    is_system_column,
    load_source_data,
    load_source_type_map,
)
from hv_dataqc.hv_dataqc_common import MAX_CATEGORICAL_KEYS, categorical_stats


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

    def test_study_native_participant_ids_are_system_columns(self) -> None:
        # FHS shareid and CARDIA individual_id enumerate individual subjects and
        # must be treated as identifiers (regression: previously uncaught).
        self.assertTrue(is_system_column("shareid"))
        self.assertTrue(is_system_column("SHAREID"))
        self.assertTrue(is_system_column("individual_id"))
        self.assertTrue(is_system_column("Individual_ID"))
        self.assertFalse(is_system_column("idtype"))  # a discriminator, not an ID

    def test_is_quasi_identifier_column_flags_dates_and_ages(self) -> None:
        for name in ("cvddate", "chddate", "EX_DATE", "DATE", "visitdt", "dob", "age_s1", "AGE"):
            self.assertTrue(is_quasi_identifier_column(name), name)
        for name in ("idtype", "a09mdnow", "ffd30", "blood_pressure", "package"):
            self.assertFalse(is_quasi_identifier_column(name), name)

    def test_is_join_unsafe_column_combines_id_and_quasi_identifier(self) -> None:
        self.assertTrue(is_join_unsafe_column("idtype", "shareid"))     # id axis
        self.assertTrue(is_join_unsafe_column("cvd", "cvddate"))        # date axis
        self.assertTrue(is_join_unsafe_column("individual_id", "a09mdnow"))
        self.assertFalse(is_join_unsafe_column("g3a539", "g3a540"))     # both coded

    def test_compute_joint_distributions_excludes_identifier_and_date_pairs(self) -> None:
        df = pd.DataFrame(
            {
                "IDTYPE": [1, 1, 2],
                "shareid": [1001, 1002, 1003],
                "STATUS": [1, 1, 0],
                "cvddate": ["2001-01-01", "2002-02-02", "2003-03-03"],
                "FLAG": ["Y", "Y", "N"],
            }
        )
        names = {
            "phv000001": "IDTYPE",
            "phv000002": "shareid",
            "phv000003": "STATUS",
            "phv000004": "cvddate",
            "phv000005": "FLAG",
        }

        joint = _compute_joint_distributions(
            df,
            [
                ("phv000001", "phv000002"),  # IDTYPE x shareid  -> excluded (id)
                ("phv000003", "phv000004"),  # STATUS x cvddate  -> excluded (date)
                ("phv000003", "phv000005"),  # STATUS x FLAG      -> kept (coded)
            ],
            names,
        )

        # Only the coded-value pair survives; no subject ids or dates appear.
        self.assertEqual(list(joint.keys()), ["phv000003+phv000005"])
        self.assertEqual(joint["phv000003+phv000005"], {"0": {"N": 1}, "1": {"Y": 2}})

    def test_categorical_stats_normalizes_keys_and_sums_collisions(self) -> None:
        # "1" and "1.0" are the same logical value; they must collapse to one
        # key with summed count (H1 — prevents false C7/C12 mismatches).
        summary = categorical_stats(pd.Series(["1", "1.0", "1", "2"]))
        self.assertEqual(summary["distribution"]["1"]["n"], 3)
        self.assertEqual(summary["distribution"]["2"]["n"], 1)
        self.assertNotIn("1.0", summary["distribution"])
        self.assertEqual(summary["n_distinct"], 2)

    def test_categorical_stats_caps_high_cardinality_distribution(self) -> None:
        # A high-cardinality (free-text/date-like) column must not enumerate a
        # long tail of near-unique values (H5). Keep top-K + __other__.
        values = [f"v{i}" for i in range(MAX_CATEGORICAL_KEYS + 25)]
        summary = categorical_stats(pd.Series(values))
        self.assertTrue(summary.get("distribution_truncated"))
        self.assertLessEqual(len(summary["distribution"]), MAX_CATEGORICAL_KEYS + 1)
        self.assertIn("__other__", summary["distribution"])
        self.assertEqual(summary["n_distinct"], MAX_CATEGORICAL_KEYS + 25)
        # Counts still reconcile to n_valid.
        self.assertEqual(
            sum(v["n"] for v in summary["distribution"].values()), summary["n_valid"]
        )

    def test_apply_quasi_identifier_suppression(self) -> None:
        cat = {"type": "categorical", "n_valid": 3, "distribution": {"2001-01-01": {"n": 1}}}
        # Date column -> distribution emptied, counts retained, flagged.
        out = apply_quasi_identifier_suppression(cat, "exdate")
        self.assertEqual(out["distribution"], {})
        self.assertEqual(out["distribution_suppressed"], "quasi_identifier")
        self.assertEqual(out["n_valid"], 3)
        # Non-QI categorical column -> unchanged (same object).
        self.assertIs(apply_quasi_identifier_suppression(cat, "idtype"), cat)
        # Continuous summary -> never touched even for a QI name.
        cont = {"type": "continuous", "mean": 45.0, "min": 20, "max": 80}
        self.assertIs(apply_quasi_identifier_suppression(cont, "age_s1"), cont)

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


if __name__ == "__main__":
    unittest.main()