"""Smoke tests for hv-dcc-compare.

These tests use only synthetic data and verify packaging, CLI startup, and the
aggregate-only safety contract. They must not require participant-level data.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HvDccCompareSmokeTests(unittest.TestCase):
    def run_script(self, relative_path: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / relative_path), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_config_imports(self) -> None:
        original_sys_path = sys.path.copy()
        try:
            sys.path.insert(0, str(ROOT))
            import config  # type: ignore  # noqa: PLC0415

            self.assertIn("ARIC", config.COHORTS)
            self.assertIn("demographics", config.DATASETS)
            self.assertGreaterEqual(len(config.BDC_MEASUREMENT_MAP), 1)
            self.assertEqual(config.normalize_cohort_name("HCHS"), "HCHS_SOL")
        finally:
            sys.path[:] = original_sys_path

    def test_cli_help_starts(self) -> None:
        scripts = [
            "extract-topmed/extract_topmed_summaries.py",
            "extract-harmonized/extract_harmonized_summaries.py",
            "compare/compare.py",
            "compare/match_quality_table.py",
            "compare/validate_completeness.py",
            "compare/batch_scorecard.py",
            "compare/core_variable_coverage_table.py",
        ]
        for script in scripts:
            with self.subTest(script=script):
                result = self.run_script(script, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout.lower())

    def test_topmed_extract_outputs_aggregate_json_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "demographics.tsv"
            out_dir = tmp_path / "out"
            input_path.write_text(
                "SUBJECT_ID\tunique_subject_key\ttopmed_study\tdcc_harmonization_id\tvariable\tvalue\n"
                "TEST_ID_001\tKEY001\tARIC\tH1\tannotated_sex_1\tFemale\n"
                "TEST_ID_002\tKEY002\tARIC\tH1\tannotated_sex_1\tMale\n"
                "TEST_ID_001\tKEY001\tARIC\tH1\trace_us_1\tWhite\n",
                encoding="utf-8",
            )

            result = self.run_script(
                "extract-topmed/extract_topmed_summaries.py",
                "--demographics-file",
                str(input_path),
                "--output-dir",
                str(out_dir),
                "--cohorts",
                "ARIC",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            combined_output = result.stdout + result.stderr
            self.assertNotIn("TEST_ID_001", combined_output)
            self.assertNotIn("KEY001", combined_output)

            json_path = out_dir / "topmed_aric_summary.json"
            data = json.loads(json_path.read_text(encoding="utf-8"))
            serialized = json.dumps(data)
            self.assertNotIn("TEST_ID_001", serialized)
            self.assertNotIn("KEY001", serialized)
            self.assertEqual(data["total_participants"], 2)
            self.assertIn("annotated_sex_1", data["variables"])

    def test_translate_bdc_json_remaps_concept_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            in_path = Path(tmp) / "bdc.json"
            out_path = Path(tmp) / "translated.json"
            in_path.write_text(
                json.dumps(
                    {
                        "metadata": {"cohort": "ARIC"},
                        "variables": {
                            "OBA:VT0001253": {
                                "type": "continuous",
                                "n_valid": 1,
                                "bdc_label": "Height",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_script(
                "compare/translate_bdc_json.py",
                str(in_path),
                str(out_path),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertIn("height_baseline_1", data["variables"])
            self.assertNotIn("OBA:VT0001253", data["variables"])

    def test_no_known_participant_level_debug_prints(self) -> None:
        source_files = [
            ROOT / "extract-harmonized" / "extract_harmonized_summaries.py",
            ROOT / "extract-topmed" / "extract_topmed_summaries.py",
            ROOT / "compare" / "validate_completeness.py",
        ]
        forbidden_fragments = [
            "Sample IDs:",
            "Sample procedure IDs:",
            "Sample demography IDs:",
            "Raw samples:",
            "Check sample output above",
        ]
        for path in source_files:
            text = path.read_text(encoding="utf-8")
            for fragment in forbidden_fragments:
                with self.subTest(path=path.name, fragment=fragment):
                    self.assertNotIn(fragment, text)


if __name__ == "__main__":
    unittest.main()
