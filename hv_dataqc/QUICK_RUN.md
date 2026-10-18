# Quick run guide — Tables S4 and S5

Cheat-sheet for regenerating Tables S4 and S5. Both run entirely on Seven
Bridges, all cohorts in one run. For background and design, see the
[main README](README.md).

| Table | What it is |
|-------|-----------|
| **S4** | Pre-harmonized phv counts + source N per variable/cohort |
| **S5** | Harmonized summary stats (mean/min/max/…) per variable, pooled across cohorts |

QAQC (the source-vs-harmonized comparison) is not run from here: dm-bip's
harmonization workflow runs it per cohort
([`hv-dataqc-cohort.sh`](https://github.com/linkml/dm-bip/blob/main/scripts/workflow/hv-dataqc-cohort.sh)).

## Getting started on SB (Data Studio)

**Fresh Data Studio instance:** open a terminal, then

```bash
cd /sbgenomics/workspace
git clone https://github.com/RTIInternational/NHLBI-BDC-DMC-HV.git
cd NHLBI-BDC-DMC-HV
source hv_dataqc/sb_scripts/setup.sh
```

SB sessions can time out and lose the workspace, so expect to repeat this.

**Saved analysis, repo already cloned:** open a terminal, then

```bash
cd /sbgenomics/workspace/NHLBI-BDC-DMC-HV
git pull
source hv_dataqc/sb_scripts/setup.sh
```

`setup.sh` installs `uv` and the Python packages, and sets a sane umask and
`core.fileMode false` (SB rewrites file permissions). Source it in every new
terminal session; it ends by printing the run commands below.

Optional:

```bash
source hv_dataqc/sb_scripts/vi_defaults.sh       # vi as editor (SB doesn't persist dotfiles)
uv run python -m pytest hv_dataqc/tests/ -q      # sanity check before a long run
```

The reports read the transform specs in `priority_variables_transform/`, so
run from `main` unless you were given a specific branch.

## S4 — pre-harmonized phv report (SB enclave)

Spec-sourced: phv list/count from the transform specs, source `N` measured
by `extract_source` from the raw TSVs. No spreadsheets. One command, all
cohorts.

`run_s4_report.sh` takes no arguments and is idempotent: it fetches dbGaP
caches, extracts any cohort whose extract is missing or stale (its specs now
reference a phv it wasn't scoped to), reuses the rest, and builds the table.
Extraction is the **default** — you only need a flag to opt out of it or to
force it.

S4 keeps its extracts in `/sbgenomics/workspace/S4-output-files/extracts/`.
**When that folder is empty, the run extracts every cohort, FHS included**,
which is slow. Later runs reuse the extracts.

Watch for `WARNING: <COHORT>: N PHV(s) counted in phv_count but missing from
N`. Each listed phv says why (usually a stale dbGaP cache or a spec naming the
wrong PHT); that cohort's N for those rows is an undercount.

```bash
hv_dataqc/sb_scripts/run_s4_report.sh                 # the normal run
hv_dataqc/sb_scripts/run_s4_report.sh --list-cohorts  # cohorts with spec dirs
hv_dataqc/sb_scripts/run_s4_report.sh --no-extract    # build from existing extracts only
hv_dataqc/sb_scripts/run_s4_report.sh --force         # re-extract every cohort (slow)
# subset: --cohorts FHS,MESA
```

Output: `/sbgenomics/workspace/S4-output-files/s4_report_<ts>.csv` (+ a
`latest_s4_report.csv` symlink). Paste it (minus header) into the Table S4
template.

**Expected on a healthy run** (not errors):
- `LTRC BLOCKED … no source dir`: SB has no LTRC source data; S4 has no LTRC
  column.
- `WARNING: CARDIA: … pht003298 not in extract`: those specs reference
  CARDIA's GENEVA/ESP table, which SB's source data doesn't include, so those
  CARDIA cells are blank or undercount. Open curation question. Any *other*
  cohort in this warning is new and worth a look.
- `NOTE: … no template row: Interleukin 18 in blood`: the S4 template has no
  row for it yet.

A full first run (all cohorts extracting) takes about 15 minutes; later runs
reuse the extracts.

Inspect one variable's resolved phvs + per-phv N:

```bash
uv run python -m transform_assessment.spec_phv_report \
    --specs-root priority_variables_transform \
    --cohort FHS \
    --source-json <S4-output-files/extracts/FHS/latest_source/fhs_source_*.json> \
    --cache-dir hv_dataqc/local_output/dbgap-cache/fhs \
    --debug-variable ast_sgot
```

> **The new counts will be higher than the published Table S4. That is
> correct, not a bug.** The old pipeline filtered phvs two ways — hand-made
> `valid-phvs/` allow lists and an "out of scope" column in the curator
> spreadsheets — and both were retired on 2026-08-12 as unmaintainable. The
> published table is a frozen historical artifact; reproducing it is not a
> goal. An *increase* needs no explanation; a *decrease* is worth a look.
> Background: [`../transform_assessment/README.md`](../transform_assessment/README.md).
>
> The old sheet-based `preharmonized_qaqc_report.py` and the whole count
> investigation were removed on 2026-08-12; recover from tag
> `pre-s4-doc-cleanup-20260812` if you ever need to audit the published table.
> Don't try to re-run that pipeline — it reads live Google Sheets that have
> since moved.

## S5 — harmonized summary table (SB enclave)

One command, all cohorts in the chosen DataRun. Reads existing dm-bip
harmonized output — it does **not** re-run dm-bip.

```bash
hv_dataqc/sb_scripts/run_s5_report.sh --list-dataruns       # pick the newest
hv_dataqc/sb_scripts/run_s5_report.sh --datarun DataRun_20260624_1200
# or, for the latest automatically:
hv_dataqc/sb_scripts/run_s5_report.sh
# subset: --cohorts ARIC,MESA
```

Output tgz lands in `/sbgenomics/workspace/`; download via the JupyterLab
file browser. The `table_s5_paste_*.tsv` inside is the paste-ready table.

> **Currently broken: the S5 runner can only find harmonized data under
> `/sbgenomics/project-files/_QC_STAGING/DataRun_*`.** It has no
> `--harmonized-root` option to point it elsewhere yet (issue #929). A cached
> per-cohort extract is re-made automatically when Table S1 is newer than it;
> pass `--force` to re-extract for any other reason.

> **S5 reflects the DataRun's harmonized data, not the specs directly.**
> If a value looks wrong, confirm the DataRun was harmonized *after* the
> relevant spec fix. Picking an older DataRun reproduces old values.
