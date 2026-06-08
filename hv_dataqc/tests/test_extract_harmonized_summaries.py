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


if __name__ == "__main__":
    unittest.main()