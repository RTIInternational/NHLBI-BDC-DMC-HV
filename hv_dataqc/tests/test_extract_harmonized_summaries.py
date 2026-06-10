"""Focused tests for harmonized TSV summary extraction.

All fixtures are synthetic and contain no participant identifiers or source
study records.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from hv_dataqc.extract_harmonized.extract_harmonized_summaries import (
    build_visit_id_to_label,
    load_entity,
    process_measurement_observation_sets,
    process_measurements,
    process_observations,
    resolve_visit_series,
)


class ExtractHarmonizedSummaryTests(unittest.TestCase):
    def test_load_entity_concatenates_mapped_data_dirs_and_strips_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mapped_dirs: list[Path] = []
            for idx, value in enumerate(["YES", "NO"], start=1):
                mapped_dir = root / f"run_{idx}" / "synthetic_BDCHM" / "mapped-data"
                mapped_dir.mkdir(parents=True)
                mapped_dirs.append(mapped_dir)
                (mapped_dir / "MeasurementObservation.tsv").write_text(
                    " observation_type \t value_enum \n"
                    f"OBA:SYNTHETIC\t{value}\n",
                    encoding="utf-8",
                )

            df = load_entity(mapped_dirs, "MeasurementObservation")

        self.assertIsNotNone(df)
        self.assertEqual(list(df.columns), ["observation_type", "value_enum"])
        self.assertEqual(len(df), 2)
        self.assertEqual(df["value_enum"].tolist(), ["YES", "NO"])

    def test_visit_id_resolution_prefers_name_and_preserves_unknown_values(self) -> None:
        visit_df = pd.DataFrame(
            {
                "id": ["uuid-visit-1", "uuid-visit-2"],
                "name": ["baseline", "year_2"],
                "visit_type": ["fallback_baseline", "fallback_year_2"],
            }
        )

        mapping = build_visit_id_to_label(visit_df)
        resolved = resolve_visit_series(
            pd.Series(["uuid-visit-1", "already_labeled", None]),
            mapping,
        )

        self.assertEqual(mapping["uuid-visit-1"], "baseline")
        self.assertEqual(resolved.iloc[:2].tolist(), ["baseline", "already_labeled"])
        self.assertTrue(pd.isna(resolved.iloc[2]))

    def test_measurements_summarize_flat_enum_status_and_resolved_visits(self) -> None:
        df = pd.DataFrame(
            {
                "observation_type": ["OBA:ENUM", "OBA:ENUM", "OBA:STATUS", "OBA:STATUS"],
                "value_enum": ["YES", "NO", None, None],
                "measurement_status": [None, None, "present", "absent"],
                "associated_visit": ["uuid-visit-1", "uuid-visit-2", "uuid-visit-1", "uuid-visit-2"],
            }
        )
        visit_map = {"uuid-visit-1": "baseline", "uuid-visit-2": "year_2"}

        variables = process_measurements(df, visit_map, by_visit=True)

        enum_summary = variables["measurement_OBA:ENUM"]
        self.assertEqual(enum_summary["type"], "categorical")
        self.assertEqual(enum_summary["n_valid"], 2)
        self.assertEqual(enum_summary["distribution"]["YES"]["n"], 1)
        self.assertEqual(enum_summary["by_visit"]["baseline"]["distribution"]["YES"]["n"], 1)

        status_summary = variables["measurement_OBA:STATUS"]
        self.assertEqual(status_summary["type"], "categorical")
        self.assertEqual(status_summary["n_valid"], 2)
        self.assertEqual(status_summary["distribution"]["present"]["n"], 1)
        self.assertEqual(status_summary["by_visit"]["year_2"]["distribution"]["absent"]["n"], 1)

    def test_measurement_observation_sets_parse_values_methods_and_visits(self) -> None:
        df = pd.DataFrame(
            {
                "associated_visit": ["uuid-visit-1", "uuid-visit-2"],
                "observations": [
                    json.dumps(
                        [
                            {
                                "observation_type": "OBA:DECIMAL",
                                "method_type": "seated",
                                "value_quantity": {"value_decimal": 10.0},
                            },
                            {
                                "observation_type": ["OBA:CONCEPT"],
                                "value_quantity": {"value_concept": "OMOP:123"},
                            },
                        ]
                    ),
                    "[{'observation_type': ('OBA:CODED',), "
                    "'value_quantity': {'value_coded': 'HIGH'}}]",
                ],
            }
        )
        diagnostics: dict = {}

        variables = process_measurement_observation_sets(
            df,
            {"uuid-visit-1": "baseline", "uuid-visit-2": "year_2"},
            by_visit=True,
            diagnostics_out=diagnostics,
        )

        decimal = variables["measurement_OBA:DECIMAL|seated"]
        self.assertEqual(decimal["type"], "continuous")
        self.assertEqual(decimal["mean"], 10.0)
        self.assertEqual(decimal["by_visit"]["baseline"]["n_valid"], 1)

        self.assertEqual(
            variables["measurement_OBA:CONCEPT"]["distribution"]["OMOP:123"]["n"],
            1,
        )
        self.assertEqual(
            variables["measurement_OBA:CODED"]["by_visit"]["year_2"]["distribution"]["HIGH"]["n"],
            1,
        )
        self.assertEqual(diagnostics["measurement_observation_set_parse_errors"], 0)
        self.assertEqual(diagnostics["measurement_observation_set_rows_examined"], 2)

    def test_measurement_observation_sets_report_parse_errors(self) -> None:
        df = pd.DataFrame({"observations": ["not a parseable observations list", ""]})
        diagnostics: dict = {}

        variables = process_measurement_observation_sets(df, {}, diagnostics_out=diagnostics)

        self.assertEqual(variables, {})
        self.assertEqual(diagnostics["measurement_observation_set_parse_errors"], 1)
        self.assertEqual(diagnostics["measurement_observation_set_rows_examined"], 2)


class LabelMapWiringTests(unittest.TestCase):
    """The three entity processors should populate `bdc_label` when a label
    map is supplied, and leave it `None` otherwise."""

    LABEL_MAP = {
        "OBA:VT0001253": "Height",
        "OMOP:4245997": "BMI",
        "CESD_SCORE": "CESD score",
    }

    def test_process_measurements_populates_bdc_label(self) -> None:
        df = pd.DataFrame(
            {
                "observation_type": ["OBA:VT0001253", "OMOP:4245997"],
                "value_quantity__value_decimal": [180.0, 24.5],
            }
        )
        variables = process_measurements(df, {}, label_map=self.LABEL_MAP)
        self.assertEqual(variables["measurement_OBA:VT0001253"]["bdc_label"], "Height")
        self.assertEqual(variables["measurement_OMOP:4245997"]["bdc_label"], "BMI")

    def test_process_measurements_bdc_label_none_when_no_map(self) -> None:
        df = pd.DataFrame(
            {
                "observation_type": ["OBA:VT0001253"],
                "value_quantity__value_decimal": [180.0],
            }
        )
        variables = process_measurements(df, {})
        self.assertIsNone(variables["measurement_OBA:VT0001253"]["bdc_label"])

    def test_process_measurements_bdc_label_none_for_unknown_obs_type(self) -> None:
        df = pd.DataFrame(
            {
                "observation_type": ["OBA:UNMAPPED"],
                "value_quantity__value_decimal": [42.0],
            }
        )
        variables = process_measurements(df, {}, label_map=self.LABEL_MAP)
        self.assertIsNone(variables["measurement_OBA:UNMAPPED"]["bdc_label"])

    def test_process_observations_populates_bdc_label(self) -> None:
        df = pd.DataFrame(
            {
                "observation_type": ["CESD_SCORE"],
                "value_quantity__value_decimal": [12.0],
            }
        )
        variables = process_observations(df, label_map=self.LABEL_MAP)
        self.assertEqual(variables["observation_CESD_SCORE"]["bdc_label"], "CESD score")

    def test_process_observations_bdc_label_none_when_no_map(self) -> None:
        df = pd.DataFrame(
            {
                "observation_type": ["CESD_SCORE"],
                "value_quantity__value_decimal": [12.0],
            }
        )
        variables = process_observations(df)
        self.assertIsNone(variables["observation_CESD_SCORE"]["bdc_label"])

    def test_process_measurement_observation_sets_populates_bdc_label(self) -> None:
        # MOS observations are stringified Python list-of-dicts that get
        # parsed by ast.literal_eval.
        df = pd.DataFrame(
            {
                "observations": [
                    "[{'observation_type': 'OBA:VT0001253', "
                    "'value_quantity': {'value_decimal': 175.0}}]",
                ],
            }
        )
        variables = process_measurement_observation_sets(
            df, {}, label_map=self.LABEL_MAP,
        )
        # MOS uses 'measurement_set_{obs_type}' as the key prefix.
        keys = [k for k in variables if "VT0001253" in k]
        self.assertTrue(keys, f"expected a Height key, got: {list(variables)}")
        self.assertEqual(variables[keys[0]]["bdc_label"], "Height")


class LabelMapMainWiringTests(unittest.TestCase):
    """Regression tests for the main() -> _run_extract -> processor wiring.

    When the label_map flag was first added, ``main()`` loaded the map but
    didn't pass it through to ``_run_extract``, which still referenced
    ``label_map`` from its enclosing scope and raised ``NameError`` at
    runtime — caught only on the first SB run.  These tests use
    ``inspect.signature`` to verify the wiring without needing TSV fixtures.
    """

    def test_run_extract_accepts_label_map_parameter(self) -> None:
        import inspect
        from hv_dataqc.extract_harmonized.extract_harmonized_summaries import _run_extract
        sig = inspect.signature(_run_extract)
        self.assertIn(
            "label_map", sig.parameters,
            "_run_extract must accept label_map; main() loads it and "
            "_run_extract uses it in the processor call sites.",
        )

    def test_main_passes_label_map_to_run_extract(self) -> None:
        # Structural check: main()'s body should contain `label_map=label_map`
        # as a kwarg in the _run_extract call.  If a refactor renames either
        # side, this test fails loudly.
        import inspect
        from hv_dataqc.extract_harmonized.extract_harmonized_summaries import main
        source = inspect.getsource(main)
        self.assertIn(
            "label_map=label_map", source,
            "main() must forward its loaded label_map into _run_extract.",
        )


class ParticipantsCountedOverValidRowsTests(unittest.TestCase):
    """Regression tests for the participants-vs-n_valid mask alignment.

    Anne reported S5 rows where the participants column exceeded n (8-epi-
    PGF2a in urine: participants=9,730 vs n=3,096; WHI BUN per-cohort:
    participants=39,046 vs n_valid=5,928).  Root cause: participants was
    counted via `group[pcol].nunique()` over the *whole* group, including
    rows whose value column was null.  Those rows contribute nothing to
    n_valid but were inflating the distinct-participant count.

    Fix: count distinct participants only over rows where the chosen value
    column is non-null — the same population that produced n_valid.
    """

    def test_participants_not_counted_for_rows_with_null_value(self) -> None:
        # 4 distinct participants in the group, but only participants A and
        # B contribute non-null values.  Expect participants=2, not 4.
        df = pd.DataFrame(
            {
                "observation_type": ["OMOP:X"] * 4,
                "value_quantity__value_decimal": [10.0, 20.0, None, None],
                "associated_participant": ["A", "B", "C", "D"],
            }
        )
        variables = process_measurements(df, {})
        self.assertEqual(variables["measurement_OMOP:X"]["n_valid"], 2)
        self.assertEqual(variables["measurement_OMOP:X"]["participants"], 2)

    def test_participants_never_exceeds_n_valid(self) -> None:
        # Synthetic case where 100 participants visited but only 30 had a
        # value recorded.  participants should be at most 30 (and is in
        # fact 30 here because each of those 30 is distinct).
        rows = []
        for i in range(30):
            rows.append({"observation_type": "OMOP:Y",
                         "value_quantity__value_decimal": float(i),
                         "associated_participant": f"P{i}"})
        for i in range(30, 100):
            # Same observation_type but no value recorded.
            rows.append({"observation_type": "OMOP:Y",
                         "value_quantity__value_decimal": None,
                         "associated_participant": f"P{i}"})
        df = pd.DataFrame(rows)
        variables = process_measurements(df, {})
        n_valid = variables["measurement_OMOP:Y"]["n_valid"]
        participants = variables["measurement_OMOP:Y"]["participants"]
        self.assertEqual(n_valid, 30)
        self.assertLessEqual(participants, n_valid,
                             "participants must not exceed n_valid")
        self.assertEqual(participants, 30)

    def test_repeat_visits_same_participant_counted_once(self) -> None:
        # Same participant contributing 3 measurements should count once
        # in participants but as 3 in n_valid (this is the harmless case
        # — participants <= n_valid).
        df = pd.DataFrame(
            {
                "observation_type": ["OMOP:Z"] * 3,
                "value_quantity__value_decimal": [10.0, 11.0, 12.0],
                "associated_participant": ["A", "A", "A"],
            }
        )
        variables = process_measurements(df, {})
        self.assertEqual(variables["measurement_OMOP:Z"]["n_valid"], 3)
        self.assertEqual(variables["measurement_OMOP:Z"]["participants"], 1)

    def test_observation_processor_also_masks(self) -> None:
        # Same bug existed in process_observations; same fix.
        df = pd.DataFrame(
            {
                "observation_type": ["OMOP:W"] * 4,
                "value_quantity__value_decimal": [5.0, None, None, 6.0],
                "associated_participant": ["A", "B", "C", "A"],
            }
        )
        variables = process_observations(df)
        # Only A (twice) and... wait, A has two rows.  Rows 0 and 3 have
        # values; row 0 is A, row 3 is A again.  So participants = 1, not 2.
        self.assertEqual(variables["observation_OMOP:W"]["n_valid"], 2)
        self.assertEqual(variables["observation_OMOP:W"]["participants"], 1)

    def test_non_numeric_value_strings_do_not_inflate_participants(self) -> None:
        # Anne caught FHS ALT SGPT showing participants=3,732 over n_valid=3,728.
        # Root cause: continuous_stats coerces value strings to numeric via
        # pd.to_numeric(errors="coerce"), so rows with non-numeric values
        # (sentinels like "<5", "censored") contribute to n_total but not
        # n_valid.  The participants-count mask must apply the same coercion
        # — otherwise those non-coerce-able rows' participants count toward
        # participants but not toward n_valid, inflating the former.
        df = pd.DataFrame(
            {
                "observation_type": ["OBA:LIVER"] * 6,
                # 4 numeric, 2 sentinels.  pd.to_numeric coerces the sentinels
                # to NaN, so n_valid=4.  Participants from sentinel rows
                # (E, F) must NOT inflate the count beyond 4.
                "value_quantity__value_decimal": [10.0, 20.0, 30.0, 40.0,
                                                  "censored", "<5"],
                "associated_participant": ["A", "B", "C", "D", "E", "F"],
            }
        )
        variables = process_measurements(df, {})
        result = variables["measurement_OBA:LIVER"]
        self.assertEqual(result["n_valid"], 4)
        # Participants must not exceed n_valid even though six distinct
        # participant IDs are present in the raw group.
        self.assertEqual(result["participants"], 4)


if __name__ == "__main__":
    unittest.main()