# S4 count investigation — handoff (updated 2026-08-12)

Every figure below is reproducible with a command given inline. Where something
is inference rather than measurement, it says so. Prefer re-running the commands
to trusting the numbers.

## Read this first: the goal changed on 2026-08-12

**Reproducing the published Table S4 is no longer the objective.** Most of this
document was written while it was, so read the rest through this lens.

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
- Any task premised on matching the published cells. Sections below that assume
  otherwise are marked.

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

## The problem in one paragraph (as it stood before 2026-08-12)

The spec-sourced S4 generator produces numbers that don't match the published
Table S4. **The published numbers are now fully accounted for**: they are
exactly the CSV committed in `1e6a34db` ("uploading generated csv from
2025-12-11") — output of the superseded pipeline, pasted into the Google Sheet
and frozen since. All 1332 compared cells match, same 148 labels, same order.
Every earlier change in the sheet is attributed too, to a specific code commit
or a specific input-sheet edit (see the timeline below). So the comparison to
make is *current generator vs. that CSV*: two pipelines, no spreadsheet handling
in between, no corruption to explain away. The earlier worries — that counts had
drifted mysteriously, or been pasted out of alignment with their labels — were
tested and are false.

> **Read this before the sections below.** An earlier version of this handoff
> reported that the published sheet "changed twice", that 582 cells moved
> between 2026-03-23 and 2026-06-25, that row alignment had to be established
> before anything else, and that the published numbers came from code never
> committed. All four were wrong. See "Corrected on 2026-08-11".

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

## Every change in the sheet is now attributed

With 13 exports and only 7 code revisions of the old pipeline, each numeric
event lines up with either a code commit or an input-sheet change. Three
committed CSVs match a contemporaneous sheet export exactly:

| CSV commit | date | matches sheet | residual |
|---|---|---|---|
| `903f6d41` | 2025-08-28 | 2025-08-28 | **0 / 1449** |
| `1e6a34db` | 2025-12-11 | 2025-12-11, 12-23, 2026-03-23 | **0 / 1332** |
| `31bd764a` | 2026-06-09 | 2026-06-25 | 3 hand-typed `-` |

And the full timeline:

| transition | cells | cause |
|---|---|---|
| 2025-08-05 → 08-27 | 0 | — |
| **08-27 → 08-28** | **884** | code `903f6d41` "Got it working with the two other sheets" — COPDGene/FHS added |
| 08-28 → 11-03 | 0 | — |
| 11-03 → 11-26 | 1 | input sheet (`Cause of death` CARDIA 36→38) |
| **11-26 → 12-09** | **127** | code `c72e781c` "Filter out 'out of scope' rows" (2025-12-09) |
| 12-09 → 12-11 | 3 | input sheet (Hematocrit ×2, `Cause of death`) |
| 12-11 → 2026-03-23 | 0 | frozen |
| 03-23 → 05-26 | 1 | hand edit (FHS `Cause of death` cleared) |
| 05-26 → 06-18 | 3 | hand edits (`-` typed over three zero counts) |
| 06-18 → 06-29 | 0 | frozen |

**The two big events are code changes, and both are explained.** The August jump
is the commit that first pulled in the COPDGene and FHS sheets. The December
drop is the commit that added an "out of scope" filter on `Transform Comment` to
the BDCHM and FHS source sheets — a deliberate *reduction*, which is why counts
fell. `git diff 903f6d41 c72e781c -- transform_assessment/preharmonized_qaqc_report.py`
shows it in 26 lines.

**The limit on code-only explanation.** The old pipeline reads three live Google
Sheets, curator-maintained and mutating independently of git — spreadsheet /
worksheet as passed to `load_gsheet_as_df`:

| spreadsheet | worksheet | has `Transform Comment`? |
|---|---|---|
| `Export_BDCHM_noFHS-noCOPDGene_phv_mappings` | `Export_BDCHM_noFHS-noCOPDGene_p` | yes |
| `FHS_VariableProperties` | `right_join_full` | yes |
| `COPDGene_FullMatchWithManuals_Join_Dedup_XML_BDC Mapped Variables V1` | `COPDGene_FullMatchWithManuals_J` | no filter applied |

The `Transform Comment` column is a **curator annotation**, and the "out of
scope" filter (`c72e781c`, 2025-12-09) honors it rather than imposing a rule of
its own. So the 127-cell December drop reflects curator scope decisions, not a
counting change — worth knowing before anyone treats it as a bug.

Because those inputs move, some changes have no code cause and never will. The
clean proof: `1e6a34db` (12-11) and `31bd764a` (2026-06-09) have **no code
commit between them**, yet their CSVs differ in one cell (`Cause of death`/FHS
8/65700 → empty). Same code, six months apart, different answer — the FHS input
sheet changed. Expect this whenever a diff doesn't line up with a commit.

The one loose end: `ce27257c` (2025-08-27, "Fixed N values") matches neither the
08-27 nor the 08-05 sheet (716/1206 both). Its CSV is presumably already the
post-fix output while the sheet still held pre-fix numbers — the paste lagged the
commit. Not worth chasing unless August numbers become relevant.

## What is measured

This section is the supporting evidence for the section above. It is kept
because the individual findings still constrain what can be true, but nothing
here is an open question any more.

Thirteen dated exports of the Google Sheet are in `xlsx/`, covering every
version that changed from 2025-08-05 on. **`xlsx/` holds published-sheet
exports only** — generated runs live in `new_pipeline_runs/`, because the
comparison scripts glob `xlsx/*.xlsx` and parse a date from each filename, so a
generated file dropped in there silently corrupts the version history. More can
be made: the saved Google Sheet versions they were exported from live in the
repo owner's Drive at *My Drive / old_s4_files_for_debuggin*, symlinked as
`xlsx/old_gsheet_versions` (**resolves on that one machine only** — dangling
anywhere else, including Seven Bridges). Exporting another version is a manual
step only they can do; ask. Since the published table is no longer the target
(see the top of this document), you are unlikely to need one.

Run:

```bash
./.venv/bin/python transform_assessment/s4_count_investigation/compare_s4_versions.py
```

That reproduces the timeline above and everything in this section.

Three things worth keeping.

**1. The published sheet has been frozen since 2025-12-11.** Every version from
then through 2026-06-29 is the same numbers, apart from four hand edits. The
2025-12-23 → 2026-03-23 window spans commit `1623e1f1` (2026-03-17), which
disabled 7 of the 10 measurement blocks in `CARDIA-ingest/alcohol_servings.yaml`
— and changed nothing. CARDIA alcohol reads 67/278328 throughout. **The
published S4 has never been generated from the transform specs at all**, so no
theory explaining the generated-vs-published gap via a spec defect can be right.

**2. The duplicated row is cosmetic — it shifted nothing.** `8-epi-PGF2a in
urine` appears twice from the 2026-06-18 export onward (excel rows 5 and 6),
which confirms a half-remembered report of a duplicate. Both copies carry
identical counts
(CARDIA 1/2720, MESA 1/376), every label below keeps its own correct counts, and
a positional test found no offset that explains anything. It is a repeated whole
row, not a paste slip. Per-row comparisons against the published sheet are safe.

**3. The four post-December changes are hand edits, not pipeline output:**

```
2026-05-26  Cause of death                   FHS   8/65700 -> (blank)
2026-06-18  History of coronary artery byp.  CARDIA    2/0 -> 2/-
2026-06-18  Mean platelet volume             CARDIA    2/0 -> 2/-
2026-06-18  Red cell distribution width      JHS       1/0 -> 1/-
```

Three are a zero count typed over as `-`. The fourth clears FHS cause-of-death;
the 2026-06-09 CSV has that cell empty too, so the sheet was being reconciled by
hand against a newer run rather than repasted.

**Will these hand edits need re-making after the next paste? Only the three
dashes, and only if the convention is wanted.** They are purely presentational —
`2/0` displayed as `2/-` — and a paste of generated output will overwrite them
with `0` again. The FHS `Cause of death` clearing does *not* need redoing: the
generator has no value there either, so a paste reproduces the blank on its own.

The better fix is to stop re-making them by hand: decide whether a zero count
should render as `-` and put that in the generator's xlsx writer, so the
convention survives every future paste. Seven cells is not worth a manual
checklist that will be forgotten. If the decision is "leave zeros as 0", then
nothing needs redoing at all.

**So the ~112 low / ~30 high cells are the December pipeline's numbers vs. the
current generator's, with no intervening corruption to explain them.**

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
   282-invisible-specs / 50-empty-rows problem already described under "Related
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
   is the real work. 282 spec files are invisible to the generator, producing 50
   empty S4 rows, because variable identity is keyed on `observation_type` and
   Condition / DrugExposure / Procedure / Demography specs don't have one. The
   extraction rules are designed in
   [`../SPEC_SOURCED_S4_DESIGN.md`](../SPEC_SOURCED_S4_DESIGN.md)
   §"Non-measurement classes" — designed, not built. **Start here.**
3. **Make the generator report matched-but-empty template rows.** A row that is
   silently blank because its class was never parsed is exactly the failure that
   took a full session to notice. Cheap, and it prevents a repeat.
4. **Sanity-check the new run against the published table** — *not* to make them
   match, but to catch real bugs. The signal to look for is a count that
   **decreases** (unexplained by the known spec deletions below) or moves by
   orders of magnitude. Increases are expected and need no investigation.
   `verify_published_source.py --xlsx <run>` still does the comparison; just
   read its output with the new expectation.

**Dropped from the old task list** (do not pick these up):

- ~~Test the 2× / double-count hypothesis against the old pipeline's counting
  loop.~~ It concerned whether the *published* numbers were inflated. Nothing
  depends on that answer any more. The 17 exact-half cases are recorded below
  for the record only.
- ~~Group the generator-vs-CSV diff by cohort to test the valid-phvs
  asymmetry.~~ Done, and it came back negative; the filter is retired regardless.

**Do not** carry forward per-row leads as framed in earlier handoffs; re-derive
from a current run.

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

A fourth correction, made the same day: this handoff briefly claimed "compare
against the CSV, not against a rerun", on the grounds that the published numbers
came from code that was never committed. That was an overstatement built on a
misreading. `c72e781c` changed *only* the `.py` and carried no CSV of its own, so
the CSV sitting in the tree at that commit was the leftover from `903f6d41`
(2025-08-28) — August output, three months stale. Comparing it to a December
sheet was never meaningful. Once the 08-28 and 12-11 exports arrived, both
matched their contemporaneous CSVs exactly, and the code history turned out to
explain the two large events outright. **Rerunning the old pipeline is a
reasonable thing to do**; the real obstacle is that its inputs are live Google
Sheets that have since moved, not that the code is missing.

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
