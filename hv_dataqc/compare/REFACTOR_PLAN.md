# HV-DataQC Compare Refactor Plan — Draft for Review

> **Status:** Draft proposal for Chris's review. This file is **temporarily
> committed** for ease of inline comments; we'll remove it from the repo once
> the discussion converges (or move it into `docs/` if we want to keep it).
>
> Source of truth during the discussion: this file. Changes here are
> non-binding — nothing has been implemented yet.

## Context

`compare_source_harmonized.py` is currently ~4,090 lines and does five jobs:
crosswalk building, mode detection, check execution (C1–C12), JSON output, and
Markdown rendering. The goals of this refactor:

1. Break the file into navigable modules.
2. Make check logic, thresholds, descriptions, and rendering behavior
   config-driven where possible.
3. Make JSON the single source of truth for report generation, so reports can
   be re-rendered (e.g., after annotation) without re-running the comparison.
4. Use Chris's transform-mode table consistently to dispatch comparison
   strategy and avoid false FAILs on YAML shapes the comparator can't evaluate.
5. Clean up the redundant `variables`/`variables_by_pht` duplication in source
   extracts.
6. Improve report content (header metadata, dbGaP/ontology links, surfacing
   PHVs in more places).

---

## Sequencing

Recommended order. Each phase is intended to merge as a coherent change set
before the next begins:

1. **Phase A — File split** (mechanical, low-risk; sets the stage)
2. **Phase B — JSON extract cleanup** (drops `variables` flat dict; breaking)
3. **Phase C — Config externalization + mode-aware dispatch**
4. **Phase D — Report content improvements**
5. **Phase E (deferred)** — Standalone `render_report.py`
6. **Phase F (deferred)** — SB bootstrap + private results repo

Rationale for ordering: the mode-aware dispatch in Phase C lives inside the
checks, so doing the file split first means each check is already in its own
module before its dispatch logic is touched. The JSON cleanup is independent
of the file split but should land before Phase C so config schema and check
code aren't reasoning about two parallel views of the source data.

---

## Phase A: File split

`compare_source_harmonized.py` is ~4,090 lines. Proposed layout (subject to
refinement as the split proceeds):

```
hv_dataqc/compare/
├── __main__.py                # CLI entry, orchestration
├── compare.py                 # top-level run_comparison(...) function
├── crosswalk.py               # YAML parsing, mode detection, PHV resolution
├── io.py                      # JSON read/write, schema versioning
├── render.py                  # MD rendering
├── checks/
│   ├── __init__.py
│   ├── base.py                # CheckResult dataclass, shared helpers
│   ├── n_preservation.py      # C1, C2
│   ├── missing_values.py      # C3
│   ├── distributions.py       # C4, C5, C6, C7
│   ├── visit_n.py             # C8
│   ├── clinical_ranges.py     # C9
│   ├── cross_variable.py      # C10
│   └── type_consistency.py    # C11
└── config/                    # existing config dir
```

**Open question for Chris:** per-check files (C1.py, C2.py, …, ~12 small
files) vs. per-family (above, ~7 files of moderate size). The per-family
grouping above is a starting suggestion — we'd refine during the walkthrough
of each check.

**Targets:**
- Each file under ~500 lines where practical.
- Each check exposes `run(crosswalk, source, harmonized, config) -> CheckResult`.
- No behavior changes in this phase. Tests must pass with bit-identical JSON
  output. Add a snapshot test (compare pre/post JSON) before starting.

---

## Phase B: JSON extract cleanup

**Problem:** `extract_source_summaries.py` emits two parallel views of the
same data:

- `variables` — flat dict, keyed by column name. Uses a collision rule:
  the first PHT to introduce a column claims the bare name; later PHTs get
  a `pht.colname`-prefixed key.
- `variables_by_pht` — nested dict, keyed by `(pht, column_name)`.

The flat view is fragile (collision rule depends on iteration order,
no way for a consumer to know whether a bare key means "single PHT" or
"first PHT among many"), redundant with the nested view, and inflates JSON
size. Consumers should always use `variables_by_pht`.

**Plan (no backward compatibility):**
- Audit `compare_source_harmonized.py` and tests for reads of `variables`
  and migrate them to `variables_by_pht`.
- Remove the `variables` field from `extract_source_summaries.py` output.
- Update example JSON snapshots in tests.
- Re-run extracts for active cohorts after merging; older `local_output/`
  JSONs will need to be regenerated.

---

## Phase C: Config externalization + mode-aware comparison dispatch

### Currently hardcoded → proposed config

| Currently hardcoded | Proposed home | Notes |
|---|---|---|
| Check descriptions (`_check_descriptions` dict) | `config/checks.yaml` | Descriptions, names, status order |
| Domain grouping labels (`measurement_*`, `condition_*`, etc.) | `config/checks.yaml` or `config/domains.yaml` | Used in crosswalk grouping |
| Status icons (`_STATUS_ICONS`) | `config/report_format.yaml` | Renderer config |
| Collapse threshold (currently `4`) | `config/report_format.yaml` | |
| dbGaP URL patterns | `config/dbgap.yaml` | See Phase D links |
| Ontology URL patterns (MONDO, OBA, etc.) | `config/ontologies.yaml` | See Phase D links |
| Check execution order (C1–C11) | `config/checks.yaml` | Also: which to run/skip |
| Study ID extraction regex | Manifest files (already exist) | Replace fragile regex |

### Already externalized (keep as-is)

- `thresholds.yaml` — PASS/WARN/FAIL boundaries per check
- `clinical_ranges.yaml` — plausible ranges, cross-variable rules
- `harmonized_extract.yaml` — entity filenames, demography columns
- Manifest files — study IDs, versions, dbGaP URLs per cohort

### Mode-aware comparison dispatch

Chris's transform mode table (from
`hv_dataqc/compare/WALKTHROUGH_CONTEXT.md`):

| Mode | Detected From YAML | Comparison |
|---|---|---|
| `single_source` | one block, one value PHV | current behavior |
| `multi_block_sum` | same concept emitted by multiple blocks | sum expected rows across blocks |
| `value_mapping_route` | concept/status uses `value_mappings` | compare against mapped source-code counts |
| `case_filtered` | simple `case(phv == value, output)` | compare against filtered source-code counts |
| `multi_phv_expression` | expression references multiple PHVs | WARN/INFO unless evaluable from aggregate summaries |
| `unsupported_complex` | arbitrary expression / join logic | surface as "manual review needed," not false FAIL |

C2–C7 should consult the detected mode before applying pass/fail semantics.
The two big wins: (1) `multi_block_sum`, `value_mapping_route`, and
`case_filtered` get *meaningful* comparisons instead of noisy fails;
(2) `unsupported_complex` no longer produces false FAILs — it produces a
clear "manual review needed" status.

Commit `1e6a61fe` (source-driven comparison type dispatch) started this
work; this phase continues it.

---

## Phase D: Report content improvements

### Header additions (cheap, high-value)

- **Study version** (e.g., `phs000179.v8.p2`) and PHS accession at the top
  of the report. Already in manifest files — just thread through to the
  report header.
- Already there: dbGaP study link, dataset list URL. Confirm consistency
  across cohorts.

### dbGaP / ontology links — all types, config-toggleable

| Link type | Target |
|---|---|
| PHV IDs | dbGaP `variable.cgi` |
| PHT IDs | dbGaP `dataset.cgi` |
| Study ID (header) | dbGaP study page |
| Concept codes (MONDO, OBA, …) | OLS or BioPortal (per-ontology pattern) |

Design notes:
- Each link type has an on/off toggle in `config/report_format.yaml` so
  individual users can dial down visual noise.
- URL templates live in `config/dbgap.yaml` and `config/ontologies.yaml`,
  not hardcoded in renderer code.
- Linking logic lives entirely in the renderer (Phase E preview). The JSON
  always carries plain IDs; the renderer decides what (if anything) to wrap
  them in. This makes the same comparison JSON re-renderable with different
  link configs.
- TBD before implementation: confirm OLS / BioPortal URL templates for the
  concept-code families we use; figure out whether we need an API key for
  any of them. Worth a quick spike.

### Surface PHVs in more places

Many report sections reference harmonized concepts
(e.g., `measurement_OBA:VT0001253`) without surfacing the underlying PHV(s)
that map to them. The user has to flip back to the crosswalk table to look
up the source variable.

Candidates for inline PHV inclusion:
- C2 (N Loss) per-variable rows
- C4 / C6 mean & SD comparison rows
- C7 distribution sections
- C9 clinical range findings

Implementation: each `CheckResult.detail` should carry the resolved PHV(s)
from the crosswalk so the renderer can include them inline.

---

## Phase E (deferred): Standalone `render_report.py`

Once Phase A has separated `render.py` and Phase C/D have produced a stable,
self-describing JSON, the renderer becomes a free-standing script:

- `render_report.py JSON_PATH [--config config/report_format.yaml]` → produces
  Markdown.
- Enables: annotate JSON → re-render; switch link/format config without
  re-running the comparison; investigation-tracker workflows.
- Chris confirmed ARIC report size (488KB) is fine; no need to split reports.

## Phase F (deferred): SB bootstrap + private results repo

- `bootstrap.sh` for fresh Seven Bridges sessions
- Private GitHub repo for comparison reports (kept out of the public code repo)
- `publish_results.sh` convenience script

---

## Open questions for Chris

1. **Phase A grouping** — per-check files vs. per-family modules? Proposal
   above is per-family, but happy to go per-check if you'd rather.
2. **Phase B timing** — OK to land the JSON cleanup as a hard break (force
   re-extraction), or do you want a one-release backward-compatible window
   where compare can read either form?
3. **Phase C config naming** — `config/checks.yaml` mixes "list of checks
   to run" with "descriptions/icons/etc.". Should those be one file or two
   (e.g., `checks.yaml` for behavior, `report_format.yaml` for cosmetics)?
4. **Phase D ontology links** — which ontology registries should we
   target as primary (OLS, BioPortal, OBO Foundry, ontology-specific
   sites)? Any prior preference?
5. **Phase A behavior parity test** — do you have a preferred way to do
   snapshot tests for JSON output, or should we just diff with `jq -S`?

---

## Files most likely to change

| File | Phase |
|---|---|
| `compare/compare_source_harmonized.py` | A (split out), C, D |
| `compare/{crosswalk,render,io}.py`, `compare/checks/*` | A (new), C, D |
| `extract_source/extract_source_summaries.py` | B |
| `compare/config/checks.yaml` (new) | C |
| `compare/config/report_format.yaml` (new) | C, D |
| `compare/config/dbgap.yaml` (new) | D |
| `compare/config/ontologies.yaml` (new) | D |
| `tests/test_compare_source_harmonized.py` | A (split alongside), B, C |
