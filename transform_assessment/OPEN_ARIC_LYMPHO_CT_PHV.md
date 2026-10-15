# Open: ARIC lymphocyte and WBC counts read the same source column

**Status:** needs a curator/spec-owner decision. Nothing else is blocked on it —
CI passes, and the code change that exposed it is correct.

This is the single account of the issue. Everywhere else that mentions it points
here; you do not need to read those.

## The problem, in one sentence

ARIC's `lympho_ct.yaml` and `whtbld_ct.yaml` both populate their measurement
value from **the same dbGaP column** — `pht006422` / `phv00294954` — and a
lymphocyte count and a white-blood-cell count cannot be the same column.

```
priority_variables_transform/ARIC-ingest/lympho_ct.yaml   block 0
  observation_type: OBA:VT0000717   (Lymphocytes count)
  value_decimal populated_from: phv00294954   <-- same column

priority_variables_transform/ARIC-ingest/whtbld_ct.yaml   block 1
  observation_type: OBA:VT0000217   (White blood cell count)
  value_decimal populated_from: phv00294954   <-- same column
```

Reproduce:

```bash
./.venv/bin/python check_phv_dedup.py
```

## Why it appeared now (it is not new, and it is not a regression)

ARIC's `lympho_ct.yaml` used to carry `OBA:VT0000217` — the *white blood cell*
code — which was a digit-transposition typo. It was corrected to `OBA:VT0000717`
in 2026-08 (rationale:
[`history/SPEC_CODE_CORRECTIONS_20260803.md`](history/SPEC_CODE_CORRECTIONS_20260803.md)
§4).

While both files carried the same concept code, `check_phv_dedup.py` had nothing
to compare and the shared column was invisible. Correcting the typo made an
existing data problem visible. Verified by reverting `lympho_ct.yaml` to main's
version: no duplicate is reported.

**Do not "fix" this by reverting the concept code.** That would re-hide the bug
and reintroduce a code that means the wrong thing.

## What the curator / ARIC spec owner needs to decide

One question: **which ARIC column actually holds the lymphocyte count?**

`phv00294954` is presumably the WBC count (that is what `whtbld_ct.yaml` claims,
and every other cohort's `whtbld_ct` uses `OBA:VT0000217` correctly). If so,
`lympho_ct.yaml` is pointing at the wrong column and needs the real
lymphocyte-count phv from `pht006422`.

The alternative — that `phv00294954` is the lymphocyte count and `whtbld_ct.yaml`
is wrong — seems less likely but has not been ruled out.

Worth knowing while deciding: ARIC's `lympho_ct.yaml` has only this one block,
so whatever the answer, the change is small.

## What a programmer does afterwards

1. Edit `priority_variables_transform/ARIC-ingest/lympho_ct.yaml` (or
   `whtbld_ct.yaml`, if that is the wrong one) so `value_decimal.populated_from`
   names the correct phv. Only the `populated_from` line changes; leave
   `observation_type` alone.
2. Remove `"phv00294954"` and its comment block from `KNOWN_ISSUES` in
   `check_phv_dedup.py`.
3. Run `./.venv/bin/python check_phv_dedup.py` — it should report no new
   duplicates and no known issues for that phv.
4. Delete this file, and drop the pointer to it from
   `history/SPEC_CODE_CORRECTIONS_20260803.md` §4 and from `README.md`.
5. Re-run S4. ARIC's `Lymphocytes count` row will change, and `White blood cell
   count` may too. That is the fix landing, not a regression.

## Why it is suppressed rather than fixed

`check_phv_dedup.py`'s `KNOWN_ISSUES` is the repo's existing mechanism for
tracked-but-unresolved duplicates (8 other phvs sit there). Suppressing keeps CI
green without pretending the problem is solved. Per `CLAUDE.md`, entries should
be removed as they are resolved.
