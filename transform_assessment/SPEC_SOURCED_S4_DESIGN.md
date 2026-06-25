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

## Remaining questions for the team

1. Confirm spec-sourced S4 is the agreed direction (vs. patching sheets).
2. For S5: which spec snapshot were the enclave harmonized TSVs built
   from? Re-harmonizing from `main` + `thessen-s5-fixes` should clear the
   aptamer contamination; the residual extreme values flagged in QC are in
   the source data and stay.
