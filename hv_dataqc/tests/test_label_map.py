"""Tests for hv_dataqc.extract_harmonized.label_map."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hv_dataqc.extract_harmonized.label_map import (
    BARE_NAME_ALIASES,
    DEFAULT_PATH,
    load_label_map,
)


def _write_tsv(content: str) -> Path:
    """Write *content* to a temp TSV file and return its Path."""
    fd, path_str = tempfile.mkstemp(suffix=".tsv")
    Path(path_str).write_text(content, encoding="utf-8")
    return Path(path_str)


# Minimal header subset — load_label_map only reads these four columns.
_HEADER = (
    "var_label\tvar_name\tOMOP Standard Concept ID\tOBA CURIE"
)


class LoadLabelMapTests(unittest.TestCase):

    def test_omop_form_picked_up(self) -> None:
        tsv = _write_tsv(f"{_HEADER}\nBMI\tbmi\t4245997\t\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(lookup["OMOP:4245997"], "BMI")

    def test_oba_form_picked_up(self) -> None:
        tsv = _write_tsv(f"{_HEADER}\nHeight\theight\t\tOBA:VT0001253\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(lookup["OBA:VT0001253"], "Height")

    def test_bare_uppercase_form_from_var_name(self) -> None:
        tsv = _write_tsv(f"{_HEADER}\nHematocrit\thct\t\t\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(lookup["HCT"], "Hematocrit")

    def test_single_row_can_emit_all_three_forms(self) -> None:
        # A row with OMOP id, OBA CURIE, and var_name should produce three
        # keys pointing at the same label.
        tsv = _write_tsv(f"{_HEADER}\nAlbumin in blood\talbumin_bld\t2212186\tOBA:2050068\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(lookup["OMOP:2212186"], "Albumin in blood")
        self.assertEqual(lookup["OBA:2050068"], "Albumin in blood")
        self.assertEqual(lookup["ALBUMIN_BLD"], "Albumin in blood")

    def test_oba_without_prefix_is_ignored(self) -> None:
        # The OBA CURIE column should already include "OBA:". A bare value
        # is treated as "no OBA mapping" rather than silently prefixed.
        tsv = _write_tsv(f"{_HEADER}\nBMI\tbmi\t\t2050068\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertNotIn("OBA:2050068", lookup)
        # var_name still produces the bare form.
        self.assertEqual(lookup["BMI"], "BMI")

    def test_empty_label_skips_row(self) -> None:
        tsv = _write_tsv(f"{_HEADER}\n\tnameonly\t4245997\t\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertNotIn("OMOP:4245997", lookup)
        self.assertNotIn("NAMEONLY", lookup)

    def test_whitespace_in_fields_is_stripped(self) -> None:
        tsv = _write_tsv(f"{_HEADER}\n  BMI  \t  bmi  \t  4245997  \t\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        # Label has internal whitespace preserved but is trimmed.
        self.assertEqual(lookup["OMOP:4245997"], "BMI")
        self.assertEqual(lookup["BMI"], "BMI")

    def test_bare_alias_resolves_to_var_label_of_target_row(self) -> None:
        # BARE_NAME_ALIASES maps LYMPHOCYTES_COUNT -> lympho_ct. The TSV row
        # for var_name=lympho_ct should be found and its var_label promoted.
        tsv = _write_tsv(
            f"{_HEADER}\n"
            f"Lymphocytes count\tlympho_ct\t\t\n"
        )
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(lookup["LYMPHOCYTES_COUNT"], "Lymphocytes count")
        # The var_name's own uppercase form still works too.
        self.assertEqual(lookup["LYMPHO_CT"], "Lymphocytes count")

    def test_bare_alias_target_missing_does_not_raise(self) -> None:
        # If the alias's target var_name doesn't exist in the TSV, the
        # alias key just doesn't get added — no exception.
        tsv = _write_tsv(f"{_HEADER}\nBMI\tbmi\t4245997\t\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        for bare in BARE_NAME_ALIASES:
            self.assertNotIn(bare, lookup)

    def test_default_path_loads_real_file(self) -> None:
        # The shipped TSV at config/harmonized_vars.tsv should load and
        # produce a meaningful number of keys.
        self.assertTrue(DEFAULT_PATH.exists(), f"missing: {DEFAULT_PATH}")
        lookup = load_label_map()
        # The shipped TSV has ~150 rows and most have 2-3 contributing
        # codes; expect at least 200 keys.
        self.assertGreater(len(lookup), 200)
        # Both bare aliases should be present.
        for bare in BARE_NAME_ALIASES:
            self.assertIn(bare, lookup, f"missing bare alias: {bare}")


if __name__ == "__main__":
    unittest.main()
