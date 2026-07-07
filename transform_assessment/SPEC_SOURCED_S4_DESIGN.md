# Spec-sourced S4/S5 — what's settled, what's left

## Settled

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

## Approach

Source S4 from the transform specs, not the sheets:

- phv list / count / harmonized concept / cohort ← ingest YAMLs
  (`populated_from` phvs, `observation_type.value`, ingest dir)
- `n` (kept) ← `extract_source`, measured from source TSVs in the enclave.
  It already has a `--yaml-dir` hook that scopes phvs to whatever the
  specs reference, so out-of-spec phvs (the aptamers) are excluded
  automatically. No `extract_source` change expected.

The sheets are then not needed for any table data (phv membership,
mapping, or n).

## Multi-concept split (built)

One spec file can define several harmonized concepts, each a
MeasurementObservation with its own `observation_type` and value phvs —
`blood_pressure.yaml` (Systolic + Diastolic), `spirometry.yaml` (FEV1 /
FVC / FEV1-FVC / ...), LTRC `body_measures.yaml` / `labs_cbc.yaml`. These
map to separate rows in the S4 template, so S4 emits **one row per
`observation_type`**, not one per file.

- **Parsing** goes through linkml-map's normalizing loader
  (`load_specification`), which flattens the local `observations` /
  `object_derivations` nesting into walkable `class_derivations` (linkml/
  linkml-map issue #112). Older linkml-map *dropped* that nesting silently;
  the fix landed on `main` (commit `d5abfd0`, "Implicit cross-table join
  resolution for nested class derivations"), so HV pins **linkml-map @ main**
  (not a release — `v0.5.2` predates the fix).
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
  OMOP half is unmapped in `harmonized_vars.tsv`), giving prefer-OBA /
  fall-back-OMOP behavior for free.

## Remaining questions for the team

1. Confirm spec-sourced S4 is the agreed direction (vs. patching sheets).
2. For S5: which spec snapshot were the enclave harmonized TSVs built
   from? Re-harmonizing from `main` + `thessen-s5-fixes` should clear the
   aptamer contamination; the residual extreme values flagged in QC are in
   the source data and stay.
3. **Spirometry coverage gap (Anne).** 6 spirometry concept codes in the
   specs (`OMOP:3002094, 3005600, 3011708, 3022891, 3024594, 4196583`) have
   no row in `harmonized_vars.tsv`, so they don't resolve to a label and
   currently group under the stem "spirometry" in the unmatched block. Are
   those spirometry measures in scope, and what labels/rows should they get?
4. **harmonized_vars.tsv source + freshness (Anne).** It is a manual export
   of the curator variable-properties sheet, committed ~Jan 2026, copied in
   from `sb_for_bdc`. Is it the right source for S4's concept→label
   resolution, and is it current?
