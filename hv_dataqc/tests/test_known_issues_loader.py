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

    def test_all_variable_keys_are_match_reachable(self) -> None:
        """Every variable_key must tokenise to clean identifiers that can appear
        in a report's variable field.

        A key token containing ``[``, ``]`` or whitespace (e.g. a pasted
        ``name [phv / pht]`` enriched label) can never match — ``_variable_tokens``
        strips the bracket suffix and whitespace — so it would silently suppress
        nothing. Catch that class of authoring error at PR time.
        """
        config_dir = known_issues._CONFIG_DIR
        for f in sorted(config_dir.glob("*.yaml")):
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            for i, entry in enumerate(data.get("known_issues") or []):
                with self.subTest(config=f.name, entry=i):
                    key = str(entry.get("variable_key", "")).strip()
                    self.assertTrue(key, f"{f.name}[{i}]: empty variable_key")
                    tokens = [t.strip() for t in key.split("+")]
                    self.assertTrue(
                        all(tokens),
                        f"{f.name}[{i}]: empty token in variable_key '{key}'",
                    )
                    for tok in tokens:
                        self.assertNotIn(
                            "[", tok,
                            f"{f.name}[{i}]: token '{tok}' contains '[' — unreachable "
                            "(looks like a pasted enriched label)",
                        )
                        self.assertNotIn(
                            "]", tok,
                            f"{f.name}[{i}]: token '{tok}' contains ']' — unreachable",
                        )
                        self.assertFalse(
                            any(c.isspace() for c in tok),
                            f"{f.name}[{i}]: token '{tok}' contains whitespace — "
                            "unreachable (report variable tokens never contain spaces)",
                        )


class EntryMatchingTests(unittest.TestCase):
    """Matching semantics of _entry_matches / apply_known_issues.

    Covers the single-token path (unchanged) and the pooled ``+``-joined key
    path (previously never matched; now subset-matches the pooled variable).
    """

    def test_single_token_matches_when_present(self) -> None:
        entry = {"checks": ["C2"], "variable_key": "a11mstrk"}
        self.assertTrue(
            known_issues._entry_matches(entry, "C2", "a11mstrk [phv00000001 / pht000001]")
        )

    def test_single_token_does_not_match_different_variable(self) -> None:
        entry = {"checks": ["C2"], "variable_key": "a11mstrk"}
        self.assertFalse(
            known_issues._entry_matches(entry, "C2", "e12hgt [phv00000002 / pht000001]")
        )

    def test_pooled_key_matches_its_pooled_variable(self) -> None:
        """The regression: a '+'-joined key now matches the pooled variable it
        describes (was always False before the subset fix)."""
        entry = {"checks": ["C2"], "variable_key": "crp+crp_1+crp_7+crp_8"}
        report_var = "crp+crp_1+crp_7+crp_8 [phv00000003 / pht000001]"
        self.assertTrue(known_issues._entry_matches(entry, "C2", report_var))

    def test_pooled_key_subset_miss_does_not_match(self) -> None:
        """If the pooled variable is missing one of the named source vars, the
        subset relation fails — no over-suppression of a differently-composed
        pool."""
        entry = {"checks": ["C2"], "variable_key": "crp+crp_1+crp_7+crp_8"}
        report_var = "crp+crp_1+crp_7 [phv00000003 / pht000001]"  # crp_8 absent
        self.assertFalse(known_issues._entry_matches(entry, "C2", report_var))

    def test_pooled_key_does_not_match_unrelated_single_var(self) -> None:
        """A multi-token key cannot be a subset of a single-token variable that
        merely shares one token."""
        entry = {"checks": ["C2"], "variable_key": "crp+crp_1+crp_7+crp_8"}
        self.assertFalse(
            known_issues._entry_matches(entry, "C2", "crp [phv00000003 / pht000001]")
        )

    def test_check_id_scoping_still_enforced(self) -> None:
        entry = {"checks": ["C2"], "variable_key": "crp+crp_1+crp_7+crp_8"}
        report_var = "crp+crp_1+crp_7+crp_8 [phv00000003 / pht000001]"
        self.assertFalse(known_issues._entry_matches(entry, "C7", report_var))

    def test_apply_suppresses_pooled_fail_to_skip(self) -> None:
        from hv_dataqc.compare._common import CheckResult

        results = [
            CheckResult("C2", "crp+crp_1+crp_7+crp_8 [phv00000003 / pht000001]",
                        "FAIL", "N loss detected"),
            CheckResult("C2", "unrelated [phv00000009 / pht000001]",
                        "FAIL", "N loss detected"),
        ]
        entries = [{"checks": ["C2"], "variable_key": "crp+crp_1+crp_7+crp_8",
                    "summary": "known pooled N difference", "related_issues": [651]}]
        out, n = known_issues.apply_known_issues(results, entries)
        self.assertEqual(n, 1)
        by_var = {r.variable.split(" [")[0]: r for r in out}
        self.assertEqual(by_var["crp+crp_1+crp_7+crp_8"].status, "SKIP")
        self.assertEqual(by_var["unrelated"].status, "FAIL")  # untouched


if __name__ == "__main__":
    unittest.main()
