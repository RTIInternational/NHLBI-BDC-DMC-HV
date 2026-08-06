# hv-dcc-compare

Cross-pipeline comparison toolkit: BDC DMC harmonized output vs. TOPMed DCC
harmonized phenotypes, across all 9 shared NHLBI cohorts.

---

## Architecture

The **TOPMed DCC side is a fixed reference** — extract it once and reuse it for
every run. The **BDC side is extracted per dm-bip run**, then compared against
that reference.

```
ONE-TIME  (only when the TOPMed DCC release changes)

  TOPMed DCC EAV files  -->  extract_topmed_dcc.sh
                         -->  topmed_<cohort>_summary.json   (kept in a stable dir)

PER dm-bip RUN

  BDC dm-bip output      -->  run_dcc_compare.sh   (reads the fixed TOPMed reference)
  (DMC_*_Processed_*)         |-- extract-harmonized  -> bdc_<cohort>_summary.json
                              |-- compare/compare.py           -> reports (TXT + MD)
                              |-- compare/batch_scorecard.py   -> scorecards
                              `-- core_variable_coverage_table -> coverage matrix
```

**Everything runs inside the enclave** — both extractions and the comparison
step. Nothing is designed to run outside it. The summaries and reports are
engineered so that IF it ever becomes critical to move a specific one out, it
can be — but by default nothing leaves the enclave.

That is why every output is **aggregate-only** — no participant IDs, raw source
values, or individual-level rows are written to JSON, stdout, stderr, or log
files. Categorical distributions also apply small-cell suppression (any category
with n&lt;5 is pooled into an `Other (n<5)` bucket). These guards exist so a
summary or report *could* be released when a specific export is justified; they
are not an invitation to run any step outside the enclave.

---

## Cohorts

ARIC · CARDIA · CHS · COPDGene · FHS · HCHS-SOL · JHS · MESA · WHI

---

## Setup

Requires Python 3.10+.

```bash
pip install -r requirements.txt
```

---

## How to run

Two wrapper scripts drive the whole pipeline. Run both from the
`hv-dcc-compare/` directory.

### Step 1 — build the TOPMed DCC reference (one-time)

The TOPMed DCC harmonized phenotypes are a fixed external reference; they do not
change between dm-bip runs. Extract them once into a stable directory you keep:

```bash
./extract_topmed_dcc.sh \
    --topmed-dir /data/topmed-dcc-eav \      # dir of DCC EAV files / *.tar.gz bundles
    --out        /data/topmed-dcc-summaries  # stable reference dir, reused every run
```

Re-run this only when the TOPMed DCC release itself changes.

### Step 2 — compare a dm-bip run against the reference

Point `--bdc-dir` at your dm-bip output root — the directory holding the
`DMC_*_<COHORT>_Processed_*` folders (e.g. the `/root` output mount from the
Docker workflow) — and `--topmed-summaries` at the Step 1 reference:

```bash
./run_dcc_compare.sh \
    --bdc-dir          /root \
    --topmed-summaries /data/topmed-dcc-summaries
```

This extracts the BDC side (all cohorts auto-discovered), then builds reports,
scorecards, and the coverage matrix into a timestamped run directory:

```
runs/<timestamp>/
  bdc/         bdc_<cohort>_summary_<ts>.json     (this run's BDC extracts)
  reports/     <COHORT>_comparison_<date>.{txt,md} + Cross_Cohort_Summary
  scorecards/  <COHORT>_scorecard + cross_cohort_summary
  coverage/    core_variable_coverage.txt
```

The TOPMed reference is read in place and never regenerated.

Common options for `run_dcc_compare.sh`:

| Flag | Purpose |
|------|---------|
| `--cohorts "ARIC CHS WHI"` | Restrict to specific cohorts (default: all discovered) |
| `--all-vars` | Grade every matched variable, not just the 19 core |
| `--out <dir>` | Custom run directory (default: `runs/<timestamp>/`) |
| `--hv-repo <path>` | HV checkout for the coverage matrix (default: two levels up) |
| `--skip-coverage` | Skip the YAML coverage matrix |

The whole thing runs inside the enclave, where the input data lives — extraction
and comparison alike. The resulting `runs/<timestamp>/` contents are
aggregate-only; that property is what would let a specific summary or report be
released if it ever became critical, but the default is that everything stays in
the enclave. Override the interpreter with `PYTHON=python3 ./run_dcc_compare.sh ...`.

---

## Manual invocation (what the wrappers call)

The wrapper scripts above call the scripts below. Run these directly only for
single-cohort runs, debugging, or the extra comparison tools not wired into
`run_dcc_compare.sh` (`match_quality_table.py`, `validate_completeness.py`,
`translate_bdc_json.py`). All of these run inside the enclave.

## Extraction — build the summary JSONs

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

## Comparison — build reports from the summaries

All comparison scripts in `compare/` read the JSON summaries as inputs. They run
inside the enclave alongside the extraction step.

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
| `extract_topmed_dcc.sh` | **Wrapper** — one-time TOPMed DCC reference extraction (Step 1) |
| `run_dcc_compare.sh` | **Wrapper** — per-run driver: BDC extract + reports + scorecards + coverage (Step 2) |
| `config.py` | Central configuration -- 62 matched variables, 9 cohort definitions, value-mapping dictionaries, BDC concept maps, baseline visit config |
| `extract-topmed/extract_topmed_summaries.py` | Extracts TOPMed DCC EAV files into per-cohort aggregate JSON summaries |
| `extract-harmonized/extract_harmonized_summaries.py` | Extracts BDC dm-bip harmonized TSVs into per-cohort aggregate JSON summaries |
| `compare/compare.py` | Generates a side-by-side comparison report from two JSON summaries |
| `compare/match_quality_table.py` | Produces a per-variable Value Tier / Miss Tier grading table |
| `compare/validate_completeness.py` | Builds anonymized phenotype completeness profiles for both pipelines |
| `compare/batch_scorecard.py` | Processes all cohorts in batch; produces cross-cohort summary table |
| `compare/translate_bdc_json.py` | Post-processes a BDC JSON to rename raw concept codes to canonical TOPMed variable names |
| `compare/core_variable_coverage_table.py` | Cross-cohort 19 Core Variable coverage matrix (requires HV repo path) |

Note: the deprecated legacy `mapping-quality-table.py` wrapper was not carried
forward. Use `compare/match_quality_table.py` for per-variable grading.

---

## Safety and tests

Before running on restricted data, run the synthetic smoke tests:

```bash
python -m unittest discover -s tests
```

The tests verify CLI startup, config imports, aggregate-only TOPMed extraction,
concept-code translation, and absence of known participant-level debug print
patterns. Test fixtures are synthetic only.

---

## Configuration

All variable definitions, cohort metadata, and value-mapping dictionaries live in
`config.py` at the top level. Edit that file to:

- Add or remove matched variables
- Update cohort version numbers
- Add new value-mapping entries for encoded variables
- Update per-cohort baseline visit labels (`BASELINE_VISIT_CONFIG`)
