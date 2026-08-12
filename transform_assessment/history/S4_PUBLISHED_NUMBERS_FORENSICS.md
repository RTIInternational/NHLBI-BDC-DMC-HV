# How the published Table S4 numbers were traced (2026-08 forensics)

Archived 2026-08-12. This is the closed-out record of an investigation into
where the published Table S4 numbers came from. **It is history, not
instructions** — the question it answers is settled, and the goal it served
(reproducing those numbers) has since been retired. See
[`../s4_count_investigation/HANDOFF.md`](../s4_count_investigation/HANDOFF.md)
for what is actually live.

Kept for two reasons: the scripts described here still run and still pass, so
the findings are re-verifiable; and the method — attributing every changed cell
to a code commit or an input edit — is worth reusing if the published table
ever needs auditing again.

**The short version.** The published numbers are exactly the CSV committed in
`1e6a34db` (2025-12-11), output of the superseded pipeline, pasted into the
Google Sheet and frozen since. All 1332 compared cells match. Every earlier
change is attributed to a specific code commit or input-sheet edit. Earlier
theories — that counts drifted mysteriously, or were pasted out of alignment
with their labels — were tested and are false.

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

Thirteen dated exports of the Google Sheet are in `s4_count_investigation/xlsx/`, covering every
version that changed from 2025-08-05 on. **`s4_count_investigation/xlsx/` holds published-sheet
exports only** — generated runs live in `new_pipeline_runs/`, because the
comparison scripts glob `s4_count_investigation/xlsx/*.xlsx` and parse a date from each filename, so a
generated file dropped in there silently corrupts the version history. More can
be made: the saved Google Sheet versions they were exported from live in the
repo owner's Drive at *My Drive / old_s4_files_for_debuggin*, symlinked as
`s4_count_investigation/xlsx/old_gsheet_versions` (**resolves on that one machine only** — dangling
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

