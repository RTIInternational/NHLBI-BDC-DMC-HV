# transform_assessment

Generates Tables S4/S5 for the Data Harmonization supplementary data, sourced
from the transform specs in `priority_variables_transform/` rather than from the
curator spreadsheets. Table S1 is the concept-code → publication-label source.

## Open questions for the team

Live decisions blocking or shaping this work. Nothing here is settleable without
the person named.

**For the curator — [`S1_QUESTIONS_20260803.md`](S1_QUESTIONS_20260803.md).**
Drafted, reviewed, **still unsent** (as of 2026-08-04; none of its questions have
been resolved since). Three questions: whether LTRC/SPIROMICS should be S4
columns, seven `var_name` spellings that drift from S1, and thirteen spec
variables with no S1 row. It was written to be sent "after the next S4 run" so it
could cite real numbers — but given the state of those numbers (see the count
investigation below), that gate may never cleanly arrive. Consider sending it
independently.

**For the schema owner — specs and BDCHM enums disagree.** Raised in
[`history/SPEC_CODE_CORRECTIONS_20260803.md`](history/SPEC_CODE_CORRECTIONS_20260803.md)
§"Open items"; unresolved:

- `cig_smok` now uses the curator-directed `OMOP:35811013`, but
  `MeasurementObservationTypeEnum` binds `SMOKING_STATUS` to the old
  `OMOP:4282779`. One of them has to move. Same shape, less urgent, for
  `vege_serving` `OMOP:37311566` and Basophils `OMOP:3006315`.
- `edu_lvl` has four different shapes across six cohorts, and neither candidate
  concept code is a permissible `observation_type` value today.
- `alpha1_antitrypsin` (LTRC) is correctly coded but has no Table S1 row.
- 36 of 127 distinct `observation_type` codes in the live specs are not
  permissible enum values. Most predate this work; worth a reconciliation pass.

**For CARDIA spec owners — asked 2026-08-04 in Slack, awaiting answer.** Seven
`value_decimal` expressions in `CARDIA-ingest/alcohol_servings.yaml` are
commented out; will they return for ingest? Anne Thessen's read is that the 3
live phvs are beer/wine/liquor components and the disabled expressions summed
them — see [`SPEC_SOURCED_S4_DESIGN.md`](SPEC_SOURCED_S4_DESIGN.md).

## The count investigation (active)

**The generated S4 does not reproduce the published S4.** This is the main open
work — see [`s4_count_investigation/HANDOFF.md`](s4_count_investigation/HANDOFF.md).

Where it stands: the published numbers are no longer mysterious. They are
exactly the CSV committed on 2025-12-11 (`1e6a34db`), output of the superseded
pipeline, pasted into the Google Sheet and frozen since — all 1332 compared
cells match. Across 13 dated exports, every earlier change is attributed to
either a code commit (the two large ones: adding COPDGene/FHS in August, adding
an "out of scope" filter in December) or an edit to the curator-maintained
Google Sheets the old pipeline read. Earlier theories that the numbers had
drifted mysteriously or been pasted out of alignment with their labels were
tested and rejected.

What remains is a straight comparison of two pipelines, and the leading
hypothesis is that the old one *overcounted*: it filtered phvs against
`valid-phvs/{cohort}.tsv` where a list existed and left them unfiltered where
none did, and ARIC, CARDIA, and JHS had no lists. If that holds, the published
table is wrong and the generator is right.

## What's here

**Current pipeline**

- `spec_phv_report.py` — the spec-sourced S4/S5 generator. Design and rationale
  in [`SPEC_SOURCED_S4_DESIGN.md`](SPEC_SOURCED_S4_DESIGN.md).
- `config/s4_layout.yaml` — canonical cohort columns and template row order.
- `compare_s4_to_published.py` — compares one generated run against one
  published sheet.
- `spec_code_fixes_20260803.tsv` — the six concept-code corrections, in the form
  handed to the spec owner.

**Investigation** — `s4_count_investigation/`

- `HANDOFF.md` — state of the investigation; start here.
- `published_source_20251211.csv` — the pipeline output the published Table S4
  was pasted from. **This, not the spreadsheet, is what to diagnose against.**
- `verify_published_source.py` — proves that CSV reproduces the published sheet
  exactly (0/1332 cells differ).
- `xlsx/` — 13 dated exports of the Google Sheet, covering every version that
  changed. The only record of its history. **Published-sheet exports only** —
  the comparison scripts glob this directory and parse dates from filenames.
- `new_pipeline_runs/` — output of the spec-sourced generator, for comparison
  against the published numbers. `s4-new-pipeline-2026-08-03.xlsx` is the
  latest and uses the published template layout.
- `change_ledger.py` / `s4_change_ledger.csv` — every cell that ever changed in
  the published table, tagged with its cause (code commit, input-sheet change,
  or hand edit).
- `compare_s4_versions.py` — compares published versions to each other and
  checks row alignment.
- `s4_sheets.py` — shared sheet/CSV readers for both scripts. Normalizes blank
  encodings and drops summary rows; skipping either fabricates hundreds of
  changes that aren't in the data.
- `old_pipeline/` — the superseded pipeline that produced the published numbers
  (`preharmonized_qaqc_report.py`, `valid-phvs/`, and its notes). Symlinked from
  this directory so it still runs. It is evidence, not dead code: its filtering
  rules and its paste-at-line-5 workflow are what the investigation is trying to
  reconstruct.

**History** — `history/`, completed work kept for its reasoning

- `S1_LABEL_SOURCE_MIGRATION.md` — the `harmonized_vars.tsv` → Table S1
  migration.
- `SPEC_CODE_CORRECTIONS_20260803.md` — per-code rationale for the six
  concept-code fixes, and what was deliberately *not* changed.

## Running S4

On Seven Bridges (a local run is not a substitute — only 5 cohorts have dbGaP
caches locally):

```bash
./hv_dataqc/sb_scripts/run_s4_report.sh      # no args, idempotent
```

Output lands in `/sbgenomics/workspace/S4-output-files/`.
