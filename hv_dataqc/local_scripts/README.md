# local_scripts — Local Runner Scripts

Convenience wrappers that run **outside the enclave** (your laptop).
They resolve repo paths automatically so commands are copy-paste ready.

**Assumed working directory:** Run these scripts from within
`NHLBI-BDC-DMC-HV/hv_dataqc/local_scripts/`. The scripts derive the
repo root from their own location, so no hardcoded paths are needed.

## Scripts

### `unpack.sh [path-to-tgz]`

Unpacks a dataqc output tgz (downloaded from SB via `run_extracts.sh`)
into `local_output/`. By default, finds the most recent
`~/Downloads/dataqc_*_output.tgz`.

```bash
./unpack.sh                                         # auto-find in ~/Downloads
./unpack.sh ~/Downloads/dataqc_copdgene_output.tgz  # explicit path
```

### `compare.sh <cohort> [extra flags...]`

Runs the source-vs-harmonized comparison. Looks for extract JSONs in
`local_output/latest_source/` and `local_output/latest_harmonized/` first
(from `unpack.sh`), then falls back to flat files in `local_output/`.
Automatically locates the YAML transform dir and dbGaP cache.

```bash
./compare.sh COPDGene
./compare.sh SPIROMICS
./compare.sh COPDGene --thresholds custom.yaml
./compare.sh COPDGene --yaml-dir /path/to/integration/HV/priority_variables_transform/COPDGene-ingest
```

Each run is archived. Outputs are written into
`../local_output/archive/<git-commit>_<UTC-timestamp>/` alongside a
`manifest.json` recording the inputs used, and the top-level
`../local_output/<cohort>_comparison_{report.md,results.json}` symlinks
are updated to point at the latest archive entry. The script also creates
timestamped top-level symlinks for each run, such as
`../local_output/<cohort>_comparison_report_<UTC-timestamp>.md`. Old reports
are never overwritten.

Pass `--yaml-dir` to compare against transform YAMLs from another checkout,
such as an integration/testing repo. The wrapper consumes this flag and uses
that directory instead of auto-resolving `priority_variables_transform/` from
the local repo.

For HCHS-SOL runs, source/harmonized extract filenames may use the short
cohort name `HCHS`, while the dbGaP cache directory uses the canonical
manifest key `hchs_sol`. `compare.sh HCHS` automatically looks for the cache
under `../local_output/dbgap-cache/hchs_sol`.

The script exits non-zero when the comparison surfaces any `FAIL` results
(matching the underlying `python -m hv_dataqc.compare` exit behavior).

**Prerequisites:**
1. Source and harmonized JSONs in `../local_output/` (via `unpack.sh` or manual copy)
2. dbGaP cache fetched (see `fetch_cache.sh`)
3. HV transform YAMLs at `<repo>/priority_variables_transform/<COHORT>-ingest/`
   (always present in this repo)

### `fetch_cache.sh <cohort> [flags...]`

Wrapper for `cache_fetcher/fetch_dbgap_cache.py` that writes to
`local_output/dbgap-cache/` instead of the default location. Extra
flags are forwarded.

```bash
./fetch_cache.sh copdgene
./fetch_cache.sh mesa --dry-run
./fetch_cache.sh --list                   # list available cohorts
```

## Typical local workflow

```bash
# 1. Fetch dbGaP cache (once per cohort)
./fetch_cache.sh copdgene

# 2. Download dataqc_<cohort>_output.tgz from SB and unpack
./unpack.sh

# 3. Run comparison
./compare.sh COPDGene
```

Comparison reports are archived under `../local_output/archive/`. The
stable top-level symlinks at `../local_output/<cohort>_comparison_*` always
point at the most recent run; timestamped top-level symlinks provide durable
paths for individual runs.
