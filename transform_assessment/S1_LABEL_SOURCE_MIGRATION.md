# Migrating the label source from `harmonized_vars.tsv` to Table S1

**Status:** review sheet built (2026-07-27); reviewed and returned (2026-07-28);
review rows reconciled and the resulting spec corrections applied (2026-08-03).
Do the code migration next.

**Spec-side outcome:** reconciling the specs against S1 surfaced four wrong
`observation_type` concept codes, now corrected in
`priority_variables_transform/` — see
[`SPEC_CODE_CORRECTIONS_20260803.md`](SPEC_CODE_CORRECTIONS_20260803.md), which
is the document to hand to the transform spec owner for review. Those edits are
independent of the label_map migration below and can land separately.

**Review outcome (2026-08-03) — all 12 review rows resolved.** The curator's
decisions came back as *threaded cell comments* on the `note` column of the
`Table S1 augmented` tab, not as cell edits (openpyxl: load without
`read_only`, then read `cell.comment.text`). Resolutions:

- **6 renamed labels** (Alcohol Consumption, CRP c-reactive protein, Fruit
  consumption, Sleep apnea status, Stroke status, Vegetable consumption) —
  "confirming it still applies". Carried-over `var_name`s stand; no change.
- **Basophils Count** — S1's `OMOP:4172647` was the error; corrected in S1 to
  the spec's `OMOP:3006315`.
- **CD40 / Cigarette smoking** — S1 authoritative, specs wrong. Fixed in the
  specs.
- **IL-18** — added as a real S1 row (`OMOP:3043144`).
- **lympho_ct `OBA:VT0000217`** — confirmed an ARIC-only typo for
  `OBA:VT0000717`. Fixed in the spec.
- **vege_serving `OMOP:37311566`** — resolved the *opposite* way from first
  reading: `OMOP:4042886` (Vegetable, a *substance*) is wrong for a
  servings-intake measurement, and the six specs using it were corrected to
  `OMOP:37311566`. S1's row was corrected to match. Rationale in
  `SPEC_CODE_CORRECTIONS_20260803.md` §2.

**Sheet end-state:** the `note` column is scaffolding for this review round and
is dropped once the review rows are cleared — no code reads it. `status` is
retained: the pipeline reads `status=ignore` to replace
`ignore_observation_types` in `config/s4_layout.yaml` (consumed as a plain set
of codes at `spec_phv_report.py:342`). `var_name` is retained — `label_map.py`
and `spec_phv_report.py` both key on it and S1 has no native equivalent. A new
`Deprecated Codes` column records superseded codes (see open question below).

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
decision. It went out with 139 variable rows, 12 review, 6 ignore. All 12
review rows came back resolved (see the review outcome above); once they are
cleared, `review` disappears as a value and `status` carries only `ignore`.

**Ignore rows (6):** the spirometry-metadata OMOP codes (`3002094, 3005600,
3011708, 3022891, 3024594, 4196583`) flagged 2026-07-07 — now declarative in
the sheet instead of hardcoded in `s4_layout.yaml`.

## Code migration (next session, after Anne)

1. **`label_map.py`** — read the S1-derived file: `Variable Label` -> label,
   `OMOP Concept ID` (already `OMOP:`-prefixed) and `Ontology CURIE` (OBA) as
   code keys, derived `var_name` for the bare-uppercase key + `BARE_NAME_ALIASES`.
   Preserve all three key forms so `bdc_label` and S5 aggregation are unchanged.

   **Decide: does `Deprecated Codes` become a fourth key form?** The reviewed
   sheet added this column to record codes a variable *used* to carry (e.g.
   `OMOP:4209737` on CD40, `OMOP:4282779` on Cigarette smoking,
   `OMOP:4042886` on Vegetable consumption). Mapping them to the same label
   would make S4 resolve historical/uncorrected specs instead of dumping them
   in the `unmatched` block — shrinking that block rather than just relocating
   it. Argues against: it silently masks specs that still carry a corrected
   code, which is exactly what the unmatched block is for surfacing. A middle
   option is to resolve them but mark the row, so they are visible and not
   silently absorbed.
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
     the label_map swap before deleting — note the 2026-07-27 check predates
     the four spec code corrections, so redo it against the current specs.
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
