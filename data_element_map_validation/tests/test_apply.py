"""Round-trip tests for _apply_yaml, _apply_csv, and submit_all bookkeeping."""
import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import curator_review_app as app


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _studies_patch(yaml_dir: Path, curie_csv: Path) -> dict:
    return {
        "TEST": {
            "label": "TEST",
            "description": "Test study",
            "file_key": "TEST",
            "yaml_dir": yaml_dir,
            "curie_csv": curie_csv,
            "review_md": yaml_dir / "review.md",
            "mapreview_csv": yaml_dir / "mapreview.csv",
        }
    }


def _write_curie_csv(path: Path, rows: list[dict]) -> list[str]:
    fieldnames = ["YAML File", "Slot", "CURIE"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return fieldnames


# ---------------------------------------------------------------------------
# _apply_yaml
# ---------------------------------------------------------------------------

class TestApplyYaml:
    def test_single_block_success(self, tmp_path):
        yf = tmp_path / "test.yaml"
        yf.write_text("condition_concept:\n  value: MONDO:0001111\n", encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        assert ok
        assert "MONDO:9999999" in yf.read_text()

    def test_multi_block_uniform_no_phv_refused(self, tmp_path):
        """Two blocks currently agreeing is NOT proof they're the same variable —
        this is exactly the pattern that corrupted 4 ARIC + 1 HCHS spirometry.yaml
        predicted-FVC blocks at once (2026-08-26). Must refuse, not blanket-apply."""
        yf = tmp_path / "test.yaml"
        original = (
            "condition_concept:\n  value: MONDO:0001111\n"
            "---\n"
            "condition_concept:\n  value: MONDO:0001111\n"
        )
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        assert not ok
        assert "no phv" in msg
        assert yf.read_text() == original  # file must be untouched

    def test_multi_block_with_phv_updates_only_that_block(self, tmp_path):
        """The PHV-scoped path is the hardened model: given a phv, only the one
        block referencing it is touched, even when sibling blocks share a value."""
        yf = tmp_path / "test.yaml"
        yf.write_text(
            "- class_derivations:\n"
            "    Condition:\n"
            "      populated_from: phvAAA\n"
            "      slot_derivations:\n"
            "        condition_concept:\n"
            "          value: MONDO:0001111\n"
            "- class_derivations:\n"
            "    Condition:\n"
            "      populated_from: phvBBB\n"
            "      slot_derivations:\n"
            "        condition_concept:\n"
            "          value: MONDO:0001111\n",
            encoding="utf-8",
        )
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "condition_concept", "MONDO:9999999", "phvAAA")
        assert ok
        content = yf.read_text()
        assert content.count("MONDO:9999999") == 1
        assert content.count("MONDO:0001111") == 1  # phvBBB's block untouched

    def test_phv_not_found_refuses_without_fallback(self, tmp_path):
        """A phv that doesn't resolve to a unique block must refuse outright —
        never fall back to a file-wide guess, even if that guess would happen
        to be unambiguous."""
        yf = tmp_path / "test.yaml"
        original = "condition_concept:\n  value: MONDO:0001111\n"
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "condition_concept", "MONDO:9999999", "phvNotPresent")
        assert not ok
        assert yf.read_text() == original

    def test_original_curie_single_match_applied(self, tmp_path):
        """No phv, but original_curie narrows to exactly one match — safe to apply."""
        yf = tmp_path / "test.yaml"
        yf.write_text(
            "condition_concept:\n  value: MONDO:0001111\n"
            "---\n"
            "condition_concept:\n  value: MONDO:0002222\n",
            encoding="utf-8",
        )
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml(
                "TEST", "test.yaml", "condition_concept", "MONDO:9999999",
                original_curie="MONDO:0001111",
            )
        assert ok
        content = yf.read_text()
        assert "MONDO:9999999" in content
        assert "MONDO:0002222" in content  # the other block untouched

    def test_original_curie_multiple_matches_refused(self, tmp_path):
        """No phv, and original_curie still matches more than one block — refuse,
        don't update them as a group."""
        yf = tmp_path / "test.yaml"
        original = (
            "condition_concept:\n  value: MONDO:0001111\n"
            "---\n"
            "condition_concept:\n  value: MONDO:0001111\n"
        )
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml(
                "TEST", "test.yaml", "condition_concept", "MONDO:9999999",
                original_curie="MONDO:0001111",
            )
        assert not ok
        assert "no phv" in msg
        assert yf.read_text() == original

    def test_original_curie_expr_single_match_applied(self, tmp_path):
        """original_curie matching a drug_concept-style expr literal, single
        occurrence — should apply via the expr branch, not just plain value:."""
        yf = tmp_path / "test.yaml"
        yf.write_text(
            'drug_concept:\n  expr: case(({phvAAA} == 1, "RxCUI:1111"))\n',
            encoding="utf-8",
        )
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml(
                "TEST", "test.yaml", "drug_concept", "RxCUI:9999",
                original_curie="RxCUI:1111",
            )
        assert ok
        assert '"RxCUI:9999"' in yf.read_text()

    def test_phv_expr_single_curie_literal_applied(self, tmp_path):
        """One phv, one expr: line with exactly one CURIE-shaped literal —
        unambiguous, safe to replace via the phv-scoped expr branch."""
        yf = tmp_path / "test.yaml"
        yf.write_text(
            "- class_derivations:\n"
            "    DrugExposure:\n"
            "      populated_from: pht0001\n"
            "      slot_derivations:\n"
            "        drug_concept:\n"
            '          expr: case(({phvAAA} == 1, "RxCUI:1111"))\n',
            encoding="utf-8",
        )
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "drug_concept", "RxCUI:9999", "phvAAA")
        assert ok
        assert '"RxCUI:9999"' in yf.read_text()

    def test_phv_expr_multiple_curie_literals_refused(self, tmp_path):
        """One phv whose expr: line packs multiple free-text drug names into a
        single case() (CARDIA tak_statin.yaml's actual shape — up to 7 distinct
        drug names sharing one phv). Which literal is "the" change? The app
        can't know — must refuse rather than guess or update all of them."""
        yf = tmp_path / "test.yaml"
        original = (
            "- class_derivations:\n"
            "    DrugExposure:\n"
            "      populated_from: pht0001\n"
            "      slot_derivations:\n"
            "        drug_concept:\n"
            '          expr: case((str({phvAAA}).lower().strip() == "niacin 500mg tablets", "RxCUI:1111"), '
            '(str({phvAAA}).lower().strip() == "metoprolol", "RxCUI:2222"), '
            '(str({phvAAA}).lower().strip() == "gemfibrozil", "ATC:C10AB"))\n'
        )
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "drug_concept", "RxCUI:9999", "phvAAA")
        assert not ok
        assert "ambiguous" in msg
        assert yf.read_text() == original  # file must be untouched

    def test_original_curie_expr_single_quoted_literal_applied(self, tmp_path):
        """Same as test_original_curie_expr_single_match_applied, but the CURIE
        literal is wrapped in single quotes (tak_insulin.yaml's actual style,
        the reverse of the fleet-standard double-quote-inside-single-quoted-expr
        convention) — must still match and must preserve the original quote
        style on write, not silently switch it."""
        yf = tmp_path / "test.yaml"
        yf.write_text(
            "drug_concept:\n  expr: case(({phvAAA} == 2, 'MeSH:D007328'))\n",
            encoding="utf-8",
        )
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml(
                "TEST", "test.yaml", "drug_concept", "ATC:A10A",
                original_curie="MeSH:D007328",
            )
        assert ok
        assert "'ATC:A10A'" in yf.read_text()
        assert "MeSH:D007328" not in yf.read_text()

    def test_phv_expr_single_quoted_curie_literal_applied(self, tmp_path):
        """phv-scoped expr branch must also accept a single-quoted CURIE literal,
        not just the double-quoted fleet-standard style."""
        yf = tmp_path / "test.yaml"
        yf.write_text(
            "- class_derivations:\n"
            "    DrugExposure:\n"
            "      populated_from: pht0001\n"
            "      slot_derivations:\n"
            "        drug_concept:\n"
            "          expr: case(({phvAAA} == 2, 'MeSH:D007328'))\n",
            encoding="utf-8",
        )
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "drug_concept", "ATC:A10A", "phvAAA")
        assert ok
        assert "'ATC:A10A'" in yf.read_text()

    def test_original_curie_stale_falls_through_to_coarser_check(self, tmp_path):
        """original_curie given but not found anywhere (stale finding) — falls
        through to the coarser single-occurrence check rather than failing outright."""
        yf = tmp_path / "test.yaml"
        yf.write_text("condition_concept:\n  value: MONDO:0003333\n", encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml(
                "TEST", "test.yaml", "condition_concept", "MONDO:9999999",
                original_curie="MONDO:0001111",  # not present in file at all
            )
        assert ok
        assert "MONDO:9999999" in yf.read_text()

    def test_multi_block_differing_values_refused(self, tmp_path):
        yf = tmp_path / "test.yaml"
        original = (
            "condition_concept:\n  value: MONDO:0001111\n"
            "---\n"
            "condition_concept:\n  value: MONDO:0002222\n"
        )
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        assert not ok
        assert "differing values" in msg
        assert yf.read_text() == original  # file must be untouched

    def test_missing_yaml_returns_error(self, tmp_path):
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "missing.yaml", "condition_concept", "MONDO:9999999")
        assert not ok
        assert msg.startswith("❌")

    def test_slot_not_found_returns_warning(self, tmp_path):
        yf = tmp_path / "test.yaml"
        yf.write_text("other_slot:\n  value: MONDO:0001111\n", encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        assert not ok

    def test_blocked_slot_returns_warning(self, tmp_path):
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "relationship_to_participant", "ONESELF")
        assert not ok
        assert "directly in the YAML file" in msg

    def test_crlf_line_endings(self, tmp_path):
        yf = tmp_path / "test.yaml"
        yf.write_bytes(b"condition_concept:\r\n  value: MONDO:0001111\r\n")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        assert ok
        assert "MONDO:9999999" in yf.read_text()

    def test_slot_with_dashes(self, tmp_path):
        yf = tmp_path / "test.yaml"
        yf.write_text("some-slot:\n  value: MONDO:0001111\n", encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "some-slot", "MONDO:9999999")
        assert ok
        assert "MONDO:9999999" in yf.read_text()

    def test_no_partial_slot_match(self, tmp_path):
        """Slot 'type' must not match inside 'method_type'."""
        yf = tmp_path / "test.yaml"
        yf.write_text("method_type:\n  value: MONDO:0001111\n", encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "type", "MONDO:9999999")
        assert not ok
        assert yf.read_text() == "method_type:\n  value: MONDO:0001111\n"

    def test_surrounding_content_preserved(self, tmp_path):
        yf = tmp_path / "test.yaml"
        yf.write_text(
            "# top comment\ncondition_concept:\n  value: MONDO:0001111\nother:\n  value: keep\n",
            encoding="utf-8",
        )
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            app._apply_yaml("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        content = yf.read_text()
        assert "# top comment" in content
        assert "other:\n  value: keep" in content
        assert "condition_concept:\n  value: MONDO:9999999" in content


class TestApplyYamlFallbackExprSupport:
    """No phv, no resolvable original_curie -- the old-format-entry fallback
    path. Previously understood only a plain `value:` line; reported
    2026-08-29 that this silently refused (reporting 'no pattern') for any
    file using expr:/case() here instead, even when there was really just
    one unambiguous block -- and that refusal let a concurrent _apply_csv
    write proceed anyway, desyncing CSV from YAML (82 historical entries,
    9 files). These tests cover the fix: the fallback now also recognizes
    single-line expr: case() CURIE literals, file-wide."""

    def test_single_expr_block_no_phv_applied(self, tmp_path):
        yf = tmp_path / "test.yaml"
        yf.write_text(
            "drug_concept:\n  expr: case(({phvAAA} == 1, \"RxCUI:1111\"))\n",
            encoding="utf-8",
        )
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "drug_concept", "RxCUI:9999")
        assert ok
        assert '"RxCUI:9999"' in yf.read_text()

    def test_single_expr_block_no_phv_single_quoted_applied(self, tmp_path):
        yf = tmp_path / "test.yaml"
        yf.write_text(
            "drug_concept:\n  expr: case(({phvAAA} == 1, 'RxCUI:1111'))\n",
            encoding="utf-8",
        )
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "drug_concept", "RxCUI:9999")
        assert ok
        assert "'RxCUI:9999'" in yf.read_text()

    def test_multiple_expr_blocks_differing_values_refused(self, tmp_path):
        original = (
            "drug_concept:\n  expr: case(({phvAAA} == 1, \"RxCUI:1111\"))\n"
            "---\n"
            "drug_concept:\n  expr: case(({phvBBB} == 1, \"RxCUI:2222\"))\n"
        )
        yf = tmp_path / "test.yaml"
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "drug_concept", "RxCUI:9999")
        assert not ok
        assert "differing values" in msg
        assert yf.read_text() == original

    def test_multiple_expr_blocks_same_value_no_phv_refused(self, tmp_path):
        original = (
            "drug_concept:\n  expr: case(({phvAAA} == 1, \"RxCUI:1111\"))\n"
            "---\n"
            "drug_concept:\n  expr: case(({phvBBB} == 1, \"RxCUI:1111\"))\n"
        )
        yf = tmp_path / "test.yaml"
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "drug_concept", "RxCUI:9999")
        assert not ok
        assert "no phv to say which one" in msg
        assert yf.read_text() == original

    def test_ambiguous_multi_literal_expr_line_refused(self, tmp_path):
        original = (
            'drug_concept:\n  expr: case(({phvAAA} == 1, "RxCUI:1111"), ({phvAAA} == 2, "RxCUI:2222"))\n'
        )
        yf = tmp_path / "test.yaml"
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "drug_concept", "RxCUI:9999")
        assert not ok
        assert "ambiguous" in msg
        assert yf.read_text() == original

    def test_mixed_value_and_expr_forms_differing_refused(self, tmp_path):
        """A plain value: block and an expr: block for the same slot, with
        different CURIEs -- must be treated as 2 disagreeing blocks, not
        silently pick one form over the other."""
        original = (
            "drug_concept:\n  value: RxCUI:1111\n"
            "---\n"
            "drug_concept:\n  expr: case(({phvAAA} == 1, \"RxCUI:2222\"))\n"
        )
        yf = tmp_path / "test.yaml"
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "drug_concept", "RxCUI:9999")
        assert not ok
        assert "differing values" in msg

    def test_still_refuses_when_truly_no_pattern_at_all(self, tmp_path):
        yf = tmp_path / "test.yaml"
        yf.write_text("other_slot:\n  value: RxCUI:1111\n", encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "drug_concept", "RxCUI:9999")
        assert not ok
        assert "No" in msg and "pattern" in msg


class TestApplyYamlValueMappingsSupport:
    """value_mappings (code -> CURIE dict, e.g. race:/sex:/value_enum: slots)
    was previously invisible to _apply_yaml entirely: slot_re only recognized
    a `value:`/`expr:` line immediately after the slot, but a value_mappings
    slot's next line is `populated_from:` instead -- so _find_block_for_phv
    never matched the block, and every such finding fell through to "No YAML
    block found for phv" even when the fix was completely unambiguous.

    A single table often maps several different codes to several different
    CURIEs (confirmed via curie.csv, which files one row per distinct CURIE
    a table emits for the same (yaml_file, slot, phv) -- e.g. ARIC
    cig_smok.yaml's value_enum table maps U/N/Y to three different OMOP
    concepts), so original_curie is required to pick which single code's
    entry a finding is about."""

    def test_phv_single_match_applied(self, tmp_path):
        yf = tmp_path / "test.yaml"
        yf.write_text(
            "- class_derivations:\n"
            "    Demography:\n"
            "      populated_from: pht0001\n"
            "      slot_derivations:\n"
            "        race:\n"
            "          populated_from: phvAAA\n"
            "          value_mappings:\n"
            "            N: OMOP:8527\n"
            "            B: OMOP:8516\n",
            encoding="utf-8",
        )
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml(
                "TEST", "test.yaml", "race", "OMOP:9999", "phvAAA",
                original_curie="OMOP:8516",
            )
        assert ok
        content = yf.read_text()
        assert "B: OMOP:9999" in content
        assert "N: OMOP:8527" in content  # sibling code untouched

    def test_phv_no_original_curie_refused(self, tmp_path):
        """value_mappings can't be applied without original_curie -- there's
        no way to know which code's entry a bare (slot, phv) finding means."""
        yf = tmp_path / "test.yaml"
        original = (
            "- class_derivations:\n"
            "    Demography:\n"
            "      populated_from: pht0001\n"
            "      slot_derivations:\n"
            "        race:\n"
            "          populated_from: phvAAA\n"
            "          value_mappings:\n"
            "            N: OMOP:8527\n"
            "            B: OMOP:8516\n"
        )
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml("TEST", "test.yaml", "race", "OMOP:9999", "phvAAA")
        assert not ok
        assert "original_curie" in msg
        assert yf.read_text() == original

    def test_phv_ambiguous_same_table_refused(self, tmp_path):
        """Two codes in the same table both currently hold original_curie --
        refuse rather than guess (or update both)."""
        yf = tmp_path / "test.yaml"
        original = (
            "- class_derivations:\n"
            "    Demography:\n"
            "      populated_from: pht0001\n"
            "      slot_derivations:\n"
            "        race:\n"
            "          populated_from: phvAAA\n"
            "          value_mappings:\n"
            "            N: OMOP:8527\n"
            "            X: OMOP:8527\n"
        )
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml(
                "TEST", "test.yaml", "race", "OMOP:9999", "phvAAA",
                original_curie="OMOP:8527",
            )
        assert not ok
        assert "ambiguous" in msg
        assert yf.read_text() == original

    def test_phv_original_curie_not_in_table_refused(self, tmp_path):
        yf = tmp_path / "test.yaml"
        original = (
            "- class_derivations:\n"
            "    Demography:\n"
            "      populated_from: pht0001\n"
            "      slot_derivations:\n"
            "        race:\n"
            "          populated_from: phvAAA\n"
            "          value_mappings:\n"
            "            N: OMOP:8527\n"
        )
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml(
                "TEST", "test.yaml", "race", "OMOP:9999", "phvAAA",
                original_curie="OMOP:0000000",
            )
        assert not ok
        assert "doesn't" in msg and "value_mappings" in msg
        assert yf.read_text() == original

    def test_phv_only_targets_that_blocks_table(self, tmp_path):
        """Two blocks with the same slot/code/value -- phv must scope the
        edit to only its own block's table, same guarantee as the plain
        value:/expr: phv-scoped paths."""
        yf = tmp_path / "test.yaml"
        yf.write_text(
            "- class_derivations:\n"
            "    Demography:\n"
            "      populated_from: pht0001\n"
            "      slot_derivations:\n"
            "        race:\n"
            "          populated_from: phvAAA\n"
            "          value_mappings:\n"
            "            N: OMOP:8527\n"
            "- class_derivations:\n"
            "    Demography:\n"
            "      populated_from: pht0002\n"
            "      slot_derivations:\n"
            "        race:\n"
            "          populated_from: phvBBB\n"
            "          value_mappings:\n"
            "            N: OMOP:8527\n",
            encoding="utf-8",
        )
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml(
                "TEST", "test.yaml", "race", "OMOP:9999", "phvAAA",
                original_curie="OMOP:8527",
            )
        assert ok
        content = yf.read_text()
        assert content.count("OMOP:9999") == 1
        assert content.count("OMOP:8527") == 1  # phvBBB's table untouched

    def test_original_curie_no_phv_single_match_applied(self, tmp_path):
        """No phv, but original_curie narrows to exactly one value_mappings
        entry across the whole file -- safe to apply, same principle as the
        existing plain value:/expr: no-phv fallback."""
        yf = tmp_path / "test.yaml"
        yf.write_text(
            "race:\n  populated_from: phvAAA\n  value_mappings:\n    N: OMOP:8527\n    B: OMOP:8516\n",
            encoding="utf-8",
        )
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml(
                "TEST", "test.yaml", "race", "OMOP:9999",
                original_curie="OMOP:8516",
            )
        assert ok
        content = yf.read_text()
        assert "B: OMOP:9999" in content
        assert "N: OMOP:8527" in content

    def test_original_curie_no_phv_multiple_matches_refused(self, tmp_path):
        original = (
            "race:\n  populated_from: phvAAA\n  value_mappings:\n    N: OMOP:8527\n"
            "---\n"
            "race:\n  populated_from: phvBBB\n  value_mappings:\n    N: OMOP:8527\n"
        )
        yf = tmp_path / "test.yaml"
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml(
                "TEST", "test.yaml", "race", "OMOP:9999",
                original_curie="OMOP:8527",
            )
        assert not ok
        assert "no phv to say which one" in msg
        assert yf.read_text() == original

    def test_original_curie_no_phv_combined_with_plain_value_refused(self, tmp_path):
        """original_curie matching both a plain value: block and a separate
        value_mappings entry -- must count as 2 disagreeing candidates
        total, not just check each form in isolation."""
        original = (
            "race:\n  value: OMOP:8527\n"
            "---\n"
            "race:\n  populated_from: phvAAA\n  value_mappings:\n    N: OMOP:8527\n"
        )
        yf = tmp_path / "test.yaml"
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, msg = app._apply_yaml(
                "TEST", "test.yaml", "race", "OMOP:9999",
                original_curie="OMOP:8527",
            )
        assert not ok
        assert "no phv to say which one" in msg
        assert yf.read_text() == original


# ---------------------------------------------------------------------------
# _apply_csv
# ---------------------------------------------------------------------------

class TestApplyCsv:
    def test_success_updates_matching_row(self, tmp_path):
        csv_path = tmp_path / "TEST_curie.csv"
        rows = [{"YAML File": "test.yaml", "Slot": "condition_concept", "CURIE": "MONDO:0001111"}]
        _write_curie_csv(csv_path, rows)
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, csv_path)):
            ok, msg = app._apply_csv("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        assert ok
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            written = list(csv.DictReader(f))
        assert written[0]["CURIE"] == "MONDO:9999999"

    def test_no_matching_rows_returns_warning(self, tmp_path):
        csv_path = tmp_path / "TEST_curie.csv"
        rows = [{"YAML File": "other.yaml", "Slot": "condition_concept", "CURIE": "MONDO:0001111"}]
        _write_curie_csv(csv_path, rows)
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, csv_path)):
            ok, msg = app._apply_csv("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        assert not ok

    def test_only_matching_rows_updated(self, tmp_path):
        csv_path = tmp_path / "TEST_curie.csv"
        rows = [
            {"YAML File": "test.yaml", "Slot": "condition_concept", "CURIE": "MONDO:0001111"},
            {"YAML File": "other.yaml", "Slot": "condition_concept", "CURIE": "MONDO:0002222"},
        ]
        _write_curie_csv(csv_path, rows)
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, csv_path)):
            app._apply_csv("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            written = list(csv.DictReader(f))
        assert written[0]["CURIE"] == "MONDO:9999999"
        assert written[1]["CURIE"] == "MONDO:0002222"  # untouched

    def test_multiple_rows_no_phv_refused(self, tmp_path):
        """Two rows for the same (yaml_file, slot) with no phv to disambiguate —
        this is the CSV-side twin of the ARIC/HCHS spirometry.yaml corruption:
        must refuse rather than update both."""
        csv_path = tmp_path / "TEST_curie.csv"
        fieldnames = ["YAML File", "Slot", "CURIE", "PHV"]
        rows = [
            {"YAML File": "test.yaml", "Slot": "condition_concept", "CURIE": "MONDO:0001111", "PHV": "phvAAA"},
            {"YAML File": "test.yaml", "Slot": "condition_concept", "CURIE": "MONDO:0001111", "PHV": "phvBBB"},
        ]
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, csv_path)):
            ok, msg = app._apply_csv("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        assert not ok
        assert "no phv" in msg
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            written = list(csv.DictReader(f))
        assert written[0]["CURIE"] == "MONDO:0001111"
        assert written[1]["CURIE"] == "MONDO:0001111"

    def test_multiple_rows_with_phv_updates_only_that_row(self, tmp_path):
        """Same setup as above, but with a phv attached — should update only
        the one row for that phv, leaving the sibling row untouched."""
        csv_path = tmp_path / "TEST_curie.csv"
        fieldnames = ["YAML File", "Slot", "CURIE", "PHV"]
        rows = [
            {"YAML File": "test.yaml", "Slot": "condition_concept", "CURIE": "MONDO:0001111", "PHV": "phvAAA"},
            {"YAML File": "test.yaml", "Slot": "condition_concept", "CURIE": "MONDO:0001111", "PHV": "phvBBB"},
        ]
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, csv_path)):
            ok, msg = app._apply_csv("TEST", "test.yaml", "condition_concept", "MONDO:9999999", phv="phvAAA")
        assert ok
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            written = list(csv.DictReader(f))
        assert written[0]["CURIE"] == "MONDO:9999999"
        assert written[1]["CURIE"] == "MONDO:0001111"  # phvBBB's row untouched

    def test_multiple_rows_original_curie_narrows_to_one_applied(self, tmp_path):
        """No phv, but original_curie narrows the match down to exactly one
        row — safe to apply without a phv."""
        csv_path = tmp_path / "TEST_curie.csv"
        rows = [
            {"YAML File": "test.yaml", "Slot": "condition_concept", "CURIE": "MONDO:0001111"},
            {"YAML File": "test.yaml", "Slot": "condition_concept", "CURIE": "MONDO:0002222"},
        ]
        _write_curie_csv(csv_path, rows)
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, csv_path)):
            ok, msg = app._apply_csv(
                "TEST", "test.yaml", "condition_concept", "MONDO:9999999",
                original_curie="MONDO:0001111",
            )
        assert ok
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            written = list(csv.DictReader(f))
        assert written[0]["CURIE"] == "MONDO:9999999"
        assert written[1]["CURIE"] == "MONDO:0002222"  # untouched


# ---------------------------------------------------------------------------
# submit_all applied bookkeeping
# ---------------------------------------------------------------------------

class TestSubmitAllBookkeeping:
    def _pending(self):
        return {
            "key1": {
                "change_request": "MONDO:9999999",
                "slot": "condition_concept",
                "yaml_files": ["test.yaml"],
                "notes": "",
            }
        }

    def test_applied_true_when_all_succeed(self, tmp_path):
        pending = self._pending()
        log = tmp_path / "log.json"
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")), \
             patch.object(app, "_apply_yaml", return_value=(True,  "✓ YAML updated")), \
             patch.object(app, "_apply_csv",  return_value=(True,  "✓ CSV updated")), \
             patch.object(app, "_save_pending"), \
             patch.object(app, "_next_log_path", return_value=log):
            app.submit_all("TEST", pending, "Curator")
        assert pending["key1"].get("applied") is True

    def test_applied_not_set_on_yaml_failure(self, tmp_path):
        pending = self._pending()
        log = tmp_path / "log.json"
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")), \
             patch.object(app, "_apply_yaml", return_value=(False, "❌ YAML not found")), \
             patch.object(app, "_apply_csv",  return_value=(True,  "✓ CSV updated")), \
             patch.object(app, "_save_pending"), \
             patch.object(app, "_next_log_path", return_value=log):
            app.submit_all("TEST", pending, "Curator")
        assert "applied" not in pending["key1"]

    def test_applied_not_set_on_csv_failure(self, tmp_path):
        pending = self._pending()
        log = tmp_path / "log.json"
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")), \
             patch.object(app, "_apply_yaml", return_value=(True,  "✓ YAML updated")), \
             patch.object(app, "_apply_csv",  return_value=(False, "✗ Could not write CSV")), \
             patch.object(app, "_save_pending"), \
             patch.object(app, "_next_log_path", return_value=log):
            app.submit_all("TEST", pending, "Curator")
        assert "applied" not in pending["key1"]

    def test_applied_not_set_on_multi_block_refusal(self, tmp_path):
        pending = self._pending()
        log = tmp_path / "log.json"
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")), \
             patch.object(app, "_apply_yaml", return_value=(False, "⚠ differing values — edit YAML directly")), \
             patch.object(app, "_apply_csv",  return_value=(True,  "✓ CSV updated")), \
             patch.object(app, "_save_pending"), \
             patch.object(app, "_next_log_path", return_value=log):
            app.submit_all("TEST", pending, "Curator")
        assert "applied" not in pending["key1"]

    def test_csv_write_skipped_when_yaml_fails(self, tmp_path):
        """The actual fix: _apply_csv must never even be called when
        _apply_yaml didn't land -- not just 'applied' staying unset. Reported
        2026-08-29: 82 historical entries where the CSV write proceeded
        anyway and desynced from a YAML edit that silently no-op'd."""
        pending = self._pending()
        log = tmp_path / "log.json"
        mock_csv = MagicMock(return_value=(True, "✓ CSV updated"))
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")), \
             patch.object(app, "_apply_yaml", return_value=(False, "⚠ No `condition_concept: value:` pattern")), \
             patch.object(app, "_apply_csv", mock_csv), \
             patch.object(app, "_save_pending"), \
             patch.object(app, "_next_log_path", return_value=log):
            app.submit_all("TEST", pending, "Curator")
        mock_csv.assert_not_called()
        assert "applied" not in pending["key1"]

    def test_csv_write_still_happens_when_yaml_succeeds(self, tmp_path):
        pending = self._pending()
        log = tmp_path / "log.json"
        mock_csv = MagicMock(return_value=(True, "✓ CSV updated"))
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")), \
             patch.object(app, "_apply_yaml", return_value=(True, "✓ YAML updated")), \
             patch.object(app, "_apply_csv", mock_csv), \
             patch.object(app, "_save_pending"), \
             patch.object(app, "_next_log_path", return_value=log):
            app.submit_all("TEST", pending, "Curator")
        mock_csv.assert_called_once()
        assert pending["key1"].get("applied") is True

    def test_already_applied_entries_skipped(self, tmp_path):
        pending = {
            "key1": {
                "change_request": "MONDO:9999999",
                "slot": "condition_concept",
                "yaml_files": ["test.yaml"],
                "notes": "",
                "applied": True,
            }
        }
        log = tmp_path / "log.json"
        mock_yaml = MagicMock(return_value=(True, "✓ YAML updated"))
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")), \
             patch.object(app, "_apply_yaml", mock_yaml), \
             patch.object(app, "_save_pending"), \
             patch.object(app, "_next_log_path", return_value=log):
            app.submit_all("TEST", pending, "Curator")
        mock_yaml.assert_not_called()


class TestRowKey:
    """_row_key must give two genuinely different findings on the same
    (study, file, phv) -- even the same slot -- distinct pending-changes
    keys, or saving a decision on one silently overwrites the other
    (reported 2026-08-28: a schema-violation finding and an 'agent suggests
    better CURIE' finding both fired for the same phv+slot)."""

    def test_same_phv_same_slot_different_finding_text_gives_different_keys(self):
        k1 = app._row_key(
            "TEST", "obesity.yaml", "phv00001111",
            "Current mapping for `condition_concept` is definitely wrong: ...",
        )
        k2 = app._row_key(
            "TEST", "obesity.yaml", "phv00001111",
            "Agent suggests better CURIE for `condition_concept`: MONDO recommends `MONDO:0011122`",
        )
        assert k1 != k2

    def test_same_finding_text_is_stable_across_calls(self):
        issue = "Current mapping for `condition_concept` is definitely wrong: ..."
        k1 = app._row_key("TEST", "obesity.yaml", "phv00001111", issue)
        k2 = app._row_key("TEST", "obesity.yaml", "phv00001111", issue)
        assert k1 == k2

    def test_no_finding_text_preserves_old_phv_only_key(self):
        """Backward compatibility: callers that don't pass finding text
        (or existing pending_changes.json entries saved before this fix)
        must still resolve to the same key as before."""
        assert app._row_key("TEST", "obesity.yaml", "phv00001111") == \
            "TEST::confirmed::obesity.yaml::phv00001111"

    def test_different_phv_same_finding_text_gives_different_keys(self):
        issue = "Agent suggests better CURIE for `condition_concept`: MONDO recommends `MONDO:0011122`"
        k1 = app._row_key("TEST", "obesity.yaml", "phv00001111", issue)
        k2 = app._row_key("TEST", "obesity.yaml", "phv00002222", issue)
        assert k1 != k2


# ---------------------------------------------------------------------------
# value_mappings: slot scoping and YAML/CSV pairing (PR #821 review)
# ---------------------------------------------------------------------------

class TestValueMappingsSlotScoping:
    """_vm_table_re only required intermediate lines to be *indented*, not
    indented deeper than the slot, so a slot with no table of its own walked
    forward into the next sibling slot's table and rewrote it."""

    _YAML = (
        "- class_derivations:\n"
        "    MeasurementObservation:\n"
        "      populated_from: pht0001\n"
        "      slot_derivations:\n"
        "        observation_type:\n"
        "          expr: 'no_phv_here'\n"
        "        value_enum:\n"
        "          populated_from: phvAAA\n"
        "          value_mappings:\n"
        "            N: OMOP:8527\n"
    )

    def test_regex_does_not_cross_into_sibling_slot(self):
        assert app._vm_table_re("observation_type").search(self._YAML) is None
        assert list(app._iter_value_mapping_entries(self._YAML, "observation_type", "OMOP:8527")) == []
        assert len(list(app._iter_value_mapping_entries(self._YAML, "value_enum", "OMOP:8527"))) == 1

    def test_apply_yaml_refuses_instead_of_rewriting_sibling_table(self, tmp_path):
        yf = tmp_path / "test.yaml"
        yf.write_text(self._YAML, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            ok, _ = app._apply_yaml(
                "TEST", "test.yaml", "observation_type", "OMOP:9999", "phvAAA",
                original_curie="OMOP:8527",
            )
        assert not ok
        assert yf.read_text() == self._YAML


class TestSubmitAllValueMappingsCrossProduct:
    """curie.csv is a cross-product: within one PHT block every phv gets a row
    for every CURIE the block's tables emit, so one value_mappings entry is
    described by several CSV rows. Shape copied from ARIC demography.yaml /
    ARIC_curie.csv: PHT004061's block has sex from phv00204449 and race from
    phv00204568, and the CSV files both race CURIEs under both phvs. A second
    block (PHT004053) holds an identical race table that must stay untouched."""

    _YAML = (
        "- class_derivations:\n"
        "    Demography:\n"
        "      populated_from: pht004053\n"
        "      slot_derivations:\n"
        "        race:\n"
        "          populated_from: phv00204215\n"
        "          value_mappings:\n"
        "            N: OMOP:8527\n"
        "            B: OMOP:8516\n"
        "- class_derivations:\n"
        "    Demography:\n"
        "      populated_from: pht004061\n"
        "      slot_derivations:\n"
        "        sex:\n"
        "          populated_from: phv00204449\n"
        "          value_mappings:\n"
        "            F: OMOP:8532\n"
        "            M: OMOP:8507\n"
        "        race:\n"
        "          populated_from: phv00204568\n"
        "          value_mappings:\n"
        "            N: OMOP:8527\n"
        "            B: OMOP:8516\n"
    )

    _FIELDS = ["PHT", "PHV", "CURIE", "Slot", "YAML File"]

    def _setup(self, tmp_path):
        (tmp_path / "demography.yaml").write_text(self._YAML, encoding="utf-8")
        rows = [
            {"PHT": pht, "PHV": phv, "CURIE": c, "Slot": "race", "YAML File": "demography.yaml"}
            for pht, phv in [("PHT004053", "phv00204215"),
                             ("PHT004061", "phv00204449"), ("PHT004061", "phv00204568")]
            for c in ("OMOP:8516", "OMOP:8527")
        ]
        with open(tmp_path / "c.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=self._FIELDS)
            w.writeheader()
            w.writerows(rows)

    def _submit(self, tmp_path, phv):
        pending = {"k": {
            "change_request": "OMOP:9999", "slot": "race", "phv": phv,
            "original_curie": "OMOP:8527", "yaml_files": ["demography.yaml"],
        }}
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")), \
             patch.object(app, "_save_pending"), \
             patch.object(app, "_next_log_path", return_value=tmp_path / "log.json"):
            results, _, _ = app.submit_all("TEST", pending, "Curator")
        with open(tmp_path / "c.csv", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        return pending, results, rows

    def _race_values(self, tmp_path):
        return [l.strip() for l in (tmp_path / "demography.yaml").read_text().splitlines()
                if l.strip().startswith(("N:", "B:"))]

    def test_every_sibling_row_for_the_edited_entry_is_updated(self, tmp_path):
        self._setup(tmp_path)
        pending, results, rows = self._submit(tmp_path, "phv00204449")
        assert pending["k"].get("applied") is True, results
        assert self._race_values(tmp_path) == ["N: OMOP:8527", "B: OMOP:8516", "N: OMOP:9999", "B: OMOP:8516"]
        by_key = {(r["PHV"], r["CURIE"]) for r in rows}
        # both PHT004061 phvs now record the new CURIE -- no stale sibling
        assert ("phv00204449", "OMOP:9999") in by_key
        assert ("phv00204568", "OMOP:9999") in by_key
        assert not any(r["PHT"] == "PHT004061" and r["CURIE"] == "OMOP:8527" for r in rows)
        # other code in the edited table, and the other block's identical table, untouched
        assert ("phv00204449", "OMOP:8516") in by_key and ("phv00204568", "OMOP:8516") in by_key
        assert ("phv00204215", "OMOP:8527") in by_key

    def test_csv_rows_match_what_yaml_emits_per_pht(self, tmp_path):
        """Invariant the review asked for: after submit, the CURIEs the CSV
        records for each PHT equal the CURIEs that block's race table emits."""
        self._setup(tmp_path)
        self._submit(tmp_path, "phv00204568")
        _, _, rows = self._submit(tmp_path, "phv00204568")  # re-submit is a no-op
        emitted = {"PHT004053": {"OMOP:8527", "OMOP:8516"}, "PHT004061": {"OMOP:9999", "OMOP:8516"}}
        for pht, curies in emitted.items():
            assert {r["CURIE"] for r in rows if r["PHT"] == pht} == curies

    def test_no_phv_unique_entry_updates_block_rows(self, tmp_path):
        """No-phv path: original_curie unique in the file -> its block's rows."""
        self._setup(tmp_path)
        yf = tmp_path / "demography.yaml"
        yf.write_text(self._YAML.replace("N: OMOP:8527\n            B", "N: OMOP:1111\n            B", 1),
                      encoding="utf-8")
        pending, results, rows = self._submit(tmp_path, "")
        assert pending["k"].get("applied") is True, results
        assert not any(r["PHT"] == "PHT004061" and r["CURIE"] == "OMOP:8527" for r in rows)
        assert ("phv00204215", "OMOP:8527") in {(r["PHV"], r["CURIE"]) for r in rows}
