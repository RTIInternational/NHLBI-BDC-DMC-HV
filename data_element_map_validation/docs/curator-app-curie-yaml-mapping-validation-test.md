# Curator App — CURIE / YAML Mapping Validation Tests

**Location:** `data_element_map_validation/tests/`
**Run with:**

```bash
uv run pytest data_element_map_validation/tests/
```

The test suite validates round-trip data mapping between the CURIE CSV and YAML files. It uses `tmp_path` fixtures and mocked study configurations, ensuring that no real study files are modified during testing.

---

## TestApplyYaml — YAML Write Correctness

Tests that `_apply_yaml()` correctly updates a slot value in a YAML file.

| Test                                        | What it verifies                                                                                   |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `test_single_block_success`                 | Single-block YAML: slot value is replaced and result starts with ✓                                 |
| `test_multi_block_uniform_replaced`         | Multi-block YAML where all blocks share the same value: all values are replaced                    |
| `test_multi_block_differing_values_refused` | Multi-block YAML with differing values: write is refused, file remains unchanged, returns ⚠        |
| `test_missing_yaml_returns_error`           | Missing YAML file returns ❌                                                                        |
| `test_slot_not_found_returns_warning`       | Slot absent from YAML returns ⚠                                                                    |
| `test_blocked_slot_returns_warning`         | `relationship_to_participant` is blocked from automated edits and must be updated manually in YAML |
| `test_surrounding_content_preserved`        | Comments and unrelated slots remain unchanged after replacement                                    |

---

## TestApplyCsv — CSV Write Correctness

Tests that `_apply_csv()` correctly updates the CURIE value in the CURIE CSV file.

| Test                                    | What it verifies                                                 |
| --------------------------------------- | ---------------------------------------------------------------- |
| `test_success_updates_matching_row`     | Matching row (same YAML file and slot) has its CURIE updated     |
| `test_no_matching_rows_returns_warning` | No matching rows returns ⚠                                       |
| `test_only_matching_rows_updated`       | Only the matched row is updated; all other rows remain unchanged |

---

## TestSubmitAllBookkeeping — Applied Flag Integrity

Tests that `submit_all()` only marks a change as `applied: true` when both YAML and CSV updates succeed.

| Test                                          | What it verifies                                                                             |
| --------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `test_applied_true_when_all_succeed`          | `applied` is set to `True` only when both YAML and CSV updates succeed                       |
| `test_applied_not_set_on_yaml_failure`        | YAML failure (❌) prevents `applied` from being set                                           |
| `test_applied_not_set_on_csv_failure`         | CSV failure prevents `applied` from being set                                                |
| `test_applied_not_set_on_multi_block_refusal` | Multi-block refusal (⚠) prevents `applied` from being set                                    |
| `test_already_applied_entries_skipped`        | Entries already marked `applied: True` are skipped entirely; `_apply_yaml()` is never called |

---

## Summary

The validation suite verifies:

* Correct YAML slot updates
* Correct CURIE CSV updates
* Preservation of unrelated YAML content
* Protection against unsafe multi-block edits
* Proper handling of missing files and missing slots
* Integrity of the `applied` bookkeeping flag
* Idempotent behavior for previously applied changes

Together, these tests ensure that CURIE ↔ YAML synchronization remains reliable, reproducible, and safe.
