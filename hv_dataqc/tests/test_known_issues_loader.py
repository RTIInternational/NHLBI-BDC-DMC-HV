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


if __name__ == "__main__":
    unittest.main()
