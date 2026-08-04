# S4 count investigation — handoff (2026-08-04)

**Written to be read cold.** Assume the reader remembers nothing about this,
including Siggie, who is away for a week and whose memory for this kind of
detail is short by his own account. Nothing here depends on having been in the
session that produced it.

Every figure below is reproducible with a command given inline. Where something
is inference rather than measurement, it says so. Prefer re-running the commands
to trusting the numbers.

## The problem in one paragraph

The spec-sourced S4 generator produces numbers that don't match the published
Table S4. The obvious move — treat the published sheet as ground truth and find
the generator's bug — **is not available**, because the published sheet is
itself unreliable: its numbers changed twice in ways that correspond to no
change in the transform specs, and one export contains a duplicated row. Counts
were pasted positionally into cell B5 before xlsx generation existed, so nothing
joined a count to its label. **Establish row alignment before diagnosing any
individual cell.**

## What is measured

Four dated exports of the Google Sheet are in `xslx/`. More can be made: the
saved Google Sheet versions they were exported from live in Siggie's Drive at
*My Drive / old_s4_files_for_debuggin*, symlinked as `xslx/old_gsheet_versions`
(**resolves on his machine only** — dangling anywhere else, including Seven
Bridges). Exporting another version is a manual step only he can do; ask.

Run:

```bash
./.venv/bin/python transform_assessment/s4_count_investigation/compare_s4_versions.py
```

That reproduces everything in this section.

**Cell drift between consecutive versions:**

| transition | labels | cells differing |
|---|---|---|
| 2025-08-05 → 2025-12-23 | 151 → 150 | **1149 / 1179** |
| 2025-12-23 → 2026-03-23 | 150 → 150 | **0 / 1350** |
| 2026-03-23 → 2026-06-25 | 150 → 148 | 582 / 1332 |

**Row alignment:**

```
2025-08-05: 151 rows, 151 distinct
2025-12-23: 150 rows, 150 distinct
2026-03-23: 150 rows, 150 distinct
2026-06-25: 149 rows, 148 distinct  DUPLICATED: ['8-epi-PGF2a in urine']
2025-08-05 -> 2025-12-23:  68 shared labels in a different relative order
2025-12-23 -> 2026-03-23: shared labels in the same order
2026-03-23 -> 2026-06-25: 147 shared labels in a different relative order
```

Three things follow.

**1. The published sheet does not respond to spec changes.** The
2025-12-23 → 2026-03-23 window contains *zero* changes across 1350 cells, and it
spans commit `1623e1f1` (2026-03-17), which disabled 7 of the 10 measurement
blocks in `CARDIA-ingest/alcohol_servings.yaml`. CARDIA alcohol reads
67/278328 in every version from 2025-12-23 onward while the spec sat unchanged.
So the published S4 was not regenerated from the transform specs in that window,
and no theory that explains the gap via a spec defect can be right.

**2. The duplicated row is real.** `8-epi-PGF2a in urine` appears twice in the
2026-06-25 export — this was a half-remembered suspicion of Siggie's and it
checks out. *Not established:* whether the duplication shifted counts below it
or is a harmlessly repeated row. `Alcohol Consumption` reads identically across
all three later versions, so at least that row did not shift. **Determining the
consequence is task 1 below.**

**3. Row order moved.** 147 shared labels sit in a different relative order
between 2026-03-23 and 2026-06-25. Any per-row comparison against the
2026-06-25 sheet is suspect until this is understood.

**The event most worth explaining is 2025-08-05 → 2025-12-23**, which rewrote
essentially every cell and inflated counts across the board:

```
Cigarette smoking  ARIC   5 → 30      CARDIA 10 → 20     JHS 7 → 3
Troponin all types ARIC   9 → 60      CARDIA  2 → 4
```

Cohorts CHS, COPDGene, FHS, WHI appear for the first time there. The 2025-08-05
numbers are the same order of magnitude as what the current generator produces;
the December ones are ~6× larger. **That window, not the specs, is the likely
source of the ~112 cells where the generator reads lower than the published
sheet.** (Inference, not measurement — it is the obvious hypothesis, untested.)

## What to do

1. **Determine whether the duplicated row shifted anything.** Check whether
   label→count pairing in the 2026-06-25 export is consistent with 2026-03-23
   below the duplicate. If counts shifted, every per-row comparison done to date
   is meaningless and needs redoing; if not, the duplicate is cosmetic and the
   count differences are real. Everything else waits on this.
2. **Get the two missing exports.** Siggie offered 2026-07-28 and 2026-08-03;
   they are not in `xslx/` yet. They bracket the most recent changes and are
   likely the most diagnostic. **Ask him for them** — he can export from Google
   Sheets, and this is not something to work around.
3. **Relate count changes to script changes.** Siggie's framing: *"I doubt we'll
   be able to solve the problem without relating count changes to script
   changes."* For each sheet transition, find what changed in the generator
   between those dates. Start with the 2025-08-05 → 2025-12-23 inflation. The
   superseded pipeline is preserved in `old_pipeline/` for exactly this.
4. **Only then** diagnose the ~112 low / ~30 high cells individually.

**Do not start from per-row leads** (`Troponin all types` ARIC, `AHI
Apnea-Hypopnea Index` CHS) that earlier handoffs flagged. They predate the row
alignment finding and may be artifacts of it.

## The superseded pipeline is evidence

`old_pipeline/` holds the pipeline that produced the published numbers:
`preharmonized_qaqc_report.py`, its `valid-phvs/` filter lists, its output CSV,
and its notes (`CLAUDE.OLD.md`). Both the script and `valid-phvs/` are symlinked
from `transform_assessment/` so they still run.

Two things in there bear directly on the investigation:

- **The paste workflow:** copy all rows from the generated CSV *except the
  header*, paste starting at **line 5** of the template. Positional alignment by
  hand, no key joining count to label. This is the mechanism that makes
  misalignment plausible.
- **The filtering logic:** phvs were filtered against
  `valid-phvs/{cohort}-ingest.tsv` where a list existed, and *unfiltered* where
  none did. ARIC, CARDIA, and JHS had no lists — all their phvs were counted.
  COPDGene and FHS had lists but no data rows. That asymmetry is a candidate
  explanation for the December inflation, since COPDGene/FHS/CHS/WHI first appear
  in that transition. (Hypothesis, untested.)

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
  └─ s4-s5-tooling   cc0e2c64   pushed
       └─ s4-spec-codes  …       local; run S4 from here
```

`s4-spec-codes` is a fast-forward ahead of `s4-s5-tooling`, so merging it there
is trivial — but doing so pulls all of `main` plus the six concept-code fixes
into what was a tooling-only branch.

`origin/s4-spec-codes` is **stale and holds no work that isn't local**: its two
commits (`ca8a0dd2`, `f4deb029`) are byte-identical patches to local
`be10a45c` / `0c133794` under different SHAs, left over from a branch rebuild.
Do not `git pull` — it would merge the duplicates back in. Push with
`--force-with-lease`.

The six concept-code fixes are the entire delta from `main` in
`priority_variables_transform/` (20 files, one-line `observation_type` swaps plus
one tracking comment): `OMOP:4282779`→`OMOP:35811013`,
`OMOP:4042886`→`OMOP:37311566`, `OMOP:4209737`→`OBA:2052305`,
`OBA:VT0000217`→`OBA:VT0000717`, `OMOP:8842`→`OMOP:4021291`,
`OBA:2050108`→`OMOP:4138462`. Rationale per code in
[`../history/SPEC_CODE_CORRECTIONS_20260803.md`](../history/SPEC_CODE_CORRECTIONS_20260803.md).
Stephanie is expected to land these in `main` independently; if she does, drop
them here rather than landing both.
