# HV-DataQC: Source vs. Harmonized Output Comparison Suite

Validates that the BDC dm-bip harmonized output faithfully preserves the
source dbGaP data — checking N preservation, distribution matching, clinical
ranges, visit structure, and cross-variable consistency.

---

## Components

| Folder | Script | Purpose | Runs where |
|--------|--------|---------|-----------|
| `extract-source/` | `extract_source_summaries.py` | Summarize raw dbGaP TSVs | **Inside enclave** |
| `extract-harmonized/` | `extract_harmonized_summaries.py` | Summarize dm-bip harmonized output | **Inside enclave** |
| `compare/` | `compare_source_harmonized.py` | Compare both summaries; run checks C1-C11 | Outside enclave |
| `cache-fetcher/` | `fetch_dbgap_cache.py` | Download dbGaP data dictionaries for PHV resolution | Outside enclave |
| `sb_scripts/` | Runner/analysis scripts | Ad-hoc scripts for enclave work | **Inside enclave** |
| `local_scripts/` | `compare.sh`, `fetch_cache.sh` | Convenience wrappers (auto-resolve paths) | Outside enclave |
| `sb_output/` | *(gitignored)* | Output produced on Seven Bridges | **Inside enclave** |
| `local_output/` | *(gitignored)* | Downloaded JSONs, dbgap-cache, comparison reports | Outside enclave |

---

## Design Principles

1. **Source extract is YAML-agnostic.** It summarizes every column in the raw
   TSV regardless of what the current HV YAMLs reference. This makes it a
   stable, reusable artifact — it never needs to be re-run when YAMLs change,
   only when the source study version changes or a new PHT table is added.

2. **Harmonized extract is also YAML-agnostic.** It reads entity TSVs produced
   by dm-bip and groups by `observation_type` / `condition_concept` columns —
   concept codes that are already baked into the pipeline output. Visit UUIDs
   are resolved to human-readable labels from `Visit.tsv` at extraction time.

3. **Comparison uses live YAMLs.** The crosswalk (source PHV → harmonized concept
   code) is built fresh from the current HV YAML checkout on every compare run.
   Re-run `compare_source_harmonized.py` as often as needed as YAMLs evolve — no
   re-entry to the enclave required.

4. **dbGaP cache is required for YAML mode.** When `--yaml-dir` is supplied, a
   local dbGaP cache is also required (`--cache-dir`) to resolve PHV accessions to
   source column names. Use `cache-fetcher/fetch_dbgap_cache.py` to build the cache
   (deps: `requests`, `pyyaml`; one command per cohort, idempotent on re-runs).

---

## Workflow

### Quick start (using convenience scripts)

**On Seven Bridges** (run extracts):
```bash
cd NHLBI-BDC-DMC-HV && git pull && source hv-dataqc/sb_scripts/setup.sh &&
cd ../local_scripts
./fetch_cache.sh --cohort <cohort name e.g. copdgene> # fetch metadata
cd ..
./NHLBI-BDC-DMC-HV/hv-dataqc/sb_scripts/run_extracts.sh <cohort name e.g. COPDGene> # run the extract
# → auto-discovers DataRun, runs both extracts, packages output.tgz for download
```

***Note, if the most recent version is running on the branch, then you will need to pull from a specific branch to run the latest QC code which has not been merged to the main.
```
# 1. Go into the repo
cd NHLBI-BDC-DMC-HV

# 2. Fetch all remote branches
git fetch origin

# 3. Switch to the target branch
git checkout <feature branch name>

# 4. Pull latest from that branch
git pull origin <feature branch name>
```

**Locally** (fetch cache, unpack, compare):
```bash
git pull
cd hv-dataqc/local_scripts/
./fetch_cache.sh --cohort copdgene        # once per cohort
./unpack.sh                                # unpacks ~/Downloads/dataqc_*_output.tgz
./compare.sh COPDGene                      # auto-finds latest JSONs, YAML dir, cache
```

### Output layout

Both extract scripts write into timestamped subdirectories with `latest_*`
symlinks, so you never need to type timestamps:

```
QC-output-files/<COHORT>/
  source_<ts>/copdgene_source_<ts>.json
  harmonized_<ts>/copdgene_harmonized_<ts>.json
  latest_source -> source_<ts>
  latest_harmonized -> harmonized_<ts>
```

### Full manual workflow

See [local_scripts/README.md](local_scripts/README.md) and
[sb_scripts/README.md](sb_scripts/README.md) for details on running
individual steps or without the convenience wrappers.

---

## Exported JSON Format (both extracts)

Both `extract_source_summaries.py` and `extract_harmonized_summaries.py` write
**aggregate-only** JSON — no individual participant rows.

```json
{
  "metadata": { "source": "raw_dbgap", "cohort": "SPIROMICS", ... },
  "total_participants": 2973,
  "total_rows": 11892,
  "rows_per_visit": { "VISIT_1": 2973, ... },
  "variables": {
    "<key>": {
      "type": "continuous",
      "n_valid": 7757, "n_missing": 135,
      "mean": 170.4, "sd": 9.1, ...
    },
    "<key>": {
      "type": "categorical",
      "distribution": { "1": {"n": 5000, "pct": 42.1}, ... }
    }
  }
}
```

---

## Checks (C1-C11)

| Check | What it validates |
|-------|------------------|
| C1 | Total participant N preserved |
| C2 | Per-variable valid N (no silent row loss) |
| C3 | Missing value rates stable |
| C4 | Continuous mean preserved (same unit) |
| C5 | Continuous mean preserved after unit conversion |
| C6 | Standard deviation preserved |
| C7 | Categorical distributions match (with value_mappings translation) |
| C8 | Visit N distribution preserved |
| C9 | Harmonized values within clinical plausible range |
| C10 | Cross-variable consistency (SBP > DBP, FEV1 < FVC) |
| C11 | Source/harmonized type consistency (continuous vs categorical) |

Recent comparison report details:

- C7 includes full source/harmonized categorical distribution tables, with many-to-one
  YAML value mappings aggregated before percentages are compared.
- C9 annotates range findings as `[out+src]`, `[out only]`, or `[src only]` when
  source min/max context is available.
- C10 reads `_cross_variable_rules` from `clinical_ranges.yaml`; simple two-variable
  mean comparisons run automatically, while formula rules are reported as `SKIP`
  until implemented.

---

## Requirements

```
pandas >= 1.3
pyyaml >= 5.4
requests >= 2.25  # cache-fetcher only
```

Install: `uv sync` (from repo root)
