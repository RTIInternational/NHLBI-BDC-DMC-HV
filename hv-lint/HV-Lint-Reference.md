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
2. **Extended detail index** (`<cohort>_detail.json.gz`) -- adds variable name, type, unit, description, coded values, and collection interval (`coll_interval`). Used by rules 3.9-3.16 and 5.8.

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
| `hv_dataqc/cache_fetcher/manifests/_manifest-<cohort>.yaml` | -- | Cohort version pins (study IDs, data versions) — single source of truth shared with hv_dataqc |
| `hv-lint/update_data.py` | -- | Fetch + build all indexes and visit cache (single entry point) |
| `hv-lint/.yamllint` | 1 | yamllint configuration |
| `hv-lint/phase-1/run_phase1.py` | 1 | Phase 1 manager -- orchestrates all sub-components |
| `hv-lint/phase-1/validate_yaml_structure.py` | 1 | Structural checks (1.1-1.5, 1.7, 1.9, 1.10) |
| `hv-lint/phase-1/run_yamllint.py` | 1 | yamllint wrapper |
| `hv-lint/phase-1/check_quoting_rules.py` | 1 | Issue #387 quoting rule checker |
| `hv-lint/phase-1/check_cross_block_consistency.py` | 1 | Cross-block slot consistency (1.6) |
| `hv-lint/phase-1/check_cross_file_pht_consistency.py` | 1 | Cross-file PHT visit label consistency (1.8) |
| `hv-lint/phase-2/run_phase2.py` | 2 | Phase 2 manager -- orchestrates model conformance and PHV dedup |
| `hv-lint/phase-2/validate_model_conformance.py` | 2 | BDC-HM model conformance checks (2.1-2.7, 2.5b, 2.10-2.11) |
| `hv-lint/phase-2/check_phv_dedup.py` | 2 | PHV deduplication check (2.8) |
| `hv-lint/phase-3/run_phase3.py` | 3 | Phase 3 manager -- orchestrates all dbGaP cross-reference and semantic checks |
| `hv-lint/phase-3/validate_dbgap_crossref.py` | 3 | dbGaP cross-reference checks (3.1-3.5) |
| `hv-lint/phase-3/validate_semantic.py` | 3 | Semantic validation (3.9, 3.10, 3.12-3.16) |
| `hv-lint/phase-3/check_value_semantic.py` | 3 | Value-mapping label/OMOP semantic check (3.11) |
| `hv-lint/build_phv_index.py` | -- | Builds compressed PHV-to-PHT indexes from bulk HTML cache |
| `hv-lint/build_phv_detail_index.py` | -- | Builds extended PHV detail indexes from FTP data_dict.xml files |
| `hv-lint/phase-5/run_phase5.py` | 5 | Phase 5 manager -- orchestrates visit structure validation |
| `hv-lint/phase-5/validate_visit_structure.py` | 5 | Visit structure checks (5.0-5.10) |

---

## Assumptions & Design Decisions

### A1: BDCHM Schema Is Fetched at Runtime

Phase 2 loads the BDCHM schema directly from GitHub via URL at validation time, parameterized by `--bdchm-ref` (default: `main`). This ensures the validator always checks against the latest (or any pinned) schema version without requiring the schema to be committed alongside the YAML files.

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

### A6: Cross-Table PHV References for Known Slot Patterns Are Expected

Many YAML blocks reference PHVs from a different table than the class's `populated_from`. Three categories are treated as **expected** (downgraded to INFO):

1. **Slots with explicit joins**: PHV belongs to a table declared in the block's `joins` array
2. **Participant/visit linkage slots**: `associated_participant`, `associated_visit` -- these always reference a subject-level table
3. **Age-related slots**: Any slot starting with `age_at_` or `age_of_` -- age variables are routinely stored in a shared demographics/visit table

All other cross-table references are flagged as WARNING for human review.

### A7: Known Issues Are Skipped Entirely

The `KNOWN_ISSUES` dict in each phase script allows specific files to be excluded from validation. Each phase manages its own skip list independently.

### A8: Duplicate Detection Identity

Blocks are considered duplicates within a file if they share the same 5-tuple:

`(class_name, pht, visit_label, concept_value, distinguishing_phv)`

Where `distinguishing_phv` varies by class:

| Class | `concept_value` source | `distinguishing_phv` source |
|-------|----------------------|---------------------------|
| `Condition` | `condition_concept.value` | `condition_status.populated_from` or `.expr` |
| `MeasurementObservation` | `observation_type.value` | `value_quantity` Quantity `value_decimal.populated_from` or `.expr` |
| `Observation`, `SdohObservation` | `observation_type.value` | Same as MeasurementObservation |
| `DrugExposure` | `drug_concept.value` or `.expr` | -- |
| `Visit` | `id.expr` | -- |
| `Demography` | -- | `sorted(slot_names)` |

### A9: Severity Levels and Exit Code Behavior

| Severity | Meaning | Default exit behavior |
|----------|---------|----------------------|
| `CRITICAL` | Silently broken transform -- key ignored by pipeline | Fails |
| `ERROR` | Wrong data in output (typo, bad reference) | Fails (default `--fail-on`) |
| `HIGH` | Likely wrong but may be intentional (CURIE format) | Does not fail by default |
| `WARNING` | Suspicious, needs human review | Does not fail |
| `INFO` | Advisory, expected patterns | Does not fail |

The `--fail-on` flag controls the threshold. Use `--fail-on error` for production; `--fail-on critical` during initial triage.

### A10: CURIE Validation Does Not Check Ontology Existence

Check 2.6 validates the **format** of CURIEs but does **not** verify the code actually exists in its ontology. For example, `OMOP:12345678` passes format validation but may not be a real OMOP concept. Ontology existence checking requires expert review.

### A11: Cohort Detection from Directory Name

Scripts detect which cohort a file belongs to by extracting the directory name before `-ingest`:

- `priority_variables_transform/ARIC-ingest/bmi.yaml` -> cohort `ARIC`
- `priority_variables_transform/HCHS-ingest/bmi.yaml` -> cohort `HCHS`

The `HCHS` directory name maps to `hchs_sol` in the dbGaP cache (via `COHORT_TO_CACHE_KEY`).

---

## Phase 1: YAML Structural & Formatting

**Scripts**: `hv-lint/phase-1/validate_yaml_structure.py` (checks 1.1-1.5, 1.7, 1.9, 1.10), `hv-lint/phase-1/run_yamllint.py`, `hv-lint/phase-1/check_quoting_rules.py`, `hv-lint/phase-1/check_cross_block_consistency.py` (1.6), `hv-lint/phase-1/check_cross_file_pht_consistency.py` (1.8)
**Dependencies**: PyYAML
**No schema or external data required** -- YAML files only.

### 1.1 Expression Syntax Validation

Validate all `expr` fields for syntactic correctness.

- **Checks**: Balanced Jinja delimiters (`{%`/`%}`, `{{`/`}}`), non-empty expressions, no empty variable references (`{{ }}`)
- **Severity**: ERROR for unbalanced/empty; WARNING for empty variable references

### 1.2 Duplicate Block Detection

Detect `class_derivation` blocks with identical identity tuples within a file. See assumption A8 for the identity schema.

- **Catches**: Copy-paste duplicates, blocks that would produce identical output records
- **Severity**: ERROR

### 1.3 Inline Comment Detection

Inline comments -- trailing `# ...` appended to active YAML code lines -- must be detected. Standalone comment lines (entire lines starting with `#`) are not affected.

- **Severity**: ERROR
- **Rationale**: REVIEW/TODO notes should be tracked in GitHub Issues, not embedded in YAML.

### 1.6 Cross-Block Slot Consistency

Detect slots present in one `class_derivation` block but missing from another block of the same BDCHM class within the same YAML file.

- **Excluded slots**: `id`, `associated_participant`, `associated_visit` (legitimately vary between blocks)
- **Severity**: WARNING

### 1.7 Semantic Duplicate DrugExposure Blocks

Detect DrugExposure blocks within a file that share the same source PHV(s) in `drug_concept` but map to different vocabulary codes (e.g., one ATC, one VANDF).

- **Severity**: WARNING

### 1.8 Cross-File PHT Visit Label Consistency

Detect cases where the same `populated_from` PHT is associated with different visit labels across different YAML files within the same cohort. A given PHT should map to the same visit label everywhere.

- **Logic**: Extracts `(populated_from, associated_visit)` pairs from both static `value:` and `expr:`-based visit references (including uuid5 patterns). Groups by PHT across all files. If a PHT appears with >1 distinct visit label, identifies the majority label and flags minority occurrences.
- **Excluded**: Visit class blocks (visit.yaml defines visits, not consumes them)
- **uuid5 support**: Parses visit labels from uuid5 expressions, closing a coverage regression where the uuid5 migration made static-only checks blind.
- **Severity**: ERROR

### 1.9 Common Typo Detection

Detect known misspellings in YAML file text that silently produce wrong slot names or values.

- **Known typos**: `expsoure_provenance` -> `exposure_provenance`, `expsoure` -> `exposure`, `vetricular` -> `ventricular`, `diagnoisis` -> `diagnosis`, `observaton` -> `observation`, `measurment` -> `measurement`, `particpant` -> `participant`, `assocated` -> `associated`
- **Severity**: ERROR

### 1.10 Space-in-Key Detection

Detect YAML keys with illegal internal spaces (e.g., `populated from:` instead of `populated_from:`). These are silently accepted by YAML parsers but create wrong keys the pipeline ignores, causing silent data loss.

- **Patterns**: `populated from`, `slot derivations`, `class derivations`, `value mappings`, `object derivations`, `unit conversion`, `source unit`
- **Severity**: CRITICAL -- key is silently ignored, data loss

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
- **Severity**: ERROR for required; INFO for recommended
- **Extension**: Advisory `age_at_observation` check on MeasurementObservation blocks (INFO severity -- the slot is optional in bdchm but its absence is a completeness gap)

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

- **Covers**: `value:` static assignments (ERROR), `value_mappings:` target values (ERROR), `expr:` case() result strings (WARNING)
- **Extension**: Cross-file enum consistency check for consistency-critical slots (currently `relationship_to_participant`). Flags when the same slot uses different values in different files. Severity: WARNING.

### 2.8 PHV Deduplication

Flag any PHV accession that is mapped as a measured value in more than one harmonized variable block within the same cohort.

- **Severity**: WARNING

### 2.10 Unconditional age_at_condition_start on Binary Conditions

Flag Condition blocks where `age_at_condition_start` is populated unconditionally but `condition_status` maps both PRESENT and ABSENT rows. ABSENT rows would incorrectly receive an age value.

- **Severity**: WARNING

### 2.11 Condition Missing ABSENT in condition_status

Flag Condition blocks where `condition_status.value_mappings` maps PRESENT or HISTORICAL but has no ABSENT mapping. Negative responses may be silently dropped.

- **Severity**: WARNING

---

## Phase 3: dbGaP Structure & Cross-Reference

**Scripts**: `hv-lint/phase-3/validate_dbgap_crossref.py` (checks 3.1-3.5), `hv-lint/phase-3/validate_semantic.py` (checks 3.9, 3.10, 3.12-3.16), `hv-lint/phase-3/check_value_semantic.py` (3.11)
**Dependencies**: PyYAML, gzip, json
**Data required**: YAML files + compressed indexes from `--cache-dir` (basic index for 3.1-3.5; extended detail index for 3.9-3.16)

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

### 3.4 PHV-to-PHT Membership

When a PHV exists in the index but belongs to a different PHT than the class's `populated_from`, categorized into three tiers:

| Tier | Condition | Severity |
|------|-----------|----------|
| **Covered by joins** | PHV's actual PHT is in the block's `joins` array | INFO |
| **Expected cross-table** | Slot is `associated_participant`, `associated_visit`, or `age_at_*` | INFO |
| **Unexpected cross-table** | All other cases | WARNING |

### 3.5 Cross-Table Reference Detection

Implemented as part of check 3.4 (see above). Unexpected cross-table references without joins are flagged as WARNING.

### 3.9 value_mappings Completeness

Validates that `value_mappings` entries cover the full set of coded values defined in dbGaP for the referenced PHV. Catches silent data loss when a source code is unmapped.

- **Severity**: Tiered --
  - **ERROR** for high-impact slots (`race`, `annotated_sex`, `sex`, `condition_status`, `value_enum`)
  - **WARNING** for all other slots
  - **INFO** for codes matching skip patterns (unknown, refuse, missing, N/A, etc.)
- **Design note**: `ethnicity` is excluded from the high-impact set because it frequently shares a PHV with race.

### 3.10 PHV Data Type vs Slot Role Compatibility

Validates that the dbGaP data type of a source PHV is compatible with the target slot's usage role. Catches adjacent-variable errors where a continuous variable is used where a categorical indicator was needed.

- **Severity**: ERROR

### 3.11 value_mappings Label/OMOP Concept Semantic Alignment

Validates that the source label from dbGaP semantically matches the target OMOP concept. Catches copy-paste swaps where target concept IDs are assigned to the wrong source code.

- **Data**: Extended detail index + OMOP concept lookup (embedded ~43 common concepts; auto-upgrades to full Athena CSV if available)
- **Severity**: HIGH

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

Validates that `value_mappings` keys actually exist in the dbGaP coded value list for the source PHV. The inverse of Rule 3.9: a phantom code is a YAML mapping key that never matches any real data row.

- **Severity**: ERROR for high-impact slots (race, annotated_sex, sex, condition_status, value_enum); WARNING otherwise

### 3.16 Quantity Missing Unit

Validates that Quantity class blocks containing `value_decimal` or `value_integer` also have a sibling `unit` slot. A Quantity without a unit is semantically incomplete.

- **Checks**: Both top-level `class_derivations` and nested `object_derivations`
- **Severity**: WARNING

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

Expressions are parsed using regex:
1. **case() result strings**: Both double-quoted and single-quoted
2. **Suffix concatenation**: Detects `case(...) + " SUFFIX"` pattern
3. **Colon stripping**: FHS Pattern-A (`str({phv}) + ":LABEL"`) -- leading colons stripped
4. **Fallback detection**: Labels containing "UNKNOWN", "DEFAULT", or "OTHER" flagged as INFO

### 5.0 Missing visit.yaml

Flag cohorts that have an ingest directory but no `visit.yaml` file.

- **Severity**: WARNING

### 5.1 Visit ID Uniqueness

Within a cohort's `visit.yaml`, no two Visit blocks should produce the same visit ID.

- **Static IDs**: Exact string comparison
- **Dynamic IDs**: Uniqueness check on extracted labels (uuid5 is deterministic)
- **Severity**: ERROR

### 5.2 Visit ID Referential Integrity

Every `associated_visit` value or case() target in measurement/condition files must resolve to a visit ID defined in the cohort's `visit.yaml`.

- **Static references**: Must exactly match a Visit ID
- **Dynamic references**: Each extracted label must appear in the visit registry's label set
- **Fallback labels**: Labels containing "UNKNOWN", "DEFAULT", "OTHER" are flagged as INFO
- **Severity**: ERROR for static mismatches; WARNING for dynamic label mismatches; INFO for fallback labels

### 5.3 Visit/PHT Consistency

> **Requires**: `--visit-cache`

Validate that Visit block PHTs are recognized dbGaP accessions and exist in the visit cache.

- **Severity**: ERROR for malformed PHT; WARNING for PHT not in cache

### 5.4 Age Formula Structural Check

Validate that `age_at_visit_start` and `age_at_visit_end` expressions are present and structurally sound.

- **Checks**: Age slot presence, PHV validity (if `--cache-dir` provided), unit conversion (`* 365` for years-to-days)
- **Severity**: WARNING for missing age slots; ERROR for invalid PHVs; INFO for missing `* 365`

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
- **Availability**: COPDGene 95% coverage; FHS 42% (free-text, gracefully skipped); all others 0% (check skipped)
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
  --bdchm-ref main \
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

