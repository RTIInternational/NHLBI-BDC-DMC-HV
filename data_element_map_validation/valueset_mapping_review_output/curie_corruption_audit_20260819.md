# CURIE CSV corruption audit — 2026-08-19

## Root cause

`curator_review_app.py`'s `_apply_csv()` matched CSV rows to update by `(YAML File, Slot)` only —
it did not check that a row's *current* CURIE matched the specific value the curator's finding was
based on (`original_curie`). When a `(YAML File, Slot)` pair spanned multiple genuinely distinct
concepts (e.g. FVC vs. FEV1 vs. FEV1/FVC all filed under `spirometry.yaml` / `observations`), a
single "Submit" blanket-overwrote **every** row in that group to the one new value — including rows
that had nothing to do with the finding being applied.

This bug fired via the 2026-08-17 curator session and was captured in commit `f5c7bc65`
("curate ARCI, CARDIA, FHS, HCHS, JHS, MESA, curie mappings"). `_apply_yaml()` already had an
equivalent safety check (refuses to write when a file's blocks hold differing values), which is why
the YAML transform files were mostly untouched — only the CSV side silently corrupted.

**Fix applied**: `_apply_csv()` now takes `original_curie` and only overwrites a row when its current
CURIE matches it; `submit_all()` passes `original_curie` through. See
`ARIC_change_request_20260819_06.json` for the code-fix record.

## Scope checked

Audited every commit touching `{STUDY}_curie.csv` for **ARIC, CARDIA, FHS, HCHS, JHS, MESA** by
diffing removed vs. added CURIE values per `(YAML File, Slot)` group. **CARDIA, JHS, and MESA were
clean** — their 2026-08-17/18 edits went through a different, per-row "cross-study consistency"
path, not the buggy blanket submit. WHI was not implicated (no commit in this window touched its CSV).

## Affected files (6 total, 404 rows)

| Study | File | Slot | Rows | Distinct original concepts | Collapsed to | Status |
|---|---|---|---|---|---|---|
| ARIC | spirometry.yaml | observations | 195 | 9 | `OMOP: 3003197` (malformed) | CSV fixed 2026-08-19; **YAML actually fixed 2026-08-24** (`2aae3e27`) — commit `aa116b0e` on 2026-08-19 introduced the malformed value into the YAML, it was not yet corrected there until 08-24 |
| FHS | asthma.yaml | condition_concept | 93 | 8 | `MONDO:0004979` | Fixed 2026-08-19 |
| FHS | stroke.yaml | condition_concept | 29 | 6 | `MONDO:0005098` | Fixed 2026-08-19 |
| FHS | tak_cenactag.yaml | drug_concept | 21 | 2 | `OMOP: 1398937` (malformed) | CSV fixed 2026-08-19; **YAML actually fixed 2026-08-25** (`b5385b57`) — commit `aa116b0e` on 2026-08-19 introduced the malformed value into the YAML, it was not yet corrected there until 08-25 |
| FHS | tak_orlhypoag.yaml | drug_concept | 24 | 8 | `OMOP:1594973` | CSV fixed 2026-08-19; **YAML actually fixed 2026-08-25** (`b5385b57`) — commit `aa116b0e` on 2026-08-19 introduced the malformed value into the YAML, it was not yet corrected there until 08-25 |
| HCHS | spirometry.yaml | observations | 42 | 5 | `OMOP:3011505` | CSV fixed 2026-08-19; **YAML actually fixed 2026-08-24** (`2aae3e27`) — commit `aa116b0e` on 2026-08-19 introduced the malformed value into the YAML, it was not yet corrected there until 08-24 |

Note on **FHS stroke.yaml**: this one is different in kind from the others. The live YAML transform
was already uniform (17 blocks, all `HP:0001297`) and was legitimately, successfully updated to
`MONDO:0005098` — that part was never wrong. But the CSV separately carried richer, answer-value-level
documentation for two enum-style variables ("Stroke type" / "Stroke/TIA type": ischemic, hemorrhagic,
etc. — `MONDO:0005099/0005264/0006809/0011057/0013792`) that the flat YAML doesn't currently consume.
The bug blanket-erased that documentation too; it's been restored even though it doesn't change the
live transform output.

## How the fix was done, per file

For each affected `(Study, YAML File)`:
1. Pulled the full pre-corruption row set from git history (`f5c7bc65^`, the commit immediately
   before the corruption).
2. Matched rows to the current file positionally within the same `(YAML File)` group (row counts
   verified equal before touching anything — no mismatches found).
3. Rows whose *original* value equaled the finding's `original_curie` → set to the finding's intended
   new value.
4. All other rows → restored to their original (pre-corruption) value.
5. Corresponding YAML transform blocks were located and fixed the same way (or confirmed already
   correct, as with `stroke.yaml`).

## How to read the companion CSV (`curie_corruption_audit_20260819.csv`)

404 rows, one per affected CSV row across all 6 files. Columns:

- **Original CURIE (pre-2026-08-17)** — the true value before the bug, from git history.
- **Corrupted CURIE (2026-08-17 to 2026-08-19)** — what every row in the group was wrongly set to
  during the ~2-day window the bug was live.
- **Corrected CURIE (current, as of 2026-08-19)** — the value now in the working tree, after this fix.
- **Row Status** — `TARGET FIX` (this row's concept really was the one the curator's finding meant to
  change) vs. `RESTORED` (this row's concept was collateral damage from the blanket overwrite, now
  reverted to its original value).

For every row, **Original CURIE** should equal **Corrected CURIE** unless Row Status is `TARGET FIX`,
in which case **Corrected CURIE** should equal the study's intended new value from the table above.

## Follow-up correction — same day, 2026-08-19

The first fix pass applied the target fix to **every** row whose original value matched
`original_curie`, without checking whether the variable itself was a real measurement. In ARIC and
HCHS `spirometry.yaml`, 5 "Age" variables (`PFTB04`, `PULB20`, `PULP20`, `V5AGE51` in ARIC;
`AGE` in HCHS) happened to also hold `OMOP:3002094` in their pre-corruption state — purely because
they were swept into the same cross-product row-generation artifact as the real FVC/FEV1 variables
(these variables only ever appear in the YAML as `age_at_observation`, never as `observation_type`
— they have no real relationship to the FVC concept at all). The first pass wrongly moved them to
the new target CURIE along with the genuine FVC rows.

Corrected: those 5 variables' rows (24 CSV rows in ARIC, 6 in HCHS — every row sharing their `phv`,
not just the one that matched `original_curie`) were restored to their true original per-row values.
No YAML change was needed or made for them, since they never had an `observation_type` field to
begin with. **Target-fix count revised from 66 to 61** (28→24 in ARIC spirometry, 7→6 in HCHS
spirometry); the audit CSV and `_apply_csv_update_fix.md` reflect the corrected numbers.
