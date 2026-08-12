# transform_assessment

Generates Tables S4/S5 for the Data Harmonization supplementary data, sourced
from the transform specs in `priority_variables_transform/` rather than from the
curator spreadsheets. Table S1 is the concept-code → publication-label source.

## Open questions for the team

Live decisions blocking or shaping this work. Nothing here is settleable without
the person named.

### For the curator — Table S1 gaps (drafted 2026-08-03, still unsent)

Of 127 distinct concept codes across the specs, 121 resolve cleanly. These
questions cover the rest. They were held for "after the next S4 run" so they
could cite real numbers; that gate never cleanly arrived, and none of them
actually depend on it. **Send independently.**

**1. Should LTRC and SPIROMICS be S4 columns?** They have transform specs but no
columns in the template. Five LTRC-only variables are omitted from the sheet
entirely as a result — `alpha1_antitrypsin` (emits `OBA:2050075`, a correct and
permissible code with no S1 row), `asthma_md`, `bronchitis`, `bronchitis_md`,
`pulmonary_fibrosis`. If those cohorts should be included, the layout needs two
more columns and these five need S1 rows. If not, this is closed.

**2. Seven `var_name` spellings drift from S1.** Each is one variable spelled two
ways; no cohort uses both, and the S1 spelling covers the majority — but the
cohorts on the left don't join the S1-labeled row.

| Spec `var_name` | Cohorts | S1 `var_name` | S1 label |
|---|---|---|---|
| `hist_mi` | CHS | `hist_my_inf` | History of myocardial infarction |
| `hist_heart_failure` | CHS | `hist_hrtfail` | History of heart failure |
| `hist_hrt_failure` | COPDGene | `hist_hrtfail` | History of heart failure |
| `hist_heart_disease` | CHS | `hist_hrtdis` | History of heart disease |
| `hist_coronary_bypass` | CHS | `hist_cor_bypg` | History of coronary artery bypass graft |
| `history_cvd` | CHS | `hist_cvd` | History of cardiovascular disease |
| `taking_non_statin_medication` | CHS, MESA | `tak_nstat_med` | Taking non statin medication |

**Recommend** renaming the specs to match S1 rather than adding alternate names
to S1 — S1 is the published artifact and shouldn't carry duplicates. Worth
settling now, since the spec files are being revised separately. Each pair still
needs a sanity check that it really is the same concept: no cohort using both
spellings rules out their being distinct variables, but the semantic match is a
judgment call.

**3. Thirteen spec variables have no S1 row** — missing rows, or deliberately out
of scope?

*Conditions:* `chd` (CARDIA, JHS, MESA, SPIROMICS), `chf` (CARDIA, MESA,
SPIROMICS), `chr_bronchitis` (CARDIA, HCHS, MESA, SPIROMICS, WHI), `emphysema`
(CARDIA, COPDGene, LTRC, MESA, SPIROMICS), `stroke_isch_atk` (CARDIA, COPDGene),
`hist_cor_art_dis` (COPDGene), `blood_clots` (COPDGene). Note
`stroke_isch_atk` and `hist_cor_art_dis` are *not* duplicates of S1's `stroke`
and `hist_cor_angio` — cohorts that have them use both, against different source
variables, so they are genuinely separate concepts.

*Medication classes:* `tak_adrenergics`, `tak_antihypertensives`,
`tak_cort_steroid_oral`, `tak_cort_steroid_resp` (COPDGene, plus MESA on the
oral steroid). S1 has `tak_steroid` but not the oral/respiratory split.

*`med_use`* (FHS) — 82 source variables, looks like a general medication-use
rollup rather than a single harmonized variable; likely out of scope.

*`Interleukin 18 in blood`* (FHS) — added to S1 in the last review round and
resolves correctly, but has no S4 template row. Add the row, or confirm it is out
of scope for S4.

**Not for the curator — ours to fix.** Six structural entries (`participant`,
`person`, `visit`, `research_study`, `researchstudy`, `demography`) derive
non-Observation BDCHM classes and were never harmonized variables; they need a
filter on our side. `research_study` vs `researchstudy` is our own naming
inconsistency. Education level and the FHS fasting-lipid codes came up in the
same round but are value-level modeling questions for S6, not S4.

**For the schema owner — specs and BDCHM enums disagree.** Raised in
[`history/SPEC_CODE_CORRECTIONS_20260803.md`](history/SPEC_CODE_CORRECTIONS_20260803.md)
§"Open items"; unresolved:

- `cig_smok` now uses the curator-directed `OMOP:35811013`, but
  `MeasurementObservationTypeEnum` binds `SMOKING_STATUS` to the old
  `OMOP:4282779`. One of them has to move. Same shape, less urgent, for
  `vege_serving` `OMOP:37311566` and Basophils `OMOP:3006315`.
- `edu_lvl` has four different shapes across six cohorts, and neither candidate
  concept code is a permissible `observation_type` value today.
- `alpha1_antitrypsin` (LTRC) is correctly coded but has no Table S1 row.
- 36 of 127 distinct `observation_type` codes in the live specs are not
  permissible enum values. Most predate this work; worth a reconciliation pass.

**For CARDIA spec owners — asked 2026-08-04 in Slack, awaiting answer.** Seven
`value_decimal` expressions in `CARDIA-ingest/alcohol_servings.yaml` are
commented out; will they return for ingest? The project lead's read is that the 3
live phvs are beer/wine/liquor components and the disabled expressions summed
them — see [`SPEC_SOURCED_S4_DESIGN.md`](SPEC_SOURCED_S4_DESIGN.md).

## The published Table S4 is not a target

**The generated S4 does not reproduce the published S4, and it is not supposed
to.** As of 2026-08-12 the published table is a frozen historical artifact.

The old pipeline narrowed its phv set two ways. **Neither is carried forward,
and neither should be**, per the project lead in Slack: *"those lists of valid
phv were made a year ago and probably are no longer valid. You also shouldn't go
by what is in the spreadsheets anymore. We can't keep those up to date."*

| filter | what it was | status |
|---|---|---|
| `valid-phvs/{cohort}.tsv` | per-cohort allow lists, one bare phv per line, hand-supplied ~2025 | **retired — stale** |
| `Transform Comment == "out of scope"` | curator annotation in two live Google Sheets | **retired — unmaintainable** |

The current generator has no equivalent of either, and no path by which a
per-phv scope decision reaches it. Any phv in a live spec's value slot is
counted. That is now the intended behavior, not a gap to close.

**Therefore: expect the new numbers to come out higher than published.** The
retired filters only ever removed phvs, so an increase needs no explanation. A
*decrease* is worth investigating.

One caveat: a scope channel survives that *is* honored, silently. Curators
sometimes comment out a block in a spec YAML instead of annotating a sheet, and
`yaml.safe_load` never sees it — so the generator drops those phvs without
saying so. `CARDIA-ingest/alcohol_servings.yaml` is the known case. Grep the
spec for commented-out blocks before treating a low count as a bug.

The cell-by-cell investigation that once chased this gap has been removed, along
with the comparison scripts and 13 dated exports of the published sheet. See
[`history/S4_COUNT_INVESTIGATION_REMOVED.md`](history/S4_COUNT_INVESTIGATION_REMOVED.md)
for what it concluded and how to restore it (tag `pre-s4-doc-cleanup-20260812`).

## What to do next

In priority order. Everything premised on matching the published table is gone.

1. **Rerun S4 on Seven Bridges from current `main`.** Every number quoted in
   these docs predates the 2026-08-04 HCHS/SOL fix (`24396404`) and should be
   re-derived before it is trusted. `./hv_dataqc/sb_scripts/run_s4_report.sh`,
   no args.
2. **Build the non-measurement extraction — this is the real work.** ~300 spec
   files are invisible to the generator, producing 51 empty rows of 149, because
   variable identity is keyed on `observation_type` and Condition /
   DrugExposure / Procedure / Demography specs don't have one. The extraction
   rules are settled in
   [`SPEC_SOURCED_S4_DESIGN.md`](SPEC_SOURCED_S4_DESIGN.md)
   §"Non-measurement classes" — designed, not built. **Start here.**
3. **Make the generator report matched-but-empty template rows**, and add the
   config-reconciliation test described in
   [`SPEC_SOURCED_S4_DESIGN.md`](SPEC_SOURCED_S4_DESIGN.md) §"Known defects". A
   row that is silently blank because its class was never parsed took a full
   session to notice once. With the published table no longer serving as a
   check, nothing else would catch it.
4. **Fix the silently-undercounted N** — §"Known defects" defect 1. It publishes
   a plausible-looking wrong number rather than a blank, which makes it the
   highest-risk item on this list.

The three defects in §"Known defects" are recorded but unfixed; 2 and 3 there
affect S5 output today.

## What's here

Four things, and that is the whole directory.

- `spec_phv_report.py` — the spec-sourced S4/S5 generator. Design and rationale
  in [`SPEC_SOURCED_S4_DESIGN.md`](SPEC_SOURCED_S4_DESIGN.md).
- `config/s4_layout.yaml` — canonical cohort columns and template row order.
- `spec_code_fixes_20260803.tsv` — the six concept-code corrections, in the form
  handed to the spec owner.
- `history/` — completed work kept for its reasoning. None of it is required
  reading; consult it when something current looks arbitrary.
  - `S1_LABEL_SOURCE_MIGRATION.md` — the `harmonized_vars.tsv` → Table S1
    migration.
  - `SPEC_CODE_CORRECTIONS_20260803.md` — per-code rationale for the six
    concept-code fixes, and what was deliberately *not* changed.
  - `S4_COUNT_INVESTIGATION_REMOVED.md` — what the deleted count investigation
    concluded, and how to restore it if the published table ever needs auditing.

## Running S4

On Seven Bridges (a local run is not a substitute — only 5 cohorts have dbGaP
caches locally):

```bash
./hv_dataqc/sb_scripts/run_s4_report.sh      # no args, idempotent
```

Output lands in `/sbgenomics/workspace/S4-output-files/`.

## S4 and S5 cover different cohorts — say so on delivery

**S4 has 9 cohort columns. S5 covers 11.** LTRC and SPIROMICS have transform
specs (19 and 23 files) and appear in S5's `KNOWN_COHORTS`, but they have no S4
column, so their variables contribute nothing to S4 and are dropped without a
message. The curator was asked whether they should be added and did not say
they should, so the current behavior stands.

**When S5 is delivered, tell the curator which cohorts it includes, and that the
set is not the same as S4's.** The difference is invisible in either artifact —
S4 simply has no column, and nothing in the output says a cohort was skipped.
Two tables in one supplement covering different cohort sets is exactly the kind
of thing that gets noticed after publication.

There is one loose end worth knowing: because the two lists are maintained
independently (`config/s4_layout.yaml` vs `run_s5_report.sh:95`), nothing checks
them against each other or against the ingest dirs on disk. A cohort added to
the specs appears in neither table until someone edits both by hand.
