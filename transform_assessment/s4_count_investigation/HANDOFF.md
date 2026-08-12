# S4 count investigation — handoff (updated 2026-08-12)

Every figure below is reproducible with a command given inline. Where something
is inference rather than measurement, it says so. Prefer re-running the commands
to trusting the numbers.

## Read this first: the goal changed on 2026-08-12

**Reproducing the published Table S4 is no longer the objective.** This document
has been cut down accordingly — the resolved forensics moved to
[`../history/S4_PUBLISHED_NUMBERS_FORENSICS.md`](../history/S4_PUBLISHED_NUMBERS_FORENSICS.md)
and what remains is meant to be read start to finish.

The old pipeline narrowed its phv set two ways, and the project lead has retired
both (Slack, 2026-08-12): *"those lists of valid phv were made a year ago and
probably are no longer valid. You also shouldn't go by what is in the
spreadsheets anymore. We can't keep those up to date."*

| filter | what it was | status |
|---|---|---|
| `valid-phvs/{cohort}.tsv` | per-cohort allow lists, one bare phv per line, hand-supplied ~2025 | **retired — stale** |
| `Transform Comment == "out of scope"` | curator annotation in two live Google Sheets | **retired — unmaintainable** |

The current generator implements neither, and has no path by which a per-phv
scope decision reaches it (verified: it reads specs + dbGaP extracts + Table S1,
and never calls `load_gsheet_as_df`). Any phv in a live spec's value slot is
counted. **That is the intended behavior now.**

**Consequence: the new numbers are expected to be higher than published.** An
increase needs no explanation. A *decrease* does.

What this retires outright:

- The valid-phvs asymmetry hypothesis. It was already dead on evidence (the gap
  did not concentrate in ARIC/CARDIA/JHS), and is now moot as well.
- The "old pipeline overcounted, so the published table is wrong" framing. There
  is no longer a right/wrong to settle — the two pipelines answer different
  questions, and only one of them has maintainable inputs.
- Any task premised on matching the published cells.

What survives as genuinely useful work: the **`pub only` / empty-rows problem**
(§"Related open threads"), which is a real generator defect independent of any
filter, and the **per-row extremes**, as a sanity check rather than a target.

**One scope channel does survive, and it is invisible.** Curators sometimes
express a scope decision by commenting out a block in a spec YAML rather than by
annotating a sheet — e.g. the seven disabled `value_decimal` expressions in
`CARDIA-ingest/alcohol_servings.yaml`, or `ARIC-ingest/bdy_hgt.yaml:51`
("COMMENTED OUT: ABI table"). `yaml.safe_load` never sees these, so the
generator honors them silently, as absence. This is why `Alcohol Consumption`
CARDIA reads 3 against the published 67 — and 3 is the correct answer. **When a
count comes in lower than expected, grep the spec for commented-out blocks
before assuming a bug.**

## How the published numbers were traced (archived)

The question "where did the published numbers come from?" is **solved and
closed**. They are exactly the CSV committed in `1e6a34db` (2025-12-11), output
of the superseded pipeline, pasted into the Google Sheet and frozen since — all
1332 compared cells match, and every earlier change is attributed to a specific
code commit or input-sheet edit.

The full forensic record moved to
[`../history/S4_PUBLISHED_NUMBERS_FORENSICS.md`](../history/S4_PUBLISHED_NUMBERS_FORENSICS.md).
You do not need it to do the work below. Read it only if you need to audit the
published table again, or want the method.

Both verification scripts still run and still pass:

```bash
./.venv/bin/python transform_assessment/s4_count_investigation/verify_published_source.py
./.venv/bin/python transform_assessment/s4_count_investigation/compare_s4_versions.py
```

## Generated vs. published: first real comparison (2026-08-11)

A generated run finally exists to compare: `new_pipeline_runs/`, holding a
2026-06-29 run (old CSV-ish layout) and **`s4-new-pipeline-2026-08-03.xlsx`**,
which uses the published template layout and is the one to use. Both were found
in Downloads, not produced this session.

```bash
./.venv/bin/python transform_assessment/s4_count_investigation/verify_published_source.py \
    --xlsx transform_assessment/s4_count_investigation/new_pipeline_runs/s4-new-pipeline-2026-08-03.xlsx
```

649 of 1332 cells differ. Broken down by cohort, with "pub only" meaning the
published table has a value and the generator leaves the cell empty:

```
cohort      same  both differ  gen only  pub only   old pipeline
ARIC          55           50         2        41   NO valid-phvs list
CARDIA        79           23        10        36   NO valid-phvs list
CHS           66           37         5        40   filtered
COPDGene     103           12        16        17   filtered
FHS           19           69         4        56   filtered
HCHS/SOL      86            0         0        62   filtered  (see caveat)
JHS           89           22         5        32   NO valid-phvs list
MESA          81           23         8        36   filtered
WHI          105           10         2        31   filtered
```

**The valid-phvs asymmetry hypothesis is dead.** It predicted the gap would
concentrate in ARIC/CARDIA/JHS, the three cohorts the old pipeline counted
unfiltered. It does not: FHS is by far the worst (69 differing, only 19
matching) and is a *filtered* cohort. Do not spend more time on it.

Three things the data points at. **Re-prioritized 2026-08-12** — only the first
is still live work; the other two are recorded for reference.

1. **`pub only` dominates — ~351 cells across all cohorts.** These are rows the
   published table populates and the generator leaves blank. That is the
   invisible-non-measurement-specs problem already described under "Related
   open threads", and it is the single largest term in the gap. Fixing it is
   designed but not built. **Still the place to start** — and note this one is
   unaffected by the filter decision: those rows are blank because a whole class
   of specs is never parsed, not because anything filtered them out. It is a
   generator defect either way.
2. **17 exact-half cases** — *reference only, no longer worth chasing.* Spread
   across unrelated variables and cohorts: `Height` ARIC 162632→81297,
   `Hematocrit` ARIC 119990→59995, `Activity LP-PLA2` CHS 10758→5379,
   `Diastolic blood pressure` WHI 2473953→1247711. A clean 2× factor across
   variables that share nothing suggests a structural double-count in the **old**
   pipeline — counting each phv once per visit, or summing two stats rows. That
   would mean the published numbers are inflated 2× for those rows, which is now
   a fact about a retired pipeline and changes nothing about the generator.
3. **Per-row extremes** — *now sanity checks, not defects.* `AHI Apnea-Hypopnea
   Index` CHS pub=4 gen=**196** and `BMI` FHS pub=2 gen=**41** are the generator
   reading higher, which is exactly what removing the filters predicts; they need
   no explanation unless the magnitude looks implausible on inspection. The two
   worth a look are the ones going the *wrong* way: `Alcohol Consumption` CARDIA
   pub=67 gen=3 (already explained — commented-out expressions, 3 is correct) and
   **`Troponin all types` ARIC pub=60 gen=9**, which is unexplained and is a
   decrease. That last one is the only per-row item that still merits time.

**Caveat on HCHS/SOL:** the 8/3 run predates `24396404` (2026-08-04, "restore the
HCHS/SOL cohort_keys mapping"). Its 0-differing/62-pub-only column is that bug
blanking the cohort, not a clean match. Rerun before trusting HCHS/SOL. The
other eight cohorts are unaffected.

## What to do

Revised 2026-08-12 after the filter decision. The ordering changed: matching the
published table is no longer a goal, so the tasks that served it are gone.

1. **Rerun S4 on Seven Bridges from current `main`.** The 8/3 run predates the
   HCHS/SOL fix (`24396404`) and possibly others, so every number in this
   document should be re-derived from a current run before it is trusted.
   `./hv_dataqc/sb_scripts/run_s4_report.sh`, no args.
2. **Fix the `pub only` / empty-rows problem** — §"Related open threads". This
   is the real work. ~300 spec files are invisible to the generator, producing
   51 empty S4 rows of 149, because variable identity is keyed on
   `observation_type` and Condition / DrugExposure / Procedure / Demography
   specs don't have one. The extraction rules are designed in
   [`../SPEC_SOURCED_S4_DESIGN.md`](../SPEC_SOURCED_S4_DESIGN.md)
   §"Non-measurement classes" — designed, not built. **This is where to start.**
3. **Make the generator report matched-but-empty template rows.** A row that is
   silently blank because its class was never parsed is exactly the failure that
   took a full session to notice. Cheap, and it prevents a repeat. While you are
   there, add the config-reconciliation test described under "Related open
   threads" — it is the guard that catches this whole family of bugs.
4. **Fix the silently-undercounted N.** `_col_n_valid`
   (`spec_phv_report.py:259-264`) returns `None` for three different failures —
   PHT missing from the extract, column missing from the PHT, `n_valid` null —
   and `build_cohort_rows:350-357` then counts that PHV toward `phv_count` while
   contributing 0 to `total_n`. The result is a row claiming e.g. 6 phvs with an
   N covering only 4: a plausible-looking wrong number, with nothing counting or
   reporting the misses. **This is the highest-risk defect found** — every other
   one blanks a cell, this one corrupts a published value. A stale dbGaP cache
   triggers it too, via the `phv_name_map` miss at line 257.
5. **Sanity-check the new run against the published table** — *not* to make them
   match, but to catch real bugs. The signal to look for is a count that
   **decreases** (unexplained by the known spec deletions below) or moves by
   orders of magnitude. Increases are expected and need no investigation.
   `verify_published_source.py --xlsx <run>` still does the comparison; just
   read its output with the new expectation.

**Dropped from the old task list** (do not pick these up):

- ~~Test the 2× / double-count hypothesis against the old pipeline's counting
  loop.~~ It concerned whether the *published* numbers were inflated. Nothing
  depends on that answer any more. The 17 exact-half cases are recorded above,
  for the record only.
- ~~Group the generator-vs-CSV diff by cohort to test the valid-phvs
  asymmetry.~~ Done, and it came back negative; the filter is retired regardless.

**Do not** carry forward per-row leads as framed in earlier handoffs; re-derive
from a current run.

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
- **The filtering logic (retired 2026-08-12 — see the top of this document):**
  phvs were filtered against `valid-phvs/{cohort}-ingest.tsv` where a list
  existed, and *unfiltered* where none did. Six lists exist — CHS, COPDGene,
  FHS, HCHS/SOL, MESA, WHI — so ARIC, CARDIA, and JHS had all their phvs
  counted. (`CLAUDE.OLD.md` says the missing lists are ARIC/CARDIA/**MESA**;
  that prose is stale — a MESA list arrived later and JHS never got one. Trust
  the directory, not the note.) These lists are ~a year old and are no longer
  considered valid, so the current generator does not use them and should not.
  The asymmetry was tested as an explanation for the count gap and came back
  negative: FHS, a *filtered* cohort, has by far the largest gap.

## Related open threads

- **~300 spec files are invisible to the generator**, producing 51 empty S4 rows
  of 149 (all `Taking <drug>`, the disease/status rows, demographics). Cause:
  variable identity is keyed on `observation_type`, which Condition /
  DrugExposure / Procedure / Demography specs don't have. Measured 2026-08-12;
  per-class counts are in the design doc. The extraction rules to fix this are
  settled and written up in [`../SPEC_SOURCED_S4_DESIGN.md`](../SPEC_SOURCED_S4_DESIGN.md)
  §"Non-measurement classes" — designed, not built. Independent of the count
  investigation; can proceed in parallel.
- **What else did the S1 migration break silently? — audited 2026-08-12, and the
  answer is "more".** The `observation_type` narrowing came from it, as did the
  `cohort_keys` omission that blanked HCHS/SOL. Three further defects of the same
  shape are verified below. All fail *silently* — a blank cell, never an error —
  which is the pattern to keep hunting. The granular history is on the abandoned
  branch `feature/S5-report-20260603`; `93ac3910` here is a squash and shows
  nothing.

  1. **LTRC and SPIROMICS specs are silently discarded — 42 files.**
     `s4_layout.yaml` lists 9 cohorts; the specs tree has 11 ingest dirs. LTRC
     (19 specs) and SPIROMICS (23) resolve to no column, so their variables
     contribute nothing. Worse, `spec_phv_report.py:587-590` *deletes*
     all-blank rows from the unmatched appendix, so a variable found only in
     those two cohorts vanishes without even a note. This is the HCHS/SOL bug
     inverted: there, a display name had no key; here, keys have no display
     name. **Caveat: this may be intentional** — whether LTRC/SPIROMICS belong
     in S4 is an open curator question (see `../README.md`). The defect is that
     nothing distinguishes a deliberate omission from a typo.
  2. **Three Table S5 rows render blank on letter-case drift alone.**
     `TABLE_S5_LABELS` is matched against S1 exactly and case-**sensitively**
     (no `lower()` anywhere in `table_s5/`), while the S4 side normalizes case
     (`spec_phv_report.py:498`). `Bilirubin total` vs S1's `Bilirubin Total`,
     and `interleukin 6 in blood` vs `Interleukin 6 in blood`, now miss.
     **This is a regression**: both were `matched` in the June run — see
     `hv_dataqc/sb_output/20260630T172556Z/s5_coverage_20260630_172655.tsv`
     lines 13 and 60. `93ac3910` emptied `S5_LABEL_ALIASES` on the claim that
     "all 19 label aliases were dead under Table S1"; for these two the alias
     should have been *updated*, not deleted. `format_paste_tsv` emits a blank
     line, so the paste still aligns and the failure is invisible in the
     artifact. (`Fasting lipids` also misses but has no S1 row at all —
     pre-existing, not a regression.)
  3. **Demography labels are lowercase where everything else capitalizes.**
     `harmonized_extract.yaml` maps `sex: sex` / `race: race` /
     `ethnicity: ethnicity`, and `extract_harmonized_summaries.py:331-337` uses
     the value directly as `bdc_label` — the one assignment that bypasses the S1
     lookup. S1 and `s4_layout.yaml` both say `Sex` / `Race` / `Ethnicity`, so
     any join on `bdc_label` misses.

  **The old pipeline had the check that would have caught all of these.**
  `old_pipeline/preharmonized_qaqc_report.py:316-319` printed a bidirectional
  set difference — cohorts in data vs cohorts configured, both directions. It
  also *unioned* config and data cohorts (line 285) rather than letting config
  truncate, so an unconfigured cohort showed up as an extra column instead of
  vanishing. The rewrite dropped both. Restoring that reconciliation as a test
  over the **real shipped configs** is the single highest-value guard: it would
  have caught findings 1-3 and the original HCHS/SOL bug.

  **Why the tests missed all of it:** every real config file except
  `TableS1.tsv` has zero test coverage. All 17 tests in `test_spec_phv_report.py`
  build layout dicts inline; `load_layout(None)` / `DEFAULT_LAYOUT_PATH` is never
  exercised. `test_table_s5.py:330` asserts in a *comment* that "S1 matches every
  S5 label directly" — contradicted by the data above, and never tested.
- **Should the generator report matched-but-empty template rows?** A row that is
  silently blank because its class was never parsed is exactly the failure that
  took a full session to notice — the run log said only "1 spec variable had no
  template row" and looked healthy. **Answered: yes** — this is task 3 in "What
  to do". It matters more now that the published table is no longer a check on
  the output: with nothing to diff against, a silently blank row has no second
  chance to be caught.

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
- *(Applies to sandboxed AI-agent sessions only; ignore if you are working in a
  normal shell.)* `git fetch` / `git push` fail in the sandbox (no SSH auth);
  process substitution (`diff <(...)`) is blocked — use `git patch-id` or temp
  files. **The repo owner can run anything the sandbox blocks: ask rather than
  working around it.**
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
The spec owner is expected to land these in `main` independently; if they do,
drop them from this branch rather than landing both.
