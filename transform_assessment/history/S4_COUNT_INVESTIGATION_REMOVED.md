# The S4 count investigation — removed 2026-08-12, and why

There used to be a `transform_assessment/s4_count_investigation/` directory
(~2.4 MB: 13 dated xlsx exports of the published sheet, three comparison
scripts, a change ledger, the superseded pipeline, and a long HANDOFF.md). It
is gone. This note says what it was for, why it stopped mattering, and how to
get it back.

## Why it existed

The spec-sourced generator produced numbers that didn't match the published
Table S4. The investigation set out to explain the difference cell by cell. It
succeeded at the historical question: the published numbers are exactly the CSV
committed in `1e6a34db` (2025-12-11), output of a superseded pipeline, pasted
into the Google Sheet and frozen since — all 1332 compared cells matched, and
every earlier change in the sheet was attributed to a specific code commit or
input-sheet edit.

## Why it stopped mattering

The old pipeline narrowed its phv set two ways, and on 2026-08-12 the project
lead retired both: *"those lists of valid phv were made a year ago and probably
are no longer valid. You also shouldn't go by what is in the spreadsheets
anymore. We can't keep those up to date."*

- `valid-phvs/{cohort}.tsv` — hand-made per-cohort allow lists, ~2025
- `Transform Comment == "out of scope"` — a curator annotation in two live
  Google Sheets

The current generator implements neither and has no path by which a per-phv
scope decision reaches it. So the published table is a **frozen historical
artifact**, not a target: the two pipelines answer different questions, and only
one of them has maintainable inputs. Comparing them cell-by-cell no longer
decides anything, which makes the entire comparison apparatus dead weight.

**The one durable conclusion:** the retired filters only ever *removed* phvs, so
the current generator is expected to report **higher** counts than the published
table. An increase needs no explanation; a decrease does.

## How to get it back

```bash
git show pre-s4-doc-cleanup-20260812:transform_assessment/s4_count_investigation/HANDOFF.md
git checkout pre-s4-doc-cleanup-20260812 -- transform_assessment/s4_count_investigation/
```

The tag `pre-s4-doc-cleanup-20260812` (on branch `s4-s5-tooling`) holds the
whole thing intact — every xlsx export, every script, the full investigation
narrative.

## What you might want it for

Realistically, one thing: **auditing the published Table S4 again.** If someone
questions a published number, `verify_published_source.py` and
`compare_s4_versions.py` still run and still pass, and `xlsx/` is the only
record of the sheet's version history. Restore the directory rather than
rebuilding it.

Two smaller reasons:

- **The method.** Attributing every changed cell to a code commit or an input
  edit is reusable, and it is what settled a question that four spreadsheet
  exports could not.
- **The old pipeline's diagnostics.** `preharmonized_qaqc_report.py:316-319`
  printed a bidirectional config-vs-data cohort reconciliation, and line 285
  *unioned* config and data cohorts rather than letting config truncate. The
  rewrite dropped both, which is why several silent config gaps went unnoticed
  (see the handoff in `hv_dataqc/` and the notes in
  [`../SPEC_SOURCED_S4_DESIGN.md`](../SPEC_SOURCED_S4_DESIGN.md)). Worth reading
  before rebuilding that check.

## What did NOT come back with it

Do not restore `transform_assessment/valid-phvs/` or the
`preharmonized_qaqc_report.py` symlink as *working* inputs. Both were removed
deliberately. The lists are stale and the script reads Google Sheets that have
since moved — it cannot reproduce its own published output today.
