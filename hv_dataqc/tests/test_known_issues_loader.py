"""Resilience tests for the known_issues config loader.

A malformed known_issues YAML is human-edited documentation metadata and must
not abort the whole compare run (regression: a wrapped unquoted evidence value
in ARIC.yaml raised yaml.ScannerError and failed the entire ARIC run even though
both extract steps passed).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from hv_dataqc.compare import known_issues


class LoadKnownIssuesResilienceTests(unittest.TestCase):
    def _run_with_config(self, filename: str | None, text: str | None) -> list[dict]:
        tmp = tempfile.TemporaryDirectory()
        try:
            if filename is not None and text is not None:
                (Path(tmp.name) / filename).write_text(text, encoding="utf-8")
            orig = known_issues._CONFIG_DIR
            known_issues._CONFIG_DIR = Path(tmp.name)
            try:
                return known_issues.load_known_issues("testco")
            finally:
                known_issues._CONFIG_DIR = orig
        finally:
            tmp.cleanup()

    def test_valid_config_loads_entries(self) -> None:
        entries = self._run_with_config(
            "TESTCO.yaml",
            "known_issues:\n  - checks: [C2]\n    variable_key: 'x'\n",
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["variable_key"], "x")

    def test_malformed_config_returns_empty_not_raises(self) -> None:
        # Exact ARIC failure mode: a "- Label: text" evidence value that wraps
        # onto an unquoted second line, which the YAML scanner cannot parse.
        bad = (
            "known_issues:\n"
            "  - checks: [C2]\n"
            "    variable_key: 'x'\n"
            "    evidence:\n"
            "      - Harmonized JSON: measurement_OMOP:4152194 n_total=208,560\n"
            "        (plain MO across all method_types combined)\n"
        )
        # Must NOT raise; returns [] so the compare run still proceeds.
        self.assertEqual(self._run_with_config("TESTCO.yaml", bad), [])

    def test_missing_config_returns_empty(self) -> None:
        self.assertEqual(self._run_with_config(None, None), [])


class KnownIssuesConfigValidityTests(unittest.TestCase):
    """CI lint: every shipped known_issues/*.yaml must parse and be well-formed.

    Catches config typos (e.g. the ARIC evidence-block quoting failure) at PR
    time, since hv_dataqc_tests.yml runs this suite on any change under
    hv_dataqc/** — which includes the known_issues configs.
    """

    def test_all_known_issues_configs_parse_and_are_well_formed(self) -> None:
        config_dir = known_issues._CONFIG_DIR
        files = sorted(config_dir.glob("*.yaml"))
        self.assertTrue(files, f"no known_issues configs found in {config_dir}")
        for f in files:
            with self.subTest(config=f.name):
                try:
                    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                except yaml.YAMLError as exc:
                    self.fail(f"{f.name} is not valid YAML: {exc}")
                self.assertIsInstance(data, dict, f"{f.name}: top level must be a mapping")
                entries = data.get("known_issues")
                self.assertIsInstance(entries, list, f"{f.name}: 'known_issues' must be a list")
                for i, entry in enumerate(entries):
                    self.assertIsInstance(entry, dict, f"{f.name}[{i}]: entry must be a mapping")
                    self.assertIsInstance(
                        entry.get("checks"), list, f"{f.name}[{i}]: 'checks' must be a list"
                    )
                    self.assertIn("variable_key", entry, f"{f.name}[{i}]: missing 'variable_key'")


if __name__ == "__main__":
    unittest.main()
