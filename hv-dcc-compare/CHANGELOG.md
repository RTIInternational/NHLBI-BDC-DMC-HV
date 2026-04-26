# DCCCompare Scripts — Changelog

Changes to the scripts in `scripts/topmed_compare/`. Entries are in reverse
chronological order. Each entry covers one or more git commits on the same date.

## Contributing — Mandatory Rule

**Every change to any file in this directory must be documented here in the same
session the change is made.** This applies to all scripts:
`extract_bdc_all.py`, `extract_topmed_all.py`, `match_quality_table.py`,
`compare_bdc_topmed.py`, `topmed_compare_config.py`,
`validate_participant_completeness.py`, `translate_bdc_json.py`, and any future
additions.

Each entry must specify: (1) what changed, (2) why, (3) which cohorts are
affected. See `.github/instructions/dcc-compare-changelog.instructions.md` for
the full rule and example format.

---

## 2026-04-20

### `match_quality_table.py` -- Add group headers to `--all-vars` output

- **What changed**: `--all-vars` mode now groups variables by clinical domain using
  `CORE_VARIABLE_GROUPS` (Demographics, Anthropometrics, Blood Pressure, Smoking,
  Lipids, CBC, CVD History) instead of a flat alphabetical list. Variables not in any
  core group are collected under an "Other" heading at the end. The same `--- Group ---`
  separator style used in core-variable mode is now applied in `--all-vars` mode.
- **Why**: Readability — large cohorts (ARIC, FHS, WHI) match many variables; grouping
  by domain makes the table scannable. Core-variable mode already had headers; `--all-vars`
  was the only mode missing them.
- **Cohorts affected**: All cohorts when running `--all-vars`. No change to default
  (core-variable) mode behavior or output.

### `match_quality_table.py` -- Rename REF labels to TOPMed DCC throughout output

- **What changed**:
  1. **Summary line**: `REF N=` → `TOPMed DCC N=`
  2. **Column headers**: `R_N` → `T_N`, `R_mean` → `T_mean`, `R_M%` → `T_M%`
  3. **MissExplain tags**: `Pop:REF+` → `Pop:TOPMed+`, `Data:REF+` → `Data:TOPMed+`,
     `Data:REF-` → `Data:TOPMed-` (in return value, docstring, counts dict, for-loop list)
  4. **Output label**: `REF-only` → `TOPMed DCC-only`
  5. **Expl column width**: Widened from 10 to 13 chars to accommodate longer tag names
     (e.g., `Data:TOPMed+` is 12 chars)
- **Why**: Consistency — "TOPMed DCC" is the correct term for the reference data source
  throughout the project. "REF"/"R_" were informal shorthands.
- **Cohorts affected**: All 9 cohorts — output format change only, no logic change.

---

## 2026-04-12

### `match_quality_table.py` -- Grade-to-Tier refactor with split Value/Missingness assessment

- **What changed**:
  1. **Grade renamed to Tier**: Single letter grade (A+/A/B/C/D) replaced by two
     independent tier columns: Value Tier (T1-T5) and Miss Tier (M1-M5).
  2. **Value Tier (Val)**: Measures how closely BDC and REF summary statistics
     agree. Continuous variables use normalized mean delta; categorical use max
     category percentage-point difference. Thresholds: T1 (<0.005 / <0.5pp),
     T2 (<0.02 / <1pp), T3 (<0.05 / <3pp), T4 (<0.1 / <10pp), T5 (>=0.1 / >=10pp).
  3. **Missingness Tier (Miss)**: Measures absolute difference in percent-missing
     between BDC and REF. Thresholds: M1 (<1pp), M2 (<3pp), M3 (<8pp),
     M4 (<20pp), M5 (>=20pp). Independent from value tier.
  4. **MissExplain column (Expl)**: Decomposes missingness differences into
     population-driven vs data-driven causes with directionality:
     - `Pop:BDC+` / `Pop:REF+` -- valid count difference explained by total
       population difference (one side simply has more participants)
     - `Data:BDC+` / `Data:REF+` -- one side has more valid observations than
       population alone would explain (better coverage)
     - `Data:BDC-` / `Data:REF-` -- one side has fewer valid observations than
       population alone would explain (coverage gap)
     - `--` -- valid counts too close to distinguish (<0.5% relative difference)
  5. **Output label changes**: `T_N`/`T_mean`/`T_pctM` renamed to `R_N`/`R_mean`/
     `R_M%` (REF prefix). `B_pctM` renamed to `B_M%`. `TOPMed-only` renamed to
     `REF-only`. Header column `Grade` replaced by `Val Miss Expl`.
  6. **Summary section**: Single "Grade summary" line replaced by three lines:
     Value tier summary (T1-T5 counts), Miss. tier summary (M1-M5 counts),
     Miss. explain breakdown (Pop/Data direction counts).
  7. **Methodological notes**: "(grade kept)" changed to "(tier kept)".
- **Why**: Leadership feedback that (a) "Grade" implies quality judgment -- "Tier"
  better conveys similarity ranking; (b) conflating value accuracy and missingness
  into a single score loses information -- a variable can match perfectly on values
  (T1) but differ on missingness (M4) for structural reasons; (c) missingness
  differences caused by population expansion (one side has more participants) are
  fundamentally different from data coverage gaps and should be distinguished.
- **Cohorts affected**: All 9 cohorts. Tested successfully: ARIC, CARDIA, CHS,
  COPDGene, FHS, HCHS-SOL, JHS, MESA, WHI.

## 2026-04-07

### `match_quality_table.py` — Add FHS angina_prior_1 methodological note

- **What changed**: Added new KNOWN_METHODOLOGICAL_DIFFS entry for FHS angina_prior_1
  with code SURVEILLANCE_DENOMINATOR_GAP. Documents the Rose Questionnaire removal,
  the exact 104-positive match with the reference, and the 42.1% missing rate caused
  by the lack of a denominator booster.
- **Why**: After removing 4 Rose Questionnaire blocks from angina.yaml (G3A169 =
  single screening question, not Rose-positive diagnosis), angina positives dropped
  from 401 (overcounted) to exactly 104 (matching reference). But N valid dropped
  from 13,143 to 8,730 because the Rose blocks had provided ABSENT denominator rows
  for Gen3/Omni/NOS participants. The D grade is a structural pipeline limitation
  (no negative-evidence row generation), not an accuracy error.
- **Cohorts affected**: FHS only.

### `match_quality_table.py` — Precise DCC methodology in FHS CABG note

- **What changed**: Replaced vague "reference achieves lower missing by sourcing
  from longitudinal follow-up forms across more exam years" with precise DCC
  phenotype definition details from `cabg_prior_1.json` (UW-GAC/topmed-dcc-harmonized-phenotypes).
  Note now documents the exact surveillance architecture: pht000389 (CVD Event Forms,
  VESSEL count + PROCDATE), pht000309 (Verified Events, EVENT codes + DATE),
  pht003099 (age crosswalk), and pht003316 (Survival dataset) as denominator booster.
  Explains that the surveillance system covers ALL followed FHS participants
  regardless of exam attendance, unlike BDC's exam-based approach.
- **Why**: The original note was vague about how the reference achieves 22.1%
  missing vs BDC's 40.9%. Verified against the public DCC harmonization algorithm
  (GitHub UW-GAC repo) that FHS CABG, PAD, and Angina all use the same
  surveillance/event adjudication architecture (pht000389/pht000309 + pht003316
  denominator booster). This same pattern explains the coverage gaps for all three
  FHS atherosclerosis-prior variables.
- **Cohorts affected**: FHS only. Other cohorts' CABG notes already had sufficient
  specificity.

## 2026-04-06

### `match_quality_table.py` — Refresh all 8 FHS per-variable methodological notes

- **What changed**: Updated all 8 FHS entries in `KNOWN_METHODOLOGICAL_DIFFS` to
  reflect the current extract (bdc_fhs_summary_20260407_012046.json). Specific changes:
  1. **total_cholesterol_1**: Code `ASSAY_ERA_DIFF` -> `VISIT_SCOPE_DIFF`. Old note
     claimed BDC N=13,009 / mean 200.9 / +6.67 mg/dL delta; actual is N=9,917 /
     mean 194.48 / +0.25 mg/dL. The assay era concern is resolved after baseline
     visit filtering fixes.
  2. **triglycerides_1**: Code `ASSAY_ERA_DIFF` -> `VISIT_SCOPE_DIFF`. Old note
     claimed BDC N=12,705 / mean 113.1 / +5.78 mg/dL delta; actual is N=9,915 /
     mean 108.68 / +1.40 mg/dL. Same resolution as TC.
  3. **cabg_prior_1**: Rewrote to reflect Procedure->Condition entity rewrite,
     CONDITION_PROCEDURE_VISIT_OVERRIDE (Exam 21/Exam 5), and actual 40.9% missing
     (old note predicted ~22%).
  4. **hispanic_or_latino_1**: Code `AGGREGATION_DIFF` -> `EXTENDED_COVERAGE`. Old
     note claimed BDC N=7,670 / 49.3% missing; actual is N=15,086 / 0.0% missing.
     Completely rewritten to reflect current all-sub-cohort coverage.
  5. **height_baseline_1**: Updated numbers: old claimed BDC N=15,089 / gap=66 /
     delta=+0.299 cm; actual is BDC N=14,409 / gap=732 / delta=+0.12 cm.
  6. **antihypertensive_meds_1**: Removed "in this session (Fix 22)" and "may
     narrow after pipeline re-run" language. Numbers unchanged (still accurate).
  7. **current_smoker_baseline_1**: Old note claimed reference N=12,679; actual is
     N=15,100. Added current BDC result (N=15,039, +-0.3pp). Removed "Fix 23"
     session-specific language.
  8. **ever_smoker_baseline_1**: Same updates as current smoker. Added current
     result (N=15,039, +-0.6pp).
- **Why**: Notes were written against pre-fix extracts from earlier sessions.
  BASELINE_VISIT_CONFIG tightening, entity type rewrites, visit overrides, and
  shareid fixes have materially changed the numbers. Stale notes would mislead
  reviewers.
- **Cohorts affected**: FHS only.

### `extract_bdc_all.py` — Add PAD visit override for FHS

- **What changed**: Added `pad_prior_1` entry to `CONDITION_PROCEDURE_VISIT_OVERRIDE`.
  FHS PAD now routes Offspring to Exam 5 (instead of standard baseline Exam 1),
  alongside all other subcohort Exam 1 visits.  Original Exam 4 is included for
  the pht000309 joins block rows.
- **Why**: FHS pad.yaml was rewritten to use Offspring Exam 5 (pht000034, CDI-PVD)
  instead of the non-functional Offspring Exam 8 block (pht000747 — "FHS OFFSPRING
  EXAM 8" visit label doesn't exist in pipeline output).  The standard baseline
  config only matches Exam 1, so Exam 5 rows would be filtered out without this
  override.
- **Cohorts affected**: FHS only.

### `extract_bdc_all.py` — Fix procedure override clobbering valid condition data

- **What changed**: In `process_procedures()`, the L-6 guard that checks whether
  conditions already set meaningful data for a `topmed_var` used
  `existing.get("n", 0)` — but `categorical_stats()` returns `n_total`/`n_valid`,
  not `n`. The lookup always returned 0, making `existing_n = 0 - n_missing`
  negative, causing procedures to override valid condition results. Fixed to
  `existing.get("n_valid", existing.get("n_total", 0) - existing.get("n_missing", 0))`.
- **Why**: After FHS hist_cor_bypg.yaml was rewritten from Procedure to Condition
  entity, the condition loop correctly found 4,338 respondents and 11 positive
  CABG cases. But the procedure loop's override check saw "0 data" due to the
  wrong dict key and replaced the valid result with 0 Procedure rows.
- **Cohorts affected**: Any cohort whose CABG/angioplasty is mapped as Condition
  entity (currently FHS, MESA). Previously masked because FHS used Procedure
  entity and MESA conditions had no procedure fallback triggered.

### `extract_bdc_all.py` — Add CONDITION_PROCEDURE_VISIT_OVERRIDE for CABG

- **What changed**: Added `CONDITION_PROCEDURE_VISIT_OVERRIDE` dict after
  `SMOKING_VISIT_OVERRIDE`. Maps `topmed_var` -> `cohort` -> list of visit labels
  for condition/procedure variables that require non-baseline visit filtering.
  Wired the override into both `process_conditions()` and `process_procedures()`
  per-variable loops: when a topmed_var has a cohort override, the code re-filters
  from all-visits `df` using override visits instead of the global `baseline_df`.
  Initial entry: `cabg_prior_1` for FHS, routing to Exam 21 (Original), Exam 5
  (Offspring), and Exam 1 for Gen3/Omni1/Omni2/NOS. Updated same day from
  Exam 28/Exam 7 to Exam 21/Exam 5 (earliest exams with cumulative CABG
  history question) for maximum participant coverage (~8,853 vs ~4,338).
- **Why**: FHS hist_cor_bypg.yaml maps CABG to the earliest exam per subcohort
  that includes a cumulative CABG history question (Original Exam 21, Offspring
  Exam 5, Gen3 Exam 1). The standard BASELINE_VISIT_CONFIG (Original Exam 4,
  others Exam 1) filtered out all CABG data since those exams predate CABG
  questions. The override allows the extract to pick up the correct exam rows.
- **Cohorts affected**: FHS only.

### `extract_bdc_all.py` — Add SMOKING_VISIT_OVERRIDE for FHS

- **What changed**: Added `SMOKING_VISIT_OVERRIDE` dict near `BASELINE_VISIT_CONFIG`.
  For FHS, overrides smoking baseline to Exam 1 for all sub-cohorts (instead of
  Exam 4 for Original). Wired the override into the `process_observations()`
  smoking section via the existing `override_visits` parameter on
  `_select_baseline_visit()`.
- **Why**: FHS Original's MF71 (phv00000543, pht000009) at Exam 1 has full
  tripartite smoking coding (Current/Former/Never). The pht007777 CURRSMK fields
  at Exam 4 are binary (current yes/no) — mapping CURRSMK=0 to any single status
  is factually wrong for ~35-40% of those participants (former smokers miscoded as
  Never). Using Exam 1 MF71 matches the DCC approach and recovers both N coverage
  and proportional accuracy.
- **Cohorts affected**: FHS only.

### `match_quality_table.py` — Consolidate MESA CVD history notes into cohort-level note

- **What changed**: Removed all 4 per-variable CVD history notes (angina_prior_1, mi_prior_1, pad_prior_1, cabg_prior_1) from `KNOWN_METHODOLOGICAL_DIFFS`. Updated the MESA `COHORT_LEVEL_NOTES` entry to cover MI, Angina, and CABG (removed PAD — same T_N/B_N, no actual source difference). Cohort-level note code: `CVD_HISTORY_SOURCE_DIFF`.
- **Why**: Per-variable notes were redundant with the cohort-level explanation. PAD had identical N on both sides (6,429) so the "source diff" code was misleading.
- **Cohorts affected**: MESA only. Total per-variable entries reduced from 63 to 59.

### `match_quality_table.py` — Remove 11 non-core and stale M-notes (ARIC, MESA, FHS)

- **What changed**: Removed 11 `KNOWN_METHODOLOGICAL_DIFFS` entries that are either for non-core variables (not in the 19 core variable set) or stale/obsolete:
  - **ARIC (4 non-core)**: `coronary_angioplasty_prior_1`, `carotid_plaque_1`, `carotid_imt_1`, `ldl_1`
  - **MESA (5)**: `carotid_plaque_1` (non-core), `cimt_1` (non-core), `rbc_ncnc_bld_1` (non-core), `bmi_baseline_1` (core but stale -- claimed 4,270 spirometry-only coverage when bmi.yaml actually sources from 8 tables with full 8,262 coverage), `antihypertensive_meds_1` (core but stale -- claimed visit labels prevent baseline filtering when extract log shows 39.9% rate matching reference 39.2%)
  - **FHS (2 non-core)**: `hdl_1`, `mch_1`
- **Why**: Notes for non-core variables add noise to the default core-only output and are not part of the validated 19-variable comparison scope. Two MESA core-variable notes were factually wrong based on current pipeline state.
- **Cohorts affected**: ARIC, MESA, FHS. Total entries reduced from 74 to 63.

### `match_quality_table.py` — FHS: Updated Race, Ethnicity, Smoking notes + version diff cohort note

- **What changed**:
  1. **Race note** (`FHS`, `race_us_1`): Enhanced with specific reference details -- reference uses only pht006005 and ran on 3 sub-studies (Original, Offspring, Gen3), excluding Omni 1, Omni 2, NOS. Updated BDC N from 15,089 to 14,892 (1.3% missing). Added detail about code 88 imputed-race handling.
  2. **Ethnicity note** (`FHS`, `hispanic_or_latino_1`): Rewrote with specific reference phenotype definition (ethnicity_1.json uses RACE_CODE from pht006005, ran only on Offspring and Gen3). Added precise BDC N=7,670 vs reference N=6,665. Removed reference to Fix 18 (no longer relevant context).
  3. **Smoking notes** (`FHS`, `current_smoker_baseline_1` and `ever_smoker_baseline_1`): Updated to reflect Fix 23 as APPLIED (was described as pending). Changed wording from "means current BDC output is not reliable" to "participant UUIDs now resolve correctly, recovering ~5,079 Original cohort records".
  4. **Cohort-level note** (`FHS`): Added new `VERSION_MISMATCH` entry documenting the 84-participant gap (15,173 reference vs 15,089 BDC) caused by consent withdrawals between the ~2020 reference snapshot and v35 (released 2025-07-25). Confirmed via dbGaP study page and pht003099.v10 var_report (7,023 M + 8,066 F = 15,089).
- **Why**: Race/Ethnicity notes lacked specific reference phenotype definition details. Smoking notes still described the IDTYPE bug as unfixed. No cohort-level note existed to explain the systematic 84-participant N gap.
- **Cohorts affected**: FHS only.

## 2026-04-05

### `match_quality_table.py` — JHS: Remove 13 redundant per-variable notes

- **What changed**: Removed the `_JHS_UNIVERSE_DIFF_ONLY` list (13 variables), `_JHS_UNIVERSE_DIFF_NOTE` shared dict, and the loop that injected them into `KNOWN_METHODOLOGICAL_DIFFS`. These 13 A/A+ grade variables (Sex, Race, Height, Body weight, BMI, SBP, DBP, Current smoker, Ever smoker, Platelet count, MCH, History of MI, CABG) no longer have per-variable notes. The cohort-level `PARTICIPANT_UNIVERSE_DIFF` note fully explains their comparison differences. The 4 JHS variables with variable-specific explanations (antihypertensive_meds_1, total_cholesterol_1, triglycerides_1, pad_prior_1) remain unchanged.
- **Why**: The per-variable notes for these 13 all just said "see cohort-level note" — redundant now that the cohort-level note provides the full explanation with dbGaP evidence (genetic consent filtering, GapExchange citation, SUBJECT_SOURCE2 = JHS_CARe).
- **Cohorts affected**: JHS only.

### `match_quality_table.py` — JHS: Refine root cause to genetic consent filtering (suspected)

- **What changed**: Updated the JHS `COHORT_LEVEL_NOTES` entry and `_JHS_UNIVERSE_DIFF_NOTE` shared per-variable note to reflect new evidence from dbGaP metadata investigation. The primary suspected cause is now **genetic consent filtering** rather than the previous three equal-weight causes. Evidence: (1) v7 GapExchange study description states "approximately 3,600 gave consent that allows genetic research", matching TOPMed's N=3,602; (2) `SUBJECT_SOURCE2` variable in JHS_Subject (pht001920) shows N=3,596 sourced to "JHS_CARe" genotyping pipeline. Version diff and harmonization date retained as secondary factors. Language uses "suspected" / "appears to be" since we lack direct v5 participant counts.
- **Why**: Previous note listed three causes as equally weighted. The dbGaP metadata investigation (GapExchange XML, JHS_Subject var_report) provides strong circumstantial evidence that genetic consent filtering is the dominant factor, but we cannot confirm with 100% certainty without v5 data.
- **Cohorts affected**: JHS only.

### `match_quality_table.py` — JHS: Consolidate 13 universe-diff-only notes into shared entry

- **What changed**: Replaced 13 individual JHS `KNOWN_METHODOLOGICAL_DIFFS` entries (annotated_sex_1, bmi_baseline_1, bp_diastolic_1, bp_systolic_1, cabg_prior_1, current_smoker_baseline_1, ever_smoker_baseline_1, height_baseline_1, mch_entmass_rbc_1, mi_prior_1, platelet_ncnc_bld_1, race_us_1, weight_baseline_1) with a single `_JHS_UNIVERSE_DIFF_ONLY` list and shared `_JHS_UNIVERSE_DIFF_NOTE` dict, populated via loop after the main dict. Kept 4 variable-specific entries inline (pad_prior_1, antihypertensive_meds_1, total_cholesterol_1, triglycerides_1) because they have additional explanations beyond the participant universe difference (different source methodology, closed-world artifacts, B/C-grade mean shifts). Condensed the JHS comment block to reference the consolidated approach.
- **Why**: The 13 removed entries all had identical causal explanations (participant universe diff only). Consolidating eliminates ~200 lines of duplicate note text and makes the JHS section easier to maintain.
- **Cohorts affected**: JHS only.

### `match_quality_table.py` — JHS: Reclassify all 17 per-variable notes from AGGREGATION_DIFF to PARTICIPANT_UNIVERSE_DIFF

- **What changed**: Changed `"code"` from `"AGGREGATION_DIFF"` to `"PARTICIPANT_UNIVERSE_DIFF"` for all 17 JHS entries in `KNOWN_METHODOLOGICAL_DIFFS` (annotated_sex_1, bmi_baseline_1, bp_diastolic_1, bp_systolic_1, cabg_prior_1, height_baseline_1, mch_entmass_rbc_1, mi_prior_1, pad_prior_1, platelet_ncnc_bld_1, race_us_1, weight_baseline_1, current_smoker_baseline_1, ever_smoker_baseline_1, antihypertensive_meds_1, total_cholesterol_1, triglycerides_1). Rewrote the JHS General Pattern comment block from "multi-exam aggregation artifact" to "participant universe difference". Updated all per-variable note text to remove incorrect "multi-exam union", "non-baseline visit", and "union-of-visits" language; notes now reference the cohort-level PARTICIPANT_UNIVERSE_DIFF note for the structural explanation.
- **Why**: Extract log review confirmed ALL BDC JHS measurements are correctly filtered to "JHS Exam 1" only. The consistent +281 to +369 N surplus is NOT from multi-exam aggregation — it's from dbGaP version diff (v5 vs v7), genotype selection (sequenced subset vs full phenotype population), and harmonization date (2020 vs 2026). The earlier AGGREGATION_DIFF characterization was incorrect and misleading.
- **Cohorts affected**: JHS only.

### `match_quality_table.py` — JHS: Add PARTICIPANT_UNIVERSE_DIFF cohort-level note

- **What changed**: Added `"JHS"` entry to `COHORT_LEVEL_NOTES` with code `PARTICIPANT_UNIVERSE_DIFF`.
- **Why**: Investigation revealed BDC N=3,883 vs TOPMed N=3,602 (+281, +7.8%) is NOT a multi-exam aggregation artifact. Extract logs confirm all BDC measurements are correctly filtered to "JHS Exam 1" only. The surplus has three causes: (1) dbGaP version difference (TOPMed from v5, BDC from v7), (2) TOPMed harmonized only the genotype-sequenced subset while BDC covers the full phenotype-consented population across 4 consent groups (c1=878, c2=201, c3=2,289, c4=515), (3) harmonization date difference (TOPMed frozen 2020-05-21 vs BDC April 2026). This corrects the earlier mischaracterization that the N delta was from multi-exam union leaking non-baseline data.
- **Cohorts affected**: JHS only.

### `match_quality_table.py` — Clinical domain grouping for core variables

- **What changed**: Replaced flat `CORE_VARIABLES` frozenset with `CORE_VARIABLE_GROUPS` ordered list of (group_name, [vars]) tuples. Core mode output now displays variables grouped by clinical domain (Demographics, Anthropometrics, Blood Pressure, Smoking, Lipids, CBC, CVD History) with `--- Group Name ---` separator lines. `--all-vars` mode remains alphabetical with no group headers.
- **Why**: Alphabetical sorting mixed unrelated domains together (e.g., Angina next to BMI). Grouping by clinical domain makes the table easier to scan and review.
- **Impact**: All cohorts. Output format change only — no grading or logic changes. `CORE_VARIABLES` frozenset is now derived from the groups, so membership is identical.

### `match_quality_table.py` — MESA mi_prior_1: Update KNOWN_METHODOLOGICAL_DIFFS after CHR fix

- **What changed**: Updated `("MESA", "mi_prior_1")` entry. Changed code from
  `UNION_OF_FORMS` to `SOURCE_CORRECTION`. Rewrote note to reflect the 4 removed
  blocks and corrected numbers.
- **Why**: CHR deep investigation (2026-04-05) found 4 incorrect source blocks in
  `hist_my_inf.yaml`: (1) pht001116 major21 = ECG Q-wave surrogate, not personal
  MI history; (2) pht001117 fhxmi2 = family-member MI history misattributed as
  ONESELF (multi-row table, 51,207 obs); (3) pht001122 Family Spiro ECG = same
  ECG surrogate; (4) pht003091 Exam5 ECG = same ECG surrogate. Also removed
  `'0': ABSENT` from 2 spirometry blocks (screening safety question != lifetime
  MI history). Previous note claimed 198 positives from pht001116 "self-reported
  prior MI" -- this was wrong (pht001116 was ECG data). Corrected to 51 genuine
  positives from 3 remaining blocks (~80% missing, honest and expected).
- **Cohorts affected**: MESA only.

### `match_quality_table.py` — COPDGene: Add SIMPLE_STRUCTURE cohort-level note

- **What changed**: Added `"COPDGENE"` entry to `COHORT_LEVEL_NOTES` dict with
  code `SIMPLE_STRUCTURE`.
- **Why**: Documents why COPDGene achieves 15/15 A+ -- single-table architecture
  (pht002239, ~1,003 vars), flat visit structure (one cross-sectional P1 visit),
  no sub-cohort complexity, and pre-derived variables. Provides context for
  cross-cohort comparison readers.
- **Cohorts affected**: COPDGene only.

---

## 2026-04-04

### `extract_bdc_all.py` — CARDIA BASELINE_VISIT_CONFIG: Remove "CARDIA EXAM 0" workaround

- **What changed**: Removed `"CARDIA EXAM 0"` from the CARDIA `exact` list in
  `BASELINE_VISIT_CONFIG`. Updated the comment and tightened the regex pattern
  from `r"(?i)CARDIA\s+(YEAR|EXAM)\s+0$"` to `r"(?i)CARDIA\s+YEAR\s+0$"`.
- **Why**: "CARDIA EXAM 0" was a non-canonical visit label introduced by a YAML
  authoring error in the HV repo (pht001557/A4CHEM-sourced blocks in `albumin_bld.yaml`,
  `ast_sgot.yaml`, `bilirubin_tot.yaml`, `glucose_bld.yaml`, `cig_smok.yaml`,
  `demography.yaml`, and the Visit entity in `visit.yaml`). CARDIA uses "Year"
  numbering exclusively — the baseline is "YEAR 0" in all dbGaP data dictionaries.
  The HV YAML fix (fix/cardia-chr-20260330 Fix 20, 2026-04-04) renamed all 8
  occurrences to "CARDIA YEAR 0". The `BASELINE_VISIT_CONFIG` workaround entry
  is no longer needed.
- **Cohorts affected**: CARDIA only.

---

## 2026-04-23

### `match_quality_table.py` — ARIC: 4 new KNOWN_METHODOLOGICAL_DIFFS entries for D-grade variables

- **`("ARIC", "coronary_angioplasty_prior_1")` — CONFIRMED_BUG_FIXED**: Documents
  the root cause and fix for the D-grade angioplasty inversion bug.
  `hist_cor_angio.yaml` was missing `procedure_status` in all 7 blocks, causing
  null procedure_status rows to be filtered out by the extractor's
  `_proc_status.isin()` guard when `hist_cor_bypg.yaml` (CABG) activated
  `has_proc_status=True`. Result: 96 true "Prior History" cases labeled as
  "No Prior History". Fix applied to `hist_cor_angio.yaml` — all blocks now use
  hardcoded `procedure_concept: value: OMOP:4184832` + `procedure_status:
  Y: PRESENT, N: ABSENT`. Re-extraction needed to confirm grade improvement.
- **`("ARIC", "carotid_plaque_1")` — COMPARISON_ARTIFACT**: D grade is spurious.
  BDC produces text labels ("No Prior History"/"Prior History") while reference
  uses numeric labels ("0"/"1"). Max category delta of 66.5pp is an artifact of
  label mismatch; true distribution difference is ~2pp (33.5% vs 35.5% Prior
  History). YAML is correct.
- **`("ARIC", "carotid_imt_1")` — VISIT_SCOPE_DIFF**: BDC captures 4,912 valid
  CIMT values (67.4% missing) at ARIC EXAM 1 only. Reference has 14,151 valid
  (5.9%) — ARIC began primary CIMT measurement at Exam 2/3. Means are virtually
  identical (+0.004 mm). Same policy issue as mch_entmass_rbc_1. Potential fix:
  visit_override to include Exam 2/3.
- **`("ARIC", "ldl_1")` — SOURCE_TABLE_DIFF**: BDC ldl.yaml includes
  pht012511/phv00507552 (LIPF4b, "LDL Cholesterol Calculated [Lipid Lab, LIPF]")
  alongside pht012853/phv00519834 (LDL_V1 = ldl02 from derived data set).
  Reference uses DERIVE13/pht004063/phv00204764 (LDL02 recalibrated) only.
  LIPF4b systematic underestimation pulls BDC mean to 131.84 vs reference 137.80
  mg/dL (-5.96 delta, D grade). Recommended fix: remove pht012511 from ldl.yaml
  EXAM 1 blocks; use pht012853 only (or add pht004063 directly as
  tot_chol_bld.yaml does).

## 2026-04-04

### `match_quality_table.py` — Bulk enable real grades for all 38 M-grade entries

- **Added `"no_override": True`** to all 38 `KNOWN_METHODOLOGICAL_DIFFS` entries
  that previously had no `no_override` key and therefore defaulted to displaying
  grade `M` (methodological override). All entries now show their real computed
  grade with a `*` annotation instead of the flat `M` placeholder.
- **Affected cohorts / variables (38 total)**:
  - WHI: `antihypertensive_meds_1`
  - ARIC: `antihypertensive_meds_1`, `mch_entmass_rbc_1`, `pad_prior_1`,
    `hispanic_or_latino_1`, `angina_prior_1`
  - MESA: `hispanic_or_latino_1`, `angina_prior_1`, `mi_prior_1`, `pad_prior_1`,
    `cabg_prior_1`, `carotid_plaque_1`, `bmi_baseline_1`, `antihypertensive_meds_1`,
    `cimt_1`, `platelet_ncnc_bld_1`, `rbc_ncnc_bld_1`
  - FHS: `hdl_1`, `total_cholesterol_1`, `triglycerides_1`, `cabg_prior_1`,
    `hispanic_or_latino_1`, `race_us_1`, `mch_1`, `height_baseline_1`,
    `antihypertensive_meds_1`, `current_smoker_baseline_1`, `ever_smoker_baseline_1`
  - JHS: `pad_prior_1`, `current_smoker_baseline_1`, `ever_smoker_baseline_1`,
    `antihypertensive_meds_1`, `mi_prior_1`, `bp_systolic_1`, `total_cholesterol_1`,
    `triglycerides_1`
  - HCHS-SOL: `race_us_1`, `antihypertensive_meds_1`
- **M-grade infrastructure preserved**: The `no_override` check in `run()` and the
  `'M'` display path remain intact so individual entries can be reverted to M by
  removing their `no_override` key.
- **Verified**: `audit_no_override.py` confirms 87/87 entries now have `no_override`;
  0 entries remain in M-grade-default state.

### `match_quality_table.py` — Sort table rows by displayed variable name (bdc_label)

- **Sort fix**: `matched` list was sorted by internal dict key (e.g., `bmi_baseline_1`),
  but the table displays `bdc_label` (e.g., "Body Mass Index"). Changed sort key to
  `tv[v].get('bdc_label', v).lower()` in both `--all-vars` and default (core-only) paths
  so the Variable column is always in alphabetical order by the name shown.

## 2026-04-04

### `match_quality_table.py` — HCHS-SOL: cohort-level VERSION_MISMATCH note

- **Added `COHORT_LEVEL_NOTES` dict** — a new top-level dict for cohort-level
  methodological observations that are not tied to a single variable. Includes a
  corresponding print block in the footer of `run()`.
- **HCHS-SOL `VERSION_MISMATCH` entry**: Documents the root cause of all N
  differences between TOPMed (N=12,895) and BDC (N=11,831). TOPMed's files were
  produced from phs000810.**v1**.p1 (snapshot 2020-05-21; c1=3,681, c2=9,214).
  BDC operates on phs000810.**v2**.p2 (12,121 consented; c1=2,304, c2=9,817).
  The 1,064-subject gap breaks down as: 774 consent reclassification/removal
  between v1→v2, plus 290 v2 consented subjects with no rows in pht004715. Not
  a pipeline error — structural and expected.

### `match_quality_table.py` — ARIC: 13 methodological notes for all remaining matched variables

- **Added `KNOWN_METHODOLOGICAL_DIFFS` entries for all 13 ARIC matched variables
  that previously had no note** (all `no_override: True` — computed A/A+ grades
  preserved; notes appear as `*` annotations):
  - `bmi_baseline_1` [CONSERVATIVE_DERIVATION]: BDC uses DERIVE13 BMI01
    (phv00204719, pht004063), the study's official derived Exam 1 BMI. 14,452
    valid (4.1% missing) vs reference 14,915 (0.9%); 463-record gap likely from
    participants excluded from DERIVE13 despite having raw height/weight. Means
    essentially identical (+0.07 kg/m2). BDC is equivalent in accuracy, slightly
    less complete in coverage.
  - `bp_diastolic_1` [EXTENDED_COVERAGE]: BDC 15,050 valid (0.1% miss) vs
    reference 14,926 (0.8% miss). Means identical to 5 sig figs (73.71 mmHg).
    BDC has broader Exam 1 source coverage. BDC is better coverage.
  - `bp_systolic_1` [EXTENDED_COVERAGE]: Same pattern as diastolic. BDC 15,050
    valid (0.1% miss); means effectively identical (121.49 vs 121.44 mmHg, +0.04).
  - `cabg_prior_1` [EXTENDED_COVERAGE]: BDC 15,060 valid (0.1% miss) vs reference
    14,817 (1.5% miss). Distribution IDENTICAL at 0.0pp (98.4%/1.6%). BDC better
    coverage with same accuracy.
  - `current_smoker_baseline_1` [EXTENDED_COVERAGE]: BDC 15,064 valid (0.0% miss)
    vs reference 14,926 (0.8% miss). Max 0.1pp distribution difference. BDC better.
  - `ever_smoker_baseline_1` [EXTENDED_COVERAGE]: BDC 15,064 valid (0.0% miss) vs
    reference 14,930 (0.8% miss). Max 0.1pp difference. BDC better.
  - `height_baseline_1` [EXTENDED_COVERAGE]: BDC 15,045 valid (0.2% miss) vs
    reference 14,921 (0.8% miss). Means -0.05 cm. BDC better coverage.
  - `mi_prior_1` [UNION_OF_FORMS]: BDC unions 18 source tables (Exams 1-7, Death
    Event, AFQ, Cohort, Hospital Form), achieving 0% missing (15,067). Reference
    uses single DERIVE13 variable (14,717 valid, 2.2% missing). BDC prevalence
    5.2% vs reference 4.4% (0.8pp); hospital/death records capture incident MI
    retrospectively coded as prior history. BDC is more complete; 0.8pp inflation
    from multi-form union is a known trade-off.
  - `platelet_ncnc_bld_1` [EXAM_COMPOSITION]: Both pipelines effectively source
    from Exam 1 CBC (pht004107). BDC 14,808 vs reference 14,815 (7-record
    difference); means 257.76 vs 257.57 K/uL (+0.19). Near-perfect match; BDC
    and reference are equivalent.
  - `race_us_1` [BROADER_CLASSIFICATION]: BDC captures AIAN (n=15), Asian (n=28),
    Other (n=1) beyond the binary Black/White reference mapping. The 44 additional
    participants reduce White percentage from 73.9% to 73.4% (0.5pp). BDC is more
    accurate to actual population composition.
  - `total_cholesterol_1` [EXTENDED_COVERAGE]: BDC 14,873 valid (1.3% miss) vs
    reference 14,705 (2.3% miss). Means -0.17 mg/dL. BDC covers multiple lipid
    tables (pht004063/4064/4121/6444/12504+). Better coverage, equivalent accuracy.
  - `triglycerides_1` [EXTENDED_COVERAGE]: Same pattern as cholesterol. BDC 14,875
    valid (1.3% miss) vs reference 14,707 (2.2% miss). Means -0.04 mg/dL.
  - `weight_baseline_1` [EXTENDED_COVERAGE]: BDC 15,039 valid (0.2% miss) vs
    reference 14,915 (0.9% miss). Means -0.01 kg (lbs-to-kg conversion in
    bdy_wgt.yaml). Better coverage, equivalent accuracy.
  - **Affects**: ARIC only.

### `match_quality_table.py` — CHS ever_smoker_baseline_1: M -> B* (no_override)

- **Changed `("CHS", "ever_smoker_baseline_1")` to `no_override: True`**:
  - Grade was forced to M; now allows computed grade (B*) to display
  - B* reflects the 1.9pp structural difference caused by the reference
    reconstructing from raw fields vs BDC using the study-team curated EVERSM
    variable — the discrepancy is methodological (BDC is correct), not a pipeline
    error, so the computed grade is more informative than a forced M
  - Note unchanged: still documents EVERSM authoritativeness vs rowSums heuristic
  - **Affects**: CHS only.

### `match_quality_table.py` — CHS 6 additional variable methodological notes

- **Added KNOWN_METHODOLOGICAL_DIFFS entries for 6 CHS A+ variables**
  (all `no_override: True` — A+ grades preserved, notes appear as `A+*`):
  - `bmi_baseline_1` [AGGREGATION_DIFF]: Both BDC and reference use BASEBOTH
    pre-computed BMI (phv00100386, n=5,513, nulls=18). The +0.0014 kg/m2 delta
    is a floating-point precision artifact from decimal representation; same N
    and missing%. Approach: identical.
  - `bp_systolic_1` [AGGREGATION_DIFF]: BDC output (n=5,522, miss=9) exactly
    matches BASEBOTH AVZMSYS (phv00100435). Reference has n=5,515, miss=16 — 7
    fewer valid, likely from physiological QC exclusions BDC does not apply.
    +0.05 mmHg delta across 21.88 SD = 0.002 normalized. BDC more complete.
  - `bp_diastolic_1` [AGGREGATION_DIFF]: BDC output (n=5,516, miss=15) exactly
    matches BASEBOTH AVZMDIA (phv00100436). Reference has n=5,515, miss=16 — 1
    fewer valid. BDC extract flags 12 implausible DBP=0.0 mmHg values; reference
    likely excludes these, explaining the N and mean delta. Reference is more
    clinically correct for excluding implausibles; BDC should apply DBP > 0 QC.
  - `cabg_prior_1` [AGGREGATION_DIFF]: Two differences: (1) BDC defaults
    no-record participants to No (miss=0 vs reference miss=38); reference
    preserves 38 genuine unknowns from BPSSUR null. (2) BDC baseline=218 (3.9%)
    vs reference=236 (4.3%) — 18 CABG cases in EVENT_SUMMARY excluded by BDC's
    baseline-visit filter. Reference is more accurate on both dimensions.
  - `current_smoker_baseline_1` [AGGREGATION_DIFF]: BDC uses CHS study-team
    curated SMOKE variable (BASE1 phv00099445 + YR5NEW phv00105886 = exact
    BASEBOTH match, n=5,525, miss=6). Reference reconstructs from raw SMOKE101/
    SMOKE201 fields, leaving 28 more participants as missing (n=5,497, miss=34).
    BDC approach is more authoritative (study-team adjudication).
  - `weight_baseline_1` [AGGREGATION_DIFF]: Reference uses BASEBOTH WEIGHT13
    (phv00100383, n=5,514, miss=17). BDC fills the 17 missing using BASE1
    fallbacks including WGT5008 "usual weight at age 50" (self-reported
    retrospective), resulting in n=5,531, miss=0. The +0.003 kg delta is from
    these 17 fill-in values. Reference is cleaner (measured only); BDC more
    complete but mixes measured and self-reported for 17 participants.
  - **Affects**: CHS only.

### `extract_bdc_all.py` — Per-variable visit override mechanism (ARIC MCH)

- **New feature: `visit_override` key in `BDC_MEASUREMENT_MAP` spec dicts**.
  Allows a variable to use a different set of visit labels than the cohort-wide
  `BASELINE_VISIT_CONFIG`, without affecting any other variable in the same cohort.

  Implementation:
  - `_select_baseline_visit()`: added `override_visits: list[str] | None = None`
    parameter. When provided, the function bypasses `BASELINE_VISIT_CONFIG`
    entirely and matches case-insensitively against the override list. Raises
    `ValueError` if no override visits are found in the data (same SKIP behavior
    as a config miss).
  - `process_measurements()`: extracts `spec.get("visit_override", {}).get(cohort)`
    before calling `_select_baseline_visit()` and passes it as `override_visits`.
  - `BDC_MEASUREMENT_MAP["OBA:2045301"]` (MCH): added
    `"visit_override": {"ARIC": ["ARIC EXAM 3", "ARIC EXAM 4", "ARIC EXAM 5"]}`.
    ARIC never ran CBC at Exams 1/2; this matches the TOPMed DCC's own
    "first available" convention for ARIC MCH. The override applies only to ARIC;
    all other cohorts continue to use `BASELINE_VISIT_CONFIG` for MCH.

  **Affects**: ARIC `mch_entmass_rbc_1` only. All other cohorts and all other
  ARIC variables are unaffected.

### `match_quality_table.py` — CHS hypertension treatment methodological note

- **Added KNOWN_METHODOLOGICAL_DIFFS entry for CHS `antihypertensive_meds_1`**
  (`no_override: True` — A grade preserved, note appears as `A*` annotation):
  - `antihypertensive_meds_1` [AGGREGATION_DIFF]: BDC sources from two baseline
    tables — pht001450 BASE1 (phv00099656, original 1989 cohort only, N=4,900)
    and pht001452 BASEBOTH (phv00100595, both cohorts merged, N=5,526). The
    reference extract uses BASEBOTH only (the CHS study team's authoritative
    merged baseline), exactly matching the BASEBOTH var_report (Yes=2,634 /
    No=2,892 / missing=5). BDC's union of both tables inflates Yes count by ~36
    and eliminates the 5 missing values because BASE1 and BASEBOTH partially
    overlap for original-cohort participants. Gap: 0.6pp (ref 47.7% vs BDC 48.3%).
    The reference approach is cleaner; the dual-source BDC approach is a minor
    over-count but not a clinical error. Grade kept at A.
  - **Affects**: CHS only.

### `match_quality_table.py` — ARIC angina and MCH note updates

- **Updated `("ARIC", "angina_prior_1")` entry in `KNOWN_METHODOLOGICAL_DIFFS`**:
  - Changed `code` from `STUDY_DESIGN` to `DATA_QUALITY_FLAG` (new code type,
    not a known methodology difference but a suspected data quality problem).
  - Expanded note to explicitly document: (1) TOPMed DCC excluded this variable
    from ARIC harmonization; (2) BDC maps it from DERIVE13 RANGNA01,
    phv00204724, value_mapping '1'=ABSENT / '4'=PRESENT per data dictionary;
    (3) the resulting 94.5% PRESENT prevalence is biologically impossible for
    Rose Angina (~3-7% expected); (4) an archived YAML version used '0'=ABSENT /
    '1'=PRESENT, suggesting the actual data file may store 0/1 rather than 1/4;
    (5) explicit recommendation not to use this variable in analysis until the
    encoding is verified against the actual DERIVE13 data file.
  - **Affects**: ARIC only.

- **Updated `("ARIC", "mch_entmass_rbc_1")` entry in `KNOWN_METHODOLOGICAL_DIFFS`** (revised):
  - Code changed from `VISIT_SCOPE_DIFF` to `BASELINE_DEFINITION_DIFF`.
  - Note rewritten to clarify that the extractor SKIP is intentional and correct
    under our comparison philosophy (Exam 1 = ARIC baseline; no Exam 1 CBC = no
    comparable baseline measurement). The TOPMed DCC used a different definition
    for CBC variables: "earliest exam where variable was ever measured" (= Exam 3,
    N=8,710). The two approaches are not directly comparable. The SKIP is not a bug
    to fix. Whether BDC should adopt TOPMed's "first available" convention for
    variables never measured at enrollment is a separate upstream policy decision.
  - **Affects**: ARIC only.

### `match_quality_table.py` — COPDGene BMI methodological note

- **Added KNOWN_METHODOLOGICAL_DIFFS entry for COPDGene `bmi_baseline_1`**
  (`no_override: True` — A+ grade preserved, note appears as `*` annotation):
  - `bmi_baseline_1` [DERIVED_VS_STORED]: BDC reads the pre-stored BMI field
    phv00159593 (pht002239), which the study pre-computed and rounded to 2 decimal
    places before dbGaP deposit (marked `<comment>calculated</comment>` in the data
    dict). The reference recomputes BMI at full float precision from Weight_KG
    (phv00159591) and Height_CM (phv00159592). The +0.01 kg/m2 mean delta
    (28.83 vs 28.82) is the accumulated rounding noise across 10,371 observations
    (~0.005/sqrt(N) per obs). N_valid identical (10,371); 0% missing difference.
    No data disagreement -- floating-point arithmetic artifact only.

### `match_quality_table.py` — CARDIA methodological notes

- **Added KNOWN_METHODOLOGICAL_DIFFS entries for 3 CARDIA variables**
  (all `no_override: True` — computed grades preserved, notes appear as `*` annotation):
  - `bmi_baseline_1` [DERIVED_VS_STORED]: BDC reads pre-stored A20BMI (phv00113661);
    reference recalculates from A20HGT/A20WGT raw fields — floating-point unit conversion
    produces +0.052 kg/m2 delta. Clinically negligible; neither approach is incorrect.
  - `current_smoker_baseline_1` [GATING_VARIABLE_DIFF]: BDC maps A01SMNOW directly
    (N_valid=3,621, 0.0% missing); reference gates on A01SM100 (100-cigarette threshold)
    first, yielding 62 missing (1.7%). Reference approach is epidemiologically standard.
  - `ever_smoker_baseline_1` [GATING_VARIABLE_DIFF]: BDC derives ever-smoker from SMNOW
    (former+current=Ever); reference uses A01SM100 directly as gate. Causes ~3-participant
    misclassification (SM100=Yes but SMNOW=0). BDC should use phv00112434 for ever_smoker.
  **Cohorts affected**: CARDIA.

### `mapping-quality-table.py` — A+ grade tier missing (bug fix)

- **Fixed A+ grade tier omission** in `mapping-quality-table.py`. The A+ tier
  was added to `batch_scorecard.py` but never applied to `mapping-quality-table.py`.
  Added A+ thresholds to `_grade_continuous` (norm_delta < 0.005 AND miss_diff < 1pp)
  and `_grade_categorical` (max_pct_diff < 0.5pp AND miss_diff < 1pp), updated
  `grade_counts` dict to include `"A+"` key, and updated grade summary printout.
  **Cohorts affected**: All (per-cohort table now correctly awards A+ for near-exact matches).

### `match_quality_table.py` + `batch_scorecard.py` — Replace M-grade with * annotation

- **Replaced M-grade override with `*` annotation** on computed grades.
  Previously, variables with known methodological differences were forced to
  grade M, hiding the actual statistical quality. Now the computed grade is
  kept (A+, A, B, C, D) and `*` is appended (e.g., `D*`, `A+*`) to flag
  the methodological note. Grade summary counts the base grade; a separate
  line shows how many `*`-annotated variables exist. This makes the true
  quality distribution visible while still flagging known differences.
  **Cohorts affected**: All (display change only, no data changes).

### `match_quality_table.py` + `batch_scorecard.py` — A+ grade tier

- **Added A+ (near-exact match) grade tier** to both per-cohort and batch
  grading scripts. Thresholds:
  - Continuous: norm_delta < 0.005 AND miss_diff < 1pp
  - Categorical: max_pct_diff < 0.5pp AND miss_diff < 1pp
  - Existing A/B/C/D thresholds unchanged
  - A+ counts toward A+B rate in batch scorecard
  - Grade summary display updated to show A+ column
  **Cohorts affected**: All (new grade category, no changes to existing grades).

### Cross-script fixes -- Batch 4 (Fourth Audit)

- **F-1 (MEDIUM): `batch_scorecard.py` — Added `no_override` guard** in
  `grade_variable()`. Previously unconditionally returned M-grade for any entry
  in `KNOWN_METHODOLOGICAL_DIFFS`, ignoring the `no_override` flag that
  `match_quality_table.py` respects. Now checks `if not entry.get('no_override')`
  before overriding to M, matching the canonical grading behavior.
  **Cohorts affected**: ARIC (`annotated_sex_1` has `no_override: True`).

- **F-2 (MEDIUM): `extract_topmed_all.py` — Fixed NaN sd for n_valid==1** in
  `continuous_stats()`. Same bug as BDC extractor Batch 3 F-3, never ported.
  Changed guard from `n_valid > 0` to `n_valid > 1`.
  **Cohorts affected**: Any cohort with single-observation TOPMed variables.

- **F-3 (LOW): `extract_topmed_all.py` — Added `pct_of_total` to
  `categorical_stats()`** distribution entries for schema parity with the BDC
  extractor (which added this in Batch 2 M-4).
  **Cohorts affected**: All (adds field to TOPMed JSON output).

- **F-4 (LOW): `extract_bdc_all.py` — Recalculated `pct_missing` after
  `n_total` override** in `process_demography()`. After `categorical_stats()`
  returns, `n_total` is overridden to `n_participants`, but `pct_missing` was
  still based on the original denominator. Now recalculated for sex, race,
  and ethnicity.
  **Cohorts affected**: All (corrects latent denominator inconsistency).

- **F-5 (INFO): `topmed_compare_config.py` — Fixed formatting** where `cd40_1`
  closing brace and `il18_1` opening were on the same line.
  **Cohorts affected**: None (formatting only).

- **F-6 (LOW): `validate_participant_completeness.py` — Replaced duplicated
  `_CANONICAL_ALIASES`** with import from `extract_bdc_all.COHORT_FOLDER_TO_CANONICAL`
  (inverted). Falls back to hardcoded map if import fails.
  **Cohorts affected**: None (same runtime aliases today).

- **F-7 (INFO): `mapping-quality-table.py` — Added deprecation banner**.
  Docstring and runtime `DeprecationWarning` directing users to
  `match_quality_table.py --cohort FHS` instead.
  **Cohorts affected**: FHS only (script is FHS-specific).

### `extract_bdc_all.py` — L-6 Guard Fix for CABG/Angioplasty (F-10)

- **F-10 (CRITICAL): L-6 guard now checks data before skipping** — The
  duplicate-variable guard between `process_conditions` and `process_procedures`
  previously skipped any `topmed_var` already in `variable_stats`, regardless of
  whether conditions found actual data. In 5 cohorts (ARIC, CHS, COPDGene, JHS,
  WHI), CABG (`OMOP:4336464`) is mapped as a **Procedure** entity, not a Condition.
  `process_conditions` found 0 rows for `OMOP:4336464` in `Condition.tsv` but still
  wrote a 0-affected/100%-missing entry. When `process_procedures` ran next, it found
  hundreds of thousands of rows in `Procedure.tsv` but the L-6 guard skipped it
  because the key already existed. Fix: guard now checks whether the existing entry
  has `n > n_missing` (i.e., real responses). If conditions wrote 0 data, procedures
  are allowed to override.
  **Cohorts affected**: ARIC (551K rows), CHS (22K), COPDGene (22K), JHS (90K),
  WHI (329K). Also fixes `coronary_angioplasty_prior_1` where present.
  MESA unaffected — uses Condition entity for CABG.

### `extract_bdc_all.py` — Resilient Baseline Visit Handling (F-5 through F-9)

- **F-5 (CRITICAL): Discovery loop graceful skip** — Wrapped `_select_baseline_visit`
  calls in both discovery loops (measurement ~line 1810, observation ~line 2685)
  with try/except so discovered observation types with no baseline visit rows
  are logged and skipped instead of crashing the entire cohort.

- **F-6 (CRITICAL): Mapped measurement loop graceful skip** — Same fix for the
  `BDC_MEASUREMENT_MAP` loop (~line 1731). Variables like ARIC MCH (only at
  Exams 3-5, not Exam 1) raised ValueError and killed extraction before it could
  reach conditions/procedures/drugs/output. Now prints "SKIPPED" and continues.

- **F-7 (MEDIUM): Smoking baseline fallback** — `process_observations` smoking
  handler now catches ValueError from `_select_baseline_visit` instead of crashing.
  Produces empty baseline + warning when smoking data has no baseline rows.

- **F-8 (MEDIUM): Conditions/Procedures/Drugs baseline fallback** — Converted
  hard `raise ValueError` in `process_conditions`, `process_procedures`, and
  `process_drugs` to warnings with all-rows fallback when no baseline visit
  matches. Logs expected vs available visits so diagnostic value is preserved.

- **F-9 (MEDIUM): FHS consent-group collision downgraded to warning** — The
  `load_demography` check for participants in multiple consent groups (1 FHS
  participant in both c1 and c2) now warns instead of raising ValueError. The
  downstream coalesce/dedup handles this case correctly anyway.

  **Root cause for all**: Every `raise ValueError` and uncaught `_select_baseline_visit`
  call propagated to the outer try/finally in `extract_one_cohort`, which
  restored stdout/stderr and closed the log file BEFORE the error message was
  printed — so logs appeared truncated with no error, and no JSON was produced.

  **Cohorts affected**: All multi-visit cohorts (ARIC, CARDIA, CHS, COPDGene,
  FHS, JHS, MESA, WHI).

### `extract_bdc_all.py` — Batch 3 (Third Audit Fixes)

- **F-1 (CRITICAL): Fixed `process_measurements()` two early `return []`** that
  should have been `return [], set()`. The caller unpacks `(results, seen_vars)`,
  so returning a bare list caused a crash when the function hit an early exit.
  **Cohorts affected**: Any cohort that triggers the early-return paths.

- **F-2 (MEDIUM): Added `try/finally` around stdout/stderr Tee redirect** in
  `extract_one_cohort()`. If an exception occurred mid-extraction, the log file
  handle was never closed and stdout/stderr were never restored. Now wrapped in
  try/finally that always restores streams and closes the log handle.
  **Cohorts affected**: All (crash-safety improvement, no behavioral change).

- **F-3 (MEDIUM): Fixed `continuous_stats()` NaN when n_valid==1**. `s.std()`
  returns NaN for a single-element series. NaN breaks JSON serialization. Now
  returns `None` for sd when `n_valid <= 1`.
  **Cohorts affected**: Any cohort with single-observation variables.

- **F-4 (MEDIUM): Added empty-DataFrame guard in `process_drugs()`** after the
  `exposure_status == "active_drug"` filter. Previously crashed with a misleading
  error if filtering removed all rows. Now returns `[]` with a diagnostic message.
  **Cohorts affected**: Cohorts with no active drug exposures.

- **F-5 (MEDIUM): Entity-prefixed discovered keys** to prevent key collision
  across entity types. Changed `discovered:{code}` to
  `discovered:condition:{code}`, `discovered:procedure:{code}`,
  `discovered:measurement:{code}`, `discovered:observation:{code}`,
  `discovered:drug:{code}`.
  **Cohorts affected**: All (changes JSON output keys for discovered concepts).

- **F-6 (MEDIUM): Added `visit_label` to condition and procedure discovery stats**.
  Discovered conditions/procedures were missing the `visit_label` field that all
  mapped variables have. Now sets `stats["visit_label"] = baseline_label`.
  **Cohorts affected**: All (adds field to JSON output).

- **F-7 (LOW): Removed ~12 unused imports from `topmed_compare_config`**.
  `DATASETS`, all `LABEL_*` constants, and `get_variable_spec` were imported but
  never referenced. Kept only `COHORTS`.
  **Cohorts affected**: None (import cleanup).

- **F-8 (LOW): Added `pct_of_total` to manual observation discovery stats**.
  The no-value-column path in observation discovery was building stats dicts
  without `pct_of_total`, unlike every other stats path.
  **Cohorts affected**: All (adds missing field to JSON output).

- **F-9 (LOW): Removed `remaining_aggregated` dead logic in `process_drugs()`**.
  The dedup guard always passed (each drug code is unique), so the loop just
  re-added entries that were already present. Removed ~20 lines.
  **Cohorts affected**: None (dead code removal).

- **F-10 (LOW): Normalized `List[str]` to `list[str]`** throughout (8
  occurrences). Removed `from typing import List` import. Python 3.9+ supports
  lowercase generics natively.
  **Cohorts affected**: None (type annotation only).

- **F-11 (INFO): Moved `from collections import defaultdict`** from inside
  `process_conditions()` and `process_procedures()` function bodies to module-
  level imports.
  **Cohorts affected**: None (import reorganization).

- **F-12 (INFO): Removed redundant `import re as _re`** inside
  `resolve_baseline_visits()`. The module already imports `re` at the top level.
  Changed `_re.search()` to `re.search()`.
  **Cohorts affected**: None (import cleanup).

- **F-13 (INFO): Added SPIROMICS to `_HAS_CONFIG=False` fallback cohort list**
  in `discover_all_cohorts()`. Was the only cohort missing from the fallback.
  **Cohorts affected**: SPIROMICS (only when config module is unavailable).

### `extract_bdc_all.py` — Batch 2 (Second Audit Fixes)

- **C-1: Fixed `process_measurements()` return type hint** from `-> list[str]`
  to `-> tuple[list[str], set[str]]` to match actual return value.
  **Cohorts affected**: None (type annotation only).

- **C-2: Removed fragile `dir()` guards in `process_drugs()`** discovery block.
  The `'n_med_denom' in dir()` check was unreliable for detecting local variable
  existence. Replaced with direct references since `n_med_denom` and
  `med_denom_ids` are always defined in the same enclosing `if` block.
  **Cohorts affected**: None (same runtime behavior).

- **C-3: Prefixed all discovery stat keys with `discovered:`** to prevent key
  collision across entity types. Discovered concept codes (OMOP IDs) now stored
  as `discovered:OMOP:1234567` in `variable_stats`, preventing overwrites when
  the same concept appears in both condition and procedure discovery loops.
  Affects: measurement, condition, procedure, observation, and drug discovery.
  **Cohorts affected**: All (changes JSON output keys for discovered concepts).

- **M-2: Fixed observation discovery dedup** from `sort_values(all columns) +
  drop_duplicates` to `groupby(id_col).agg("first")` coalesce pattern, matching
  the measurement discovery dedup strategy.
  **Cohorts affected**: All (functionally equivalent for most data).

- **M-3: Smoking dedup now uses explicit clinical priority** instead of relying
  on accidental lexicographic sort of OMOP codes. Priority: Current Smoker >
  Former Smoker > Never Smoked > Unknown > null.
  **Cohorts affected**: All (same effective priority as before, now explicit).

- **M-4: Added `pct_of_total` to `categorical_stats()` distribution entries**.
  Each distribution value now includes both `pct` (respondent-based) and
  `pct_of_total` (full-cohort-based) percentages for clarity.
  **Cohorts affected**: All (adds new field to JSON output).

- **M-5: Procedure mapped loop now uses `topmed_var_groups` pattern** (same as
  conditions). Multiple BDC codes mapping to the same topmed_var will UNION
  affected participants instead of overwriting. No functional change today
  (both procedure codes have distinct topmed_vars), but future-proofs the map.
  **Cohorts affected**: None (structural only).

- **M-6: `load_visit_mapping()` called once per cohort** instead of 6 times.
  The visit mapping is now loaded once in `extract_one_cohort()` and passed as
  a parameter to all 6 processor functions.
  **Cohorts affected**: All (performance improvement, no behavioral change).

- **M-7: Removed redundant `not subset.empty` checks** in condition and procedure
  discovery loops. These checks were always true because a `continue` guard above
  already skips empty subsets.
  **Cohorts affected**: None (dead code removal).

- **L-6: Added overlap guard in procedure mapped loop**. If a topmed_var was
  already written by `process_conditions()` (e.g., CABG, angioplasty share
  OMOP codes across condition and procedure maps), the procedure loop now skips
  it with a diagnostic message instead of silently overwriting.
  **Cohorts affected**: Cohorts with overlapping condition/procedure concepts.

- **Breaking change: Removed `min_coverage` parameter and earliest-per-participant
  fallback from `_select_baseline_visit()`**.
  Previously, when preferred baseline visits covered <80% of participants, the
  function fell through to an "earliest-per-participant" strategy that selected
  each participant's first available record from ANY visit. This was wrong:
  it mixed follow-up data with baseline data, inflating N counts and skewing
  means (e.g., FHS triglycerides: BDC reported 11,324 from 11 visits vs.
  TOPMed 9,505, with +22 mg/dL mean delta from including older participants'
  later-exam values). The function now always uses the configured preferred
  visits -- match what you can, and the comparison report shows the rest.
  Also updated two stale comments referencing the removed fallback behavior.
  **Cohorts affected**: Primarily FHS (multi-generational, most variables hit
  the fallback). Also ARIC for variables where baseline visit coverage was
  borderline. Other cohorts unaffected (single baseline visit = 100% coverage).

- **Cross-consent duplicate detection in `load_demography()`**.
  Added a guard that raises `ValueError` if the same participant ID appears in
  multiple consent groups after concatenation. dbGaP consent groups are mutually
  exclusive by design -- duplicates indicate corrupt extract data.
  **Cohorts affected**: All (new validation, no behavioral change for clean data).

- **Demography and measurement coalesce comments updated to "DEFENSIVE"**.
  Investigation confirmed that current YAMLs produce complete rows per block
  (not sparse rows with NULLs in different columns), and consent groups don't
  overlap. The groupby coalesce is a no-op in practice. Comments updated to
  reflect this; code retained as a safety net for future YAML changes.
  **Cohorts affected**: None (comment-only for coalesce; new guard for consent).

---

## 2026-04-03

### `extract_bdc_all.py`

- **Fix (C-1): Condition discovery loop now uses `baseline_df` instead of `df`**.
  The "Discover ALL remaining condition concepts" loop was scanning all-visits
  data (`df`) instead of the baseline-filtered DataFrame (`baseline_df`). This
  caused discovered conditions to include incident/follow-up events, inflating
  counts relative to the mapped conditions which already used `baseline_df`.
  Now both mapped and discovered conditions use the same baseline scope.
  **Cohorts affected**: All cohorts with conditions at non-baseline visits.

- **Fix (C-2): Procedure discovery loop now uses `baseline_df` instead of `df`**.
  Same issue as C-1 but for the "Discover ALL remaining procedure concepts"
  loop. Now consistent with the mapped procedures block.
  **Cohorts affected**: All cohorts with procedures at non-baseline visits.

- **Fix (M-1): Dead fallback code removed from `_select_baseline_visit()`**.
  The "Fallback: use visit with most records" and "return df, 'all visits'"
  paths at the end of `_select_baseline_visit()` were unreachable after the
  ValueError guard was added earlier today. Replaced with a `raise ValueError`
  for the edge case where the low-coverage path cannot build an
  earliest-per-participant selection (no id_col or empty df). This ensures no
  silent auto-selection can ever occur.
  **Cohorts affected**: None (dead code removal).

- **Fix (M-6): Drug discovery denominator corrected to `n_med_denom`**.
  The per-concept drug discovery loop (individual drugs and remaining
  aggregated ATCs) was using `n_participants` as the denominator for computing
  "Not Exposed" counts. This inconsistently used the full cohort N instead of
  the baseline-measurement participant count (`n_med_denom`) that the
  aggregated antihypertensive and lipid-lowering stats already use. Now uses
  `med_denom_ids` for participant intersection and `n_med_denom` for the
  denominator, with `n_missing` and `pct_missing` properly reflecting
  participants outside baseline.
  **Cohorts affected**: All cohorts with discovered drug concepts.

- **Fix (I-2): HCHS_SOL alias maps hoisted to module-level constants**.
  The `HCHS` -> `HCHS_SOL` alias mapping was duplicated in both
  `discover_all_cohorts()` and `discover_mapped_data_dirs()`. Hoisted to
  module-level `COHORT_FOLDER_TO_CANONICAL` and `COHORT_CANONICAL_TO_ALIASES`
  constants. Added `normalize_cohort_name()` helper. CLI `--cohort` and
  `--cohorts` arguments now pass through `normalize_cohort_name()` so that
  `--cohort HCHS` correctly resolves to `HCHS_SOL` for `BASELINE_VISIT_CONFIG`
  lookup and all downstream processing.
  **Cohorts affected**: HCHS_SOL (alias now works end-to-end).

- **Fix: replace silent age-based fallback with hard errors in all four
  baseline-selection paths**. Four code paths in the extractor silently fell
  back to age-sorted earliest-per-participant heuristics when
  `BASELINE_VISIT_CONFIG` labels did not match any visit label in the pipeline
  output. This masked visit.yaml misconfiguration for weeks (JHS and SPIROMICS
  were both affected). All four paths now raise `ValueError` with a diagnostic
  message listing the expected labels and the available ones:
  - `_select_baseline_visit()`: raises when `matched_prefs` is empty (no label
    matched at all). The legitimate low-coverage path (preferred visits matched
    but cover <80% of participants, e.g., FHS staggered sub-cohort collection)
    is preserved and still uses earliest-per-participant.
  - `process_conditions()`: replaces the `HEALTH_EXAMINATION` + age-sort `else:`
    block with `raise ValueError`.
  - `process_procedures()`: same as `process_conditions()`.
  - `process_drugs()`: replaces "Path B" (`elif age_at_observation ...`) with
    `raise ValueError`.
  - **Cohorts affected**: JHS and SPIROMICS (fixes take effect after pipeline
    rerun with their updated visit.yamls). All other cohorts already had correct
    label matching and are unaffected.

- **Fix: baseline-restricted participant universe in `process_demography()`**.
  Added `cohort: str` parameter and a new "Baseline participant filter" block
  that restricts the participant ID set returned by `process_demography()` to
  only those participants with at least one **baseline-visit** row in
  Demography.tsv, using `resolve_baseline_visits()` and `BASELINE_VISIT_CONFIG`.
  Previously the function coalesced across ALL phases and returned every unique
  participant ever seen, regardless of which phases they attended.  This inflated
  the denominator passed to all downstream processors (`process_conditions`,
  `process_measurements`, `process_observations`, `process_procedures`,
  `process_drugs`) for cohorts that enroll new participants in later phases.

  **Root cause confirmed for COPDGene**: 348 participants enrolled for the first
  time in Phase 2 or 3 had no Phase 1 rows — they appeared in the all-phase
  coalesced universe (10,719) but not in the Phase 1 universe (10,371).  This
  produced two artefacts in the comparison table:
  1. B_N inflated to 10,719 for categorical variables (sex, race, ethnicity,
     angina, CABG, MI, PAD) whose denominators derive from `n_participants`.
  2. B_pctM inflated to ~3.2% for continuous variables (BMI, height, weight,
     smoking, blood pressure) because those 348 participants had no Phase 1
     measurement row and counted as "missing" against the inflated denominator.

  **Implementation**: saves `raw_df` before the coalesce groupby so each row's
  visit label is still accessible; translates UUIDs to names via
  `load_visit_mapping()`; calls `resolve_baseline_visits(cohort, ...)` to find
  matching baseline rows; intersects with the coalesced df.  Falls back to
  all-participants (no behaviour change) when:
  - `associated_visit` column is absent from Demography.tsv (e.g. ARIC)
  - `BASELINE_VISIT_CONFIG` has no entry for the cohort
  - No demography rows match the baseline visit labels

  **Cohorts affected**: COPDGene (confirmed fix). CHS (removes any SHHS1_PSG
  ancillary-study participants with no baseline row) and MESA (removes any
  ancillary-only participants) may see minor N reductions that were unquantified
  before this fix. All other cohorts unchanged because their demography tables
  begin at baseline or have no `associated_visit` column.

  Updated call site at line ~3316: `process_demography(dirs, cohort, variable_stats)`.

- **Fix: add JHS `preferred_method_override` for `bp_systolic_1`** (`OMOP:4152194`).
  JHS `bp_systolic.yaml` contains analysis-derived blocks from the Omron automated
  device (pht008729/pht008730/pht008731); without an override the extractor selects
  these rows via `preferred_method: "Analysis derived"`, reading systematically
  higher (~0.64 mmHg) than the sphygmomanometer used by TOPMed. The fix adds
  `"JHS": "Sphygmomanometer average"` to `preferred_method_override`, directing the
  extractor to pht001974 SBPA19 (phv00128376) — the seated random-zero sphygmomanometer
  net average. This matches the instrument already used for JHS DBP (the DBP entry
  already had `"JHS": "Sphygmomanometer average"`). The ARIC override is unchanged.
  - **Affects**: JHS only. All other cohorts have no `preferred_method_override` for
    SBP (CARDIA, CHS, COPDGene, FHS, HCHS, MESA, WHI apply no method filter; ARIC
    continues using its own `"Seated random-zero average"` override).

- **Fix: remove closed-world imputation from `process_conditions` and
  `process_procedures`**. Previously, participants without any Condition or
  Procedure row for a given concept were coded as "No Prior History" /
  "Unaffected" (i.e. `n_unaffected = n_participants - n_affected`). This
  is a closed-world assumption — absence of a record does not mean absence
  of the condition/procedure.
  - **Fix**: Both functions now track `all_respondent_ids` (participants with
    ANY row for the relevant concept codes, regardless of status) alongside
    `all_affected_ids`. The denominator for "unaffected" is now respondent
    count, not total population. Participants without any record become
    missing (`None` in the categorical series), which `categorical_stats`
    reports as `n_missing` / `pct_missing`.
  - **4 sites fixed** (matching the already-correct `process_drugs` pattern):
    1. `process_conditions` — mapped prior-history binary (pad_prior_1,
       angina_prior_1, mi_prior_1, cabg_prior_1, coronary_angioplasty_prior_1)
    2. `process_conditions` — discovered non-mapped conditions
    3. `process_procedures` — mapped prior-history binary
    4. `process_procedures` — discovered non-mapped procedures
  - `process_drugs` was already fixed in the 2026-04-02 session (uses
    `baseline_meas_ids` denominator) and is NOT changed here.
  - **Affects all 9 cohorts** for any condition/procedure variable.
  - **Expected output change**: condition/procedure variables will now show
    non-zero `pct_missing` instead of the previous artificial 0%, and
    `n_total` remains the full population for comparison context.

### `match_quality_table.py`
- **New M-grade — ARIC `pad_prior_1`** [UNION_OF_FORMS]: BDC unions
  MONDO:0005386 (PAD, ABI-based, Exams 1/3/4) with MONDO:0005294 (PVD, hospital
  form self-report from pht004102). Reference uses only Exam 1 ABI-based PAD.
  Result: BDC 7.7% vs reference 4.3% (+3.4pp). The MONDO:0005294 alias stays in
  extract_bdc_all.py because COPDGene pad.yaml uses only that code. Annotated as
  known methodological difference. Affects ARIC only.
- **New note-only entry — ARIC `annotated_sex_1`** [EXTENDED_COVERAGE]: BDC
  sources sex from 30 tables (0% missing) vs reference single derived table
  pht004063 (0.7% missing, 104 participants dropped). Grade kept at A because
  distributions are identical. Uses new `no_override: True` flag.
- **New feature — `no_override` flag in KNOWN_METHODOLOGICAL_DIFFS**: Entries
  with `no_override: True` appear in the methodological notes section with a
  "(grade kept)" tag but do NOT change the computed grade to M. Useful for
  documenting known differences that don't affect data quality.
- **Output header changed**: "Methodological differences (M):" renamed to
  "Methodological notes:" to accommodate note-only entries. Each entry now shows
  "(grade kept)" suffix when `no_override` is set.

## 2026-04-02 (session 24 -- fix medication closed-world "No" assumption)

### `extract_bdc_all.py`
- **Fix: medication binary stats now use baseline measurement participants as
  denominator** instead of all participants.
  - **Root cause**: `process_drugs` previously computed `n_off_med = n_participants
    - n_on_med`, coding every participant without a DrugExposure row as "No" —
    a closed-world assumption. Participants who never attended the baseline visit
    (e.g., FHS Original Exam 1-3-only participants who died/dropped before Exam 4,
    when medication was first recorded) have no DrugExposure row for factual reasons,
    not because they were not on medication.
  - **Fix**: `process_measurements` now accumulates `baseline_meas_ids` — the set
    of participants present in any baseline-filtered measurement (BP, labs, etc.).
    This set is returned alongside `found_vars` and passed to `process_drugs`.
    Participants in `baseline_meas_ids` who have no antihypertensive record are
    correctly coded "No"; participants outside `baseline_meas_ids` (never at
    baseline) are counted as `n_missing` rather than "No".
  - **Impact on output**: `n_missing` and `pct_missing` for `antihypertensive_meds_1`
    and `lipid_lowering_medication_1` now reflect participants absent from baseline
    rather than 0. `n_total` remains the full cohort size. The "No" count is reduced
    by the number of baseline-absent participants.
  - **FHS quantification**: ~757 FHS Original participants attended only Exams 1-3
    (before medication tracking began at Exam 4); these now appear as missing rather
    than "No". Estimated `pct_missing` for FHS antihypertensive meds increases from
    0.0% to ~5.0%.
  - **Affects**: All cohorts. Most significant for FHS (Original Exam 1-3 attrition).
    Other cohorts where `baseline_meas_ids` == `participant_ids` see no change.

---

## 2026-04-02 (session 23 -- ARIC MCH M-grade)

### `match_quality_table.py`
- **New ARIC M-grade: `mch_entmass_rbc_1`** (VISIT_SCOPE_DIFF): ARIC never
  conducted CBC labs at Exams 1 or 2; MCH only exists in HMTCV301 (pht004109,
  Visit 3), HMTCV401 (pht004110, Visit 4), and CBC (pht006422, Visit 5). Both
  BDC and reference draw from these same tables. BDC earliest-per-participant
  yields N=8,959 (EXAM 3=3,285, EXAM 5=3,063, EXAM 4=2,782); reference N=8,710
  anchored on EXAM 3. The +0.13 pg/cell mean delta (norm_delta=0.057, just over
  B/C at 0.05) and +249 participant gap reflect exam-composition differences --
  no YAML change can close this. The YAML is correct; MCH simply doesn't exist
  at ARIC baseline.
- **Affects**: ARIC only.

## 2026-04-02 (session 22 -- ARIC antihypertensive M-grade)

### `match_quality_table.py`
- **New ARIC M-grade: `antihypertensive_meds_1`** (ADMIN_VS_SURVEY): BDC uses
  HYPTMDCODE01 (phv00204798, pht004063 DERIVE13) -- a Medi-Span GPI
  pharmaceutical-code-based derived variable capturing any participant who
  filled an antihypertensive prescription (4,791 Yes = 30.6%). Reference
  uses HYPTMD01 (phv00204754, same table), the survey-based variable where
  participants explicitly attributed their med to high blood pressure (~3,961
  Yes = 25.3%). The 830-participant gap (~4.9pp) represents patients on
  antihypertensive therapy who did not self-attribute it to BP. BDC approach
  (pharmaceutical code) is epidemiologically more complete and correct.
  0% vs 1.3% missing gap is extractor-design artefact (absence = No).
- **Affects**: ARIC only.

## 2026-04-02 (session 21 -- FHS IDTYPE bug fix and smoking structural gap M-grades)

### `match_quality_table.py`
- **New FHS M-grade: `current_smoker_baseline_1`** (STRUCTURAL_GAP): FHS Original
  cohort has no tripartite smoking status (Current/Former/Never) at any single
  baseline exam in dbGaP. pht007777 (fhsvarv7) contains CURRSMK1-32 as binary
  (0/1) only. MF71 (phv00000543, pht000009) is a multi-exam tobacco summary --
  MF70 shows the source may be Exam 1-4 per participant; not safely attributable
  to FHS ORIGINAL EXAM 4. Source data limitation, not a YAML error.
- **New FHS M-grade: `ever_smoker_baseline_1`** (STRUCTURAL_GAP): Same structural
  limitation as current_smoker -- no ever-smoked binary or tripartite variable
  exists in pht007777. cig_smok.yaml maps CIGSMOK (phv00000545) as a proxy but
  the multi-exam MF70 sourcing and prior IDTYPE bug (now corrected) mean reliable
  FHS Original baseline smoking output requires further investigation.
- **Affects**: FHS only.

## 2026-04-02 (session 20 -- FHS antihypertensive YAML fix and M-grade additions)

### `match_quality_table.py`
- **New FHS M-grade: `height_baseline_1`** (VISIT_SCOPE_DIFF): BDC maps FHS
  Original height to EXAM 4 per BASELINE_VISIT_CONFIG; reference uses EXAM 1.
  66-record N gap (BDC N=15,089 vs ref N=15,023) reflects survivor bias --
  participants who died between Exam 1 and Exam 4 are excluded from BDC but
  present in the reference. +0.299 cm mean diff confirms systematic exclusion
  of shorter participants. YAML is correct per the FHS baseline visit definition.
- **New FHS M-grade: `antihypertensive_meds_1`** (VISIT_SCOPE_DIFF): Documents
  the residual gap after Fix 22 (pht000009 block added to hypert_trt.yaml).
  Codes 9997/9999 still resolve to "No" via extract imputation -- an unavoidable
  structural difference. BDC N=15,089 (0.0% missing) vs ref N=14,377 (5.2%
  missing). Gap expected to narrow after pipeline re-run.
- **Affects**: FHS only.

## 2026-04-02 (session 19 — value-first sort in earliest-per-participant dedup)

### `extract_bdc_all.py`
- **Bug fix — null-value preference in `_select_baseline_visit()`**: Added
  `_has_value` as the primary sort key in the earliest-per-participant fallback
  path. `_has_value` is 0 when `value_quantity__value_decimal` is non-null and
  1 when null, so rows with valid measurements sort before coded-missing rows
  for the same participant. Previously, a participant with a coded-missing value
  at their earliest exam (e.g., ARIC HMTC7=`"A"` or `"O"` at Exam 3 → stored
  as `value_decimal = null`) would be locked in as "missing" by
  `drop_duplicates(keep="first")` even though valid MCH data existed for them
  at Exam 4 or Exam 5. The fix recovers those participants.
- **Secondary sort keys preserved**: `_age_sort` (ascending) and `label_col`
  (alphabetical) remain in the sort sequence as tie-breakers, so behaviour for
  participants with valid values at multiple exams is unchanged.
- **Log output updated**: `age_note` now reports both `value-first` and
  `age-sorted` flags when present (e.g., `"(value-first, age-sorted)"`).
- **Scope**: Only affects the earliest-per-participant fallback (fires when
  preferred-visit matching fails or covers <80% of participants). Categorical
  variables (smoking — stored in `value_enum`, not `value_decimal`) are
  unaffected.
- **Affects**: ARIC MCH (primary motivation — ~2,786 participants with null V3
  but valid V4/V5 MCH recovered). Potential positive impact on CARDIA and any
  other cohort with coded-missing lab values at earlier exams.

---

## 2026-04-02 (session 18 — CHS ever_smoker M-grade note refinement)

### `match_quality_table.py`
- **Updated CHS `ever_smoker_baseline_1` M-grade note**: Expanded explanation to
  clarify the conceptual difference between approaches (curated study-team
  derivation vs. mechanical heuristic reconstruction). Added concrete example of
  why the override is questionable (non-zero SMKAGE/AMOUNT could be data entry
  artifacts) and note that the CHS study team presumably adjudicated these edge
  cases when deriving EVERSM. No change to grade or code — note text only.
- **Affects**: CHS only.

## 2026-04-02 (session 17 — FHS M-grade additions for race_us_1 and mch_1)

### `match_quality_table.py`
- **Added two new FHS M-grade entries** to `KNOWN_METHODOLOGICAL_DIFFS`:
  - `("FHS", "race_us_1")` [EXTENDED_COVERAGE]: BDC demography.yaml sources race
    from multiple FHS race summary tables (pht016162, pht009760, pht003094,
    pht000074) covering all sub-cohorts including Gen3, Omni 1/2, and NOS.
    Result: BDC N=15,089 (0.0% missing) vs reference N=12,848 (15.3% missing).
    The ~2,241 participant gap reflects sub-cohorts excluded from the TOPMed
    baseline scope or specific race codes treated as unclassifiable by the
    reference. BDC mapping is correct per dbGaP data dictionaries.
  - `("FHS", "mch_1")` [VISIT_SCOPE_DIFF]: BDC mch.yaml covers 5 CBC lab tables
    (pht000031, pht002889, pht004802, pht001045, pht015118) none of which covers
    a baseline Exam 1 CBC for most sub-cohorts. BASELINE_VISIT_CONFIG filter
    falls through to all-visit data, producing only 2,795 non-missing values
    (81.5% missing) vs reference 8,010 (47.2% missing). The reference likely
    sources MCH from additional CBC tables not yet in the YAML. pht015118
    (Offspring Exam 10 / Omni1 Exam 5) was added this session to partially
    close the gap; further sourcing investigation is pending.
- **Affects**: FHS only.

---

## 2026-04-02 (session 16 — Correct topmed_version metadata for ARIC and FHS)

### `topmed_compare_config.py`
- **Corrected `topmed_version` for ARIC: `"v3"` -> `"v5"`** and **FHS: `"v29"` ->
  `"v30"`**.
- **Source:** Verified against `topmed_dcc_harmonized_demographic_v4_harmonization_algorithms.md`
  (the DCC's own harmonization documentation, included in the 2020-05-21 upload).
  The R algorithm code for each cohort references explicit `study_accession` fields:
  ARIC uses `phs000280.v5` (line 816) and FHS uses `phs000007.v30` (line 1102).
  Table 3 of Stilp et al. 2021 (Am J Epidemiol 190:1977-1992, PMC8485147) shows
  `phs000007.v29` for FHS tagging (a different activity from harmonization), which
  explains the prior v29 entry — but the harmonization algorithms doc is more
  authoritative for which version was actually used to generate harmonized data.
- **Runtime impact: none.** `topmed_version` is written into output JSON metadata
  only (`cohort.topmed_version`); it is not read back by any downstream script to
  filter rows or alter cohort selection. This is a documentation-only correction.
- **Cohorts affected:** ARIC and FHS metadata fields only.

---

## 2026-04-02 (session 15 — HEALTH_EXAMINATION fallback for condition/procedure baseline filter)

### `extract_bdc_all.py`
- **Replaced unconditional all-rows fallback with a HEALTH_EXAMINATION filter** in
  `process_conditions()` and `process_procedures()`, in the `else` branch that fires
  when `BASELINE_VISIT_CONFIG` finds no matching visit label.
- **Root cause:** `BASELINE_VISIT_CONFIG` uses cohort-specific visit label names
  (e.g. `"ARIC EXAM 1"`, `"JHS Exam 1"`) but some cohorts store raw OMOP visit type
  concepts (`HEALTH_EXAMINATION`, `TELEHEALTH`, `INPATIENT_VISIT`, `UNKNOWN`) in
  their Condition TSVs instead of cohort-specific names. The name match always failed,
  silently falling through to any-positive aggregation across ALL rows — accumulating
  incident events from follow-up contacts, hospitalizations, and post-baseline exams
  as if they were prior-to-baseline history.
- **What the new fallback does:**
  1. Filters to `HEALTH_EXAMINATION` rows only — the OMOP visit type corresponding to
     in-person study exam visits, excluding `TELEHEALTH` (AFU annual follow-up calls
     tracking incident events), `INPATIENT_VISIT` (hospitalization records), and
     `UNKNOWN`.
  2. Takes the earliest `HEALTH_EXAMINATION` per participant (age-sorted), mirroring
     the measurement extractor's `earliest-per-participant` logic to isolate Exam 1.
  3. Falls through to all rows only if no `HEALTH_EXAMINATION` rows exist at all.
- **Confirmed impact by cohort (from log analysis):**
  - **ARIC** — Condition TSV: `HEALTH_EXAMINATION` + `INPATIENT_VISIT` + `UNKNOWN`;
    7.877M total rows. Prior fallback accumulated all 7 exams + Hospital Form + AFU
    follow-up contacts -> `mi_prior_1` inflated to 89.6% (BDC) vs 4.4% (TOPMed ref).
    Fix: retain only HEALTH_EXAMINATION rows, earliest-per-participant -> expected to
    reduce to ~4-5%. All other ARIC condition variables similarly affected.
  - **JHS** — Condition TSV: 1,140,622 TELEHEALTH rows (85.6%) + 183,400
    HEALTH_EXAMINATION (13.8%) + 9,116 UNKNOWN. TELEHEALTH = AFU annual phone calls
    tracking incident events. Prior fallback: any-positive across all causing
    `angina_prior_1` = 84.4% (impossible for prior-to-baseline) and gaps of 1-3pp on
    all other condition vars vs TOPMed ref. Fix: HEALTH_EXAMINATION filter + earliest-
    per-participant -> all variables move closer to TOPMed.
  - **CARDIA** — Condition TSV: 248,173 HEALTH_EXAMINATION (90.3%) + 26,772 UNKNOWN;
    no TELEHEALTH. Near-zero CVD prevalences (young adult cohort). Effect: minor
    (<0.5pp), no graded variables impacted.
- **Cohorts unaffected (zero risk):**
  - **CHS, MESA, FHS** — Condition TSVs use cohort-specific visit label names that
    match `BASELINE_VISIT_CONFIG` exactly (e.g. `"CHS BASELINE BOTH"`,
    `"MESA CLASSIC EXAM 1"`). These cohorts never enter the fallback `else` branch and
    are completely unaffected by this change.
- **Both extractors updated:** `process_conditions()` (primary) and
  `process_procedures()` (same pattern, same bug, same fix).

---

## 2026-04-02 (session 14 — FHS Original BP baseline: Exam 1 -> Exam 4)

### `extract_bdc_all.py`
- **Changed FHS Original cohort baseline from `"FHS ORIGINAL EXAM 1"` to
  `"FHS ORIGINAL EXAM 4"`** in `BASELINE_VISIT_CONFIG["FHS"]["exact"]`.
- **Root cause:** BP for the FHS Original cohort should use Exam 4 as baseline,
  not Exam 1. The TOPMed DCC explicitly chose Exam 4 because antihypertensive
  medication was not recorded before Exam 4 for the Original cohort (documented
  in `bp_systolic_1.json` and `bp_diastolic_1.json`, UW-GAC harmonization).
  Using Exam 1 caused BDC to include ~578 Original cohort participants who
  attended Exam 1 but died/dropped out before Exam 4, inflating BDC N
  (15,076-15,079) vs TOPMed N (14,501) and producing a +1.15/+0.84 mmHg mean
  BP delta (BDC higher). The pht007777 data dict confirms: SBP4=phv00370034
  and DBP4=phv00369842 are "Average SBP/DBP, Exam 4" — correctly mapped in
  blood_pressure.yaml.
- **Updated `pattern`** from `r"(?i)FHS\s+(?!.+SHHS).+\s+EXAM\s+1$"` to
  `r"(?i)FHS\s+(?!ORIGINAL)(?!.+SHHS).+\s+EXAM\s+1$"` so the pattern
  fallback no longer matches `FHS ORIGINAL EXAM 1` for cohorts where the
  exact list fails.
- **Updated comment** to document the Exam 4 rationale inline.
- **Affects:** FHS only (exact list and pattern are keyed to the FHS cohort).
  All other FHS sub-cohorts (Offspring, Gen3, Omni1, Omni2, NOS) retain
  Exam 1 as their baseline. No other cohort is affected.

---

## 2026-04-02 (session 13 — ARIC BP preferred_method_override)

### `extract_bdc_all.py`
- **Added `preferred_method_override: {"ARIC": "Seated random-zero average"}`**
  to both the SBP (`OMOP:4152194`) and DBP (`OMOP:4154790`) extractor specs.
- **Root cause:** ARIC `bp_systolic.yaml` has 48 blocks spanning 6 visit labels
  and 10+ method types — none use `"Analysis derived"` (the global
  `preferred_method`). The method filter silently fell through, causing the
  extractor to mix supine ABI readings (pht004041 Dinamap supine, pht004027/28/29
  ankle-brachial index, pht006414 ABI Exam 5) and ancillary-study context readings
  (pht004229/4230 carotid ultrasound context, pht004079 echocardiogram Jackson
  substudy) with the correct seated clinicial BP. Supine measurements run ~8-12
  mmHg higher than seated, explaining the +12.45 mmHg SBP mean delta (BDC 133.9
  vs TOPMed 121.4 mmHg) and the elevated missing rate for DBP (7.1% vs 0.8%).
- **Correct source:** pht004192 SBPA02 (Seated Blood Pressure, Exam 1). PHVs:
  phv00210290 (SBPA21, zero-corrected average SBP) and phv00210291 (SBPA22, DBP).
  This is the same source used by the TOPMed DCC harmonization — verified against
  the ARIC unit in `bp_systolic_1.json` in the UW-GAC/topmed-dcc-harmonized-
  phenotypes repository. TOPMed recomputes the zero correction from raw readings
  (SBPA15, SBPA17, SBPA18, SBPA20); BDC uses the ARIC pre-computed corrected
  average (SBPA21/SBPA22), which is semantically equivalent.
- **For DBP:** also carried over existing JHS override
  (`{"JHS": "Sphygmomanometer average"}`) — now the dict is
  `{"JHS": "Sphygmomanometer average", "ARIC": "Seated random-zero average"}`.
- **Affects:** ARIC only. All other cohorts retain their existing behavior.

---

## 2026-04-01 (session 12 — cross-cohort 19 core variable coverage table)

### `core_variable_coverage_table.py` (new file)
- **New script** added to `scripts/topmed_compare/`: cross-cohort presence/absence
  matrix for the 19 Core Variables across all 9 cohorts.
- Reads per-cohort TOPMed DCC summary JSONs from
  `memory/research/TOPMed_DCC_Compare/TOPMed_Output/` and scans each cohort's
  HV ingest directory for matching YAML file stems.
- Outputs a matrix with two flags per cell: T (TOPMed DCC has variable) and B
  (BDC has YAML), plus per-cohort summary counts.
- Covers all 9 cohorts: ARIC, CARDIA, CHS, COPDGene, FHS, HCHS-SOL, JHS, MESA,
  WHI. SPIROMICS excluded (not in TOPMed DCC harmonization).
- **Affects all cohorts.** Run with: `python scripts/topmed_compare/core_variable_coverage_table.py`

---

## 2026-04-01 (session 11 — FHS mapping quality table)

### `mapping-quality-table.py` (new file)
- **New script** added to `scripts/topmed_compare/`: FHS-specific per-variable
  mapping quality table generator.
- **Always runs in full comparison mode** (BDC vs TOPMed). Defaults to the
  standard local TOPMed JSON at
  `memory/research/TOPMed_DCC_Compare/TOPMed_Output/topmed_fhs_summary.json`.
  Override with `--topmed-json <path>` if needed.
- **Imports shared definitions** (`CORE_VARIABLES`, `KNOWN_METHODOLOGICAL_DIFFS`)
  from `match_quality_table.py`. FHS M-grades (ASSAY_ERA_DIFF for
  `total_cholesterol_1` and `triglycerides_1`; EXTENDED_COVERAGE for `hdl_1`)
  are automatically applied from the shared table.
- **FHS sub-cohort coverage notes** in `_COVERAGE_NOTE_BY_VAR` for known
  low-coverage variables (CBC analytes Gen3-only, smoking ~16% miss, etc.).
- **Context**: generated to support FHS DCCCompare session using
  `bdc_fhs_summary_20260401_225312.json`. Only FHS is affected.

## 2026-04-02 (session 11)

### `extract_bdc_all.py`
- **Added `import re`** to top-level imports (needed for UUID detection regex).

---

## 2026-04-02 (session 12 — FHS D-grade root cause fixes)

### `extract_bdc_all.py`
- **Fixed SHHS regex over-match in FHS `BASELINE_VISIT_CONFIG`** (line ~762).
  - Previous pattern `r"(?i)FHS\s+.+\s+EXAM\s+1$"` matched SHHS sub-study
    visit labels ("FHS OFFSPRING SHHS EXAM 1", "FHS OMNI 1 SHHS EXAM 1").
  - CABG procedure records do not exist at SHHS visits, so the extractor found
    0 positives there and fell back to all-visit aggregation, reporting only
    5 CABG cases (D-grade vs reference 22.1% missing).
  - Fixed to `r"(?i)FHS\s+(?!.+SHHS).+\s+EXAM\s+1$"` — negative lookahead
    excludes SHHS sub-study visits while still matching all six FHS sub-cohort
    Exam 1 visit labels.
  - **Affects**: FHS only. All other cohort patterns are unchanged.

### `match_quality_table.py`
- **Added two FHS M-grade entries** to `KNOWN_METHODOLOGICAL_DIFFS`:
  - `("FHS", "cabg_prior_1")` — code `VISIT_SCOPE_DIFF`. Explains the SHHS
    regex bug (now fixed) and the residual ~22% missing expected after the fix,
    reflecting that Gen3/Omni 2/NOS sub-cohorts were not asked CABG history
    at their Exam 1 enrollment.
  - `("FHS", "hispanic_or_latino_1")` — code `AGGREGATION_DIFF`. Explains
    pht016162 code 88 ("Defaulted ethnicity (Not Hispanic)") — FHS study-team-
    assigned imputed value for Original Cohort participants enrolled before
    standardized ethnicity collection. BDC maps code 88 correctly per dbGaP
    data dict; reference extract treats it as missing.
  - **Affects**: FHS only.


- **Fixed destructive visit mapping in `load_visit_mapping()`**: When Visit.tsv `id` values
  are human-readable visit names (e.g., "CARDIA YEAR 0") rather than UUIDs, the old code
  mapped them to generic `visit_category` labels (e.g., "HEALTH_EXAMINATION"), destroying
  exam-specific granularity. New logic: (1) sample up to 20 `id` values from Visit.tsv,
  (2) check if any match the UUID4/5 regex pattern, (3) if none match, build an identity
  mapping (id -> id) so specific visit names are preserved. This allows
  `BASELINE_VISIT_CONFIG` exact/pattern matching (e.g., "CARDIA YEAR 0", "WHI SCREENING",
  "MESA CLASSIC EXAM 1") to work correctly in `_select_baseline_visit()`.
- **Also handles cohorts with no label column at all** (WHI, CHS, HCHS-SOL): previously
  returned empty mapping immediately when `visit_category`/`name`/`label` columns were
  absent. Now the UUID detection runs first on the `id` column — if ids are human-readable,
  an identity mapping is built even without a label column. This unblocks baseline visit
  filtering for these cohorts.
- **Decision tree**: (a) ids are UUIDs + label_col exists -> UUID-to-label mapping (JHS path),
  (b) ids are human-readable + label_col exists but less specific -> identity mapping
  (CARDIA, MESA path), (c) ids are human-readable + no label_col -> identity mapping
  (WHI, CHS, HCHS-SOL path), (d) ids are UUIDs + no label_col -> empty mapping (warning).
- Affects: CARDIA, MESA, WHI, CHS, HCHS-SOL. No change for JHS (UUIDs) or COPDGene
  (no Visit.tsv).

---

## 2026-04-01 (session 10)

### `match_quality_table.py`
- **Added JHS General Pattern comment block** explaining the systemic visit-label/aggregation
  pattern affecting multiple JHS variables: pipeline output labels all visits as
  "HEALTH_EXAMINATION" (bdchm visit_category), causing DrugExposure and some Condition
  entities to fall through to all-visits aggregation. Added above the JHS M-grade entries.
- **New M-grade -- JHS `antihypertensive_meds_1`** [UNION_OF_FORMS]: BDC unions 7+ drug-class
  YAML files (ATC:C02/C03/C07A/C08/C09A/C09C) across Exams 1-3, 6, and AFU. DrugExposure
  baseline filter fell through to all-visits (321,365 rows). BDC 81.0% vs TOPMed 53.8%;
  27pp excess = incident med starts after baseline. D -> M. Only JHS affected.
- **New M-grade -- JHS `mi_prior_1`** [AGGREGATION_DIFF]: hist_my_inf.yaml has 10 blocks
  across 9 tables (Exams 1-3). Baseline filter found no match; all-visits any-positive dedup
  accumulates incident MI. BDC 7.4% vs TOPMed 5.6% (94 excess cases). B -> M. Only JHS.
- **New M-grade -- JHS `bp_systolic_1`** [AGGREGATION_DIFF]: 18 blocks across 6 tables.
  Method filter correctly selects 'Analysis derived'. Mean delta +0.65 mmHg (0.04 SD),
  clinically negligible. BDC N=3,872 vs TOPMed 3,526. B -> M. Only JHS affected.
- **New M-grade -- JHS `total_cholesterol_1`** [AGGREGATION_DIFF]: 9 blocks across 8 tables.
  Earliest-per-participant across 2 visit labels. Mean delta +0.65 mg/dL (0.016 SD). BDC
  8.8% missing vs TOPMed 3.6%. B -> M. Only JHS affected.
- **New M-grade -- JHS `triglycerides_1`** [AGGREGATION_DIFF]: 10 blocks across 9 tables.
  Mean delta -2.45 mg/dL (0.026 SD). TOPMed has higher SD/max suggesting outliers. B -> M.
  Only JHS affected.
- **Removed `rbc_ncnc_bld_1` from CORE_VARIABLES** (was var 20, now 19): `rdbld_ct.yaml`
  exists only in `_archive/` for CARDIA, FHS, HCHS, MESA — no active pipeline support in
  any cohort. Retained exclusion comment in CORE_VARIABLES block. Affects all cohorts.
- **New M-grade -- CHS `ever_smoker_baseline_1`** [AGGREGATION_DIFF]: BDC sources from
  BASEBOTH EVERSM (phv00100372, pht001452) -- the CHS study team's pre-derived
  ever-regular-smoker binary (2,966 Yes / 2,559 No / 6 missing), which exactly matches
  the dbGaP var_report. The reference extract applies an 'any positive indication'
  override, summing 4 raw questionnaire fields (SMOKE101, SMOKE201, SMKAGE, AMOUNT)
  via rowSums(na.rm=TRUE); any non-zero SMKAGE or AMOUNT overrides a 'No' on the
  primary question, reclassifying 102 participants whose CHS EVERSM = No. BDC is
  correct per dbGaP; reference overcounts by 102 (55.60% vs 53.70%). B-grade -> M.
  Source: UW-GAC/topmed-dcc-harmonized-phenotypes, ever_smoker_baseline_1.json, v4.
  Only CHS affected.
- **New M-grade -- MESA `platelet_ncnc_bld_1`** [UNION_OF_FORMS]: MESA has no
  population-wide baseline CBC. Platelet counts exist only in two ancillary
  sub-studies: pht001984 (Inflammation, Exam 1 era, N=894) and pht004319
  (Epigenomic CBC, Exam 5, N=2,750). TOPMed used only pht004319; BDC unions
  both. Mean diff (+4.96) reflects real longitudinal change for overlapping
  participants across exam eras. Added to KNOWN_METHODOLOGICAL_DIFFS.
- **New M-grade -- MESA `rbc_ncnc_bld_1`** [UNION_OF_FORMS]: Identical root
  cause to platelet_ncnc_bld_1. Same two ancillary tables (pht001984 N=900,
  pht004319 N=2,756); TOPMed used only pht004319; BDC unions both (N=3,169).
  Mean difference is minimal (+0.015) because RBC is physiologically stable
  across exam eras. Added to KNOWN_METHODOLOGICAL_DIFFS.

### `extract_bdc_all.py`
- **Added `preferred_method_override: {CARDIA: "Year 0"}` to `OBA:VT0001259` (body weight)**:
  CARDIA bdy_wgt.yaml has multi-exam blocks; pht001795 (Year 10) and pht001706 (Year 7) have
  active `age_at_observation` while Year 0 (pht001583) has none. Year 10 weight wins age-sorted
  dedup, biasing mean +5.27 kg (BDC 76.45 vs TOPMed 71.18). Override filters to "Year 0"
  method_type label added in corresponding CARDIA HV fix. Only CARDIA affected.
- **Added `preferred_method_override: {CARDIA: "Year 0"}` to `OBA:VT0002644` (triglycerides)**:
  CARDIA triglyc_bld.yaml has 5 multi-exam blocks with no age. pht001802 (Year 10) appears
  first in file and wins the no-age tie-breaker, producing +17.84 mg/dL delta (BDC 91.10 vs
  TOPMed 73.26). Override filters to "Year 0" method_type label. Only CARDIA affected.

### `CARDIA-ingest/bdy_hgt.yaml` (HV repo -- CARDIA local)
- **Restored `value_decimal` on 4 commented-out inch-to-cm blocks** using `expr: "{phv} * 2.54"`
  (single-variable, simpleeval-safe) instead of the blocked `unit_conversion` approach:
  - pht001781 (Year 10): `phv00118957 * 2.54`
  - pht001626 (Year 2): `phv00114609 * 2.54`
  - pht001667 (Year 5): `phv00115704 * 2.54`
  - pht001795 (Year 10): `phv00119506 * 2.54`
  - Root cause: These blocks had active `age_at_observation` but `value_decimal` was commented
    out (original `unit_conversion: [in_us] -> cm` is not supported). Null-value rows won the
    age-sorted dedup for 98.5% of participants. Only 55 participants got values (from the Year 7
    block pht001706 which had both active age and active value_decimal).
  - Expected: height coverage jumps from n=55 to n=3,614; grade D -> A.
  - Only CARDIA affected.

### `CHS-ingest/bmi.yaml` (HV repo -- CHS local, new file)
- **Created `bmi.yaml`** with 6 MeasurementObservation blocks covering all CHS exam
  tables that include BMI (OBA:2045455, kg/m2): pht001450 (phv00099468 BASE1),
  pht001452 (phv00100386 BASEBOTH), pht001490 (phv00105306 YR5NEW),
  pht001491 (phv00106840 YR5OLD), pht001495 (phv00110612 YR9),
  pht003700 (phv00198926 SHHS2). Addresses CHS bmi_baseline_1 completeness gap.
  Only CHS affected.

### `CHS-ingest/mch.yaml` (HV repo -- CHS local)
- **Added gap documentation comment** to empty mch.yaml: CHS CBC does not include
  MCH. All 65 data dicts searched -- only WBC, Hgb, Hct, Platelet are reported.
  File intentionally empty per Fix 9. Only CHS affected.

### `CHS-ingest/blood_pressure.yaml` (HV repo -- CHS local, new file)
- **Created `blood_pressure.yaml`** with 13 MeasurementObservationSet blocks
  (FHS pattern) for all CHS exam tables that have averaged seated BP readings.
  Systolic OMOP:4152194, diastolic OMOP:4154790, unit mm[Hg]. Tables covered:
  pht001450/1452 (AVZMSYS/AVZMDIA, BASELINE), pht001488 (YR3),
  pht001489 (YR4), pht001490/1491 (YR5NEW/OLD), pht001492 (YR6), pht001493 (YR7),
  pht001474 (YR10), pht001475 (YR11), pht001495 (YR9), pht003699 (SHHS1 ssyst40),
  pht003700 (SHHS2 avg23bps_s2). YR8 (pht001494) excluded -- no measured BP.
  Addresses CHS bp_systolic_1 / bp_diastolic_1 completeness gap. Only CHS affected.

### `CARDIA-ingest/bdy_wgt.yaml` (HV repo -- CARDIA local)
- **Added `method_type: value: "Year 0"` to pht001583 (Year 0) body weight block**.
  Enables the preferred_method filter in extract_bdc_all.py to select baseline weight.
  Only CARDIA affected.

### `CARDIA-ingest/triglyc_bld.yaml` (HV repo -- CARDIA local)
- **Added `method_type: value: "Year 0"` to pht001588 (Year 0) triglycerides block**.
  Enables the preferred_method filter in extract_bdc_all.py to select baseline triglycerides.
  Only CARDIA affected.

---

## 2026-04-01 (session 9)

### `match_quality_table.py`
- **New M-grade entry -- HCHS_SOL `race_us_1`** [LABEL_REMAP]: HCHS-SOL has no OMB race
  variable. TOPMed maps all participants to "Other"; BDC maps to "UNKNOWN". BDC's approach
  is semantically more accurate (signals absence of data vs positive assertion). Produces
  permanent 100pp categorical divergence and D grade. Added to KNOWN_METHODOLOGICAL_DIFFS
  so it grades as M instead. Only HCHS-SOL affected.
- **New M-grade entry -- HCHS_SOL `antihypertensive_meds_1`** [UNION_OF_FORMS]: BDC unions
  5 ATC drug classes (C02, C03, C07A, C09A, C09C) from pht004715, yielding 2,565 Yes
  (21.7%). TOPMed used only the single binary MED_ANTIHYPERT (phv00226324), yielding
  2,078 Yes (16.9%) with 615 missing. The +4.8pp difference comes from 593 participants
  who reported a specific drug class but were No/missing on the binary summary question.
  Same UNION_OF_FORMS pattern as WHI. Only HCHS-SOL affected.
  HCHS core-20 grades now: A=14, B=0, C=0, D=0, M=2.

---

## 2026-04-01 (session 8)

### `JHS-ingest/hist_my_inf.yaml` (HV repo — JHS local)
- **Removed 3 annual follow-up (afulong) MI blocks** that incorrectly inflated History of MI prevalence (BDC 12.4% vs TOPMed 5.6%, +6.8pp, C-grade).
  - Removed: phv00400914 (`MIEVER` — "Has a doctor said you have had a heart attack?"), pht008725
  - Removed: phv00400915 (`MILASTCNTCT` — "Since our last contact, has a doctor said you had a heart attack?"), pht008725
  - Removed: phv00400916 (`MIHOSPLASTCNTCT` — "Were you hospitalized for a heart attack since our last contact?"), pht008725
  - Root cause: All three are from the JHS Annual Follow-Up (afulong) longitudinal tracking form, not baseline exam data. With any-positive dedup, a participant who has an incident MI years after baseline yields `MIEVER = Y` at future contacts — this collapses into the "prior history" HISTORICAL condition status, inflating baseline prevalence. `MILASTCNTCT` and `MIHOSPLASTCNTCT` are unambiguous incident event trackers ("since last contact"). `MIEVER`, though phrased as "ever", is asked rolling at each annual follow-up, so a Y at contact 5 means MI occurred between contacts 4 and 5.
  - Retained: pht001963 (Medical History questionnaire, phv00127708) and pht001967 (Personal and Family History Questionnaire, phv00128091) — both Visit 1 baseline blocks that correctly capture pre-study MI.
  - Expected outcome: History of MI prevalence drops from ~12.4% to closer to TOPMed's ~5.6%; grade expected to improve from C to A or B.
  - Only JHS affected.

---

## 2026-04-01 (session 7)

### `extract_bdc_all.py`
- **Added `preferred_method_override` per-cohort dict to DBP spec (`OMOP:4154790`)**:
  - New optional key `preferred_method_override` in `BDC_MEASUREMENT_MAP` entries allows per-cohort override of the global `preferred_method`.
  - JHS override: `{"JHS": "Sphygmomanometer average"}`.
  - Filtering logic at the preferred_method step updated to check `spec["preferred_method_override"].get(cohort, ...)` first, falling back to the global `preferred_method` for all other cohorts. Zero impact on any cohort without an override.
  - **Why**: JHS `bp_diastolic.yaml` Exam 1/2/3 "Analysis derived" blocks source DBP from the Omron automated device (pht008729/8730/8731, phv00401119/309/410), which reads ~3 mmHg lower for DBP than the sphygmomanometer (confirmed by logical_min/max [42.67, 112.4] matching Omron range). TOPMed's harmonization used pht001974 SBPA20 (random-zero sphygmomanometer average). Without this fix, JHS DBP grades **D** (-3.12 mmHg, BDC 75.67 vs TOPMed 78.79). Domain science discussion of whether to make the sphygmomanometer the universal preferred method is deferred.
  - Only JHS affected.

> **OPEN QUESTION — raise at JHS PR review:**
> Should sphygmomanometer be the universal preferred device for DBP across ALL cohorts, or only JHS?
> Evidence: Omron automated devices read ~3-4 mmHg lower for DBP (but agree closely for SBP) due to oscillometric vs auscultatory measurement differences. TOPMed's harmonization consistently used sphygmomanometer/auscultatory readings where available. ARIC already uses sphygmomanometer-family labels ("Seated random-zero average", "Seated sphygmomanometer average"). Making this global would require:
> (1) auditing all cohort bp_diastolic.yaml files for device type,
> (2) adding "Sphygmomanometer average" blocks to any cohort that currently only has Omron-derived blocks, and
> (3) changing the global `preferred_method` for `OMOP:4154790` from "Analysis derived" to "Sphygmomanometer average".
> The current per-cohort override is an interim fix to unblock JHS comparison; global standardization needs domain scientist sign-off.

### `JHS-ingest/bp_diastolic.yaml` (HV repo — JHS local)
- **Renamed 3 "Analysis derived" method_type labels → "Omron derived"** on the Exam 1/2/3 analysis-derived blocks (pht008729, pht008730, pht008731).
  - Labels now accurately reflect the instrument source (Omron automated device).
  - The extractor's JHS override selects "Sphygmomanometer average" instead, so the Omron blocks remain in the pipeline output (no data loss) but are not selected for cross-cohort comparison.
  - The existing "Sphygmomanometer average" block at line ~158 (pht001974 phv00128377) is unchanged.
  - Only JHS affected.

---

## 2026-04-01 (session 7)

### `extract_bdc_all.py`
- **Bug fix — `preferred_method` filter ordering**: The filter was applied AFTER
  `_select_baseline_visit()`, which internally deduplicates to 1 row per
  participant (earliest age). For MESA body weight, recalled-weight blocks have
  hardcoded age=7,300 days (20 yr), so they always beat current measured blocks
  (~16,000+ days) in the earliest-first dedup. By the time the filter ran, only
  recalled-weight rows remained — `method_match.empty == True` — and the filter
  silently skipped. Fix: moved `preferred_method` filter to apply to `subset`
  BEFORE calling `_select_baseline_visit()`. Affects any cohort with
  `preferred_method` configured (currently only MESA body weight).

### `match_quality_table.py`
- **New M-grade — MESA `antihypertensive_meds_1`** [MULTI_VISIT_AGGREGATION]:
  MESA pipeline output labels all visit records as 'HEALTH_EXAMINATION', so
  the DrugExposure baseline-visit filter cannot isolate Exam 1 and falls back
  to all-visits aggregation (Yes=57.6% BDC vs Yes=39.2% TOPMed). The ~18pp
  excess reflects participants who started antihypertensives after Exam 1.
  Root cause is MESA visit labeling in pipeline output, not a YAML error.

---

## 2026-04-01 (session 6)

### `extract_bdc_all.py`
- **New `preferred_method` for body weight (`OBA:VT0001259`)**: Added
  `"preferred_method": "Current measured"` to the BDC_MEASUREMENT_MAP entry.
  MESA's `bdy_wgt.yaml` includes 6 recalled-weight blocks (age 20 and age 40
  retrospective self-report) alongside 5 current measured exam weight blocks,
  all sharing `observation_type: OMOP:4099154`. Without the filter, the
  earliest-per-participant dedup selected recalled age-20 weights (hardcoded
  age 7,300 days) over actual exam weights, depressing the BDC mean by 8.3 kg
  (71.2 vs TOPMed 79.5). The preferred_method filter now selects only
  "Current measured" blocks before dedup. Affects MESA only.

---

## 2026-04-01 (session 5)

### `match_quality_table.py`
- **Added JHS PAD methodological diff entry** (`KNOWN_METHODOLOGICAL_DIFFS`):
  - `("JHS", "pad_prior_1")` — `AGGREGATION_DIFF`
  - BDC sources from pht008725 afulong PADEVER ("Has a doctor EVER said you have PAD?") — a cumulative lifetime question at every annual follow-up contact. Any-positive dedup accumulates incident PAD cases developed after baseline, inflating prevalence (BDC 6.0% vs TOPMed 2.7%). No Visit 1 baseline PAD variable exists in JHS dbGaP. This is a known source limitation, not a YAML error. PAD now grades M (was C). JHS summary: A=8 B=1 C=3 D=1 M=3.
  - Only JHS affected.
- **Added JHS smoking methodological diff entries** (`KNOWN_METHODOLOGICAL_DIFFS`):
  - `("JHS", "current_smoker_baseline_1")` — `AGGREGATION_DIFF`
  - `("JHS", "ever_smoker_baseline_1")` — `AGGREGATION_DIFF`
  - Both variables previously graded D due to BDC N=2,743 vs TOPMed N=3,505/3,530 (~762-participant gap, 29.4% BDC missing). Investigation confirmed this is a deliberate source scope difference: BDC maps two Visit 1 tables (pht001977 toba + pht008729 analysis1). Alternative sources evaluated and rejected: analysis3 (pht008731) has `everSmoker` only — no `currentSmoker` field — which would create asymmetric N across the two smoking variables; afulong (pht008725) is an annual follow-up form, not Visit 1 baseline. TOPMed's baseline_covariates file used a first-available-across-all-exams aggregation strategy. BDC correctly restricts to Visit 1; the gap reflects participants with smoking data only at later exams.
  - Both variables now grade **M** (was **D**). JHS summary: A=8 B=1 C=4 D=1 M=2.
  - Only JHS affected.

---

## 2026-04-01 (session 4)

### `match_quality_table.py`
- **Core variable set trimmed from 25 → 20**: removed `hdl_1`, `hematocrit_vfr_bld_1`, `hemoglobin_mcnc_bld_1`, `wbc_ncnc_bld_1`, and `coronary_angioplasty_prior_1` after reviewing per-variable grades across all 8 cohorts:
  - `hdl_1` — D in CARDIA (17% SD delta) and JHS (11% SD + 16pp miss_diff); score 6
  - `hematocrit_vfr_bld_1` — D in FHS (16pp miss_diff), C in CHS/MESA; CBC coverage gaps; score 7
  - `hemoglobin_mcnc_bld_1` — D in FHS (18pp miss_diff), C in CHS/MESA; CBC coverage gaps; score 7
  - `wbc_ncnc_bld_1` — D in CARDIA (×1000 units bug: 37 vs 6), D in FHS (31% SD delta); score 7
  - `coronary_angioplasty_prior_1` — D in MESA (22.5pp miss_diff); only 5 cohorts in scope; score 4
  - All five are retained in `--all-vars` output and documented in the excluded variables table in `QC/reports/BDC-vs-TOPMed-Comparison-Scope-2026-04-01.md` with re-inclusion criteria.
  - `platelet_ncnc_bld_1`, `rbc_ncnc_bld_1`, `mch_entmass_rbc_1` remain in the CBC group (3 variables).
  - Updated header comment: "20 variables" (was "28 variables" — comment was stale from before session 3 trim).
- All cohorts affected.

---

## 2026-04-01 (session 3)

### `match_quality_table.py`
- **Core variable set trimmed from 28 → 25**: removed `ldl_1`, `crp_1`, and `sleep_duration_1` after cross-cohort grade analysis showed these three variables score poorly and inconsistently:
  - `ldl_1` — D in FHS and JHS, C in CARDIA and CHS (score 10/24)
  - `crp_1` — D in CARDIA and CHS, C in FHS and JHS (score 10/24)
  - `sleep_duration_1` — D in CARDIA, CHS, WHI due to active units bug (raw coded value emitted instead of hours)
  - All three are retained in `--all-vars` output and documented in the excluded variables table in `QC/reports/BDC-vs-TOPMed-Comparison-Scope-2026-04-01.md` with re-inclusion criteria.
- All cohorts affected.

---

## 2026-04-01 (session 2)

### `match_quality_table.py`
- **Core variable set — default scope**: added `CORE_VARIABLES` frozenset (28 variables) as the default comparison scope. The script now compares only core variables unless `--all-vars` is passed. Rationale: the full matched set includes variables present in only 1–2 cohorts or with no meaningful cross-cohort story; the core set is defined as variables present in both BDC and TOPMed extracts in at least 5 of 8 cohorts, covering demographics, anthropometrics, BP, smoking, lipids, CBC, inflammation, prior CVD history, and sleep. Defined in `QC/reports/BDC-vs-TOPMed-Comparison-Scope-2026-04-01.md`.
- **`--all-vars` flag**: when passed, restores the previous behaviour of comparing all matched variables. Useful for full audits and regression checking. Replaces positional-only argument parsing with `argparse`.
- **Scope header line**: output now opens with `Scope: core variables (N of 28 present)` or `Scope: all matched variables` so the mode is visible in saved output files.
- All cohorts affected.

### `batch_scorecard.py`
- **`--all-vars` flag**: mirrors `match_quality_table.py`; default is core variables. Passes `all_vars` parameter through to `run_cohort_scorecard()`.
- **M-grade support**: imported `CORE_VARIABLES` and `KNOWN_METHODOLOGICAL_DIFFS` from `match_quality_table`; `grade_variable()` now accepts a `cohort` parameter and applies M-grade overrides. Grade summary table now includes M column.
- **Cohort name resolution**: `run_cohort_scorecard()` now reads cohort name from `t["metadata"]["cohort"]` (used for M-grade lookup) rather than relying only on filename stem.
- All cohorts affected.

---

## 2026-04-01

### `extract_bdc_all.py`
- **Bug fix — DrugExposure baseline filter drops to 1 row per participant**:
  `process_drugs()` was calling `_select_baseline_visit()` for the baseline
  filter. When no named baseline visit matched (e.g. all visits resolved to
  `HEALTH_EXAMINATION`), `_select_baseline_visit()` fell to its
  "earliest-per-participant" path which calls `drop_duplicates(subset=
  [participant], keep="first")` — collapsing each participant from many drug
  rows to exactly 1. With only 1 drug row per participant, most participants'
  ATC:C02/C09A/C09C/C03 rows were discarded, producing 32/8,296 (0.4%) for
  antihypertensive medications instead of the expected ~39%.

  Fix: replaced the `_select_baseline_visit()` call inside `process_drugs()`
  with an inline drug-specific filter that preserves ALL rows per participant:
  - Path A: if `resolve_baseline_visits()` matches named visits, keep all rows
    for those visit labels (no dedup).
  - Path B: if no label match, group by participant and keep all rows where
    `age_at_observation == min(age_at_observation)` for that participant (proxy
    for Exam 1 / baseline). Falls back to all rows if age is unavailable.

  This fix is isolated to `process_drugs()` and has no effect on
  `_select_baseline_visit()` or any other entity processor (MeasurementObservation,
  Condition, Procedure). For all cohorts with named baseline visits (ARIC,
  CARDIA, CHS, COPDGene, FHS, HCHS-SOL, JHS, SPIROMICS, WHI), Path A fires
  and behavior is identical to before.

- **Bug fix -- `_select_baseline_visit()` age-sort in earliest-per-participant
  fallback**: when all visits resolve to the same enum label (e.g.
  `HEALTH_EXAMINATION`), the previous sort was by visit label -- a no-op,
  leaving dedup order dependent on file-load order. For MESA, this caused CAC
  Score to drop from N=8,221 to N=3,244 (many Exam 2-4 rows with null
  value_decimal selected instead of Exam 1 rows with real values).

  Fix: "earliest-per-participant" now sorts by `age_at_observation` ascending
  (youngest = Exam 1 baseline) before `drop_duplicates()`. A temp `_age_sort`
  column is added via `pd.to_numeric(..., errors="coerce")`; NaN ages sort last.
  Visit label is retained as a secondary sort key for tie-breaking.

  Note: this fix improves MeasurementObservation selection. DrugExposure
  is now handled separately (see fix above) and does not use this fallback path.

- **Bug fix -- visit label column priority in `load_visit_mapping()`**: the
  function previously tried `visit_category` before `name`. In the new MESA
  pipeline run (2026-04-01 11:50), `visit_category` is populated with the
  standardized bdchm enum value `HEALTH_EXAMINATION` for every one of the 26
  MESA visits, making all visits indistinguishable. The extractor fell back to
  "earliest-per-participant" deduplication with no baseline filter, causing 17
  D-grades (vs 3 in the previous run) including a +8.3 kg weight mean shift and
  BP/cholesterol N drops of ~1,000 participants.
  
  Fix: column candidate order changed to `label` → `name` → `visit_category`;
  the first column with **more than one unique non-null value** is used. If
  `label` has descriptive names (e.g. "MESA CLASSIC EXAM 1"), it will be selected
  over the enum `visit_category`. If all candidates are single-valued, the
  last candidate is used as before.
  
  Added diagnostic: after loading the mapping, now prints the unique visit labels
  found (up to 10) so visit-label regressions are immediately visible in logs.
  
  **Action required**: re-run `extract_bdc_all.py` for MESA in the enclave with
  the updated script to confirm label column is resolved correctly.

- **MESA extractor map overhaul** — two categories of fixes:
  1. *Alias additions*: MESA YAML files use OMOP codes where the map expected OBA
     codes (e.g. `OMOP:607590` for height, `OMOP:4099154` for weight,
     `OMOP:3038553` for BMI, `OMOP:4151358` for hematocrit, `OMOP:4094758` for
     hemoglobin, `OMOP:3006315` for basophils, etc.). Added as `aliases` so
     existing primary keys match both code conventions.
  2. *New map entries*: 14 variables were entirely absent from
     `BDC_MEASUREMENT_MAP`: lymphocytes (`OMOP:37208689`), neutrophils
     (`OMOP:37208699`), E-selectin (`OBA:2052778`), TNF-α (`OBA:2051979`),
     TNF-α-R1 (`OBA:2051975`), LP-PLA2 activity (`OMOP:36305170`), LP-PLA2 mass
     (`OMOP:3041450`), CD40 (`OMOP:4209737`), MMP9 (`OMOP:40761106`), IL-10
     (`OMOP:3004578`), CAC score (`OMOP:42872742`), CAC volume (`OMOP:4166120`),
     carotid IMT (`OMOP:4138462`), carotid stenosis left/right
     (`OMOP:43020498`/`43021859`).
  3. `var_type` for carotid stenosis corrected from `continuous` to `categorical`
     (YAML stores coded scale via `value_concept`, not a raw numeric).
- **`BDC_CONDITION_MAP` additions**: CABG (`OMOP:4336464`) and coronary
  angioplasty (`OMOP:4184832`) were already in `BDC_PROCEDURE_MAP` but MESA maps
  these as `Condition` entities; added to `BDC_CONDITION_MAP` so Condition.tsv
  rows are matched. Carotid plaque (`OMOP:4102124`) added as new entry.

### `match_quality_table.py`
- **M-grade mechanism**: added `KNOWN_METHODOLOGICAL_DIFFS` dict. Variables
  listed there receive grade `M` (Methodological) instead of `D`. Stats are still
  displayed in full for transparency. Grade summary now shows A/B/C/D/M counts
  with a legend line.
- **New M-grade entries for MESA** (5 added this date):
  - `cabg_prior_1` [UNION_OF_FORMS] — BDC sources from FamilyExamMain
    self-report; TOPMed sources from adjudicated incident outcomes table
    (Classic-only, CVD-free enrollment).
  - `carotid_plaque_1` [LABEL_REMAP] — BDC uses "Affected"/"Unaffected" vs
    TOPMed integer codes "0"/"1"; underlying prevalence closely aligned (4.4pp
    real diff).
  - `bmi_baseline_1` [EXTENDED_COVERAGE] — BDC covers spirometry sub-study
    tables only (N=4,270); TOPMed derives BMI from universal height+weight
    (N=8,262). Mean nearly identical where data overlaps.
  - `cimt_1` [VISIT_SCOPE_DIFF] — Classic Exam 1 block matches; Air Exam 5
    block is follow-up, not baseline. No Family block exists in YAML. Mean IMT
    identical (0.74mm). cimt_2 cannot be distinguished (same OMOP code).
  - Pre-existing WHI `antihypertensive_meds_1` [UNION_OF_FORMS] entry retained.
- **Pre-existing MESA M-grade entries retained** (4 from prior session):
  `angina_prior_1`, `mi_prior_1`, `pad_prior_1` [UNION_OF_FORMS /
  EXTENDED_COVERAGE], `hispanic_or_latino_1` [LABEL_REMAP].
- **MESA matched variable count**: 21 → 50 after extractor map and translation
  fixes. Grade summary: A=27 B=10 C=2 D=3 M=8.
- **New M-grade entries for FHS** (3 added 2026-04-01):
  - `hdl_1` [EXTENDED_COVERAGE] — BDC hdl.yaml starts at FHS ORIGINAL EXAM 15
    (1977, earliest HDL assay in dbGaP); Original Cohort Exam 1 (1948) has no HDL
    data, so the baseline filter falls through and picks Exam 15 for ~5,079
    Original Cohort participants. TOPMed treats these as missing for its '_1'
    baseline. Mean delta negligible (-0.45 mg/dL, <1%); no data accuracy issue.
    BDC N=13,138 vs TOPMed N=9,488.
  - `total_cholesterol_1` [ASSAY_ERA_DIFF] — BDC baseline filter matches FHS
    ORIGINAL EXAM 1 (1948), pulling ~5,079 cholesterol values measured with
    non-enzymatic Abell-Kendall assay. This assay produces results not directly
    comparable to modern enzymatic methods used in post-1980 exams. BDC mean
    +6.67 mg/dL higher (200.9 vs 194.2 mg/dL). YAML is correct; discrepancy
    reflects assay era difference on Original Cohort Exam 1 data. Decision to
    exclude pre-enzymatic era data is a pending domain science question.
    BDC N=13,009 vs TOPMed N=9,507.
  - `triglycerides_1` [ASSAY_ERA_DIFF] — Same assay era issue. TG data starts at
    FHS ORIGINAL EXAM 7 (no Exam 1 TG data), so baseline filter falls through and
    picks early-era TG for Original Cohort. Early non-enzymatic colorimetric
    methods produce elevated readings vs modern enzymatic assays. BDC mean +5.78
    mg/dL higher (113.1 vs 107.3 mg/dL). Same pending domain science decision.
    BDC N=12,705 vs TOPMed N=9,505.
- **FHS grade summary** (after ethnicity fix + 3 new M entries):
  D=9, M=3, C=9, B=1, A=7 (was D=12, M=0 before this session).

### `translate_bdc_json.py` *(new file)*
- New utility script. Post-processes a previously-generated BDC summary JSON to
  rename raw concept-code keys (e.g. `OMOP:607590`) to canonical TOPMed variable
  names (e.g. `height_baseline_1`) using the current `BDC_MEASUREMENT_MAP`,
  `BDC_CONDITION_MAP`, and `BDC_PROCEDURE_MAP`.
- Intended use: apply the current map retroactively to a stale JSON without
  re-running the full extraction from TSV source files.
- Handles merging when two source codes alias to the same canonical name (keeps
  the entry with higher `n_valid`).

---

## 2026-03-31

### `extract_bdc_all.py`
- **Major expansion** (~400 lines added). Principal additions:
  - Per-cohort `BASELINE_VISIT_CONFIG` dict with exact-match lists and regex
    fallback patterns for all 9 cohorts. Replaces brittle string comparisons that
    were silently missing visits (old config had incorrect labels like "ARIC Visit
    1", "JHS Visit 1", "MESA Exam 1", "WHI PM 80").
  - `resolve_baseline_visits()` function centralises baseline-visit resolution
    with a two-pass algorithm (exact → regex fallback) and diagnostic logging.
  - `BASELINE_VISIT_PREFS` backward-compatibility alias.
  - Auto-discovery improvements: `_ci_glob_processed_dirs()` for
    case-insensitive cohort folder matching; `discover_all_cohorts()` and
    `discover_mapped_data_dirs()` now handle HCHS_SOL → HCHS folder-alias.
  - Smoking map: added `OMOP:45885135` (Unknown if ever smoked) to
    `OMOP_SMOKING_MAP`.
  - **LDL bug identified and documented**: primary key `OBA:VT0001815` was always
    dead (no cohort uses that CURIE); `OBA:VT0000181` added as first alias so LDL
    now matches. Dead key retained as map key with inline comment explaining the
    history.
  - IL-6 (`OBA:2052890`), ICAM-1 (`OMOP:4284103`), and sleep duration
    (`OBA:2040171`) added as new measurement map entries (previously missing,
    causing these variables to appear as TOPMed-only).

---

## 2026-03-30

### `extract_bdc_all.py`
- **`preferred_method` filter** added to `BDC_MEASUREMENT_MAP` entries for BP
  systolic, BP diastolic, and HDL. When `method_type` data is present in the TSV,
  the extractor filters to rows matching `preferred_method` (e.g. "Analysis
  derived") before deduplication. This selects the correct single value per
  participant when multi-instrument YAML blocks produce one record per instrument.
- Baseline visit configuration updated: corrected labels for ARIC ("ARIC Visit 1"
  → "ARIC EXAM 1"), JHS ("JHS Visit 1" → "JHS Exam 1"), and MESA ("MESA Exam 1"
  → "MESA CLASSIC EXAM 1" / "MESA FAMILY" / "MESA AIR EXAM").
- General cleanup and refactoring pass.

---

## 2026-03-29

### `extract_bdc_all.py`
- Baseline visit filtering improvements; additional cohort-specific label
  corrections.
- Diagnostic logging enhancements for baseline visit resolution.

### `validate_participant_completeness.py`
- New helper functions for anonymized phenotype completeness profile comparison.

---

## 2026-03-28

### `extract_bdc_all.py`
- **Condition entity processing**: added full support for extracting Condition.tsv
  rows into match-quality variables (prior conditions, incident flags). Conditions
  are keyed by `condition_concept` CURIE via `BDC_CONDITION_MAP`.
- **Procedure entity processing**: added extraction of Procedure.tsv rows via
  `BDC_PROCEDURE_MAP` (CABG, coronary angioplasty).
- Drug exposure processing improvements for ATC-coded medications.
- Smoking observation extraction: full `OMOP_SMOKING_MAP` for current/former/never
  codes; `SMOKING_OBSERVATION_TYPE` constant.

### `compare_bdc_topmed.py`
- Major expansion (~450 lines added). Side-by-side report generation from two
  JSON summaries: participant count comparison, per-variable mean/distribution
  tables, missingness analysis, and grade-level rollup.

---

## 2026-03-27

### `extract_bdc_all.py`
- Initial full multi-entity extraction architecture: MeasurementObservation,
  Condition, DrugExposure, Procedure, Observation, Demography.
- `BDC_MEASUREMENT_MAP` established with initial set of continuous variables
  (BP, lipids, CBC, glucose, CRP, fibrinogen, serum creatinine).
- Baseline visit filtering: first implementation of per-cohort visit label
  resolution.

### `match_quality_table.py` *(new file)*
- Initial version: per-variable A/B/C/D grading table for continuous and
  categorical variables. Grade thresholds: A < 0.02 SD / <5pp; B < 0.05 SD /
  <3pp; C < 0.10 SD / <10pp; D otherwise.

### `compare_bdc_topmed.py`
- Incremental additions to side-by-side report.

---

## 2026-04-01

### `extract_bdc_all.py`
- **Coalesce dedup for measurements** (affects CHS; safe no-op for all other cohorts).

  Replaced `drop_duplicates(subset=["associated_participant"], keep="first")` with
  a `groupby().agg("first")` coalesce in both the `BDC_MEASUREMENT_MAP` loop and
  the Discovery loop inside `process_measurements()`.

  **Why:** CHS has three baseline tables (pht001450 BASE1, pht001452 BASEBOTH,
  pht001490 YR5NEW) all mapped to the `CHS BASELINE 2` or `CHS BASELINE BOTH`
  visit labels. For new-cohort participants (N=628), `_select_baseline_visit()`
  correctly collects rows from all three tables, but the subsequent age-sort +
  `drop_duplicates(keep="first")` silently kept the first-by-age row even when its
  `value_quantity__value_decimal` was null. The valid measurement in a later row
  (same participant, different table) was then discarded. For example, a new-cohort
  participant had a null height in BASE1 and a valid 165.2 cm in BASEBOTH — the
  old logic kept the null, inflating missingness to ~11-13%.

  The coalesce approach preserves the age-sort ordering (rows are already sorted
  before groupby by `_select_baseline_visit`) and takes the first non-null value
  per column, so participants with a null in one table get their valid value from
  another.

  **Cohorts affected:** CHS only (the only cohort where a participant can appear
  in multiple distinct baseline tables at the same visit label). For all other
  cohorts each participant has at most one baseline row after the visit filter,
  so `agg("first")` is identical to `drop_duplicates(keep="first")`.

  **Expected grade improvement:** Height, Body weight, Hematocrit, Hemoglobin,
  Platelet count, HDL, Triglycerides, LDL — all had ~11-13% missingness vs
  TOPMed's 1-2%. Fix expected to restore these to A/B grades.

---

## 2026-03-26

### `extract_bdc_all.py`
- Fixes to participant N counting and deduplication logic (one row per
  participant after baseline-visit filter).
- OMOP smoking status codes corrected after Athena verification (OMOP:45883459
  is a Fagerström test score, not a smoking status → removed from map).

---

## 2026-03-24–25

### `extract_bdc_all.py`
- Iterative improvements to multi-cohort extraction: FHS multi-generation
  baseline handling, WHI screening visit, HCHS single-exam cohort.
- Plausibility range filtering added to continuous measurements (values outside
  `plausible_lo`/`plausible_hi` excluded from stats).

### `validate_participant_completeness.py` *(new file)*
- Full implementation: builds anonymized per-participant phenotype completeness
  vectors from both TOPMed and BDC outputs; compares completeness profiles at
  aggregate level.

---

## 2026-03-23

### `extract_bdc_all.py`
- Initial FHS, WHI, and HCHS cohort support added.
- Consent-group concatenation: reads multiple mapped-data directories and
  concatenates across consent groups before summarizing.

### `compare_bdc_topmed.py`
- Initial implementation of side-by-side JSON comparison report.

---

## 2026-03-22

### `extract_bdc_all.py` *(new file)*
- Initial creation (~1,300 lines). Established the core architecture:
  multi-entity TSV loading, aggregate-only JSON output, per-cohort
  auto-discovery of dm-bip output directories, `Tee` class for simultaneous
  screen+log output.

### `compare_bdc_topmed.py` *(new file)*
- Initial creation (~340 lines).

---

## 2026-03-21

### `extract_topmed_all.py` *(new file)*
- Initial creation: extracts TOPMed DCC EAV flat files into per-cohort JSON
  summaries matching the output format of `extract_bdc_all.py`.

### `topmed_compare_config.py` *(new file)*
- Initial creation: central configuration for 62 matched variables, 9 cohort
  definitions, and value-mapping dictionaries for categorical variables.

### `__init__.py`
- Package initialisation.
