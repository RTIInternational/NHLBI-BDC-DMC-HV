# hv-dcc-compare

Cross-pipeline comparison toolkit: BDC DMC harmonized output vs. TOPMed DCC
harmonized phenotypes, across all 9 shared NHLBI cohorts.

---

## Architecture

Two-phase design — Phase 1 requires enclave access; Phase 2 runs anywhere.

```
PHASE 1 (run inside the enclave — requires raw restricted data)

  TOPMed DCC EAV files  -->  extract-topmed/extract_topmed_summaries.py
                         -->  topmed_<cohort>_summary.json

  BDC dm-bip TSV output -->  extract-harmonized/extract_harmonized_summaries.py
                         -->  bdc_<cohort>_summary.json

PHASE 2 (run anywhere — consumes aggregate JSON summaries only)

  topmed_*.json + bdc_*.json  -->  compare/compare.py
                                   compare/match_quality_table.py
                                   compare/validate_completeness.py
                                   compare/batch_scorecard.py
```

All outputs are **aggregate-only** — no participant IDs or individual-level data
are written, making results safe for export from restricted enclaves.

---

## Cohorts

ARIC · CARDIA · CHS · COPDGene · FHS · HCHS-SOL · JHS · MESA · WHI

---

## Setup

```bash
pip install -r requirements.txt
```

---

## Phase 1 — Inside the enclave

### Extract TOPMed DCC summaries

```bash
# From the hv-dcc-compare/ directory
python extract-topmed/extract_topmed_summaries.py \
    --demographics-file /path/to/topmed_dcc_harmonized_demographic_v4_eav.txt \
    --baseline-covariates-file /path/to/baseline_common_covariates_eav.txt \
    --blood-pressure-file /path/to/blood_pressure_eav.txt \
    --lipids-file /path/to/lipids_eav.txt \
    --blood-cell-count-file /path/to/blood_cell_count_eav.txt \
    --output-dir ./runs/topmed/
```

Produces: `runs/topmed/topmed_<COHORT>_summary.json` for each cohort present
in the input files.

### Extract BDC harmonized summaries

```bash
python extract-harmonized/extract_harmonized_summaries.py \
    --cohort ARIC \
    --base-dir /path/to/bdc_pipeline_output/ \
    --output-dir ./runs/bdc/
```

Produces: `runs/bdc/bdc_<COHORT>_summary_<timestamp>.json`

---

## Phase 2 — Outside the enclave

All comparison scripts in `compare/` read the JSON summaries as inputs.

### Side-by-side comparison report

```bash
python compare/compare.py \
    --topmed-json ./runs/topmed/topmed_aric_summary.json \
    --bdc-json    ./runs/bdc/bdc_aric_summary_<timestamp>.json
```

### Per-variable match quality table

```bash
python compare/match_quality_table.py \
    ./runs/topmed/topmed_aric_summary.json \
    ./runs/bdc/bdc_aric_summary_<timestamp>.json
```

### Batch scorecard (all cohorts)

```bash
# From a directory containing topmed/ and bdc/ subdirs
python compare/batch_scorecard.py \
    --topmed-dir ./runs/topmed/ \
    --bdc-dir    ./runs/bdc/ \
    --output-dir ./runs/scorecards/
```

### 19 Core Variable YAML coverage matrix

Requires a checkout of the HV repo to check YAML file presence.

```bash
python compare/core_variable_coverage_table.py \
    --hv-repo /path/to/NHLBI-BDC-DMC-HV \
    --topmed-dir ./runs/topmed/
```

### Translate BDC JSON keys (retroactive map application)

When new concept codes are added to `config.py`, apply them to older JSON files:

```bash
python compare/translate_bdc_json.py ./runs/bdc/bdc_aric_summary_old.json
```

---

## Files

| File | Purpose |
|------|---------|
| `config.py` | Central configuration -- 62 matched variables, 9 cohort definitions, value-mapping dictionaries, BDC concept maps, baseline visit config |
| `extract-topmed/extract_topmed_summaries.py` | Extracts TOPMed DCC EAV files into per-cohort aggregate JSON summaries |
| `extract-harmonized/extract_harmonized_summaries.py` | Extracts BDC dm-bip harmonized TSVs into per-cohort aggregate JSON summaries |
| `compare/compare.py` | Generates a side-by-side comparison report from two JSON summaries |
| `compare/match_quality_table.py` | Produces a per-variable Value Tier / Miss Tier grading table |
| `compare/validate_completeness.py` | Builds anonymized phenotype completeness profiles for both pipelines |
| `compare/batch_scorecard.py` | Processes all cohorts in batch; produces cross-cohort summary table |
| `compare/translate_bdc_json.py` | Post-processes a BDC JSON to rename raw concept codes to canonical TOPMed variable names |
| `compare/core_variable_coverage_table.py` | Cross-cohort 19 Core Variable coverage matrix (requires HV repo path) |
| `CHANGELOG.md` | Change log for all scripts in this directory |

---

## Configuration

All variable definitions, cohort metadata, and value-mapping dictionaries live in
`config.py` at the top level. Edit that file to:

- Add or remove matched variables
- Update cohort version numbers
- Add new value-mapping entries for encoded variables
- Update per-cohort baseline visit labels (`BASELINE_VISIT_CONFIG`)
