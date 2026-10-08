# HV-Lint: Automated YAML Validation for the HV Repository

**Scope**: All `*-ingest/*.yaml` transformation specification files in `priority_variables_transform/`

---

## Quick Start

- **Run lint**: See [LOCAL-RUN-GUIDE.md](LOCAL-RUN-GUIDE.md) for step-by-step CLI instructions
- **Update dbGaP indexes**: See [MAINTENANCE.md](MAINTENANCE.md) for data refresh procedures
- **Dependencies**: PyYAML, yamllint (core); linkml-runtime (Phase 2 schema validation); requests-cache (optional, data fetch only)

---

## What Is HV-Lint?

HV-Lint is the automated static analysis layer for HV repository YAML files. It catches mechanical errors before merge via CI (GitHub Actions), complementing expert-driven review (HV-Audit) that handles checks requiring domain knowledge and human judgment.

### Design Principle: Schema-Driven Validation

HV-Lint validates against **authoritative schemas** (linkml-map model, BDCHM) rather than maintaining static lists of known typos. This means:

- New typos and errors are caught automatically -- no need to update the validator
- Schema changes propagate automatically -- if BDCHM adds or renames slots, validation updates for free
- The only explicit patterns are dbGaP accession format and within-cohort consistency (no schema to validate against)

---

## Architecture

HV-Lint is organized into four phases with increasing data requirements:

| Phase | Name | Data Required | Status |
|-------|------|--------------|--------|
| **Phase 1** | YAML Structural & Formatting | YAML files only | Active |
| **Phase 2** | BDC-HM Model Conformance | YAML files + BDCHM/linkml-map schemas | Active |
| **Phase 3** | dbGaP Structure & Cross-Reference | YAML files + dbGaP PHV indexes | Active |
| **Phase 4** | Regression Detection | Phase 1-3 outputs + git diff | Planned |
| **Phase 5** | Visit Structure Validation | YAML files + visit.yaml + visit cache + PHV index | Active |

### dbGaP Cache Architecture

Phases 3 and 5 use **compressed JSON indexes** (committed in `hv-lint/dbgap-cache/`) instead of raw XML:

1. **Basic index** (`<cohort>.json.gz`) -- maps each base PHV to base PHT (~425 KB total). Used by rules 3.1-3.5.
2. **Extended detail index** (`<cohort>_detail.json.gz`) -- adds variable name, type, unit, description, coded values, and collection interval (`coll_interval`). Used by rules 3.9-3.18 and 5.8.
3. **Value-count index** (`<release>_stats.json.gz`, e.g. `phs000287.v7_stats.json.gz`) -- for each coded variable, the var_report non-null count `n` and the count of each observed code (dbGaP's published aggregate summaries; no participant data). Used by rules 3.17b and 3.18. Built by `hv-lint/build_phv_stats_index.py` from the `*.var_report.xml` files of the pinned release (~1 MB for all cohorts); `update_data.py` does not fetch var_reports yet.

Indexes are committed to this repo (~4 MB total) so CI and contributors can run lint without fetching from NCBI. To rebuild: `python hv-lint/update_data.py --build-only`.

| Cohort | PHVs | PHTs | Compressed Size |
|--------|------|------|----------------|
| ARIC | 31,705 | 398 | 69 KB |
| CARDIA | 9,364 | 322 | 19 KB |
| CHS | 14,717 | 56 | 33 KB |
| COPDGene | 1,026 | 5 | 2 KB |
| FHS | 91,702 | 541 | 214 KB |
| HCHS-SOL | 1,571 | 3 | 4 KB |
| JHS | 4,224 | 103 | 9 KB |
| MESA | 22,147 | 93 | 53 KB |
| SPIROMICS | 269 | 3 | 1 KB |
| WHI | 6,207 | 86 | 13 KB |
| **Total** | **182,932** | -- | **~425 KB** |

### File Inventory

| File | Phase | Purpose |
|------|-------|---------|
| `hv-lint/_paths.py` | -- | Shared path resolution (supports `HV_ROOT` env var and `--hv-root` override) |
| `hv-lint/_http.py` | -- | Self-contained HTTP caching layer for data fetching |
| `hv-lint/_known_issues.py` | all | Known issues, stale-entry check and WARNING ratchet, called by every component (A7) |
| `hv-lint/known_issues.yaml` | all | One entry per known ERROR finding, each with its issue and status (A7) |
| `hv-lint/warning_baseline.json` | all | WARNING count per rule and cohort, ratcheted (A7) |
| `hv-lint/_visit_ids.py` | 1, 5 | ast enumerator of id / associated_visit / associated_participant values (1.8, 5.1, 5.2, 5.11) |
| `hv-lint/_expr.py` | 2 | ast readers for `expr` strings (2.4, 2.7, 2.10) |
| `hv-lint/_derivations.py` | all | Nested class-derivation parsing and the every-depth slot walker |
| `hv_dataqc/cache_fetcher/manifests/_manifest-<cohort>.yaml` | -- | Cohort version pins (study IDs, data versions) — single source of truth shared with hv_dataqc |
| `hv-lint/update_data.py` | -- | Fetch + build all indexes and visit cache (single entry point) |
| `hv-lint/.yamllint` | 1 | yamllint configuration |
| `hv-lint/phase-1/run_phase1.py` | 1 | Phase 1 manager -- orchestrates all sub-components |
| `hv-lint/phase-1/validate_yaml_structure.py` | 1 | Structural checks (1.1-1.5, 1.7, 1.9, 1.10, 1.11, 1.13) |
| `hv-lint/phase-1/run_yamllint.py` | 1 | yamllint wrapper |
| `hv-lint/phase-1/check_quoting_rules.py` | 1 | Issue #387 quoting rule checker |
| `hv-lint/phase-1/check_cross_block_consistency.py` | 1 | Cross-block slot consistency (1.6) |
| `hv-lint/phase-1/check_cross_file_pht_consistency.py` | 1 | Cross-file PHT visit label consistency (1.8) |
| `hv-lint/phase-1/check_cross_file_duplicates.py` | 1 | Cross-file identical blocks (1.12) |
| `hv-lint/phase-2/run_phase2.py` | 2 | Phase 2 manager -- orchestrates model conformance and PHV dedup |
| `hv-lint/phase-2/validate_model_conformance.py` | 2 | BDC-HM model conformance checks (2.1-2.7, 2.5b, 2.10, 2.12) |
| `hv-lint/phase-2/check_phv_dedup.py` | 2 | PHV deduplication check (2.8) |
| `hv-lint/phase-3/run_phase3.py` | 3 | Phase 3 manager -- orchestrates all dbGaP cross-reference and semantic checks |
| `hv-lint/phase-3/validate_dbgap_crossref.py` | 3 | dbGaP cross-reference checks (3.1-3.5) |
| `hv-lint/phase-3/validate_semantic.py` | 3 | Semantic validation (3.9, 3.10, 3.12-3.16) |
| `hv-lint/phase-3/check_value_semantic.py` | 3 | Value-mapping label/OMOP semantic check (3.11) |
| `hv-lint/phase-3/check_status_semantic.py` | 3 | Status-slot polarity and follow-up checks (3.17, 3.18) |
| `hv-lint/build_phv_stats_index.py` | -- | Builds compressed value-count indexes from var_report files; `--tables` builds the table-name index (`<release>_tables.json.gz`, FHS only, rule 1.8) |
| `hv-lint/tests/` | -- | Unit tests (`python -m pytest hv-lint/tests/`) |
| `hv-lint/build_phv_index.py` | -- | Builds compressed PHV-to-PHT indexes from bulk HTML cache |
| `hv-lint/build_phv_detail_index.py` | -- | Builds extended PHV detail indexes from FTP data_dict.xml files |
| `hv-lint/phase-5/run_phase5.py` | 5 | Phase 5 manager -- orchestrates visit structure validation |
| `hv-lint/phase-5/validate_visit_structure.py` | 5 | Visit structure checks (5.0-5.11) |

---

## Assumptions & Design Decisions

### A1: BDCHM Schema Is Fetched at Runtime

Phase 2 loads the BDCHM schema directly from GitHub via URL at validation time, at the commit pinned in `BDCHM_REF` (`hv-lint/phase-2/validate_model_conformance.py`, HM `3fe055ed`, 2026-09-25); `--bdchm-ref` overrides it for one run. Phase 2 is enforced and its WARNINGs are ratcheted, so the ref is pinned: a live `main` would let an upstream schema commit fail every HV PR. To bump it, change `BDCHM_REF` in an HV PR, run `HVLINT_UPDATE_BASELINE=1 python hv-lint/run_all.py --cohort all`, and review the known-issue and baseline changes in the same PR.

- **Implication**: CI requires network access to `raw.githubusercontent.com`
- **Override**: `--bdchm-schema /path/to/local/bdchm.yaml` for offline/locked validation

### A2: linkml-map Model Fields -- Live Import with Frozen Fallback

`_derive_valid_keys()` in `validate_model_conformance.py` attempts a **live import** of `linkml_map.datamodel.transformer_model` at runtime to get valid key sets. If the import fails, it falls back to **frozen constants** captured from v0.3.9 and prints a `WARNING:` to stderr.

**Why the import can fail (Python 3.14):**
`linkml_map/__init__.py` eagerly imports `ObjectTransformer` which crashes with `KeyError: 'millimeter_Hg'` on Python 3.14. The HV repo's `pyproject.toml` pins `requires-python = ">=3.12,<=3.13"` for this reason.

| Environment | Behavior |
|---|---|
| CI (Python 3.12, `linkml-map` installed) | Live import succeeds -- always accurate |
| Local (Python 3.14, no `linkml-map`) | Falls back to frozen v0.3.9 constants -- prints WARNING |

**Action required if `linkml-map` is upgraded:** Update both the frozen constants in `validate_model_conformance.py` and this assumption note.

### A3: HV Extensions (`value`, `object_derivations`) Are Valid Keys

Two keys used in HV YAML files are **not** in the base `linkml-map` model but are treated as valid:

- `value` -- used for static value assignment (e.g., `value: "OMOP:38003563"`)
- `object_derivations` -- used for nested object structure (e.g., `Quantity` inside `value_quantity`)

These are included in `VALID_SLOT_DERIVATION_KEYS` and will not trigger CRITICAL findings.

### A4: PHV/PHT Format Assumptions

- **PHV**: Exactly `phv` followed by 8 digits (e.g., `phv00098579`). Version suffix (`.v7.p3`) is stripped during index building.
- **PHT**: Exactly `pht` followed by 6 digits (e.g., `pht001440`). Version suffix stripped.

### A5: dbGaP Index Is Built from Bulk Variable List HTML

The dbGaP variable list pages (`GetListOfAllObjects.cgi`) return HTML tables. The `build_phv_index.py` script parses this HTML to extract a `{base_phv: base_pht}` mapping, then compresses it to `.json.gz`.

- **Assumption**: The HTML table has 5 columns: variable accession, variable name, variable description, dataset accession, dataset name
- **Assumption**: Stripping the version suffix (`.vN.pN`) yields the canonical accession

### A6: Cross-Table PHV References Resolve Only Through a Join

linkml-map 0.5.3 (run with dm-bip's own schema step and map call) reaches another table's column only through a join: a declared `joins` entry, a dotted `{pht.phv}` reference, or a nested derivation whose `populated_from` names that table (the last two are joins it synthesizes on `dbGaP_Subject_ID`). A BARE `{phv}` from another table is not a slot of the row: the value is None on every row, with one pre-flight log line. So no slot is "expected" to read another table bare -- not the linkage slots, not the age slots (rule 3.5).

### A7: Known Issues Are Written Down, One Entry per Finding

Every phase fails CI on ERROR (`.github/workflows/hv_lint.yml`). A known finding is not skipped and not downgraded by its rule: it is listed in `hv-lint/known_issues.yaml`, one entry per finding, read by `hv-lint/_known_issues.py` in every component. An entry names its finding by **fingerprint**, never by a count or a block's position:

- `rule`; `file` (cohort-relative, or `<C>-ingest/` for a finding about a whole cohort, such as a missing visit.yaml or a check that did not run);
- `block`: the block's content identity, `Class@pht:phvs` (the phvs its slots read, minus `id`, `associated_*` and `age_*`; a Visit block's `id` labels). Inserting or deleting another block leaves it unchanged, and so does fixing a participant seed. Two identical blocks in one file get `#2`, `#3`;
- `message`: the finding's message with unquoted numbers (row counts, block numbers, shares) replaced by `#`. Quoted codes and labels stay, so two reasons are two findings.

Each entry also carries the `issue` that tracks it and a `status`:

- `defect` -- real; the fix is tracked in the issue;
- `dbgap-error` -- the mapping is right and the dbGaP label or dictionary is wrong (ARIC ECGMI32/41, COMPLQ01);
- `false-positive` -- the rule is wrong here; `note` says why;
- `pending` -- a curator decision is open in the issue; nothing is decided yet.

A matching finding is reported at INFO with `[known issue #N, status]` appended. An ERROR with no entry prints the exact line to add. What keeps the list honest, each an ERROR:

- **stale entry** (`KI`): an entry for a rule the component ran, on a file it scanned (or a cohort it ran in full, for a cohort-level entry), that matches nothing -- the issue is fixed;
- **new WARNING** (`RATCHET`): a WARNING fingerprint that `hv-lint/warning_baseline.json` does not list. The ratchet compares fingerprints, so fixing one WARNING and adding another of the same rule fails;
- **fixed WARNING** (`RATCHET`): a baseline fingerprint, in scope, that no finding has.

Fingerprints are unique per run (two findings with one fingerprint get ` (#2)`), so an entry matches at most one finding; a duplicate entry is rejected when the file is read.

Two commands rewrite the files. Both run only under `run_all.py` and refuse a `--file` run, so a partial run never rewrites rows it did not see:

- `HVLINT_PRUNE=1 python hv-lint/run_all.py --cohort all` removes ONLY entries and baseline rows that match nothing, and never adds one. Every stale-entry and fixed-WARNING message prints it. After a PR that fixes known issues, this one command is the whole bookkeeping.
- `HVLINT_UPDATE_BASELINE=1 python hv-lint/run_all.py --cohort all` rewrites the WARNING baseline from the run, so it can add rows as well as drop them: accepting a new WARNING is a reviewed diff of `warning_baseline.json`, one line per finding.

A `--file` run checks only that file's entries and rows. On main (731984f5 + #831 + #885) the file holds 724 entries -- 5.11 383 (#882), 3.5 127 (#500, #882, #883, #884, #872), 1.12 57 (#872, #881), 2.12 49 (#883), 2.4 31 (#884), 3.16 30 (#884), 3.9 11, 3.10 7 (#883), 5.2 7 (#872, FHS cig_smok fallback), 3.18 6 and 3.17 5 (#881, #869), 1.2 4, 3.15 4 (#226), 2.7 3 (#883); 713 defect, 5 dbgap-error, 4 pending (CARDIA A12CB* / A12EM* '0', #873 Q19), 2 false-positive -- and every phase passes. Every `defect` and `pending` entry cites an open issue. Removing any one entry fails CI on exactly that finding.

### A8: Duplicate Detection Identity

Rules 1.2 (within a file) and 1.12 (across files) share one identity, `check_cross_file_duplicates.block_identities`:

`(class, populated_from table, source, concept, associated_visit, value_mappings)`

where the source and mappings come from `condition_status` / `exposure_status` / `procedure_status`, or from the Quantity value slot / `value_enum` for observations, and the concept from `condition_concept` / `drug_concept` / `procedure_concept` / `observation_type`. Other classes (MeasurementObservationSet, Visit, Demography, ...) are identified by their whole body. Context slots (provenance, ages, method_type) are not part of the identity: two blocks that differ only there still emit the same records twice.

### A9: Severity Levels and Exit Code Behavior

| Severity | Meaning | Default exit behavior |
|----------|---------|----------------------|
| `CRITICAL` | Silently broken transform -- key ignored by pipeline | Fails |
| `ERROR` | Wrong data in output (typo, bad reference) | Fails (default `--fail-on`) |
| `HIGH` | Likely wrong but may be intentional (CURIE format) | Does not fail by default |
| `WARNING` | Suspicious, needs human review | Does not fail |
| `INFO` | Advisory, expected patterns | Does not fail |

The `--fail-on` flag controls the threshold. CI runs every phase at `--fail-on error`; known findings are listed in `hv-lint/known_issues.yaml` (A7), and the WARNING count per rule and cohort is ratcheted against `hv-lint/warning_baseline.json`.

### A10: CURIE Validation Does Not Check Ontology Existence

Check 2.6 validates the **format** of CURIEs but does **not** verify the code actually exists in its ontology. For example, `OMOP:12345678` passes format validation but may not be a real OMOP concept. Ontology existence checking requires expert review.

### A11: Cohort Detection from Directory Name

Scripts detect which cohort a file belongs to by extracting the directory name before `-ingest`:

- `priority_variables_transform/ARIC-ingest/bmi.yaml` -> cohort `ARIC`
- `priority_variables_transform/HCHS-ingest/bmi.yaml` -> cohort `HCHS`

The `HCHS` directory name maps to `hchs_sol` in the dbGaP cache (via `COHORT_TO_CACHE_KEY`).

---

## Phase 1: YAML Structural & Formatting

**Scripts**: `hv-lint/phase-1/validate_yaml_structure.py` (checks 1.1-1.5, 1.7, 1.9, 1.10, 1.11), `hv-lint/phase-1/run_yamllint.py`, `hv-lint/phase-1/check_quoting_rules.py`, `hv-lint/phase-1/check_cross_block_consistency.py` (1.6), `hv-lint/phase-1/check_cross_file_pht_consistency.py` (1.8), `hv-lint/phase-1/check_cross_file_duplicates.py` (1.12)
**Dependencies**: PyYAML
**No schema or external data required** -- YAML files only.

### 1.1 Expression Syntax Validation

Validate all `expr` fields for syntactic correctness.

- **Checks**: Balanced Jinja delimiters (`{%`/`%}`, `{{`/`}}`), non-empty expressions, no empty variable references (`{{ }}`)
- **Severity**: ERROR for unbalanced/empty; WARNING for empty variable references

### 1.2 Duplicate Block Detection

Detect two blocks in one file that emit the same records, using rule 1.12's identity (assumption A8). The message names the context slots in which the two copies differ, or says they are byte-identical.

- **Catches**: Copy-paste duplicates, blocks that would produce identical output records. Blood-pressure replicates and per-drug blocks that read different source variables are not duplicates.
- **Severity**: ERROR

### 1.3 Inline Comment Detection

Inline comments -- trailing `# ...` appended to active YAML code lines -- must be detected. Standalone comment lines (entire lines starting with `#`) are not affected.

- **Severity**: ERROR
- **Rationale**: REVIEW/TODO notes should be tracked in GitHub Issues, not embedded in YAML.

### 1.6 Cross-Block Slot Consistency

Detect slots present in one `class_derivation` block but missing from another block of the same BDCHM class within the same YAML file.

- **Excluded slots**: `id`, `associated_participant`, `associated_visit` (legitimately vary between blocks), and the descriptor / provenance slots `associated_evidence`, `method_type`, `range_high`
- **Severity**: INFO (no compared slot is required; 260 of 286 findings on main were legitimate differences)

### 1.7 Semantic Duplicate DrugExposure Blocks

Detect DrugExposure blocks within a file that share the same source PHV(s) in `drug_concept` but map to different vocabulary codes (e.g., one ATC, one VANDF).

- **Severity**: WARNING

### 1.8 Cross-File PHT Visit Label Consistency

Each data block's `associated_visit` is read as a label SET by the shared enumerator (`hv-lint/_visit_ids.py`): every case() arm is enumerated, comparison operands (`'P2'`, CARDIA `'HBP'`) are never labels, and a `(True, ...)` fallback arm (`FHS UNKNOWN VISIT`) is dropped. Blocks are grouped by PHT.

- **ERROR**: a block with exactly one label disagrees with the exam its FHS table encodes in its dbGaP short name (`ex<cohort>_<exam>s`, `..._ex<NN>_<cohort>[b]_...`; a description range such as "Original Cohort Exams 1 - 7" widens it; derived `vr_` tables encode no single exam). The short names and descriptions come from `<release>_tables.json.gz` (`build_phv_stats_index.py --tables`), committed for FHS only.
- **ERROR** (any cohort): a block with exactly one label disagrees with a label that at least 5 other single-label blocks of the same table carry, and those are at least 80% of the table's other single-label blocks -- a copy-paste label on a single-exam table (the #782 class). On all cohorts today this finds nothing: the largest share of disagreeing blocks any single-label block faces is 28% (ARIC pht012853, a wide multi-exam table). The rule is armed on 163 tables (4,409 blocks). Relabelling MESA hdl b1 `MESA CLASSIC EXAM 2` among 118 EXAM 1 blocks fails Phase 1.
- **WARNING**: two blocks of one table carry label sets that overlap while neither contains the other (COPDGene phase subsets).
- Not reported: a block whose label set is a superset of another's (MESA potassium b0's Exam 3/4 case beside Exam 4 blocks), or different single exams of one multi-exam table (no label holds 80%).
- **Excluded**: Visit class blocks (visit.yaml defines visits, not consumes them)

### 1.9 Common Typo Detection

Detect known misspellings in YAML file text that silently produce wrong slot names or values.

- **Known typos**: `expsoure_provenance` -> `exposure_provenance`, `expsoure` -> `exposure`, `vetricular` -> `ventricular`, `diagnoisis` -> `diagnosis`, `observaton` -> `observation`, `measurment` -> `measurement`, `particpant` -> `participant`, `assocated` -> `associated`
- **Severity**: ERROR

### 1.10 Space-in-Key Detection

Detect YAML keys with illegal internal spaces (e.g., `populated from:` instead of `populated_from:`). These are silently accepted by YAML parsers but create wrong keys the pipeline ignores, causing silent data loss.

- **Patterns**: `populated from`, `slot derivations`, `class derivations`, `value mappings`, `object derivations`, `unit conversion`, `source unit`
- **Severity**: CRITICAL -- key is silently ignored, data loss

### 1.11 expr + value_mappings on One Slot

Detect a slot derivation (at any nesting depth) that sets both `expr` and `value_mappings`. linkml-map evaluates `expr` before `populated_from` and applies `value_mappings` only on the `populated_from` path, so the mappings are silently ignored and the expr's raw result is emitted (#701: CARDIA Year 15 income emitted raw codes 1-11).

- **Fix**: replace the expr with `populated_from` when the mappings carry the meaning; delete the dead mappings when the expr already returns final values
- **Severity**: CRITICAL -- mappings silently ignored (same class as 1.10)

### 1.12 Cross-File Identical Blocks

Detect blocks in different files of the same cohort that emit the same record: identical on class, `populated_from` table, source (the status / value slot's `populated_from` or `expr`), concept (`drug_concept`, `condition_concept`, `procedure_concept` or `observation_type`), `associated_visit`, and the status / value slot's `value_mappings`. Covers every class, DrugExposure included (#879; 13 identical DrugExposure pairs were removed by hand in #833).

- **Not compared**: provenance, evidence, age and other context slots -- two blocks that differ only there still emit the same fact twice. The finding names the slots that differ, or says the blocks are identical apart from `range:` annotations.
- **Classes without a status / value slot** (Visit, Person, Demography, ...): compared on the whole block body, so only exact copies match.
- **Within one file**: left to 1.2.
- **Known issues**: `hv-lint/known_issues.yaml` (assumption A7): the 44 FHS `med_use.yaml` / `tak_*` / `hypert_trt.yaml` pairs (#872; which copy stays is #873, "#785 decision 1") and the 13 Condition pairs of #881 section 2.
- **Severity**: ERROR

### 1.13 populated_from and expr on One Slot

A slot that sets both `populated_from` and `expr`. linkml-map 0.5.3 evaluates `expr` first (`object_transformer.py:481-483`), so the `populated_from` is dead and reads as the source. Main has 10, all CARDIA `Quantity.value_decimal` (albumin_urine b0-b1, bdy_hgt b0-b3, creat_urin b2, insulin_blood b0-b2), all behaving as intended.

- **Severity**: INFO

---

## Phase 2: BDC-HM Model Conformance

**Scripts**: `hv-lint/phase-2/validate_model_conformance.py` (checks 2.1-2.7, 2.5b, 2.10-2.11), `hv-lint/phase-2/check_phv_dedup.py` (2.8)
**Dependencies**: PyYAML, linkml-runtime (for `SchemaView`)
**Data required**: YAML files + BDCHM LinkML schema (fetched at runtime or local) + linkml-map model constants

### 2.1 LinkML-Map Key Validation

Validate every key in every `class_derivation` and `slot_derivation` block against the `linkml_map.datamodel.transformer_model`.

- **Catches**: Invalid keys -- template rendering errors, hand-editing typos in structural keywords, any key not defined in the linkml-map model
- **Implementation**: Three frozen sets (`VALID_TRANSFORMATION_SPEC_KEYS`, `VALID_CLASS_DERIVATION_KEYS`, `VALID_SLOT_DERIVATION_KEYS`) checked at each nesting level. Object derivation items and nested `class_derivations` are recursively validated.
- **Severity**: CRITICAL

### 2.2 BDCHM Slot Name Validation

Validate every slot name inside `slot_derivations` against the valid slots for its parent BDCHM class.

- **Source of truth**: BDCHM LinkML schema -- `SchemaView.class_induced_slots()` per class (includes inherited slots)
- **Severity**: ERROR

### 2.3 BDCHM Class Name Validation

Validate every class name used as keys in `class_derivations` against the BDCHM schema.

- **Source of truth**: BDCHM LinkML schema -- `SchemaView.all_classes()`
- **Severity**: ERROR

### 2.4 Required/Recommended Slot Enforcement

Validate that each BDCHM class block includes its required and recommended context slots.

- **Source of truth**: BDCHM schema `required` and `recommended` annotations per class -- not a hardcoded list
- **Severity**: ERROR for a missing required slot; INFO for recommended. A required slot that is present but written as a `case()` with no `(True, ...)` arm is a WARNING: it is null on every row no arm matches (Procedure blocks whose ABSENT rows carry no `procedure_concept`).
- **`id` is not checked per block**: it is required on every class, but linkml-map 0.5.3 does not generate it (only Person, Participant and Visit derive one). One note per run; the decision is with the HM / dm-bip owners (#873).
- The advisory `age_at_observation` INFO on MeasurementObservation is removed (#885): the slot is optional, every one of its 1,003 findings set `associated_visit`, and 64% of those visits carry an age.

### 2.5 Object Derivation Structure Validation

Validate that all `object_derivations` follow the correct structure:
1. Must be a list
2. Each item must be a dict
3. Each item must contain `class_derivations`
4. Keys validated against `VALID_TRANSFORMATION_SPEC_KEYS`
5. Nested `class_derivations` are recursively validated

- **Severity**: ERROR

### 2.5b Nested Class Range Validation

Validate that the class nested inside an `object_derivations` block matches the schema-defined range for the parent slot.

- **Subclass handling**: Accepts the exact range class OR any subclass via `SchemaView.class_ancestors()`
- **Severity**: ERROR

### 2.6 CURIE Format Validation

Validate all ontology reference values matching `PREFIX:IDENTIFIER` against per-prefix format rules. Applied to both static `value` fields and CURIEs embedded in `expr` fields.

- **Known prefix rules**:

  | Prefix | Regex Pattern | Description |
  |--------|--------------|-------------|
  | `OMOP:` | `^\d{4,9}$` | Numeric, 4-9 digits |
  | `RxCUI:` | `^\d+$` | Numeric only |
  | `OBA:` | `^\d{7}$` | Exactly 7 digits |
  | `MONDO:` | `^\d{7}$` | Exactly 7 digits |
  | `HP:` | `^\d{7}$` | Exactly 7 digits |
  | `NCIT:` | `^C\d+$` | C followed by digits |
  | `LOINC:` | `^\d+-\d$` | Digits-dash-digit |

- **Additional checks**: Extra whitespace in CURIE, space after colon, known-bad `OMOP:380035630` (common ethnicity typo)
- **Severity**: HIGH (format only -- see A10)

### 2.7 Enum / Value Set Membership

Validates that values assigned to enum-typed slots are members of the BDCHM-defined permissible value sets. Resolves enum inheritance and `include` sections recursively; accepts both PV key names and their `meaning` CURIEs. Enums with `reachable_from` (dynamic/ontology-derived) are skipped.

- **Covers**: `value:` static assignments, `value_mappings:` target values, and `expr:` case() arm results -- element `[1]` of each arm, read from the parse tree, so a membership tuple such as `in ("1","2")` is never taken for a result. All ERROR.
- The cross-file consistency extension is removed: every finding was a family-history file, where relatives are meant to differ.

### 2.8 PHV Deduplication

Flag any PHV accession that is mapped as a measured value in more than one harmonized variable block within the same cohort.

- **Severity**: ERROR. A YAML file that does not parse is also an ERROR (the file was not checked). The root `check_phv_dedup.py` (`validate_ingest_yamls.yml`) fails on the same two cases; its `KNOWN_ISSUES` is empty, and an entry that no longer matches a duplicate fails it.
- **Coverage**: raw measured values (Quantity `value_*` with a bare `populated_from`, top level or inside a MeasurementObservationSet). A Condition counts only when `condition_status` has `populated_from` and no `value_mappings`, so in practice Conditions are not covered.
- **DrugExposure is not covered** (here or in the root `check_phv_dedup.py`): a medication PHV mapped to two different concepts is often deliberate (spironolactone as diuretic and aldosterone blocker; a class block beside a drug-name block -- 45 such PHVs on main, 2026-10-07), and the real medication defect, the same block in two files with the same concept, is invisible to a distinct-concept check. Rule 1.12 covers it.

### 2.12 Bare None as a value_mappings Target

`'0': None` in a `value_mappings`, in any slot at any depth. YAML reads `None` as the string "None", and linkml-map writes that string into the record (`"value_enum": "None"`, `"condition_severity": "None"`). Delete the entry: an unmapped code already emits null (#736, #883 item 9). Rule 2.7 skips these targets so one defect is reported once.

- **Severity**: ERROR

### 2.10 Unconditional age_at_condition_start on Binary Conditions

Flag Condition blocks where `age_at_condition_start` is populated unconditionally but `condition_status` maps both PRESENT and ABSENT rows. ABSENT rows would incorrectly receive an age value. An age written `None if <test on the block's own status variable> else ...` is guarded.

- **Severity**: WARNING

### 2.11 Condition Missing ABSENT in condition_status (not checked)

Removed. As written it recommended mapping a follow-up question's "No" to ABSENT, the defect 3.18 rejects, and every one of its 127 findings on main was a false positive. An observed code a block drops is rule 3.9's, which weighs it by rows and skips follow-up questions.

## Phase 3: dbGaP Structure & Cross-Reference

**Scripts**: `hv-lint/phase-3/validate_dbgap_crossref.py` (checks 3.1-3.5), `hv-lint/phase-3/validate_semantic.py` (checks 3.9, 3.10, 3.12-3.16), `hv-lint/phase-3/check_value_semantic.py` (3.11), `hv-lint/phase-3/check_status_semantic.py` (3.17, 3.18)
**Dependencies**: PyYAML, gzip, json
**Data required**: YAML files + compressed indexes from `--cache-dir` (basic index for 3.1-3.5; extended detail index for 3.9-3.18; value-count index for 3.17b and 3.18)

### 3.1 PHV/PHT Accession Format Validation

Validate all `phv` and `pht` references match dbGaP accession format (`phv` + 8 digits; `pht` + 6 digits).

- **Severity**: ERROR

### 3.2 PHT Existence

Flag any `populated_from: phtXXXXXX` that doesn't appear in the dbGaP index.

- **Severity**: ERROR

### 3.3 PHV Existence

For every PHV reference in every YAML file, verify it exists in the dbGaP variable index for that cohort.

- **Extraction scope**: `populated_from`, `expr` (regex search), `value_mappings` keys, `expression_to_value_mappings` keys, recursive through `object_derivations`
- **Severity**: ERROR

### 3.4 Qualified Reference Membership

A dotted `{pht.phv}` (or `populated_from: pht.phv`) must name the table the PHV is in; otherwise the synthesized join reads the wrong table. **Severity**: ERROR. A correct dotted reference produces no finding.

### 3.5 Cross-Table Reference Without a Join

A BARE `{phv}` or bare `populated_from` whose table is not the block's class table, not the `populated_from` of an enclosing nested derivation, and not a declared join, in any slot (assumption A6). **Severity**: ERROR.

### 3.9 value_mappings Completeness

Flags values the source holds that `value_mappings` drops (silent data loss), at every depth (nested `Quantity.value_concept` included).

- **Reference set**: the var_report's OBSERVED values (`<release>_stats.json.gz`). A declared code no row carries loses nothing. A value written as its label (JHS) counts as mapped when the label is a key. Without var_report counts the declared codes are used, capped at WARNING; with neither, INFO "could not be validated".
- **Not reported**: the negative answer of a conditional follow-up (`check_status_semantic.detect_followup`; 3.18 rejects mapping it to ABSENT), a code the race/ethnicity sibling slot maps from the same PHV, a severity code labelled none/no.
- **Severity by rows lost** (share of observed rows the dropped value carries): ERROR from 50% on a high-impact slot (`race`, `sex`, `annotated_sex`, `ethnicity`, `condition_status`, `exposure_status`, `procedure_status`, `value_enum`), WARNING from 10%, INFO below. Skip labels (unknown, refused, missing, ...) are INFO.

### 3.10 PHV Data Type vs Slot Role Compatibility

Validates that the dbGaP data type of a source PHV is compatible with the target slot's usage role. Catches adjacent-variable errors where a continuous variable is used where a categorical indicator was needed. Walks every slot at every depth: every `value_decimal` / `value_integer` on main is nested in a Quantity.

- **Enum slots** (`condition_status`, `exposure_status`, `procedure_status`, `sex`, `annotated_sex`, `race`, `ethnicity`, `vital_status`): a bare `populated_from` with no `value_mappings` writes the variable's raw values into the enum, whatever its dbGaP type (ARIC carotid_plaque b0 wrote V1AGE01, an age, into `condition_status`; #879 item 6).
- **Numeric slots** (`value_decimal`, `value_integer`): a variable of type `encoded value` with 2 or more category codes emits the code as a measurement (WHI sleep_duration_daily b0-b5: code 4, "8-9 hours", becomes 4 h). An `encoded` type with no code list is a plain number and is not flagged.
- **Severity**: ERROR

### 3.11 value_mappings Label/OMOP Concept Semantic Alignment

Validates that the source label from dbGaP semantically matches the target OMOP concept. Catches copy-paste swaps where target concept IDs are assigned to the wrong source code.

- **Data**: Extended detail index + OMOP concept lookup (embedded ~43 common concepts; auto-upgrades to full Athena CSV if available)
- **Scope**: every `value_mappings` slot at any depth (nested `Quantity.value_concept` included) whose target is an `OMOP:` CURIE, except `*_status` slots: status polarity is rule 3.17's.
- **Severity**: ERROR (it was HIGH, which ranks below ERROR, so the enforced `--fail-on error` gate could never fail on it)

### 3.12 PHV Description vs Concept Domain

Validates that the dbGaP variable description does not conflict with the YAML file's clinical domain (e.g., "carotid" variable in a coronary file).

- **Severity**: WARNING

### 3.13 Condition Null-Default Risk (Collection Interval Mismatch)

Validates that Condition blocks using `value_mappings` on `condition_status` do not route to visit phases where the source PHV is not collected. When this mismatch occurs, `value_mappings` may default to ABSENT, producing false negatives.

- **Data**: Extended detail index with `coll_interval` field
- **Scope**: Condition class only. Rule 5.8 covers all classes more broadly.
- **Severity**: CRITICAL
- **Availability**: Only applies to cohorts with structured `coll_interval` data (currently COPDGene: 95% coverage; others: limited or none)

### 3.14 Unit Conversion Source-Unit Mismatch

Validates that `unit_conversion` blocks specify a `source_unit` consistent with the dbGaP-declared unit for the source PHV.

- **Logic**: Compares `source_unit` against dbGaP unit using a UCUM-to-dbGaP equivalence map (`[lb_av]`/lbs, `kg`/kilograms, `[in_us]`/inches, etc.)
- **Nested support**: Handles `unit_conversion` inside nested `object_derivations`
- **Severity**: CRITICAL if dbGaP unit matches the `target_unit` (data already in target unit, conversion would corrupt); ERROR otherwise

### 3.15 Phantom Code Detection

Against the var_report's observed values, at every depth:

- key observed: no finding (observed but undeclared: INFO, its meaning is undocumented);
- key equal to an observed value except for case or spacing: **ERROR**, it never matches (linkml-map compares exact strings);
- no key of the slot matches any observed value: **ERROR**, unless it is a severity slot whose observed values all mean "none" (MESA copd b5 / b17);
- key neither observed nor declared: INFO (dead defensive key). A declared code no row carries is not reported.
- Without var_report counts: a key outside the declared codes is a WARNING.

### 3.16 Quantity Missing Unit

A measured value -- a Quantity with `value_decimal` or `value_integer` -- must have a `unit`. Its value cannot be interpreted without one, and a block that converts the value (`* 38.67`) without stating the unit is a silent scale error.

- **Checks**: every depth (a Quantity inside a MeasurementObservation inside a Set included)
- **Allowlist**: `UNITLESS_OBSERVATION_TYPES` in `validate_semantic.py`, for a genuinely dimensionless observation_type; empty today. A dimensionless value can instead carry the UCUM unit `1`.
- **Severity**: ERROR

### 3.17 Status Polarity

Validates that a status slot (`condition_status`, `exposure_status`, `procedure_status`, or any other `*_status` slot read with `populated_from` + `value_mappings`) does not map a code to the opposite of what dbGaP says it means.

- **3.17a (labels)**: a code whose dbGaP label clearly means no / never / none / not taking maps to PRESENT or HISTORICAL; or a clearly affirmative label ("Yes", "Yes, now", "Taking", "Present", "Positive") maps to ABSENT.
  - Conservative label parsing: hedged or missing-like labels are never judged ("Yes, not now", "Yes, doubtful", "Don't know", "Not sure", "No answer", "Not applicable", anything with "but"); a time-limited negative ("Not present now, formerly definite", "No longer") is not judged either, because HISTORICAL may carry it.
  - A negative label on a conditional follow-up (3.18) is not reported: "No" to "hospitalized for MI?" mapped PRESENT is right, the person had the MI.
- **3.17b (unlabelled 1/2 flags)**: the variable has no code labels, its var_report shows codes 1 and 2 but never 0, and it is mapped `'0': ABSENT, '1': PRESENT`. `'0'` never fires and the "No" of a 1 = No / 2 = Yes flag is emitted PRESENT (CARDIA endpoint flags, fixed in 72d11db1). Needs the value-count index.
- **Cannot see**: dbGaP labels that are themselves inverted (ARIC ECGMI32/41, COMPLQ01). Those fire on a correct mapping and are listed in `hv-lint/known_issues.yaml` as `dbgap-error` (#869, #881); report them in `transform_assessment/dbgap_errors_to_report.md`.
- **Known issues**: `hv-lint/known_issues.yaml` (assumption A7).
- **Severity**: ERROR (enforced in the Phase 3 gate)

### 3.18 Conditional Follow-up Mapped to ABSENT

Validates that a `condition_status` does not map `'0'` (or a "No" code) to ABSENT when the variable is a follow-up asked only of people who reported the condition -- "Hospitalized for MI?" after "New MI? Yes". Its "No" means "had it, not hospitalized"; ABSENT records "no MI" for people who had one (CHS MIHOSP/ANHOSP/CHHOSP/STHOSP/TIHOSP, fixed in 5bdff784).

- **Sibling**: an earlier coded yes/no variable in the same table naming the same condition (fixed vocabulary: MI, angina, stroke, TIA, heart failure, COPD, emphysema, bronchitis, asthma, diabetes, hypertension, AF, PAD, VTE, LVH, CHD, cancer, kidney disease), not itself worded as a follow-up, not about a relative, not a "form present" flag, and not from another exam of the same table.
- **Signal (a), counts**: the variable's var_report n is between 0.5x and 1.1x the sibling's "yes" count, the sibling is answered "yes" by at most half its respondents, and that "yes" count is at least 5 (MIHOSP59 n = 38, NEWMI59 yes = 38).
- **Signal (b), wording**: "hospitalized", "hospital for", "treated in", "seen by", "how old", "under medical care", "emergency room".
- **Rule**: flag on (a); (b) plus a sibling is used only when the cohort has no value-count index. When counts exist they decide, so an interval question asked of everyone ("since your last exam, were you hospitalized for heart failure?") is not flagged.
- **Not checked**: drug and procedure status (a "taking meds for diabetes?" follow-up asks about the drug itself, so its "No" is a true ABSENT), and confirmation / adjudication follow-ups ("CONFIRMED: ATRIAL FIBRILLATION"), whose "No" re-decides the condition.
- **Known issues**: as 3.17.
- **Severity**: ERROR when (a) and (b) both hold; WARNING otherwise. The finding names the sibling and both counts.

---

## Phase 4: Regression Detection

> **Status**: NOT YET IMPLEMENTED

### 4.1 Branch Regression Check

Compare Phase 1-3 error counts between `main` and the PR branch. Block merge if new errors appear.

- **Trigger**: `pull_request` events only
- **Method**: Run full validation on both branches, diff the error sets
- **Severity**: HIGH

---

## Phase 5: Visit Structure Validation

**Scripts**: `hv-lint/phase-5/validate_visit_structure.py` (checks 5.0-5.10)
**Dependencies**: PyYAML
**Optional data**: Visit cache for checks 5.3, 5.5; PHV index for check 5.4; Extended detail index for check 5.8

Phase 5 is the first **cross-file** validation phase. It builds a per-cohort visit registry from `visit.yaml` and validates all measurement/condition transform files against it.

### Visit Registry

At startup, Phase 5 parses the cohort's `visit.yaml` and extracts:
- All Visit block IDs (static `value:` or dynamic `uuid5()` expressions)
- Visit labels (human-readable names extracted from case() expressions with suffix concatenation)
- PHT accessions (`populated_from`)
- Age formulas and their referenced PHVs

Two visit ID strategies are supported:
- **Static IDs**: `id.value: "ARIC EXAM 1"`
- **Dynamic UUIDs**: `id.expr: uuid5("...", str({phv}) + ":" + case(...) + " EXAM N")` -- labels extracted from case() result strings combined with suffix strings

### Visit Label Extraction from Expressions

Expressions are parsed with `ast` by the shared enumerator `hv-lint/_visit_ids.py` (also used by 1.8 and 5.11), not by regex. Every value an `id` / `associated_visit` expression can emit is enumerated: case() arms, `+` concatenation (so FHS visit.yaml's `case(...) + ' EXAM 7'` inside a uuid5 seed composes), and the uuid5 seed's `str({phv})` placeholders. Comparison operands are never labels. A `(True, ...)` arm of a case() that has other non-None arms is a fallback: 1.8 and 5.1 do not compare it (it is not a visit the table holds), and 5.2 checks it against the observed codes (below). An expression the enumerator cannot parse is reported as 5.12, never skipped silently.

### 5.0 Missing visit.yaml

Flag cohorts that have an ingest directory but no `visit.yaml` file: Phase 5 did not run for that cohort.

- **Severity**: ERROR (a cohort-level finding, `<C>-ingest/ | cohort`; it can be listed as a known issue)

### 5.1 Visit ID Uniqueness

Within a cohort's `visit.yaml`, no two Visit blocks should produce the same visit ID.

- **Static IDs**: Exact string comparison
- **Dynamic IDs**: Uniqueness check on extracted labels (uuid5 is deterministic); fallback labels are not compared
- **Severity**: ERROR when two blocks of the SAME table emit one label (naming that table's first block); WARNING "Visit id emitted by N tables" (listing the distinct tables and their age expressions) on the first block of each further table -- a multi-table visit by design whose duplicate Visit rows can disagree on age. A label group that mixes both gets both, pair by pair.

### 5.2 Visit ID Referential Integrity

Every `associated_visit` value or case() target in measurement/condition files must resolve to a visit ID defined in the cohort's `visit.yaml`.

- **Static references**: Must exactly match a Visit ID
- **Dynamic references**: Each extracted label must appear in the visit registry's label set
- **Fallback arms** (`(True, 'FHS UNKNOWN VISIT')`): a fallback label no Visit block defines is evaluated against the var_report value counts of the variable the case() switches on. WARNING when observed codes reach it, naming the codes and rows (FHS cig_smok b35-b41: idtype 2 / 3 / 72, 101 + 4,036 + 404 rows, link to a Visit that does not exist), and WARNING when the reach cannot be evaluated (conditions on two variables, a non-literal comparison, no counts). A fallback no observed code reaches is not reported (FHS visit.yaml's, behind `idtype in [0, 1, 7]`).
- **Non-fallback labels** containing "UNKNOWN", "DEFAULT", "OTHER" are flagged as INFO
- **Severity**: ERROR for static mismatches; WARNING for dynamic label mismatches and reached fallbacks; INFO for named catch-all labels

### 5.3 Visit/PHT Consistency

> **Requires**: `--visit-cache`

Validate that Visit block PHTs are recognized dbGaP accessions and exist in the visit cache.

- **Severity**: ERROR for malformed PHT; WARNING for PHT not in cache

### 5.4 Age Formula Structural Check

Validate that `age_at_visit_start` and `age_at_visit_end` expressions are present and structurally sound.

- **Checks**: Age slot presence, PHV validity (if `--cache-dir` provided), unit conversion (`* 365` for years-to-days)
- **Severity**: INFO for missing age slots (age is optional on BDC-HM Visit); ERROR for invalid PHVs; INFO for missing `* 365`

### 5.5 Multi-Visit Table Coverage

> **Requires**: `--visit-cache`

Validate that transform blocks using multi-visit tables include appropriate visit discrimination.

- **Severity**: WARNING for no `associated_visit` on multi-visit table; INFO for static `associated_visit`

### 5.6 Orphan Visit References

Detect Visit IDs defined in `visit.yaml` but never referenced by any measurement or condition transform file.

- **Severity**: INFO (orphan visits may represent future work)

### 5.7 Visit PHT Alignment

Validates that visit blocks' PHT references are consistent with dbGaP visit-cache metadata.

- **Sub-checks**:
  - **5.7a**: Multi-visit table with static ID and single block -> WARNING
  - **5.7b**: Multi-visit table block expressions don't reference known discriminator PHVs -> INFO
  - **5.7c**: Block's age PHVs don't overlap with table's known age variables -> INFO

### 5.8 Collection Interval Mismatch

Validates that data PHVs used in transform blocks are actually collected at all visit phases the block's `associated_visit` case expression routes to, based on `coll_interval` metadata from dbGaP.

- **Logic**: Extracts phase tokens from case expressions, loads PHV `coll_interval` from detail index, flags uncovered phases
- **Severity**: CRITICAL for Condition class (null -> false ABSENT); ERROR for Measurement/Observation/DrugExposure (null -> NaN)
- **Availability**: COPDGene 95% coverage; FHS 42% (free-text, gracefully skipped); ARIC and CHS a few variables; CARDIA, HCHS, JHS, LTRC, MESA, SPIROMICS and WHI none. For those seven the skip is a WARNING finding ("5.8 did not run for <cohort>"), so a 5.8 pass is not read as coverage. Until a proxy exists (dataset naming, var_report presence per visit), #782 addendum B option 3 stands: a one-time manual audit of their multi-visit Condition blocks.
- **Phase-alias expansion**: Sub-phases expanded from parents (e.g., COPDGene P3B treated as sub-visit of P3)
- **Relationship to Rule 3.13**: Rule 5.8 is the broad cross-file check (all classes); Rule 3.13 is the targeted Condition-only check.

### 5.9 Visit uuid5 Format Compliance

Validates that visit IDs use deterministic `uuid5()` expressions rather than plain `value:` strings. Plain value strings produce fixed IDs shared across all participants, breaking entity-level visit joins.

- **Sub-checks**:
  - **5.9a (visit.yaml)**: Visit block `id:` uses `expr:` with uuid5
  - **5.9b (entity files)**: `associated_visit` uses `expr:` with uuid5
- **Severity**: ERROR

### 5.10 Visit uuid5 Namespace Consistency

Validates that all `uuid5()` expressions use the canonical bdchm namespace URL `https://w3id.org/bdchm/Visit`. Mismatched namespaces produce incompatible UUIDs that silently break visit-entity joins.

- **Sub-checks**:
  - **5.10a (visit.yaml)**: Namespace URL in Visit block uuid5 expressions
  - **5.10b (entity files)**: Namespace URL in `associated_visit` uuid5 expressions
- **Severity**: CRITICAL

### 5.11 Participant / Visit Seed

The variable that seeds a participant or visit uuid5 must be the table's participant ID. For every Visit `id`, `associated_visit` and `associated_participant` at any depth, the `str({phv})` seeds are read by the shared enumerator and checked BY NAME against the detail index:

- (a) the seed's dbGaP name is not a participant ID (`shareid`, `SUBJECT_ID`, `SUBJID`, `Individual_ID`, `sidno`, `New_SUBJID`, `GENEVA_ID`, `dbGaP_Subject_ID`). FHS `IDTYPE` / `idtype` is the cohort code (0/1/2/3/7/72), so every row of the block collapses onto one fake participant per code (#882);
- (b) the visit seed differs from the participant seed at the same level (a nested class inherits the participant of its parent);
- (c) an unqualified seed is in no enclosing table -- the class's `populated_from` or that of a class around it, as 3.5 reads reachability: a bare reference to another table is None, so participant and visit are emitted empty (FHS bdy_hgt b42).

Name-based on purpose: shareid and idtype are adjacent accessions in FHS tables, but the distance varies by table. One finding per reason, so a second defect in a block already listed as a known issue is its own finding. Main: 383 blocks, all FHS (255 IDTYPE, 127 idtype, 1 other-table shareid).

- **Severity**: ERROR

### 5.12 Id Expression Coverage

An `id`, `associated_visit` or `associated_participant` expression the shared enumerator cannot parse (a ternary, `str(...).strip()`, a namespace held in a variable) yields no labels and no seeds, so 1.8, 5.1, 5.2 and 5.11 did not check it. Reported, so the gap is ratcheted rather than invisible. 0 on all cohorts today.

- **Severity**: WARNING

---

## CLI Reference

All phase runners accept `--hv-root` to specify an alternate HV repo clone and `--cohort` to filter to a single cohort (default: `all`).

**Phase 1:**
```bash
python hv-lint/phase-1/run_phase1.py \
  --cohort ARIC \
  --fail-on error
```

**Phase 2:**
```bash
python hv-lint/phase-2/run_phase2.py \
  --bdchm-ref <ref> \
  --cohort ARIC \
  --fail-on error
```

**Phase 3:**
```bash
python hv-lint/phase-3/run_phase3.py \
  --cache-dir hv-lint/dbgap-cache \
  --cohort ARIC \
  --fail-on error
```

**Phase 5:**
```bash
python hv-lint/phase-5/run_phase5.py \
  --cohort ARIC \
  --fail-on error \
  --cache-dir hv-lint/dbgap-cache
```

### Output Format

- **Terminal**: Human-readable grouped by file, severity-prefixed lines
- **CI**: GitHub Actions `::error file=...` / `::warning file=...` / `::notice file=...` annotations for inline PR feedback
- **Exit code**: 0 if no findings at or above `--fail-on` threshold; 1 otherwise

---

## Backlog / Future Ideas

| Idea | Notes |
|------|-------|
| **Phase 4: Regression Detection** | Compare error counts between `main` and PR branch |
| **Auto-fix suggestions** | Suggest YAML corrections for common error patterns |
| **Config-driven severity** | Per-project or per-cohort severity overrides via config |
| **Rule 2.9: Schema Version Compatibility** | Validate YAML schema version vs deployed BDCHM |
| **Rule 2.12: Range Value Validation** | Validate `range` values against LinkML built-in types |
| **Rule 3.6: Variable Name Cross-Check** | Compare dbGaP variable name against YAML usage context |
| **Rule 3.8: Cross-Cohort Mapping Consistency** | Flag PHVs used differently across cohorts for same concept |
| **Static type checking** | Validate that `populated_from`/`expr`/`value` types match expected slot types |

---

