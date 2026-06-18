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
            result = app._apply_yaml("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        assert result.startswith("✓")
        assert "MONDO:9999999" in yf.read_text()

    def test_multi_block_uniform_replaced(self, tmp_path):
        yf = tmp_path / "test.yaml"
        yf.write_text(
            "condition_concept:\n  value: MONDO:0001111\n"
            "---\n"
            "condition_concept:\n  value: MONDO:0001111\n",
            encoding="utf-8",
        )
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            result = app._apply_yaml("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        assert result.startswith("✓")
        assert yf.read_text().count("MONDO:9999999") == 2

    def test_multi_block_differing_values_refused(self, tmp_path):
        yf = tmp_path / "test.yaml"
        original = (
            "condition_concept:\n  value: MONDO:0001111\n"
            "---\n"
            "condition_concept:\n  value: MONDO:0002222\n"
        )
        yf.write_text(original, encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            result = app._apply_yaml("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        assert result.startswith("⚠")
        assert "differing values" in result
        assert yf.read_text() == original  # file must be untouched

    def test_missing_yaml_returns_error(self, tmp_path):
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            result = app._apply_yaml("TEST", "missing.yaml", "condition_concept", "MONDO:9999999")
        assert result.startswith("❌")

    def test_slot_not_found_returns_warning(self, tmp_path):
        yf = tmp_path / "test.yaml"
        yf.write_text("other_slot:\n  value: MONDO:0001111\n", encoding="utf-8")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            result = app._apply_yaml("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        assert result.startswith("⚠")

    def test_blocked_slot_returns_warning(self, tmp_path):
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")):
            result = app._apply_yaml("TEST", "test.yaml", "relationship_to_participant", "ONESELF")
        assert result.startswith("⚠")
        assert "directly in the YAML file" in result

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
            result = app._apply_csv("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        assert result.startswith("✓")
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            written = list(csv.DictReader(f))
        assert written[0]["CURIE"] == "MONDO:9999999"

    def test_no_matching_rows_returns_warning(self, tmp_path):
        csv_path = tmp_path / "TEST_curie.csv"
        rows = [{"YAML File": "other.yaml", "Slot": "condition_concept", "CURIE": "MONDO:0001111"}]
        _write_curie_csv(csv_path, rows)
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, csv_path)):
            result = app._apply_csv("TEST", "test.yaml", "condition_concept", "MONDO:9999999")
        assert result.startswith("⚠")

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
             patch.object(app, "_apply_yaml", return_value="✓ YAML updated"), \
             patch.object(app, "_apply_csv",  return_value="✓ CSV updated"), \
             patch.object(app, "_save_pending"), \
             patch.object(app, "_next_log_path", return_value=log):
            app.submit_all("TEST", pending, "Curator")
        assert pending["key1"].get("applied") is True

    def test_applied_not_set_on_yaml_failure(self, tmp_path):
        pending = self._pending()
        log = tmp_path / "log.json"
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")), \
             patch.object(app, "_apply_yaml", return_value="❌ YAML not found"), \
             patch.object(app, "_apply_csv",  return_value="✓ CSV updated"), \
             patch.object(app, "_save_pending"), \
             patch.object(app, "_next_log_path", return_value=log):
            app.submit_all("TEST", pending, "Curator")
        assert "applied" not in pending["key1"]

    def test_applied_not_set_on_csv_failure(self, tmp_path):
        pending = self._pending()
        log = tmp_path / "log.json"
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")), \
             patch.object(app, "_apply_yaml", return_value="✓ YAML updated"), \
             patch.object(app, "_apply_csv",  return_value="✗ Could not write CSV"), \
             patch.object(app, "_save_pending"), \
             patch.object(app, "_next_log_path", return_value=log):
            app.submit_all("TEST", pending, "Curator")
        assert "applied" not in pending["key1"]

    def test_applied_not_set_on_multi_block_refusal(self, tmp_path):
        pending = self._pending()
        log = tmp_path / "log.json"
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")), \
             patch.object(app, "_apply_yaml", return_value="⚠ differing values — edit YAML directly"), \
             patch.object(app, "_apply_csv",  return_value="✓ CSV updated"), \
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
        mock_yaml = MagicMock(return_value="✓ YAML updated")
        with patch.dict(app.STUDIES, _studies_patch(tmp_path, tmp_path / "c.csv")), \
             patch.object(app, "_apply_yaml", mock_yaml), \
             patch.object(app, "_save_pending"), \
             patch.object(app, "_next_log_path", return_value=log):
            app.submit_all("TEST", pending, "Curator")
        mock_yaml.assert_not_called()
