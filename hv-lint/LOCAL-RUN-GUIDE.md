# HV-Lint -- Local Run Guide

How to run HV-Lint locally against your branch before submitting a PR.

---

## Prerequisites

| Requirement | Details |
|---|---|
| Python 3.12 or 3.13 | 3.14 works but Phase 2 uses frozen fallback (see Warnings below) |
| PyYAML + yamllint | `pip install pyyaml yamllint` |
| linkml-runtime | `pip install linkml-runtime` (Phase 2 schema validation) |
| dbGaP indexes present | `hv-lint/dbgap-cache/*.json.gz` (committed -- no action needed unless updating) |

> **Tip**: Use the HV repo's existing venv if one exists: `.venv/Scripts/Activate.ps1` (Windows) or `source .venv/bin/activate` (Linux/Mac).

---

## Quick Start

From the HV repo root:

```bash
# Phase 1 -- YAML structure (no external data needed)
python hv-lint/phase-1/run_phase1.py --cohort ARIC

# Phase 2 -- Model conformance (needs network for schema fetch)
python hv-lint/phase-2/run_phase2.py --cohort ARIC

# Phase 3 -- dbGaP cross-reference (needs indexes)
python hv-lint/phase-3/run_phase3.py --cohort ARIC --cache-dir hv-lint/dbgap-cache

# Phase 5 -- Visit structure (needs indexes)
python hv-lint/phase-5/run_phase5.py --cohort ARIC --cache-dir hv-lint/dbgap-cache
```

Replace `ARIC` with any cohort name, or use `all` to lint everything.

---

## Phase-by-Phase

### Phase 1 -- YAML Structural & Formatting

No external data required. Checks syntax, duplicate blocks, inline comments, typos, cross-block consistency, cross-file PHT visit labels.

```bash
python hv-lint/phase-1/run_phase1.py --cohort ARIC --fail-on error
```

### Phase 2 -- BDC-HM Model Conformance

Fetches the BDCHM schema from GitHub at runtime (requires network). Checks key names, slot/class validity, required slots, object derivation structure, CURIE format, enum membership, PHV deduplication.

```bash
python hv-lint/phase-2/run_phase2.py --cohort ARIC --fail-on error

# Pin schema version:
python hv-lint/phase-2/run_phase2.py --cohort ARIC --bdchm-ref v1.2.0

# Use local schema:
python hv-lint/phase-2/run_phase2.py --cohort ARIC --bdchm-schema path/to/bdchm.yaml
```

### Phase 3 -- dbGaP Cross-Reference

Requires the compressed indexes in `hv-lint/dbgap-cache/`. Checks PHV/PHT existence, membership, value_mappings completeness, type compatibility, unit conversion, phantom codes, and more.

```bash
python hv-lint/phase-3/run_phase3.py --cohort ARIC --cache-dir hv-lint/dbgap-cache --fail-on error
```

### Phase 5 -- Visit Structure Validation

Cross-file validation of visit.yaml against all measurement/condition files. Checks visit ID uniqueness, referential integrity, uuid5 compliance, collection interval mismatches.

```bash
python hv-lint/phase-5/run_phase5.py --cohort ARIC --cache-dir hv-lint/dbgap-cache --fail-on error
```

---

## CLI Options

| Option | Applies to | Description |
|---|---|---|
| `--cohort <NAME>` | All phases | ARIC, CARDIA, CHS, COPDGene, FHS, HCHS, JHS, MESA, SPIROMICS, WHI, or `all` |
| `--fail-on <level>` | All phases | Exit code threshold: `critical`, `error`, `high`, `warning`, `info` (default: `error`) |
| `--skip <component>` | All phases | Skip one or more sub-components by name |
| `--bdchm-ref <ref>` | Phase 2 | Git ref for BDCHM schema (default: `main`) |
| `--bdchm-schema <path>` | Phase 2 | Local schema file (overrides `--bdchm-ref`) |
| `--cache-dir <path>` | Phase 3, 5 | Path to index directory (default: `hv-lint/dbgap-cache`) |
| `--hv-root <path>` | All phases | Override HV repo root detection |

---

## Updating dbGaP Indexes

The compressed indexes in `hv-lint/dbgap-cache/` are committed to the repo so CI works without NCBI access. To update them (e.g., after a dbGaP version bump):

```bash
# Full refresh (fetches source XML from NCBI, builds all indexes):
python hv-lint/update_data.py

# Single cohort:
python hv-lint/update_data.py --cohort aric

# Rebuild from already-fetched source data:
python hv-lint/update_data.py --build-only

# See what's currently cached:
python hv-lint/update_data.py --summary
```

See [MAINTENANCE.md](MAINTENANCE.md) for full documentation on version bumps, new cohort onboarding, and troubleshooting.

---

## Expected Warnings (Not Errors)

### Phase 2: Frozen key-set warning

On Python 3.14, `linkml_map` fails to import due to a `pint`/`ucumvert` incompatibility. Phase 2 falls back to frozen key constants from v0.3.9. Results are still reliable:

```
WARNING: linkml_map import failed ... Using frozen key sets from linkml-map v0.3.9.
```

### Phase 2: Schema fetch failure

If you are offline or `raw.githubusercontent.com` is unreachable, Phase 2 cannot load the BDCHM schema. Use `--bdchm-schema` to point at a local copy.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Phase 3: many "PHT not found" / "PHV not found" | Index is older than the YAML files | Rebuild with `python hv-lint/update_data.py --build-only` |
| `ModuleNotFoundError: No module named 'linkml_runtime'` | Missing dependency | `pip install linkml-runtime` in your venv |
| Phase 3: `No YAML files found` | Wrong working directory | Run from the HV repo root |
| Phase 2: `OBA:VTxxxxxxx` flagged | VT (Vertebrate Trait) terms incorrectly prefixed with `OBA:` | Review and correct the ontology prefix |

---

## Full Rule Reference

See [HV-Lint-Reference.md](HV-Lint-Reference.md) for the complete rule catalog, assumptions, severity definitions, and lint gap log.
