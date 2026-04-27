# local_scripts — Local Runner Scripts

Convenience wrappers that run **outside the enclave** (your laptop).
They resolve repo paths automatically so commands are copy-paste ready.

## Scripts

### `compare.sh <cohort> [extra flags...]`

Runs the source-vs-harmonized comparison. Automatically finds the most
recent source and harmonized JSONs in `local_output/`, locates the YAML
transform dir, and points at the dbGaP cache.

```bash
./compare.sh COPDGene
./compare.sh SPIROMICS
./compare.sh COPDGene --thresholds custom.yaml
```

**Prerequisites:**
1. Source and harmonized JSONs downloaded to `../local_output/`
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

# 2. Download extract JSONs from SB into ../local_output/
#    (scp, sb download, or manual copy)

# 3. Run comparison
./compare.sh COPDGene
```

Output reports land in the current directory (compare script default).
Move them to `../local_output/` to keep things tidy.
