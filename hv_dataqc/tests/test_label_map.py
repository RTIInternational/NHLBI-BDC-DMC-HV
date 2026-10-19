"""Tests for hv_dataqc.extract_harmonized.label_map."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hv_dataqc.extract_harmonized.label_map import (
    BARE_NAME_ALIASES,
    DEFAULT_PATH,
    load_ignored_codes,
    load_label_map,
    load_var_labels,
)


def _write_tsv(content: str) -> Path:
    """Write *content* to a temp TSV file and return its Path."""
    fd, path_str = tempfile.mkstemp(suffix=".tsv")
    Path(path_str).write_text(content, encoding="utf-8")
    return Path(path_str)


# Minimal Table S1 header subset — the columns load_label_map reads.
# Real S1 stores OMOP codes already "OMOP:"-prefixed.
_HEADER = (
    "Variable Label\tvar_name\tOMOP Concept ID\tOntology CURIE"
    "\tDeprecated Codes\tstatus"
)


def _row(label: str, var_name: str, omop: str = "", curie: str = "",
         deprecated: str = "", status: str = "") -> str:
    """One S1 data row matching _HEADER."""
    return f"{label}\t{var_name}\t{omop}\t{curie}\t{deprecated}\t{status}"


class LoadLabelMapTests(unittest.TestCase):

    def test_omop_form_picked_up(self) -> None:
        tsv = _write_tsv(f"{_HEADER}\n{_row('BMI', 'bmi', omop='OMOP:4245997')}\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(lookup["OMOP:4245997"], "BMI")

    def test_bare_omop_id_is_prefixed(self) -> None:
        # S1 ships prefixed codes, but a bare numeric id is tolerated.
        tsv = _write_tsv(f"{_HEADER}\n{_row('BMI', 'bmi', omop='4245997')}\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(lookup["OMOP:4245997"], "BMI")

    def test_oba_form_picked_up(self) -> None:
        tsv = _write_tsv(f"{_HEADER}\n{_row('Height', 'height', curie='OBA:VT0001253')}\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(lookup["OBA:VT0001253"], "Height")

    def test_bare_uppercase_form_from_var_name(self) -> None:
        tsv = _write_tsv(f"{_HEADER}\n{_row('Hematocrit', 'hct')}\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(lookup["HCT"], "Hematocrit")

    def test_single_row_can_emit_all_three_forms(self) -> None:
        # A row with OMOP code, ontology CURIE, and var_name should produce
        # three keys pointing at the same label.
        tsv = _write_tsv(
            f"{_HEADER}\n"
            f"{_row('Albumin in blood', 'albumin_bld', omop='OMOP:2212186', curie='OBA:2050068')}\n"
        )
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(lookup["OMOP:2212186"], "Albumin in blood")
        self.assertEqual(lookup["OBA:2050068"], "Albumin in blood")
        self.assertEqual(lookup["ALBUMIN_BLD"], "Albumin in blood")

    def test_non_oba_curie_is_registered_verbatim(self) -> None:
        # S1's "Ontology CURIE" is general-purpose, unlike the old
        # OBA-only column: whatever CURIE it holds becomes a lookup key.
        tsv = _write_tsv(f"{_HEADER}\n{_row('BMI', 'bmi', curie='SNOMED:60621009')}\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(lookup["SNOMED:60621009"], "BMI")
        self.assertEqual(lookup["BMI"], "BMI")

    def test_empty_label_skips_row(self) -> None:
        tsv = _write_tsv(f"{_HEADER}\n{_row('', 'nameonly', omop='OMOP:4245997')}\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertNotIn("OMOP:4245997", lookup)
        self.assertNotIn("NAMEONLY", lookup)

    def test_whitespace_in_fields_is_stripped(self) -> None:
        tsv = _write_tsv(
            f"{_HEADER}\n{_row('  BMI  ', '  bmi  ', omop='  OMOP:4245997  ')}\n"
        )
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        # Label has internal whitespace preserved but is trimmed.
        self.assertEqual(lookup["OMOP:4245997"], "BMI")
        self.assertEqual(lookup["BMI"], "BMI")

    def test_deprecated_code_resolves_to_same_label(self) -> None:
        # A superseded code still in some transform spec should land on its
        # row's label rather than falling through.
        tsv = _write_tsv(
            f"{_HEADER}\n"
            f"{_row('Lymphocytes count', 'lympho_ct', curie='OBA:VT0000717', deprecated='OBA:VT0000217')}\n"
        )
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(lookup["OBA:VT0000717"], "Lymphocytes count")
        self.assertEqual(lookup["OBA:VT0000217"], "Lymphocytes count")

    def test_current_code_wins_over_deprecated(self) -> None:
        # If one row's current code is another row's deprecated code, the
        # current-code label must win regardless of row order.
        tsv = _write_tsv(
            f"{_HEADER}\n"
            f"{_row('White blood cell count', 'whtbld_ct', curie='OBA:VT0000217')}\n"
            f"{_row('Lymphocytes count', 'lympho_ct', curie='OBA:VT0000717', deprecated='OBA:VT0000217')}\n"
        )
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(lookup["OBA:VT0000217"], "White blood cell count")

    def test_bare_alias_resolves_to_label_of_target_row(self) -> None:
        # BARE_NAME_ALIASES maps LYMPHOCYTES_COUNT -> lympho_ct. The row for
        # var_name=lympho_ct should be found and its label promoted.
        tsv = _write_tsv(f"{_HEADER}\n{_row('Lymphocytes count', 'lympho_ct')}\n")
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
        tsv = _write_tsv(f"{_HEADER}\n{_row('BMI', 'bmi', omop='OMOP:4245997')}\n")
        try:
            lookup = load_label_map(tsv)
        finally:
            tsv.unlink()
        for bare in BARE_NAME_ALIASES:
            self.assertNotIn(bare, lookup)

    def test_default_path_loads_real_file(self) -> None:
        # The shipped Table S1 at config/TableS1.tsv should load and
        # produce a meaningful number of keys.
        self.assertTrue(DEFAULT_PATH.exists(), f"missing: {DEFAULT_PATH}")
        lookup = load_label_map()
        # S1 has ~156 rows and most have 2-3 contributing codes;
        # expect at least 200 keys.
        self.assertGreater(len(lookup), 200)
        # Both bare aliases should be present.
        for bare in BARE_NAME_ALIASES:
            self.assertIn(bare, lookup, f"missing bare alias: {bare}")


class AnnotationRowTests(unittest.TestCase):
    """S1 rows that record a code without defining a variable."""

    def test_status_ignore_row_label_is_not_registered(self) -> None:
        tsv = _write_tsv(
            f"{_HEADER}\n"
            f"{_row('White blood cell count', 'whtbld_ct', curie='OBA:VT0000217')}\n"
            f"{_row('stray code from lympho_ct', 'lympho_ct', curie='OBA:VT0000217', status='ignore')}\n"
        )
        try:
            lookup = load_label_map(tsv)
            labels = load_var_labels(tsv)
        finally:
            tsv.unlink()
        # The real variable keeps the code; the annotation row never wins.
        self.assertEqual(lookup["OBA:VT0000217"], "White blood cell count")
        self.assertNotIn("stray code from lympho_ct", lookup.values())
        self.assertNotIn("lympho_ct", labels)

    def test_shipped_s1_stray_code_resolves_to_the_real_variable(self) -> None:
        # OBA:VT0000217 is white blood cell count in ten cohorts' specs.
        # Regression: it briefly resolved to an S1 annotation row's label.
        lookup = load_label_map()
        self.assertEqual(lookup["OBA:VT0000217"], "White blood cell count")
        self.assertEqual(lookup["OBA:VT0000717"], "Lymphocytes count")
        self.assertEqual(load_var_labels()["lympho_ct"], "Lymphocytes count")

    def test_ignore_row_labels_stay_out_of_the_label_map(self) -> None:
        # The 6 spirometry rows share one label; it must not become a variable.
        self.assertEqual(len(load_ignored_codes()), 6)
        self.assertNotIn("Spirometry metadata", load_label_map().values())


class LoadIgnoredCodesTests(unittest.TestCase):

    def test_only_ignore_rows_are_collected(self) -> None:
        tsv = _write_tsv(
            f"{_HEADER}\n"
            f"{_row('BMI', 'bmi', omop='OMOP:4245997')}\n"
            f"{_row('(spirometry metadata)', '', omop='OMOP:3002094', status='ignore')}\n"
        )
        try:
            ignored = load_ignored_codes(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(ignored, {"OMOP:3002094"})

    def test_status_match_is_case_insensitive(self) -> None:
        tsv = _write_tsv(
            f"{_HEADER}\n{_row('meta', '', omop='OMOP:1', status='Ignore')}\n"
        )
        try:
            ignored = load_ignored_codes(tsv)
        finally:
            tsv.unlink()
        self.assertIn("OMOP:1", ignored)

    def test_shipped_s1_carries_the_spirometry_metadata_codes(self) -> None:
        # These 6 codes are metadata on the spirometry specs, not reportable
        # variables (per curator decision 2026-07-07).
        ignored = load_ignored_codes()
        for code in ("OMOP:3002094", "OMOP:3005600", "OMOP:3011708",
                     "OMOP:3022891", "OMOP:3024594", "OMOP:4196583"):
            self.assertIn(code, ignored)


class LoadVarLabelsTests(unittest.TestCase):

    def test_maps_var_name_to_label(self) -> None:
        tsv = _write_tsv(
            f"{_HEADER}\n"
            f"{_row('BMI', 'bmi', omop='OMOP:4245997')}\n"
            f"{_row('', 'nolabel')}\n"
        )
        try:
            labels = load_var_labels(tsv)
        finally:
            tsv.unlink()
        self.assertEqual(labels["bmi"], "BMI")
        self.assertNotIn("nolabel", labels)

    def test_shipped_s1_resolves_the_status_suffixed_labels(self) -> None:
        # These three drifted against the retired harmonized_vars.tsv and
        # rendered as empty rows in S4; S1 carries the template's form.
        labels = load_var_labels()
        self.assertEqual(labels["copd"], "COPD status")
        self.assertEqual(labels["stroke"], "Stroke status")
        self.assertEqual(labels["slp_ap"], "Sleep apnea status")


if __name__ == "__main__":
    unittest.main()
