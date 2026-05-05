# local_scripts — Local Runner Scripts

Convenience wrappers that run **outside the enclave** (your laptop).
They resolve repo paths automatically so commands are copy-paste ready.

**Assumed working directory:** Run these scripts from within
`NHLBI-BDC-DMC-HV/hv-dataqc/local_scripts/`. The scripts derive the
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
```

**Prerequisites:**
1. Source and harmonized JSONs in `../local_output/` (via `unpack.sh` or manual copy)
2. dbGaP cache fetched (see `fetch_cache.sh`)

### `fetch_cache.sh [flags...]`

Wrapper for `cache-fetcher/fetch_dbgap_cache.py` that writes to
`local_output/dbgap-cache/` instead of the default location. All flags
are forwarded.

```bash
./fetch_cache.sh --list
./fetch_cache.sh --cohort copdgene
./fetch_cache.sh --cohort mesa --dry-run
./fetch_cache.sh                          # all cohorts
```

## Typical local workflow

```bash
# 1. Fetch dbGaP cache (once per cohort)
./fetch_cache.sh --cohort copdgene

# 2. Download dataqc_<cohort>_output.tgz from SB and unpack
./unpack.sh

# 3. Run comparison
./compare.sh COPDGene
```

Output reports land in the current directory (compare script default).
Move them to `../local_output/` to keep things tidy.
