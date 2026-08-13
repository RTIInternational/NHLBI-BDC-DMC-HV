# Transform spec concept-code corrections (2026-08-03)

**Completed work, kept for its reasoning.** Six `observation_type` concept codes
in `priority_variables_transform/*/*.yaml` are corrected here — the header
originally said four, before two more were found by resolving every live code
against S1. Nothing else in the specs changes: every edit is a one-line
`observation_type: value:` replacement, 20 files. A TSV of the same swaps
(`../spec_code_fixes_20260803.tsv`) went to the spec owner in place of this
document; **the per-code rationale below and the "What was NOT changed" section
exist only here.**

The "Open items" section at the bottom records four decisions that are still
unresolved — they are surfaced in [`../README.md`](../README.md) so they don't
get lost in a document about completed work.

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
| `vege_serving` | `OMOP:4042886` | `OMOP:37311566` | 6 | 40 | Wrong semantic class; see §2 |
| `cd40` | `OMOP:4209737` | `OBA:2052305` | MESA | 1 | Curator: "Use the OBA CURIE for CD40. The trans spec is wrong." |
| `lympho_ct` | `OBA:VT0000217` | `OBA:VT0000717` | ARIC | 1 | Mis-code: `VT0000217` is White blood cell count |
| `troponin` | `OMOP:8842` | `OMOP:4021291` | FHS | 2 | `8842` is a UCUM *unit*, not a concept; see §5 |
| `carotid_imt` | `OBA:2050108` | `OMOP:4138462` | JHS | 6 | `2050108` is a *drug*, not a measurement; see §6 |

The first four came from the Table S1 curator review. The last two were found
afterwards by resolving every live `observation_type` against S1, and were
verified in Athena and against the BDCHM schema before being changed.

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

**Follow-up (2026-08-13): this fix exposed a separate ARIC spec bug** — both
files draw their value from the same dbGaP column. Open, awaiting a spec-owner
decision; the full account is in
[`../OPEN_ARIC_LYMPHO_CT_PHV.md`](../OPEN_ARIC_LYMPHO_CT_PHV.md). The concept-code
correction above is still right and should not be reverted to silence it.

## 5. `troponin`: `OMOP:8842` -> `OMOP:4021291` (FHS only)

2 occurrences. **`OMOP:8842` is not a clinical concept at all** — Athena gives
it as `nanogram per milliliter`, Vocabulary `UCUM`, Domain `Unit`, Concept
class `Unit`. A unit code had been written into the concept slot; the spec's own
`unit: ng/mL` sits a few lines below it.

`OMOP:4021291` is SNOMED "Troponin measurement" (Domain Measurement, Standard,
Valid), is what ARIC / CARDIA / WHI already use, is what S1 lists, and is the
BDCHM `MeasurementObservationTypeEnum` value `TROPONIN`.

## 6. `carotid_imt`: `OBA:2050108` -> `OMOP:4138462` (JHS only)

6 occurrences. **`2050108` is a drug** — Athena gives OMOP concept 2050108 as
`levofloxacin 250 MG Oral Tablet [NEOBIT]`, Vocabulary `RxNorm Extension`,
Domain `Drug`. An antibiotic stood in place of an ultrasound measurement. The
`OBA:` prefix is also wrong, since 2050108 is an OMOP concept id, not an OBA
term — which is likely why the error survived review.

`OMOP:4138462` is used by ARIC / CHS / FHS / MESA, is what S1 lists, and is the
BDCHM enum value `CAROTID_IMT`.

## What was NOT changed

- All `value_enum` answer codes in `cig_smok` specs.
- `whtbld_ct.yaml` (all cohorts) and `LTRC-ingest/labs_cbc.yaml`, which use
  `OBA:VT0000217` correctly for white blood cell count.
- `SPIROMICS-ingest/cig_smok.yaml`, `FHS-ingest/vege_serving.yaml`,
  `ARIC/CARDIA/WHI troponin.yaml` and `ARIC/CHS/FHS/MESA carotid_imt.yaml`,
  which already carried the correct codes.
- **FHS's fasting-lipid codes** — `OMOP:4041720` (Plasma fasting HDL
  cholesterol measurement), `OMOP:4041722` (Plasma fasting triglyceride
  measurement), `OMOP:4042590` (Serum fasting triglyceride measurement). All
  three are valid Standard SNOMED Measurement concepts and are *more* specific
  than S1's generic `OMOP:4076704` HDL / `OMOP:4032789` Triglycerides; they
  match the specs' own `method_type: fasting minimum 12 hrs`, and the
  plasma/serum pair is a real specimen distinction. An initial reading treated
  them as redundant because method and units matched across the three codes in
  one file; Athena showed that was wrong. Whether S4 reports fasting lipids as
  separate rows or rolls them into HDL/Triglycerides is a curator decision.
- **`edu_lvl`** in all six cohorts, pending a decision on which concept code to
  standardize on — see "Open items" below.
- Every other spec file. Only the six codes in the summary table were touched.

## Verification

- All 20 affected spec files validate against the linkml-map schema
  (`validate_ingest_yamls.py`'s `validate_block`). 20/20 pass.
- All edited YAML parses.
- No residual occurrences of any of the four old codes remain outside the
  legitimate `whtbld_ct` / `labs_cbc` usage noted above.
- The 5 pre-existing validator errors in `spirometry*.yaml` are unrelated and
  untouched by this work; the validator exits 0.

## Open items (decisions needed, no code changed)

**A. `cig_smok` conflicts with the BDCHM schema.** The curator directed
`OMOP:35811013`, but `MeasurementObservationTypeEnum` binds
`SMOKING_STATUS` to the *old* code `OMOP:4282779`. `OMOP:35811013` is not a
permissible value. The specs and the schema now disagree, and one of them has
to move: either the enum's `SMOKING_STATUS` meaning is updated to
`OMOP:35811013`, or the curator decision is revisited. (LTRC's spec already
carried a comment noting this code "not in BaseObservationTypeEnum", so the
mismatch predates this change — it is not newly introduced, but it is now the
curator-endorsed code rather than an incidental one.) Same situation, less
urgently, for `vege_serving` `OMOP:37311566` and Basophils `OMOP:3006315`,
neither of which is in the enum either.

**B. `edu_lvl` — four different shapes across six cohorts.** The BDCHM schema
settles the modeling question but not the code choice. `Observation` defines
`observation_type` as **required**, range `BaseObservationTypeEnum`; `category`
is optional, range `GravityDomainEnum` on `SdohObservation`. So the two slots
are not interchangeable and `category` alone is not sufficient:

| Cohorts | `observation_type` | `category` | Status |
|---|---|---|---|
| HCHS, JHS | `OMOP:42528763` | `EDUCATIONAL_ATTAINMENT` | Correct shape |
| CHS | `OMOP:4022643` | *(absent)* | Missing the category |
| ARIC, MESA | *(absent)* | `EDUCATIONAL_ATTAINMENT` | Violates required slot |
| COPDGene, FHS | `EDUCATIONAL_ATTAINMENT` | `EDUCATIONAL_ATTAINMENT` | Enum in a CURIE slot |

`EDUCATIONAL_ATTAINMENT` is a `GravityDomainEnum` value and is **not** in any
observation-type enum, so COPDGene/FHS are putting a category value in the
concept slot. Note `BaseObservationTypeEnum` has no values of its own; it
inherits `EducationalAttainmentObservationTypeEnum`, whose seven values are
*answer* codes (8TH_GRADE_OR_LESS, HIGH_SCHOOL_GRADUATE_GED, ...) — i.e. the
`value_enum` domain, not the observation-type domain. Neither `OMOP:4022643`
nor `OMOP:42528763` is a permissible `observation_type` value today.

The code choice is genuine: `OMOP:4022643` (SNOMED, Observable Entity, synonym
"Level of educational attainment" — what S1 lists) vs `OMOP:42528763` (LOINC,
Clinical Observation, "Highest level of educ", tagged SDOH / ordinal / point in
time). Both describe education level. Once one is chosen, all six cohorts
should get it in `observation_type` plus `category: EDUCATIONAL_ATTAINMENT`,
and the enum needs a matching permissible value.

**C. `alpha1_antitrypsin` has no Table S1 row.** LTRC emits `OBA:2050075`,
which *is* in the BDCHM enum as `ALPHA-1_ANTITRYPSIN_IN_SERUM`, so the spec is
correct — S1 is simply missing the variable. Add a row, or confirm it is out of
scope for the published tables.

**D. Enum coverage generally.** 36 of the 127 distinct `observation_type` codes
in the live specs are not permissible values of
`MeasurementObservationTypeEnum`. Most predate this work (the six
spirometry-metadata codes are among them and are deliberately `status=ignore`).
Worth a separate reconciliation pass between the specs, Table S1, and the
schema enums; it is out of scope here.

## Review

The full diff is the ground truth and is small — every line a single-token code
swap:

```
git diff main -- priority_variables_transform/
```

Questions to confirm:

1. `vege_serving` -> `OMOP:37311566`: does the servings-intake reading hold for
   the six FFQ-based cohorts, or is there a reason those were deliberately
   coded to the substance concept?
2. `cig_smok` -> `OMOP:35811013`: any cohort where `OMOP:4282779` was
   intentional rather than copied? See open item A — this code is not currently
   in the BDCHM enum.
3. FHS fasting lipids: keep the fasting/specimen-specific codes as distinct S4
   rows, or roll them up into HDL / Triglycerides?
