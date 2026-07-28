# Migrating the label source from `harmonized_vars.tsv` to Table S1

**Status:** review sheet built (2026-07-27); Anne reviewed it (2026-07-28). Do
the code migration in a fresh session.

**START HERE (next session):** Anne's feedback is IN THE SHEET, not in text.
Read it from the reviewed workbook she returned — `~/Downloads/Data
Harmonization Supplementary Data.xlsx`, tab **`Table S1 augmented`** (the tab
carrying our `var_name` / `status` / `note` columns; header confirmed
2026-07-28). If a newer download exists, prefer the most recent. The file may
be open in Excel (a `~$…` lock file alongside it) — read a copy if openpyxl
balks. Reconcile her decisions on the 12 review rows (6 renamed-label var_name
confirmations, 4 code mismatches: Basophils / CD40 / Cigarette smoking / IL-18,
2 stray codes: vege_serving OMOP:37311566 and lympho_ct OBA:VT0000217) and the
6 ignore rows into the migration below before touching code.

## Background

Table S4 (`transform_assessment/spec_phv_report.py`) and Table S5
(`hv_dataqc/extract_harmonized/`) resolve a harmonized variable's
`observation_type` concept code (OMOP/OBA) to a publication label via
`hv_dataqc/extract_harmonized/label_map.py`, which reads
`hv_dataqc/extract_harmonized/config/harmonized_vars.tsv`.

That TSV was a manual export of the curator master sheet, undated and drifted.
Anne's newer **Table S1** ("Data Harmonization Supplementary Data" workbook
`1PDaX266_H0haa0aabMYQ6UNtEKT5-ClMarP0FvNntN8`, tab S1, owner
annethessen@gmail.com) supersedes it. S1 has 7 columns: BDCHM Element,
Variable Label, Data Type, UCUM Unit, Ontology CURIE, OMOP Concept ID,
Variable Description.

The raw S1 download is **not** kept in the repo (it is one Drive download away
and the review sheet below preserves every S1 column). To regenerate the review
sheet, re-download the S1 tab first, then re-run the build script.

## What S1 changes (measured, not assumed)

- **OBA coverage up: 58 -> 73 rows.** Newly resolvable OBA codes include
  cases S4 currently can't resolve and falls back to the spec stem:
  Lymphocytes count (`OBA:VT0000717`), AST SGOT, Hemoglobin A1c, D-Dimer,
  Troponin, Platelet count, IL-1beta, IL-10, and others.
- **Label text normalized** on 23 shared codes — mostly capitalization
  (`Bilirubin total` -> `Bilirubin Total`), which *fixes* the S4/S5 config
  drift previously worked around. A few are semantic (`Alcohol` ->
  `Alcohol Consumption`, `NT pro BNP` -> `BNP`, `Stroke` -> `Stroke status`).
- **Covers non-Measurement elements** the old TSV omitted: Condition (20),
  DrugExposure (17), Procedure (3), Demography (3), Person (2),
  SdohObservation (2), Observation (1) — i.e. S6/categorical territory.
- **No `var_name` column.** The old TSV had one; `spec_phv_report.py`'s
  `load_var_labels` uses it as the stem->label fallback. Recovered by matching
  S1 labels back to the old TSV's `var_label` (142/148 exact/CI; the other 6
  are renamed labels, recovered by old label text). All 148 get a var_name.

## The review sheet

`hv_dataqc/extract_harmonized/config/TableS1_review.xlsx` (generated; see the
build script archived with the session). Emitted as `.xlsx`, not `.tsv`: xlsx
is UTF-8 native (a TSV re-import guessed Windows-1252 and mangled em-dashes and
the Greek letters in Anne's IL-1β / 8-epi-PGF2α descriptions), and it carries
formatting so the sheet drops in looking like S1 without manual re-styling
(bold frozen header, wrapped note/description columns, review rows peach-filled,
ignore rows green-filled). The Ontology CURIE column is left unstyled — S1's own
yellow cells are Anne's annotation of the newly-added OBA codes and reapply on
paste-back. S1 + adjacent `var_name` / `status` / `note` columns so one sheet
carries everything for Anne:

Columns: `BDCHM Element, Variable Label, var_name, status, note, Data Type,
UCUM Unit, Ontology CURIE, OMOP Concept ID, Variable Description`.

`status`: blank = normal; `ignore` = drop this obs_type; `review` = needs a
decision. 139 variable rows, 12 review, 6 ignore.

**Review rows (12) for Anne:**
- 6 renamed labels — confirm the carried-over var_name still applies
  (Alcohol Consumption, CRP c-reactive protein, Fruit consumption,
  Sleep apnea status, Stroke status, Vegetable consumption).
- 4 code mismatches — a live spec emits a different (or absent) OMOP than S1:
  Basophils Count (spec `OMOP:3006315` vs S1 `OMOP:4172647`), CD40 in blood
  (spec `OMOP:4209737` vs S1 OBA-only), Cigarette smoking (spec `OMOP:4282779`
  vs S1 `OMOP:35811013`), Interleukin 18 (spec `OMOP:3043144`, no S1 row).
- 2 stray spec codes: FHS vege_serving also emits `OMOP:37311566` (not in S1);
  ARIC lympho_ct emits `OBA:VT0000217` which S1 resolves to *White blood cell
  count*, not Lymphocytes — possible mis-code.

**Ignore rows (6):** the spirometry-metadata OMOP codes (`3002094, 3005600,
3011708, 3022891, 3024594, 4196583`) Anne flagged 2026-07-07 — now declarative
in the sheet instead of hardcoded in `s4_layout.yaml`.

## Code migration (next session, after Anne)

1. **`label_map.py`** — read the S1-derived file: `Variable Label` -> label,
   `OMOP Concept ID` (already `OMOP:`-prefixed) and `Ontology CURIE` (OBA) as
   code keys, derived `var_name` for the bare-uppercase key + `BARE_NAME_ALIASES`.
   Preserve all three key forms so `bdc_label` and S5 aggregation are unchanged.
2. **`spec_phv_report.py`** — point `load_label_map` / `load_var_labels` at the
   S1 file; column-name updates only.
3. **Retire `s4_layout.yaml` (goal — verify first):**
   - `cohorts` (row 3) and `variables` (col A) — derive from the S4 template
     or from S1's `Variable Label` column. Open question: which source, and
     whether to fetch the template at build time (network) vs. keep an in-repo
     list. Decide in the plan.
   - `aliases` — **all 8 confirmed dead under S1** (each spec's real
     observation_type code resolves through S1 to the template label; verified
     2026-07-27). Drop the map. Re-verify by resolving live spec codes after
     the label_map swap before deleting.
   - `ignore_observation_types` — moves to S1 `status=ignore` rows; pipeline
     reads them from the sheet.
   - `unmatched_note` — keep exposed, not hidden in code (Sigfried's
     preference: exceptions live in declarative sources Anne can see/edit).
4. **`harmonized_vars.tsv`** — retire. Keep only as provenance for the derived
   var_names (header comment marking it dead); nothing in the pipeline reads it.
5. **Tests** — update `test_label_map.py` / `test_spec_phv_report.py` fixtures
   to the S1 schema; add a regression test asserting the newly-covered OBA
   codes (Lymphocytes count, AST SGOT, ...) now resolve (the gain, not just
   no-loss).

## Verification before committing the migration

Run the S4 build against real specs on SB and confirm: (a) no row regresses to
a bare-stem label, (b) the newly-covered OBA vars resolve to real labels, and
(c) BP still emits 2 rows (multi-concept split intact).
