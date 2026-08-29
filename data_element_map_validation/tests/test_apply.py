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
