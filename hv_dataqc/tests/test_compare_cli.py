"""CLI smoke tests for hv_dataqc.compare.

All fixtures are synthetic aggregate summaries only; no participant-level rows
or identifiers are embedded here.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from hv_dataqc.compare.compare import main as compare_main


class CompareCliSmokeTests(unittest.TestCase):
    def _write_smoke_inputs(self, tmp_path: Path) -> dict[str, Path]:
        source_path = tmp_path / "source.json"
        harmonized_path = tmp_path / "harmonized.json"
        report_path = tmp_path / "report.md"
        json_report_path = tmp_path / "report.json"
        yaml_dir = tmp_path / "yaml"
        cache_dir = tmp_path / "cache"
        pheno_dir = cache_dir / "pheno_variable_summaries"
        yaml_dir.mkdir()
        pheno_dir.mkdir(parents=True)

        source_path.write_text(
            json.dumps(
                {
                    "metadata": {"source": "synthetic"},
                    "total_participants": 10,
                    "participant_denominators": {"mapped_source_union_n": 10},
                    "total_rows_by_pht": {"pht000001": 10},
                    "variables_by_pht": {
                        "pht000001": {
                            "HR": {
                                "name": "HR",
                                "_pht": "pht000001",
                                "type": "continuous",
                                "n_total": 10,
                                "n_valid": 10,
                                "n_missing": 0,
                                "pct_missing": 0.0,
                                "mean": 70.0,
                                "sd": 5.0,
                                "min": 60.0,
                                "max": 80.0,
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        harmonized_path.write_text(
            json.dumps(
                {
                    "metadata": {"source": "synthetic"},
                    "total_participants": 10,
                    "entity_counts": {"MeasurementObservation": 10},
                    "rows_per_visit": {},
                    "variables": {
                        "measurement_OBA:1001087": {
                            "type": "continuous",
                            "observation_type": "OBA:1001087",
                            "n_total": 10,
                            "n_valid": 10,
                            "n_missing": 0,
                            "pct_missing": 0.0,
                            "mean": 70.0,
                            "sd": 5.0,
                            "min": 60.0,
                            "max": 80.0,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        (pheno_dir / "phs000000.v1.pht000001.v1.p1.synthetic.data_dict.xml").write_text(
            '<?xml version="1.0"?>\n'
            "<data_table>\n"
            '  <variable id="phv000001.v1">\n'
            "    <name>HR</name>\n"
            "    <type>decimal</type>\n"
            "  </variable>\n"
            "</data_table>\n",
            encoding="utf-8",
        )
        (yaml_dir / "heart_rate.yaml").write_text(
            "- class_derivations:\n"
            "    MeasurementObservation:\n"
            "      populated_from: pht000001\n"
            "      slot_derivations:\n"
            "        observation_type:\n"
            "          value: OBA:1001087\n"
            "        value_quantity:\n"
            "          object_derivations:\n"
            "          - class_derivations:\n"
            "              Quantity:\n"
            "                slot_derivations:\n"
            "                  value_decimal:\n"
            "                    populated_from: phv000001\n",
            encoding="utf-8",
        )
        return {
            "source": source_path,
            "harmonized": harmonized_path,
            "yaml_dir": yaml_dir,
            "cache_dir": cache_dir,
            "report": report_path,
            "json_report": json_report_path,
        }

    def test_compare_cli_writes_reports_for_minimal_successful_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_smoke_inputs(Path(tmp))
            argv = [
                "--source", str(paths["source"]),
                "--harmonized", str(paths["harmonized"]),
                "--cohort", "TESTCOHORT",
                "--yaml-dir", str(paths["yaml_dir"]),
                "--cache-dir", str(paths["cache_dir"]),
                "--report", str(paths["report"]),
                "--json-report", str(paths["json_report"]),
            ]

            with contextlib.redirect_stdout(io.StringIO()):
                compare_main(argv)

            self.assertTrue(paths["report"].exists())
            self.assertTrue(paths["json_report"].exists())
            payload = json.loads(paths["json_report"].read_text(encoding="utf-8"))
            self.assertEqual(payload["metadata"]["cohort"], "TESTCOHORT")
            self.assertEqual(payload["summary"].get("FAIL", 0), 0)
            self.assertEqual(payload["crosswalk"][0]["source_key"], "HR")


if __name__ == "__main__":
    unittest.main()