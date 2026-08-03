# Transform spec concept-code corrections (2026-08-03)

**For review by the transform spec owner.** Four `observation_type` concept
codes in `priority_variables_transform/*/*.yaml` are corrected here. Nothing
else in the specs changes — every edit is a one-line `observation_type: value:`
replacement. 18 files, 143 lines, no structural edits.

These originate from a curator review of **Table S1** (the harmonized-variable
label table in the "Data Harmonization Supplementary Data" workbook). Table S1
is becoming the authoritative concept-code -> publication-label source for
Tables S4/S5, replacing an older drifted TSV export; see
[`S1_LABEL_SOURCE_MIGRATION.md`](S1_LABEL_SOURCE_MIGRATION.md). Reconciling the
specs against S1 surfaced these four disagreements.

## Summary

| Variable | Old code | New code | Cohorts | Occurrences | Basis |
|---|---|---|---|---|---|
| `cig_smok` | `OMOP:4282779` | `OMOP:35811013` | 10 | 101 | Curator: "We need to use 35811013. The trans specs are incorrect." |
| `vege_serving` | `OMOP:4042886` | `OMOP:37311566` | 6 | 40 | Wrong semantic class; see below |
| `cd40` | `OMOP:4209737` | `OBA:2052305` | MESA | 1 | Curator: "Use the OBA CURIE for CD40. The trans spec is wrong." |
| `lympho_ct` | `OBA:VT0000217` | `OBA:VT0000717` | ARIC | 1 | Mis-code: `VT0000217` is White blood cell count |

Note the direction differs per case. For `cig_smok`, `cd40`, and `lympho_ct` a
minority of specs disagreed with the rest and with S1. For `vege_serving` the
**majority of specs were wrong** — that one is the least intuitive and is
detailed below.

## 1. `cig_smok`: `OMOP:4282779` -> `OMOP:35811013`

101 occurrences across ARIC, CARDIA, CHS, COPDGene, FHS, HCHS, JHS, LTRC, MESA,
WHI. **SPIROMICS already used `OMOP:35811013`** and needed no change — the other
ten now match it.

These spec files each emit 4-5 distinct OMOP codes. Only `OMOP:4282779` is the
`observation_type`; the others (`OMOP:45883537`, `OMOP:40766945`,
`OMOP:45883458`, `OMOP:45885135`) are `value_enum` answer codes and are
**untouched**. Every one of the 101 replaced occurrences was verified to sit
directly under an `observation_type:` key before editing.

`LTRC-ingest/cig_smok.yaml` carried an explanatory comment naming the old code;
it was updated in step and now reads:

```yaml
observation_type:
  # NOTE: OMOP:35811013 (tobacco smoking status) not in BaseObservationTypeEnum; matches pattern used by all cohorts
  value: OMOP:35811013
```

## 2. `vege_serving`: `OMOP:4042886` -> `OMOP:37311566`

40 occurrences across ARIC, CARDIA, CHS, JHS, MESA, WHI. **FHS already used
`OMOP:37311566`** and needed no change.

This is the correction most worth scrutinizing, because six specs agreed with
each other and were nonetheless wrong. Three independent lines of evidence:

**Athena definitions** — the two codes are not the same kind of thing:

| Code | Athena concept | Class |
|---|---|---|
| `OMOP:4042886` | Vegetable | **Substance** |
| `OMOP:37311566` | Estimated intake of vegetable servings in 24 hours | **Observable entity** |

The measured quantity is servings per week (`unit: {servings}/wk` or `{#}/wk`).
A *substance* code cannot be the `observation_type` for an intake measurement;
an *observable entity* code can.

**The sibling variable already does this correctly.** `fruit_serving` uses
`OMOP:21493059` — "Estimated intake of fruit servings in 24 hours" — in all six
cohorts that define it, including FHS. That is the exact structural parallel to
`OMOP:37311566` for vegetables, so the intended pattern was already established
elsewhere in the spec set.

**FHS's spec shape corroborates it.** FHS derives the value as a summed
expression over ~28 individual food-item `phv` fields with
`method_type: calculated`, which is what an *estimated intake* is. The other
cohorts read a single reported FFQ field. Both legitimately measure estimated
vegetable-serving intake, so both belong under `OMOP:37311566`.

The substance code appears to have originated in the specs and propagated into
Table S1, rather than the reverse — S1's row for Vegetable consumption carried
`OMOP:4042886`, which is being corrected to `OMOP:37311566` alongside this
change.

Verified: `OMOP:4042886` occurred **only** in `vege_serving.yaml` files. No
other variable referenced it, so this sweep is fully contained.

## 3. `cd40`: `OMOP:4209737` -> `OBA:2052305` (MESA only)

Single occurrence. S1 lists an OBA CURIE and no OMOP concept for CD40; the
curator directed using the OBA code. Bare `OBA:` codes as `observation_type`
are well-established in this spec set (one OBA code alone appears 249 times),
so this is idiomatic, not novel.

## 4. `lympho_ct`: `OBA:VT0000217` -> `OBA:VT0000717` (ARIC only)

Single occurrence, a digit transposition. The evidence that this is a typo
rather than a deliberate choice:

- CARDIA and HCHS `lympho_ct.yaml` already used `OBA:VT0000717`.
- `OBA:VT0000217` resolves to **White blood cell count**, not Lymphocytes.
- Every `whtbld_ct.yaml` spec (white blood cell count) uses `OBA:VT0000217`
  correctly. ARIC's `lympho_ct` was the lone file borrowing the WBC code.

**The `whtbld_ct` specs are correct and were deliberately left untouched.**

## What was NOT changed

- All `value_enum` answer codes in `cig_smok` specs.
- `whtbld_ct.yaml` (all cohorts) and `LTRC-ingest/labs_cbc.yaml`, which use
  `OBA:VT0000217` correctly for white blood cell count.
- `SPIROMICS-ingest/cig_smok.yaml` and `FHS-ingest/vege_serving.yaml`, which
  already carried the correct codes.
- Every other spec file. Only the four codes above were touched.

## Verification

- All 20 affected spec files validate against the linkml-map schema
  (`validate_ingest_yamls.py`'s `validate_block`). 20/20 pass.
- All edited YAML parses.
- No residual occurrences of any of the four old codes remain outside the
  legitimate `whtbld_ct` / `labs_cbc` usage noted above.
- The 5 pre-existing validator errors in `spirometry*.yaml` are unrelated and
  untouched by this work; the validator exits 0.

## Review

The full diff is the ground truth and is small — 143 lines, every one a
single-token code swap:

```
git diff priority_variables_transform/
```

Questions to confirm:

1. `vege_serving` -> `OMOP:37311566`: does the servings-intake reading hold for
   the six FFQ-based cohorts, or is there a reason those were deliberately
   coded to the substance concept?
2. `cig_smok` -> `OMOP:35811013`: any cohort where `OMOP:4282779` was
   intentional rather than copied?
