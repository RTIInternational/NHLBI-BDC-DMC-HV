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

- **Parsing** normalizes each spec with linkml-map's
  `Transformer._normalize_spec_dict` and walks the resulting **dict**, which
  flattens the local `observations` / `object_derivations` nesting into
  walkable `class_derivations` (linkml/linkml-map issue #112). Older
  linkml-map *dropped* that nesting silently; the fix landed on `main`
  (commit `d5abfd0`), so HV pins **linkml-map @ main** (not a release —
  `v0.5.2` predates the fix). We deliberately do NOT build the strict
  `TransformationSpecification` pydantic model (`load_specification`): some
  live specs carry local slots beyond the schema — spirometry pre/post-BD
  MOs have a `context` slot with `activity` / `relative_timing`
  (bronchodilator timing) — which the model rejects with `extra_forbidden`.
  Walking the normalized dict lets those unknown slots pass through
  harmlessly; only the value slots are read for phv counts.
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
- **Spirometry metadata codes ignored.** The spirometry specs carry 6 OMOP
  codes (`3002094, 3005600, 3011708, 3022891, 3024594, 4196583`) that are
  metadata for the 3 real spirometry variables (FEV1, FVC, FEV1/FVC), not
  separate measurements — per Anne Thessen, 2026-07-07. They are listed in
  `s4_layout.yaml`'s `ignore_observation_types` and dropped in
  `build_cohort_rows`, so they neither form a stray "spirometry" row nor
  inflate the 3 real rows' phv counts.

## Remaining questions for the team

1. Confirm spec-sourced S4 is the agreed direction (vs. patching sheets).
2. For S5: which spec snapshot were the enclave harmonized TSVs built
   from? Re-harmonizing from `main` + `thessen-s5-fixes` should clear the
   aptamer contamination; the residual extreme values flagged in QC are in
   the source data and stay.
3. ~~Spirometry coverage gap~~ — RESOLVED (Anne, 2026-07-07): the 6 codes are
   metadata for the 3 spirometry variables, not measurements. Now ignored via
   `s4_layout.yaml` `ignore_observation_types` (see Multi-concept split above).
4. **harmonized_vars.tsv source + freshness (Anne).** It is a manual export
   of the curator variable-properties sheet, committed ~Jan 2026, copied in
   from `sb_for_bdc`. Is it the right source for S4's concept→label
   resolution, and is it current?
