# dbGaP Cache Fetcher

Self-contained downloader for the dbGaP per-dataset XML metadata that the
HV-DataQC compare tool needs. Run this once per cohort to build a local
cache, then point `compare_source_harmonized.py --cache-dir` at it.

## What it downloads

For each cohort, the FTP `pheno_variable_summaries/` directory:

- `*.data_dict.xml` (always) — per-dataset variable definitions: types,
  units, coded value lists, descriptions. This is what the compare tool
  reads to resolve PHV accessions to source column names.
- `*.var_report.xml` (optional, `--include-var-reports`) — per-variable
  summary statistics. Larger; not required by the compare tool.
- `GapExchange_<study>.xml` (optional, `--include-gap-exchange`) — study-
  level XML manifest. Not required by the compare tool.

## Layout produced

```
<output-dir>/
  aric/
    pheno_variable_summaries/
      phs000280.v8.pht002286.v3.<dataset>.data_dict.xml
      ...
  cardia/
    pheno_variable_summaries/
      ...
```

This matches exactly what `compare_source_harmonized.py --cache-dir` expects.

## Cohort versions

Each cohort's pinned dbGaP version (study + data + participant version) lives
in `manifests/_manifest-<key>.yaml`. The fetcher resolves the FTP path from
those manifest entries. To upgrade a cohort to a newer dbGaP release, edit
the corresponding manifest file's `current_version:` block and re-run with
`--force`.

## Requirements

- Python 3.10+
- `pip install requests pyyaml`

## Quick start

Use the convenience wrapper in `local_scripts/` which writes to the
standard `local_output/dbgap-cache/` location:

```bash
cd ../local_scripts/
./fetch_cache.sh --cohort copdgene
./fetch_cache.sh --list
```

## Usage (direct)

List available cohorts:

```bash
python fetch_dbgap_cache.py --list
```

Fetch a single cohort (downloads to `./dbgap-cache/<cohort>/` by default):

```powershell
python fetch_dbgap_cache.py --cohort aric
```

Choose a different output location:

```powershell
python fetch_dbgap_cache.py --cohort fhs --output-dir D:\caches\bdc-dbgap
```

Fetch all cohorts:

```powershell
python fetch_dbgap_cache.py
```

Dry-run (preview without downloading):

```powershell
python fetch_dbgap_cache.py --cohort mesa --dry-run
```

Re-download (ignore existing files):

```powershell
python fetch_dbgap_cache.py --cohort chs --force
```

Show what's already cached:

```powershell
python fetch_dbgap_cache.py --summary --output-dir ./dbgap-cache
```

## Expected files (default data_dict.xml fetch)

| Cohort     | Files |
|------------|------:|
| ARIC       |  368  |
| CARDIA     |  328  |
| CHS        |   65  |
| COPDGene   |    8  |
| FHS        |  586  |
| HCHS-SOL   |    5  |
| JHS        |  114  |
| LTRC       |   27  |
| MESA       |   97  |
| SPIROMICS  |    4  |
| WHI        |  100  |

Counts come from the bundled version-pinned manifests and live FTP discovery.
Download sizes vary by dbGaP release; optional `--include-var-reports`
downloads substantially more data. Most users only need one cohort at a time.

## Wiring it into the compare tool

```powershell
python -m hv_dataqc.compare `
    --cohort ARIC `
  --source <source.json> `
  --harmonized <harmonized.json> `
    --yaml-dir <path-to-HV>\priority_variables_transform\ARIC-ingest `
    --cache-dir .\dbgap-cache\aric
```

Note: `--cache-dir` is **required** when `--yaml-dir` is supplied. The
compare tool will hard-fail loudly (exit 2) rather than silently produce
an empty crosswalk.

## Notes

- Files are version-pinned via the manifests, so re-runs are idempotent —
  already-downloaded files are skipped.
- A polite 0.5s delay separates real network requests; `--summary` and
  re-runs against existing files are instant.
- The fetcher writes only inside `--output-dir`. Nothing else on the
  filesystem is touched.
