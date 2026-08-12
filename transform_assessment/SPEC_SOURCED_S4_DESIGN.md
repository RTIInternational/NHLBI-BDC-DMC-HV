# Spec-sourced S4/S5 — design

Why the S4/S5 generator is built the way it is. Open questions for the team live
in [`README.md`](README.md), not here.

> **⚠️ Not independently reviewed.** The "Multi-concept split" section below was
> written from inside the implementation, by whoever was writing the
> implementation. It has never been read critically by someone who could push
> back on it, and at least one of its claims has already drifted from the code
> (see the Parsing bullet). That matters more than it looks: the design decision
> recorded there — key variable identity on `observation_type` — is very likely
> what made the ~300 non-measurement spec files invisible to the generator and
> cost a session to diagnose. See "How the `observation_type` assumption spread"
> below.
>
> Don't treat that section as settled just because it is written down
> confidently. The rest of the doc is lower-stakes.

## Why specs, not sheets

- **Specs are authoritative, sheets have drifted.** Live `FHS-ingest/
  ast_sgot.yaml` maps the 5 correct clinical phvs; `fibrin.yaml` maps 8.
  The aptamers that produced the S5 outliers (`phv00422716` AST,
  `phv00421971` Fibrinogen) appear only under `_archive/` — removed from
  the live specs but still in `FHS_VariableProperties`. So S4's "6 / 9"
  counts are stale-sheet artifacts; spec-derived counts are 5 / 8.
- **Pull specs from `main`** (latest of everything, nothing pending from
  QC), and **merge `thessen-s5-fixes` before re-running** (fixes some
  problems, not all — some extreme values are in the original source data).
  `thessen-s5-fixes` is unmerged, mostly spirometry/method_type, and does
  not touch ast_sgot/fibrin.

Sourcing:

- phv list / count / harmonized concept / cohort ← ingest YAMLs
  (`populated_from` phvs, `observation_type.value`, ingest dir)
- `n` (kept) ← `extract_source`, measured from source TSVs in the enclave.
  It already has a `--yaml-dir` hook that scopes phvs to whatever the
  specs reference, so out-of-spec phvs (the aptamers) are excluded
  automatically. No `extract_source` change expected.

The sheets are then not needed for any table data (phv membership,
mapping, or n).

## How the `observation_type` assumption spread

Worth reading before the next section, because it is a caution about how that
section is written.

Emitting one row per `observation_type` is a correct statement about
**measurement** files, where one file really can define several concepts. It
says nothing about how to *find* variables in general. But `observation_type`
became the identity join everywhere, and Condition / DrugExposure / Procedure /
Demography specs have no `observation_type` — so ~300 files became structurally
invisible and 51 S4 rows silently rendered empty.

The tell is that every justification recorded for the concept-code join is a
measurement justification: the dual-coding bullet below argues it entirely in
terms of collapsing HDL/LDL/triglyceride synonyms across OBA and OMOP. The other
classes were never considered. The design was not wrong; it was written from one
case and then applied universally.

**The lesson for reading the rest of this doc:** it describes the measurement
path in confident detail and is silent on everything else. Treat that silence as
unexamined rather than as "not applicable."

## Multi-concept split (built)

One spec file can define several harmonized concepts, each a
MeasurementObservation with its own `observation_type` and value phvs —
`blood_pressure.yaml` (Systolic + Diastolic), `spirometry.yaml` (FEV1 /
FVC / FEV1-FVC / ...), LTRC `body_measures.yaml` / `labs_cbc.yaml`. These
map to separate rows in the S4 template, so S4 emits **one row per
`observation_type`**, not one per file.

- **Parsing** is two steps, and an earlier version of this bullet conflated
  them — worth stating precisely, since the difference is where the fragility
  lives:
  1. `_regroup_by_entity` reads the raw YAML and regroups a per-variable spec
     file (a *list* of `{class_derivations: {Entity: ...}}` blocks) into the
     composed *dict* form (`{class_derivations: [{Entity: ...}, ...]}`). This
     step, not normalization, is what produces walkable `class_derivations`.
     It is the same grouping dm-bip's `compose_specs` does, inlined.
  2. `Transformer._normalize_spec_dict` then flattens the local `observations` /
     `object_derivations` nesting (linkml/linkml-map issue #112) so nested
     MeasurementObservations survive. Older linkml-map *dropped* that nesting
     silently; the fix landed on `main` (commit `d5abfd0`), so HV pins
     **linkml-map @ main** — `v0.5.2` predates it.

  We deliberately do NOT build the strict `TransformationSpecification` pydantic
  model (`load_specification`): some live specs carry local slots beyond the
  schema — spirometry pre/post-BD MOs have a `context` slot with `activity` /
  `relative_timing` (bronchodilator timing) — which the model rejects with
  `extra_forbidden`. Walking the normalized dict lets those unknown slots pass
  through harmlessly; only the value slots are read for phv counts. Note the
  result is *not* uniformly a dict: `_as_list` exists because
  `class_derivations` normalizes to either a list or a name→cd dict depending on
  nesting depth.

  **Fragility worth watching.** Step 2 depends on the specs using the deprecated
  `object_derivations` spelling — the flattening we rely on is exactly what
  triggers linkml-map's per-file `DeprecationWarning` (which
  `_normalize_spec` suppresses by message match). Spec files are being migrated
  to `class_derivations` (`e320be99`, `b72391a6`, `482a0152`). If that migration
  completes, this code path may stop firing, and the suppression will hide the
  signal that it did. Not currently tested for.
- **dm-bip is deliberately NOT a dependency.** Its `compose_specs` (aggregate
  per-variable blocks by entity) is the only piece S4 needs, and it is
  reimplemented inline (`_regroup_by_entity`, ~10 lines). dm-bip's `main`
  hard-pins `linkml-map==0.5.2`, which lacks the nesting fix — adding it would
  downgrade linkml-map and defeat the split. Restore the dm-bip dep +
  `compose_specs` once dm-bip's linkml-map floor catches up.
- **Dual-coding collapse.** A variable coded OBA in some cohorts and OMOP in
  others (HDL, LDL, triglycerides) must not split. Concepts are grouped by
  *resolved label*, so same-label concepts merge into one row. In every
  dual-coded case in the current specs it is the OBA code that resolves (the
  OMOP half is unmapped in the label source), giving prefer-OBA /
  fall-back-OMOP behavior for free.
- **Spirometry metadata codes ignored.** The spirometry specs carry 6 OMOP
  codes (`3002094, 3005600, 3011708, 3022891, 3024594, 4196583`) that are
  metadata for the 3 real spirometry variables (FEV1, FVC, FEV1/FVC), not
  separate measurements — per the project lead, 2026-07-07. They are listed in
  `s4_layout.yaml`'s `ignore_observation_types` and dropped in
  `build_cohort_rows`, so they neither form a stray "spirometry" row nor
  inflate the 3 real rows' phv counts.

## Non-measurement classes (designed, not yet built)

The generator currently extracts phvs only from measurement value slots
(`_VALUE_SLOTS` in `spec_phv_report.py`), so **the non-measurement spec files
are structurally invisible** — they carry their identity in slots that are never
read. Counts as of 2026-08-12, over 836 spec files:

| class | files |
|---|---|
| MeasurementObservation (parsed) | 472 |
| Condition | 171 |
| DrugExposure | 94 |
| Observation / SdohObservation | 28 |
| Procedure | 14 |
| Person | 11 |
| Demography | 11 |
| Visit / ResearchStudy / Participant (not S4 variables) | 33 |

The effect is **51 empty rows** of 149 template data rows: every `Taking <drug>`
row, the disease/status rows (Angina, Asthma, Diabetes, COPD status, …), and the
demographics rows (Ethnicity, Death, Cause of death). Reproduce by counting
all-blank rows in any current S4 run. `TableS1.tsv` retains the
non-measurement rows with a `var_name` matching spec filename stems, so label
resolution is already solved; the parser just never asks.

> Earlier versions of this section said "282 spec files" and "50 empty rows".
> Neither figure was reproducible — the per-class breakdown printed alongside
> "282" actually summed to 305. Treat the table above as the measured numbers
> and re-measure rather than trusting any single total.

**What counts as a "relevant raw variable" per class** (settled with the repo owner,2026-08-04, by reading one representative spec per class):

| class | phv source | representative spec |
|---|---|---|
| MeasurementObservation | `class_derivations → slot_derivations → value_decimal → populated_from` | `CARDIA-ingest/alcohol_servings.yaml` |
| Condition | `condition_status → populated_from` | `ARIC-ingest/diabetes.yaml` |
| Demography | `sex` / `race` / `ethnicity` → `populated_from` | `ARIC-ingest/demography.yaml` |
| DrugExposure | `drug_concept → expr` | `ARIC-ingest/tak_statin.yaml` |

Ruled out everywhere: `associated_participant` and `associated_visit` (join
keys, not variables — counting them would inflate every row), and `identity` /
`id` / `species` on Person. `condition_concept` is a constant, not a phv, so it
contributes nothing even though it carries the variable's identity. Age slots
(`age_at_condition_start`, `age_at_death`) need no decision: **there is no age
variable in S4**.

Caveat on DrugExposure: `drug_concept` holds its phv only inside a `case()`
predicate (`case(({phv00204156} == 1, "ATC:C10A"))`) — reachable, since
`_slot_phvs` already parses phvs out of `expr` strings. One phv per `case()`
line holds **in ARIC**; the other 94 DrugExposure specs have not been swept for
multi-phv predicates. Sweep before hardcoding the assumption.

### Demography and Person need slot-level mapping, not filename stems

Most classes are one file per variable, so a filename-stem lookup resolves them.
Demography and Person are not: one file feeds several S4 rows from sibling
slots. Verified against the BDCHM schema and all 23 live specs — Demography's
attributes are exactly `sex`/`race`/`ethnicity` with no naming variants (JHS
lacks `ethnicity`, which is real data, not drift), and Person carries the death
variables under slot names that do not match the S4 labels:

```yaml
slot_variables:
  Demography: {sex: Sex, race: Race, ethnicity: Ethnicity}
  Person:     {vital_status: Death, cause_of_death: Cause of death}
```

That covers 5 of the 48 non-measurement rows; the other 43 stay per-file on
filename stem. **The extractor dispatches on S1's `BDCHM Element` column**:
these two classes use the slot map, the rest use the stem lookup.

**Do not assume one file per (cohort, class).** CARDIA had both
`cause_of_death.yaml` and `person.yaml` defining a `cause_of_death` slot on
`Person`. That specific duplication is gone — `cause_of_death.yaml` was deleted
on `main` in the 2026-08-04 CARDIA PR — but the shape can recur, and an
extractor that picks one file arbitrarily will silently undercount. **Detect and
report** any (cohort, class, slot) whose phvs come from more than one file;
don't resolve it silently. Union, authoritative-file, and "the duplication is a
spec bug to fix" are all plausible answers and the right one depends on the
case.

### Combined phvs: 3 is the correct count for CARDIA alcohol

`CARDIA-ingest/alcohol_servings.yaml` has 10 measurement blocks but only 3 live
value phvs; the other 7 carry summing expressions that were commented out within
a day of being written (`07e2e819` → `2a93479f` → `1623e1f1`, 2026-03-16/17).
This looked like a large undercount against the published S4's 67.

Per the project lead (2026-08-04): the 3 live phvs are almost certainly **beer,
wine, and liquor servings per week**, and the disabled expressions summed them
into total alcohol per week. So the components are the real raw variables and
**3 is the honest count** — the sum would have been a 4th derived value, not 27
additional raw variables. They could not find these in dbGaP to confirm, so this
is domain inference, not a lookup.

Two consequences beyond this file:

- Wherever multiple phvs combine into one harmonized variable, an S4-vs-S5
  comparison will **look like data loss**. It is not, and the writeup needs to
  say so. Whether CARDIA alcohol is the only such case is unverified — the
  known-stub scan found value-less `Quantity` blocks in this file only (7 of
  2,615 across all 842 specs), but live `expr` sums elsewhere would not show up
  in that scan.
- Leaving `slot_derivations:` empty except for comments is a schema error in its
  own right, and today it is silently invisible to both the validator and the
  generator. A validator check for value-less `Quantity` blocks would fire
  exactly once right now, which is the right size for a new check.

## Known defects — found 2026-08-12, not fixed

Audited after two silent failures turned up (the `observation_type` narrowing,
and a `cohort_keys` omission that blanked the whole HCHS/SOL column). Each of
these is **verified against the code and the data**, and each fails *silently* —
a blank cell or a wrong number, never an error. None are fixed; they are
recorded so the next person doesn't rediscover them.

**1. N can be silently undercounted — the highest-risk one, because it publishes
a wrong number rather than a blank.** `_col_n_valid`
(`spec_phv_report.py:259-264`) returns `None` for three distinct failures: PHT
missing from the extract, column missing from the PHT, and `n_valid` present but
null. `build_cohort_rows` (lines 350-357) then counts that phv toward
`phv_count` while contributing 0 to `total_n`. The result is a row claiming e.g.
6 phvs with an N covering only 4 — plausible-looking and wrong, with nothing
counting or reporting the misses. A stale dbGaP cache triggers the same path via
the `phv_name_map` miss at line 257.

**2. Table S5 drops rows on letter-case drift.** `table_s5/` matches
`TABLE_S5_LABELS` against Table S1 exactly and case-**sensitively** — there is
no `lower()` anywhere in the package — while the S4 side normalizes case
(`spec_phv_report.py:498`). Two tables, one label source, opposite policies.
Currently affected: `Bilirubin total` (S1: `Bilirubin Total`) and `interleukin 6
in blood` (S1: `Interleukin 6 in blood`). **This is a regression** — both were
`matched` in the June run; see
`hv_dataqc/sb_output/20260630T172556Z/s5_coverage_20260630_172655.tsv` lines 13
and 60. `93ac3910` emptied `S5_LABEL_ALIASES` on the claim that all 19 aliases
were dead under S1; for these two the alias needed *updating*, not deleting.
`format_paste_tsv` emits a blank line, so the paste still aligns and the failure
is invisible in the delivered artifact. (`Fasting lipids` also misses but has no
S1 row at all — pre-existing, not a regression.)

**3. Demography labels are lowercase where everything else capitalizes.**
`harmonized_extract.yaml` maps `sex: sex` / `race: race` / `ethnicity:
ethnicity`, and `extract_harmonized_summaries.py:331-337` uses the value
directly as `bdc_label` — the only such assignment that bypasses the S1 lookup.
S1 and `s4_layout.yaml` both say `Sex` / `Race` / `Ethnicity`, so any join on
`bdc_label` misses.

**Why none of this was caught, and the one guard that would have.** Every real
config file except `TableS1.tsv` has zero test coverage: all 17 tests in
`test_spec_phv_report.py` build layout dicts inline, so `load_layout(None)` and
`DEFAULT_LAYOUT_PATH` are never exercised. `test_table_s5.py:330` asserts in a
*comment* that S1 matches every S5 label directly — contradicted by the data
above, and never tested.

The superseded pipeline had the check that would have caught all of these: a
bidirectional config-vs-data cohort reconciliation, plus union rather than
truncate semantics so an unconfigured cohort showed up as an extra column
instead of vanishing. The rewrite dropped both. A test asserting, over the
**real shipped configs**, that (a) every layout cohort resolves to an existing
ingest dir, (b) every ingest dir is reachable from some layout cohort, (c) every
`TABLE_S5_LABELS` entry resolves to a real S1 `Variable Label`, and (d) every
`demography_columns` label is a real S1 label, would have caught defects 2 and 3,
the LTRC/SPIROMICS drop, and the original HCHS/SOL bug. See
[`history/S4_COUNT_INVESTIGATION_REMOVED.md`](history/S4_COUNT_INVESTIGATION_REMOVED.md)
for where the old check lived.

## Open on this design

Team-facing questions have moved to [`README.md`](README.md). One remains
specific to this design:

- For S5: which spec snapshot were the enclave harmonized TSVs built from?
  Re-harmonizing from `main` + `thessen-s5-fixes` should clear the aptamer
  contamination; the residual extreme values flagged in QC are in the source
  data and stay.

Resolved 2026-08-12: **spec-sourced S4 is confirmed as the direction.** This had
proceeded on assumption since ~2026-06 without explicit sign-off. The project
lead then retired both spreadsheet-derived filters outright — *"you also
shouldn't go by what is in the spreadsheets anymore, we can't keep those up to
date"* — which settles it: sheets are not a fallback, and patching them is not
an option on the table.

Resolved, kept because the reasoning still governs code:

- **Spirometry coverage gap** — RESOLVED (project lead, 2026-07-07): the 6 codes
  are metadata for the 3 spirometry variables, not measurements. Now ignored via
  `s4_layout.yaml` `ignore_observation_types` (see Multi-concept split above).
- **`harmonized_vars.tsv` freshness** — OBSOLETE. The file was a manual export of
  the curator variable-properties sheet and has been deleted; Table S1 is now the
  only label source. See [`history/S1_LABEL_SOURCE_MIGRATION.md`](history/S1_LABEL_SOURCE_MIGRATION.md).
