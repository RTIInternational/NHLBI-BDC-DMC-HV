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
├── io.py                      # JSON read/write
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

Per-family file grouping, ~7 files of moderate size.

**Targets:**
- Each file under ~500 lines where practical.
- Each check exposes `run(crosswalk, source, harmonized, config) -> CheckResult`.
- No behavior changes in this phase. Tests must pass with bit-identical JSON
  output.

**Regression-safety approach:** before starting, capture the current JSON
output for a representative cohort (e.g., COPDGene), then diff after each
file-extraction step. Concrete: `jq -S . old.json > old.sorted` and same for
new, then `diff` them. We don't currently have snapshot-test infrastructure
in the repo, and `jq -S` diffing is enough for this kind of structural
parity check. (Open to a more rigorous approach if Chris prefers.)

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
| Domain grouping labels (`measurement_*`, `condition_*`, etc.) | `config/checks.yaml` | Used in crosswalk grouping |
| Status icons (`_STATUS_ICONS`) | `config/report_format.yaml` | Renderer config |
| Collapse threshold (currently `4`) | `config/report_format.yaml` | |
| dbGaP URL patterns | `config/links.yaml` | See Phase D links |
| Ontology URL patterns (MONDO, OBA, etc.) | `config/links.yaml` | See Phase D links |
| Check execution order (C1–C11) | `config/checks.yaml` | Also: which to run/skip |
| Study ID extraction regex | Manifest files (already exist) | Replace fragile regex |

**Two-file split:**
- `config/checks.yaml` — *behavior*: which checks to run, in what order,
  per-check descriptions, status order, domain grouping labels.
- `config/report_format.yaml` — *cosmetics*: status icons, collapse
  threshold, link-type toggles, anything purely visual.

A separate `config/links.yaml` holds URL templates (see Phase D); kept
distinct because link templates are reference data, not user-tunable
formatting preferences.

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
| Concept codes (MONDO, OBA, …) | per-ontology, see table below |

Design notes:
- Each link type has an on/off toggle in `config/report_format.yaml`.
- URL templates live in `config/links.yaml`, not hardcoded in renderer code.
- Linking logic lives entirely in the renderer. The JSON always carries plain
  IDs; the renderer decides what (if anything) to wrap them in. This means
  the same comparison JSON re-renders with different link configs.

#### Ontology resolver options — example links for comparison

All examples resolve `MONDO:0004981` ("atrial fibrillation"). For non-MONDO
ontologies the table notes coverage caveats.

| Option | Example URL | Coverage | Notes |
|---|---|---|---|
| **OBO PURL** (redirects → OLS4) | http://purl.obolibrary.org/obo/MONDO_0004981 | OBO ontologies only: MONDO, HP, OBA, GO, UBERON, CHEBI, EFO, VT, etc. | Trivial template: `{PREFIX}_{LOCAL_ID}` with underscore. No coverage for SNOMEDCT, LOINC, OMIM, RxNorm, CPT. **Recommended primary for OBO prefixes.** |
| **OLS4 direct** | https://www.ebi.ac.uk/ols4/ontologies/mondo/classes/http%253A%252F%252Fpurl.obolibrary.org%252Fobo%252FMONDO_0004981 | Same as OBO PURL | Same destination but uglier double-encoded URL. Skip unless you want to bypass the redirect. |
| **BioPortal** | https://bioportal.bioontology.org/ontologies/MONDO?p=classes&conceptid=http%3A%2F%2Fpurl.obolibrary.org%2Fobo%2FMONDO_0004981 | Universal: MONDO, OBA, SNOMEDCT, LOINC, HP, OMIM, RxNorm, CPT | No API key for browser URLs. Heavier UI than OLS. **Recommended as catch-all fallback.** |
| **Monarch (MONDO/HP)** | https://monarchinitiative.org/disease/MONDO:0004981 | MONDO, HP | Nicer disease-focused UI than OLS. |
| **LOINC** | https://loinc.org/8302-2/ | LOINC only | Clean per-code pages, loads cleanly. |
| **OMIM** | https://omim.org/entry/600807 | OMIM only | Works in browsers. |
| **SNOMED browser** | https://browser.ihtsdotools.org/?perspective=full&conceptId1=73211009 | SNOMEDCT only | Public IHTSDO browser. |
| **RxNav** | https://mor.nlm.nih.gov/RxNav/search?searchBy=RXCUI&searchTerm=198440 | RxNorm only | NLM-hosted. |
| **CPT** | — | n/a | AMA-licensed, no free public URL — render as plain code. |

#### Proposed `config/links.yaml` (layered fallback)

```yaml
dbgap:
  phv: "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/variable.cgi?study_id={study}&phv={phv}"
  pht: "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/dataset.cgi?study_id={study}&pht={pht}"
  study: "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id={study}"

ontologies:
  # OBO Foundry prefixes → OBO PURL (redirects to OLS4)
  MONDO: "http://purl.obolibrary.org/obo/{prefix}_{local_id}"
  HP:    "http://purl.obolibrary.org/obo/{prefix}_{local_id}"
  OBA:   "http://purl.obolibrary.org/obo/{prefix}_{local_id}"
  GO:    "http://purl.obolibrary.org/obo/{prefix}_{local_id}"
  UBERON: "http://purl.obolibrary.org/obo/{prefix}_{local_id}"
  CHEBI: "http://purl.obolibrary.org/obo/{prefix}_{local_id}"
  EFO:   "http://purl.obolibrary.org/obo/{prefix}_{local_id}"
  VT:    "http://purl.obolibrary.org/obo/{prefix}_{local_id}"

  # Non-OBO terminologies → per-source portals
  OMIM:    "https://omim.org/entry/{local_id}"
  LOINC:   "https://loinc.org/{local_id}/"
  RXNORM:  "https://mor.nlm.nih.gov/RxNav/search?searchBy=RXCUI&searchTerm={local_id}"
  SNOMEDCT: "https://browser.ihtsdotools.org/?perspective=full&conceptId1={local_id}"

  # Fallback for anything not listed above
  default: "https://bioportal.bioontology.org/ontologies/{prefix}?p=classes&conceptid={iri_url_encoded}"

  # No public URL — render as plain text
  no_link: [CPT]
```

**Why layered:** OBO PURL is the simplest template but only covers OBO
ontologies. BioPortal covers everything but pages are heavier and the host
blocks scripted fetches (irrelevant for human reviewers clicking links,
but would break automated link-checking). The layered approach picks the
best URL per prefix and uses BioPortal only as fallback.

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

### Idea parked: inferred corrections for unit-error patterns

Stephanie suggested: when a clinical-range FAIL looks like a unit error
(e.g., height in m vs. cm, °F vs. °C), surface an "inferred corrected"
aggregate alongside the failing value so reviewers can see the likely
hypothesis. Scope if revisited: C9 only, common unit conversions only,
clearly labeled as hypotheses not corrections, computed in the renderer
from existing aggregates (not stored in extract JSONs). Not in scope for
current plan.

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

## Files most likely to change

| File | Phase |
|---|---|
| `compare/compare_source_harmonized.py` | A (split out), C, D |
| `compare/{crosswalk,render,io}.py`, `compare/checks/*` | A (new), C, D |
| `extract_source/extract_source_summaries.py` | B |
| `compare/config/checks.yaml` (new) | C |
| `compare/config/report_format.yaml` (new) | C, D |
| `compare/config/links.yaml` (new) | D |
| `tests/test_compare_source_harmonized.py` | A (split alongside), B, C |
