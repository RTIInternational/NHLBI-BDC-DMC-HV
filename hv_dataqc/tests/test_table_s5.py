"""Tests for hv_dataqc.extract_harmonized.table_s5."""

from __future__ import annotations

import math
import unittest

from hv_dataqc.extract_harmonized.table_s5.aggregate import (
    PooledRow,
    group_by_bdc_label,
    pool_all,
    pool_entries,
)
from hv_dataqc.extract_harmonized.table_s5.report import (
    coverage_summary,
    format_coverage_tsv,
    format_paste_tsv,
)
from hv_dataqc.extract_harmonized.table_s5.spec import (
    S5_LABEL_ALIASES,
    SHEET_COLUMNS,
    TABLE_S5_LABELS,
)


# ---------------------------------------------------------------------------
# Spec sanity
# ---------------------------------------------------------------------------

class SpecSanityTests(unittest.TestCase):

    def test_table_s5_labels_are_unique(self) -> None:
        self.assertEqual(len(TABLE_S5_LABELS), len(set(TABLE_S5_LABELS)))

    def test_s5_label_aliases_keys_are_in_table_s5(self) -> None:
        # Each alias maps a TABLE_S5_LABELS row's literal label to the
        # form harmonized_vars.tsv uses.  All alias keys must be in the
        # ordered row list — otherwise the alias never fires.
        for key in S5_LABEL_ALIASES:
            self.assertIn(key, TABLE_S5_LABELS, f"alias key not in row list: {key!r}")

    def test_sheet_columns_match_expected_order(self) -> None:
        # The spreadsheet expects exactly these columns in this order;
        # any future reorder is a coordinated update with the template.
        self.assertEqual(
            SHEET_COLUMNS,
            ["n", "nulls_missing", "mean", "median", "max", "min", "sd",
             "enums", "participants"],
        )


# ---------------------------------------------------------------------------
# Aggregation math
# ---------------------------------------------------------------------------

class PoolEntriesTests(unittest.TestCase):

    def test_empty_entries_returns_zero_row(self) -> None:
        row = pool_entries([], bdc_label="BMI")
        self.assertEqual(row.bdc_label, "BMI")
        self.assertEqual(row.n, 0)
        self.assertEqual(row.n_contributors, 0)
        self.assertIsNone(row.mean)

    def test_single_entry_passes_stats_through(self) -> None:
        entry = {
            "n_valid": 100, "n_missing": 5,
            "mean": 25.0, "median": 24.5, "sd": 4.0,
            "min": 15.0, "max": 40.0,
            "observation_type": "OMOP:4245997",
            "_cohort": "ARIC",
        }
        row = pool_entries([entry], bdc_label="BMI")
        self.assertEqual(row.n, 100)
        self.assertEqual(row.nulls_missing, 5)
        self.assertEqual(row.mean, 25.0)
        self.assertEqual(row.median, 24.5)
        self.assertEqual(row.minimum, 15.0)
        self.assertEqual(row.maximum, 40.0)
        self.assertEqual(row.sd, 4.0)
        self.assertEqual(row.contributing_codes, ("OMOP:4245997",))
        self.assertEqual(row.contributing_cohorts, ("ARIC",))
        self.assertEqual(row.n_contributors, 1)

    def test_n_weighted_mean_across_contributors(self) -> None:
        # Cohort A: n=100, mean=20.  Cohort B: n=300, mean=24.
        # Weighted mean = (100*20 + 300*24) / 400 = 9200/400 = 23.
        a = {"n_valid": 100, "mean": 20.0, "_cohort": "A"}
        b = {"n_valid": 300, "mean": 24.0, "_cohort": "B"}
        row = pool_entries([a, b], bdc_label="X")
        self.assertEqual(row.mean, 23.0)
        self.assertEqual(row.n, 400)

    def test_min_of_mins_max_of_maxes(self) -> None:
        a = {"n_valid": 10, "min": 5.0, "max": 30.0, "_cohort": "A"}
        b = {"n_valid": 20, "min": 1.0, "max": 25.0, "_cohort": "B"}
        c = {"n_valid": 30, "min": 8.0, "max": 50.0, "_cohort": "C"}
        row = pool_entries([a, b, c], bdc_label="X")
        self.assertEqual(row.minimum, 1.0)
        self.assertEqual(row.maximum, 50.0)

    def test_pooled_sd_matches_parallel_samples_formula(self) -> None:
        # Two cohorts, identical mean and sd.  The parallel-samples formula
        # uses an (N-1) denominator across the combined samples, so pooled
        # SD is sqrt((n1-1)*sd^2 + (n2-1)*sd^2) / (N-1)) which slightly
        # under-counts vs the within-cohort sd.  For n=50,50 sd=10 same mean:
        # sqrt(49*100 + 49*100) / 99 ≈ 9.949.
        a = {"n_valid": 50, "mean": 100.0, "sd": 10.0, "_cohort": "A"}
        b = {"n_valid": 50, "mean": 100.0, "sd": 10.0, "_cohort": "B"}
        row = pool_entries([a, b], bdc_label="X")
        self.assertAlmostEqual(row.sd, 9.949, places=2)
        self.assertEqual(row.mean, 100.0)

    def test_pooled_sd_uses_between_variance(self) -> None:
        # Two cohorts, same n and sd but different means — pooled SD should
        # exceed the within-cohort SD because of the between-cohort spread.
        a = {"n_valid": 100, "mean": 50.0, "sd": 5.0, "_cohort": "A"}
        b = {"n_valid": 100, "mean": 60.0, "sd": 5.0, "_cohort": "B"}
        row = pool_entries([a, b], bdc_label="X")
        # Pooled mean = 55; between-variance contribution per cohort = 100*25.
        # Within: 99*25 + 99*25 = 4950.  Between: 100*25 + 100*25 = 5000.
        # Variance = (4950 + 5000) / 199 = 9950 / 199 ≈ 50.00.
        # SD ≈ 7.07.
        self.assertGreater(row.sd, 5.0)
        self.assertAlmostEqual(row.sd, math.sqrt(50.0), places=2)

    def test_pooled_sd_none_if_contributor_lacks_sd(self) -> None:
        # If any contributor is missing sd, we can't form the parallel-samples
        # formula honestly, so return None rather than under-counting.
        a = {"n_valid": 50, "mean": 100.0, "sd": 10.0, "_cohort": "A"}
        b = {"n_valid": 50, "mean": 100.0, "_cohort": "B"}  # missing sd
        row = pool_entries([a, b], bdc_label="X")
        self.assertIsNone(row.sd)
        # Mean still pools.
        self.assertEqual(row.mean, 100.0)

    def test_missing_stats_dont_crash(self) -> None:
        # A categorical entry has no numeric stats; pool should produce
        # n / participants but None for mean/sd/etc.
        entry = {"n_valid": 200, "n_missing": 0, "_cohort": "A"}
        row = pool_entries([entry], bdc_label="sex")
        self.assertEqual(row.n, 200)
        self.assertIsNone(row.mean)
        self.assertIsNone(row.sd)
        self.assertIsNone(row.minimum)

    def test_nan_inf_in_inputs_treated_as_missing(self) -> None:
        entry = {
            "n_valid": 50, "mean": float("nan"), "sd": float("inf"),
            "_cohort": "A",
        }
        row = pool_entries([entry], bdc_label="X")
        self.assertIsNone(row.mean)
        self.assertIsNone(row.sd)

    def test_participants_none_when_no_contributor_supplies_it(self) -> None:
        # When NO contributor supplies 'participants', the result is None
        # (not a silent fallback to n_valid).  This surfaces in the
        # formatter as a blank cell rather than the misleading
        # participants==n sentinel that earlier versions emitted.
        entry = {"n_valid": 80, "_cohort": "A"}
        row = pool_entries([entry], bdc_label="X")
        self.assertIsNone(row.participants)

    def test_participants_summed_across_contributors_that_supply_it(self) -> None:
        # Cohorts have disjoint participant sets, so summing distinct
        # participant counts is correct.
        a = {"n_valid": 100, "participants": 90, "_cohort": "A"}
        b = {"n_valid": 100, "participants": 95, "_cohort": "B"}
        row = pool_entries([a, b], bdc_label="X")
        self.assertEqual(row.participants, 185)

    def test_participants_partial_sums_only_contributors_with_it(self) -> None:
        # If only some contributors supply participants, sum those and
        # ignore the rest.  Better than None (we have some signal) and
        # better than misreporting (we know which cohort's count this is).
        a = {"n_valid": 100, "participants": 90, "_cohort": "A"}
        b = {"n_valid": 100, "_cohort": "B"}  # no participants field
        row = pool_entries([a, b], bdc_label="X")
        self.assertEqual(row.participants, 90)

    def test_enums_pool_by_category(self) -> None:
        # Same category 'ABSENT' across two cohorts -> summed.  Distinct
        # categories preserved.
        a = {
            "n_valid": 100, "_cohort": "A",
            "distribution": {
                "ABSENT": {"n": 80, "pct": 80.0},
                "PRESENT": {"n": 20, "pct": 20.0},
            },
        }
        b = {
            "n_valid": 200, "_cohort": "B",
            "distribution": {
                "ABSENT": {"n": 150, "pct": 75.0},
                "UNKNOWN": {"n": 50, "pct": 25.0},
            },
        }
        row = pool_entries([a, b], bdc_label="X")
        self.assertEqual(
            row.enums,
            {"ABSENT": 230, "PRESENT": 20, "UNKNOWN": 50},
        )


# ---------------------------------------------------------------------------
# Group-by + end-to-end pool
# ---------------------------------------------------------------------------

class GroupByLabelTests(unittest.TestCase):

    def test_group_collapses_cohorts_by_bdc_label(self) -> None:
        cohorts = {
            "ARIC": {"variables": {
                "measurement_OMOP:4245997": {"bdc_label": "BMI", "n_valid": 100, "mean": 27.0},
                "measurement_OBA:VT0001253": {"bdc_label": "Height", "n_valid": 120, "mean": 170.0},
            }},
            "CHS": {"variables": {
                "measurement_OBA:BMI_ALT": {"bdc_label": "BMI", "n_valid": 50, "mean": 28.0},
                "measurement_OBA:VT0001253": {"bdc_label": "Height", "n_valid": 80, "mean": 168.0},
            }},
        }
        grouped = group_by_bdc_label(cohorts)
        self.assertEqual(set(grouped), {"BMI", "Height"})
        self.assertEqual(len(grouped["BMI"]), 2)
        self.assertEqual(len(grouped["Height"]), 2)
        # Cohort provenance is preserved.
        self.assertEqual(
            {e["_cohort"] for e in grouped["BMI"]},
            {"ARIC", "CHS"},
        )

    def test_entries_without_bdc_label_are_dropped(self) -> None:
        cohorts = {
            "ARIC": {"variables": {
                "measurement_OMOP:UNKNOWN": {"bdc_label": None, "n_valid": 100, "mean": 50.0},
                "measurement_OBA:KNOWN": {"bdc_label": "BMI", "n_valid": 50, "mean": 27.0},
            }},
        }
        grouped = group_by_bdc_label(cohorts)
        self.assertEqual(set(grouped), {"BMI"})

    def test_pool_all_end_to_end(self) -> None:
        cohorts = {
            "ARIC": {"variables": {
                "measurement_OMOP:4245997": {
                    "bdc_label": "BMI", "n_valid": 100, "mean": 27.0,
                    "sd": 4.0, "median": 26.5, "min": 18.0, "max": 45.0,
                    "n_missing": 5,
                    "observation_type": "OMOP:4245997",
                },
            }},
            "CHS": {"variables": {
                "measurement_OBA:BMI_ALT": {
                    "bdc_label": "BMI", "n_valid": 200, "mean": 28.5,
                    "sd": 5.0, "median": 28.0, "min": 16.0, "max": 50.0,
                    "n_missing": 10,
                    "observation_type": "OBA:BMI_ALT",
                },
            }},
        }
        pooled = pool_all(cohorts)
        self.assertEqual(set(pooled), {"BMI"})
        bmi = pooled["BMI"]
        self.assertEqual(bmi.n, 300)
        self.assertEqual(bmi.nulls_missing, 15)
        # n-weighted: (100*27 + 200*28.5) / 300 = (2700 + 5700) / 300 = 28.0
        self.assertAlmostEqual(bmi.mean, 28.0, places=4)
        # min-of-mins / max-of-maxes
        self.assertEqual(bmi.minimum, 16.0)
        self.assertEqual(bmi.maximum, 50.0)
        # Pooled SD is well-defined since both contributors have all 3.
        self.assertIsNotNone(bmi.sd)
        # Provenance.
        self.assertEqual(bmi.contributing_cohorts, ("ARIC", "CHS"))
        self.assertEqual(sorted(bmi.contributing_codes), ["OBA:BMI_ALT", "OMOP:4245997"])


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

class FormatPasteTsvTests(unittest.TestCase):

    def test_matched_label_renders_stats(self) -> None:
        pooled = {
            "BMI": PooledRow(
                bdc_label="BMI", n=300, nulls_missing=15, participants=270,
                mean=28.0, median=27.0, minimum=16.0, maximum=50.0, sd=5.0,
                enums={},
                contributing_codes=("OBA:BMI_ALT", "OMOP:4245997"),
                contributing_cohorts=("ARIC", "CHS"), n_contributors=2,
            ),
        }
        paste, coverage = format_paste_tsv(pooled)
        lines = paste.split("\n")
        self.assertEqual(len(lines), len(TABLE_S5_LABELS))
        # Find the BMI row index and verify it's filled.
        bmi_idx = TABLE_S5_LABELS.index("BMI")
        cells = lines[bmi_idx].split("\t")
        self.assertEqual(cells[0], "300")    # n
        self.assertEqual(cells[1], "15")     # nulls_missing
        self.assertEqual(cells[2], "28.0")   # mean
        self.assertEqual(cells[3], "27.0")   # median
        self.assertEqual(cells[4], "50.0")   # max
        self.assertEqual(cells[5], "16.0")   # min
        self.assertEqual(cells[6], "5.0")    # sd
        self.assertEqual(cells[7], "")       # enums (empty for continuous)
        self.assertEqual(cells[8], "270")    # participants — distinct, not == n
        # Coverage for BMI is 'matched'.
        bmi_cov = next(r for r in coverage if r["s5_label"] == "BMI")
        self.assertEqual(bmi_cov["status"], "matched")
        self.assertEqual(bmi_cov["n_contributors"], 2)

    def test_missing_label_renders_blank_row(self) -> None:
        paste, coverage = format_paste_tsv({})
        lines = paste.split("\n")
        # Every line is empty-tab-separated.
        for line in lines:
            self.assertEqual(line, "\t" * (len(SHEET_COLUMNS) - 1))
        # Every coverage row is 'missing'.
        statuses = {r["status"] for r in coverage}
        self.assertEqual(statuses, {"missing"})

    def test_aliased_label_uses_alias_lookup(self) -> None:
        # S5 expects "Fruit consumption" but harmonized_vars.tsv uses "Fruits".
        pooled = {
            "Fruits": PooledRow(
                bdc_label="Fruits", n=50, nulls_missing=0, participants=50,
                mean=None, median=None, minimum=None, maximum=None, sd=None,
                enums={},
                contributing_codes=(), contributing_cohorts=("ARIC",),
                n_contributors=1,
            ),
        }
        paste, coverage = format_paste_tsv(pooled)
        # "Fruit consumption" row in S5 should be filled via the alias.
        idx = TABLE_S5_LABELS.index("Fruit consumption")
        cells = paste.split("\n")[idx].split("\t")
        self.assertEqual(cells[0], "50")
        # Coverage row marks it as 'aliased'.
        cov_row = next(r for r in coverage if r["s5_label"] == "Fruit consumption")
        self.assertEqual(cov_row["status"], "aliased")
        self.assertEqual(cov_row["lookup_label"], "Fruits")

    def test_coverage_tsv_has_header(self) -> None:
        pooled = {
            "BMI": PooledRow(
                bdc_label="BMI", n=100, nulls_missing=0, participants=100,
                mean=27.0, median=None, minimum=None, maximum=None, sd=None,
                enums={},
                contributing_codes=("OMOP:4245997",),
                contributing_cohorts=("ARIC",), n_contributors=1,
            ),
        }
        _, coverage = format_paste_tsv(pooled)
        cov_tsv = format_coverage_tsv(coverage)
        header = cov_tsv.split("\n")[0].split("\t")
        self.assertIn("s5_label", header)
        self.assertIn("status", header)
        self.assertIn("n_contributors", header)

    def test_categorical_row_renders_enums(self) -> None:
        # Categorical variable with three categories.  Cells 2-6 (mean...sd)
        # should be blank, enums (cell 7) should be the formatted dict
        # sorted descending by count, participants (cell 8) populated.
        pooled = {
            "Cigarette smoking": PooledRow(
                bdc_label="Cigarette smoking", n=300, nulls_missing=15,
                participants=270,
                mean=None, median=None, minimum=None, maximum=None, sd=None,
                enums={"NEVER": 180, "FORMER": 80, "CURRENT": 40},
                contributing_codes=("OMOP:45883537",),
                contributing_cohorts=("ARIC",), n_contributors=1,
            ),
        }
        paste, _ = format_paste_tsv(pooled)
        idx = TABLE_S5_LABELS.index("Cigarette smoking")
        cells = paste.split("\n")[idx].split("\t")
        self.assertEqual(cells[2], "")                # mean
        self.assertEqual(cells[3], "")                # median
        # enums sorted descending by count.
        self.assertEqual(cells[7], "NEVER: 180; FORMER: 80; CURRENT: 40")
        self.assertEqual(cells[8], "270")             # participants

    def test_participants_blank_when_none(self) -> None:
        # When participants is None (no contributor supplied it), the cell
        # should render blank — not "0", not "n", just empty.
        pooled = {
            "BMI": PooledRow(
                bdc_label="BMI", n=100, nulls_missing=0, participants=None,
                mean=27.0, median=None, minimum=None, maximum=None, sd=None,
                enums={},
                contributing_codes=(), contributing_cohorts=(),
                n_contributors=1,
            ),
        }
        paste, _ = format_paste_tsv(pooled)
        idx = TABLE_S5_LABELS.index("BMI")
        cells = paste.split("\n")[idx].split("\t")
        self.assertEqual(cells[0], "100")  # n is set
        self.assertEqual(cells[8], "")     # participants blank

    def test_coverage_summary_string(self) -> None:
        pooled = {"BMI": PooledRow(
            bdc_label="BMI", n=100, nulls_missing=0, participants=100,
            mean=27.0, median=None, minimum=None, maximum=None, sd=None,
            enums={},
            contributing_codes=(), contributing_cohorts=(), n_contributors=1,
        )}
        _, coverage = format_paste_tsv(pooled)
        summary = coverage_summary(coverage)
        self.assertIn("matched", summary)
        self.assertIn("missing", summary)
        self.assertIn(f"of {len(TABLE_S5_LABELS)}", summary)


if __name__ == "__main__":
    unittest.main()
