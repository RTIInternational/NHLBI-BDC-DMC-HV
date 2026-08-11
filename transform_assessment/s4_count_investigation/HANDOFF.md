# S4 count investigation — handoff (2026-08-11)

**Written to be read cold.** Assume the reader remembers nothing about this,
including Siggie, who is away for a week and whose memory for this kind of
detail is short by their own account. Nothing here depends on having been in the
session that produced it.

Every figure below is reproducible with a command given inline. Where something
is inference rather than measurement, it says so. Prefer re-running the commands
to trusting the numbers.

## The problem in one paragraph

The spec-sourced S4 generator produces numbers that don't match the published
Table S4. **The published numbers are now fully accounted for**: they are
exactly the CSV committed in `1e6a34db` ("uploading generated csv from
2025-12-11") — output of the superseded pipeline, pasted into the Google Sheet
and never regenerated since. All 1332 compared cells match, same 148 labels,
same order. So the comparison to make is *current generator vs. that CSV*: two
pipelines, no spreadsheet handling in between, no corruption to explain away.
The earlier worries — that counts had drifted, or been pasted out of alignment
with their labels — were tested and are false.

> **Read this before the sections below.** An earlier version of this handoff
> reported that the published sheet "changed twice", that 582 cells moved
> between 2026-03-23 and 2026-06-25, and that row alignment had to be
> established before anything else. All three were wrong — artifacts of the
> comparison script, not of the data. See "Corrected on 2026-08-11".

## The published numbers are solved

```bash
./.venv/bin/python transform_assessment/s4_count_investigation/verify_published_source.py
```

```
cells differing: 0/1332
EXACT MATCH: the published sheet is this CSV.
```

`published_source_20251211.csv` sits beside that script — a copy of
`git show 1e6a34db:transform_assessment/preharmonized_qaqc_report.csv`, checked
in so the comparison runs without going through git.

**This is the artifact to diagnose against.** Every open count question becomes
a question about two pipelines disagreeing, which is tractable: the old
pipeline's code is in `old_pipeline/`, its inputs are its `valid-phvs/` lists,
and both are readable. Chasing spreadsheet history is done.

A near miss worth knowing, so nobody re-derives it: the *code* commit
`c72e781c` (2025-12-09) is not the source. Its committed CSV has 161 rows and
differs from the sheet in 125 of 1152 cells — 80 reading higher than the sheet,
32 lower, 12 blank-vs-populated. The 2025-12-11 CSV was generated from a later
state than any committed code change, so the run that produced the published
numbers used code that may never have been committed in that exact form.
Rerunning `old_pipeline/` today will not necessarily reproduce the CSV —
**compare against the CSV, not against a rerun.**

## What is measured

This section is the supporting evidence for the section above. It is kept
because the individual findings still constrain what can be true, but nothing
here is an open question any more.

Four dated exports of the Google Sheet are in `xslx/`. More can be made: the
saved Google Sheet versions they were exported from live in Siggie's Drive at
*My Drive / old_s4_files_for_debuggin*, symlinked as `xslx/old_gsheet_versions`
(**resolves on their machine only** — dangling anywhere else, including Seven
Bridges). Exporting another version is a manual step only they can do; ask.

Run:

```bash
./.venv/bin/python transform_assessment/s4_count_investigation/compare_s4_versions.py
```

That reproduces everything in this section.

**Cell drift between consecutive versions** (summary rows excluded, blanks
normalized — see "Corrected on 2026-08-11" for why both matter):

| transition | labels | cells differing |
|---|---|---|
| 2025-08-05 → 2025-12-23 | 151 → 148 | **823 / 1179** |
| 2025-12-23 → 2026-03-23 | 148 → 148 | **0 / 1332** |
| 2026-03-23 → 2026-06-25 | 148 → 148 | **4 / 1332** |

**Row alignment:**

```
2025-08-05: 151 rows, 151 distinct
2025-12-23: 148 rows, 148 distinct
2026-03-23: 148 rows, 148 distinct
2026-06-25: 149 rows, 148 distinct  DUPLICATED: ['8-epi-PGF2a in urine']
2025-08-05 -> 2025-12-23: 68 shared labels in a different relative order
2025-12-23 -> 2026-03-23: shared labels in the same order
2026-03-23 -> 2026-06-25: shared labels in the same order
```

The one real reordering is 2025-08 → 2025-12, and it is explained: 20 labels
were renamed (`von Willebrand factor` → `Von Willebrand factor`), which moves
them under the sheet's alphabetical sort.

Four things follow.

**1. The published sheet has been frozen since December 2025.** The two
transitions after 2025-12-23 total *four* changed cells out of 2664, and all
four are cosmetic (below). The 2025-12-23 → 2026-03-23 window spans commit
`1623e1f1` (2026-03-17), which disabled 7 of the 10 measurement blocks in
`CARDIA-ingest/alcohol_servings.yaml` — and changed nothing. CARDIA alcohol
reads 67/278328 in every version from 2025-12-23 onward. **The published S4 has
not been regenerated from the transform specs since December 2025**, so no
theory explaining the generated-vs-published gap via a spec defect can be right.

**2. The duplicated row is cosmetic — it shifted nothing.** `8-epi-PGF2a in
urine` does appear twice in the 2026-06-25 export (excel rows 5 and 6), which
confirms Siggie's half-memory. But both copies carry identical counts
(CARDIA 1/2720, MESA 1/376), every label below it keeps its own correct counts,
and a positional test found no offset that explains anything. It is a repeated
whole row, not a paste slip. **This closes the question the previous handoff
made task 1.** Per-row comparisons against the published sheet are safe.

**3. The only four real post-December changes are cosmetic:**

```
History of coronary artery bypass graft  CARDIA    2/0 -> 2/-
Mean platelet volume                     CARDIA    2/0 -> 2/-
Red cell distribution width              JHS       1/0 -> 1/-
Cause of death                           FHS   8/65700 -> (blank)
```

Three are a zero count rendered as `-`. The fourth is `Cause of death` being
emptied for FHS — worth a glance given that `CARDIA-ingest/cause_of_death.yaml`
was later deleted from `main`, but it is one cell.

**4. The December rewrite was a wholesale regeneration, not a shift.** 823 of
1179 cells changed, 20 labels were renamed (`Alcohol`→`Alcohol Consumption`,
`von Willebrand factor`→`Von Willebrand factor`, …), and counts inflated across
the board:

```
Cigarette smoking  ARIC   5 → 30      CARDIA 10 → 20     JHS 7 → 3
Troponin all types ARIC   9 → 60      CARDIA  2 → 4
```

Cohorts CHS, COPDGene, FHS, WHI appear for the first time there. The 2025-08-05
numbers are the same order of magnitude as what the current generator produces;
the December ones are ~6× larger. **Tested and rejected:** that this was a
misaligned paste. Comparing Dec position *i* against Aug position *i+offset* for
every offset in −5..+5 gives a best match of 8.4% with no peak; a constant shift
would show one offset near 100%. (Test written in a scratch dir and not kept —
it is a dozen lines and the conclusion has since been superseded by the exact
CSV match, which explains the December numbers outright.)

**So the ~112 low / ~30 high cells are the December pipeline's numbers vs. the
current generator's, with no intervening corruption to explain them.** That is a
cleaner problem than the previous handoff described.

## What to do

1. **Diagnose the current generator against `published_source_20251211.csv`.**
   Run S4 on Seven Bridges, then compare generated output to that CSV per cell.
   `compare_s4_to_published.py` in the parent directory does generated-vs-sheet;
   point it at the CSV instead, or extend `verify_published_source.py`, which
   already parses both shapes. The ~112 low / ~30 high cells are the target.
2. **Test the filtering asymmetry first** — it is the leading hypothesis and it
   is cheap. The old pipeline filtered phvs against `valid-phvs/{cohort}-ingest.tsv`
   where a list existed and left them *unfiltered* where none did. ARIC, CARDIA,
   and JHS had no lists. If the generator reads low mainly for those three
   cohorts, that asymmetry is the explanation and the published numbers are
   overcounts rather than the generator undercounting. Group the diff by cohort
   before looking at individual rows.
3. **Decide what "correct" means, then say so out loud.** If the old pipeline
   was overcounting unfiltered cohorts, the published Table S4 is wrong and the
   generator is right — which is a finding for the team, not a bug to fix. This
   is the question to bring back to the group.

**Two things not to spend time on.** The 2026-07-28 / 2026-08-03 exports Siggie
offered: nothing has changed in the sheet since December, so they will be
identical to 2026-06-25 — skip unless a cheap confirmation is wanted. And the
per-row leads earlier handoffs flagged (`Troponin all types` ARIC, `AHI
Apnea-Hypopnea Index` CHS): they predate all of this and should be re-derived
from the CSV comparison rather than carried forward.

## Corrected on 2026-08-11

The previous handoff's headline figures were wrong. All three errors were in the
comparison script, and all are now fixed in `compare_s4_versions.py`:

- **Blank encoding.** A visually-empty cell is stored as `''` in the 2026-03-23
  export and as `None` in 2026-06-25. Comparing raw values counted every such
  cell as a change, reporting **582 changed cells where there are 4**. The
  earlier "1149" for the December transition was inflated the same way (true
  value: 823). `norm()` now maps blanks to `None` and all numbers to `float`.
- **Summary rows counted as variables.** The 2026-06-25 export dropped the
  trailing `TOTALS` and `TOTAL VARIABLES` rows. Counting them as data rows made
  "150 → 148 labels" look like two lost variables; no variables were lost.
  `SUMMARY_ROWS` now excludes them.
- **Duplicate read as reordering.** The row-alignment check compared shared
  labels by raw position, so the one duplicated row made every label below it
  look displaced — reported as "147 shared labels in a different relative
  order". Deduplicating before comparing shows the order is unchanged.

Two claims in the previous handoff die with these fixes: that the published
numbers "changed twice" (they changed once), and that row order/duplication
might have corrupted the pairing of counts to labels (it did not). The general
lesson the handoff already stated applies to its own numbers: **verify with
content, not plausible proxies** — a diff count is a proxy, and this one was
measuring a storage detail.

Worth noting how the real answer was found, since it was not by more careful
diffing: the question "which pipeline run produced these numbers?" was
answerable directly from git, because the old pipeline committed its output CSV.
Two `git show` commands settled what four spreadsheet exports could not.

## The superseded pipeline is evidence

`old_pipeline/` holds the pipeline that produced the published numbers:
`preharmonized_qaqc_report.py`, its `valid-phvs/` filter lists, its output CSV,
and its notes (`CLAUDE.OLD.md`). Both the script and `valid-phvs/` are symlinked
from `transform_assessment/` so they still run.

**Don't mistake `old_pipeline/preharmonized_qaqc_report.csv` for the published
source.** It is a *later* run of the same pipeline: it differs from the sheet in
exactly one cell (`Cause of death` / FHS, blank where the sheet has 8/65700).
That single cell is also the only substantive change in the 2026-06-25 export,
which suggests someone re-ran the old pipeline and patched that one value into
the sheet. Use `published_source_20251211.csv` as the reference; verify with

```bash
./.venv/bin/python transform_assessment/s4_count_investigation/verify_published_source.py \
    --csv transform_assessment/s4_count_investigation/old_pipeline/preharmonized_qaqc_report.csv
```

Two things in there bear directly on the investigation:

- **The paste workflow:** copy all rows from the generated CSV *except the
  header*, paste starting at **line 5** of the template. Positional alignment by
  hand, no key joining count to label. This made misalignment plausible a
  priori — but it was tested and did not happen (see finding 2 and 4 above).
  Still worth knowing, since it is how any future paste can go wrong.
- **The filtering logic:** phvs were filtered against
  `valid-phvs/{cohort}-ingest.tsv` where a list existed, and *unfiltered* where
  none did. ARIC, CARDIA, and JHS had no lists — all their phvs were counted.
  COPDGene and FHS had lists but no data rows. This is now the leading
  explanation for the generator reading low, and it is **directly testable**:
  group the generator-vs-CSV diff by cohort and see whether the gap concentrates
  in ARIC/CARDIA/JHS. If it does, the published numbers are overcounts. That is
  task 2 above. (Hypothesis, untested.)

## Related open threads

- **282 spec files are invisible to the generator**, producing 50 empty S4 rows
  (all `Taking <drug>`, the disease/status rows, demographics). Cause: variable
  identity is keyed on `observation_type`, which Condition / DrugExposure /
  Procedure / Demography specs don't have. The extraction rules to fix this are
  settled and written up in [`../SPEC_SOURCED_S4_DESIGN.md`](../SPEC_SOURCED_S4_DESIGN.md)
  §"Non-measurement classes" — designed, not built. Independent of the count
  investigation; can proceed in parallel.
- **What else did the S1 migration break silently?** The `observation_type`
  narrowing came from it. So did a `cohort_keys` omission that blanked the entire
  HCHS/SOL column (code correct, unit test correct, config file silently missing
  an entry, no test covering the real config). The granular history is on the
  abandoned branch `feature/S5-report-20260603`; `93ac3910` on this branch is a
  squash and shows nothing. Worth an audit for other config-vs-code gaps.
- **Should the generator report matched-but-empty template rows?** A row that is
  silently blank because its class was never parsed is exactly the failure that
  took a full session to notice — the run log said only "1 spec variable had no
  template row" and looked healthy.

## Spec changes that will move counts, unrelated to any bug

When the next S4 run differs from the last, check these before suspecting the
generator. Both arrived in the `origin/main` merge on this branch (`62e7a7e6`):

- **`CARDIA-ingest/cig_smok.yaml` lost 2 of its 4 blocks** (`b1d2b8da`, the
  2026-08-04 CARDIA PR) — the pht001818/YEAR 15 and pht001999/YEAR 20 blocks were
  deleted, `populated_from` corrected to `phv00113168`, several `value_mappings`
  rewritten. CARDIA's `Cigarette smoking` count will drop. That merge conflicted
  only in this file; the resolution took main's restructured version and
  re-applied the `OMOP:4282779` → `OMOP:35811013` fix to the 2 surviving blocks.
- **`CARDIA-ingest/cause_of_death.yaml` was deleted** in the same PR.

## Environment

- Run S4 on Seven Bridges: `./hv_dataqc/sb_scripts/run_s4_report.sh` (no args,
  idempotent). Output to `/sbgenomics/workspace/S4-output-files/`. A local run is
  not a substitute — only 5 cohorts have dbGaP caches locally.
- The cohort dir is `hchs_sol` in the dbGaP cache but `HCHS` everywhere else;
  `run_s4_report.sh:89` and `run_extracts.sh:103` map it explicitly. This
  inconsistency already caused one blanked column. Worth normalizing.
- Use `./.venv/bin/python` directly; `uv` cannot write its cache in the sandbox.
- `git fetch` / `git push` fail in the sandbox (no SSH auth); process
  substitution (`diff <(...)`) is blocked — use `git patch-id` or temp files.
  **Siggie can run anything the sandbox blocks: ask rather than working around.**
- `validate_ingest_yamls.py` over all 842 files exceeds the 120s Bash timeout;
  run it in the background or import `validate_block` for the files you touched.
- BDCHM schema: `NHLBI-BDC-DMC-HM/src/bdchm/schema/bdchm.yaml` (root symlink
  `bdchm.yaml`). Classes define slots under `attributes:`, not `slots:`.
- **Verify with content, not plausible proxies.** Several wrong turns in this
  investigation came from that: inferring a "longstanding gap" from current code
  without checking the deleted source; reading a 14KB file size as evidence of
  truncation; reading `grep -rc` output as match counts when it prints one line
  per file scanned.

## Branch state

```
origin/main (b1d2b8da)
  └─ s4-s5-tooling   a3f23e6e   ← work here; run S4 from here
```

**`s4-spec-codes` no longer exists.** It was merged into `s4-s5-tooling`
(fast-forward) on 2026-08-04 and deleted locally and on the remote. Anything in
earlier notes telling you to work on or run S4 from `s4-spec-codes` is stale.
The merge brought all of `main`, the six concept-code fixes, and this
investigation's docs into what had been a tooling-only branch.

The six concept-code fixes are the entire delta from `main` in
`priority_variables_transform/` (20 files, one-line `observation_type` swaps plus
one tracking comment): `OMOP:4282779`→`OMOP:35811013`,
`OMOP:4042886`→`OMOP:37311566`, `OMOP:4209737`→`OBA:2052305`,
`OBA:VT0000217`→`OBA:VT0000717`, `OMOP:8842`→`OMOP:4021291`,
`OBA:2050108`→`OMOP:4138462`. Rationale per code in
[`../history/SPEC_CODE_CORRECTIONS_20260803.md`](../history/SPEC_CODE_CORRECTIONS_20260803.md).
Stephanie is expected to land these in `main` independently; if she does, drop
them here rather than landing both.
