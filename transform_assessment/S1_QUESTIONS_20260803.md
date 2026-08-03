# Table S1 — open questions (2026-08-03)

Draft to send after the next S4 run, so the questions can reference what the
regenerated sheet actually shows. Everything settleable without the curator has
been settled; what's left is genuinely hers.

Table S4 labels each row by looking up the spec's `observation_type` concept
code in S1, falling back to the spec's filename. Variables below reached no
template row, so they appear under the note row at the bottom of the sheet
rather than in the table proper.

Of 127 distinct concept codes across the specs, 121 resolve cleanly.

## 1. `alpha1_antitrypsin` — in scope, or not?

LTRC emits `OBA:2050075` (Alpha-1-antitrypsin in serum). The code is correct
and is a permissible BDCHM value, but S1 has no row for it, so S4 can only
label it with the raw filename.

It is currently omitted from the sheet entirely: LTRC is the only cohort with
it, and LTRC has no S4 column. Four other LTRC-only variables are omitted for
the same reason — `asthma_md`, `bronchitis`, `bronchitis_md`,
`pulmonary_fibrosis`.

**Which raises the prior question: should LTRC and SPIROMICS be columns in
S4?** They have transform specs but no columns in the template. If they should
be included, the layout needs two more cohorts and these five variables need S1
rows. If not, they stay omitted and this is closed.

## 2. Seven variables whose `var_name` differs from S1

Each is one variable spelled two ways. No cohort uses both spellings, and the
S1 spelling covers the majority — but the cohorts on the left don't match S1,
so their counts don't join the S1-labeled row.

| Spec `var_name` | Cohorts | S1 `var_name` | S1 label |
|---|---|---|---|
| `hist_mi` | CHS | `hist_my_inf` | History of myocardial infarction |
| `hist_heart_failure` | CHS | `hist_hrtfail` | History of heart failure |
| `hist_hrt_failure` | COPDGene | `hist_hrtfail` | History of heart failure |
| `hist_heart_disease` | CHS | `hist_hrtdis` | History of heart disease |
| `hist_coronary_bypass` | CHS | `hist_cor_bypg` | History of coronary artery bypass graft |
| `history_cvd` | CHS | `hist_cvd` | History of cardiovascular disease |
| `taking_non_statin_medication` | CHS, MESA | `tak_nstat_med` | Taking non statin medication |

`hypertension` (ARIC, FHS, SPIROMICS) vs S1's `hyperten` was in this list and
is now resolved — it matches through the template.

**Recommend:** rename the specs to match S1 rather than adding alternate names
to S1 — S1 is the published artifact and shouldn't carry duplicates. Worth
settling the direction now, since the spec files are being revised separately.

Worth a sanity check that each left-hand variable really is the same concept as
its S1 partner. We verified no cohort uses both spellings, which rules out
their being distinct variables, but the semantic match is a judgment call.

## 3. Thirteen variables in the specs with no S1 row

A scope decision more than a mapping. They're in the transform specs but absent
from S1, so they're either missing rows or deliberately out of scope.

**Conditions**
| Variable | Cohorts |
|---|---|
| `chd` | CARDIA, JHS, MESA, SPIROMICS |
| `chf` | CARDIA, MESA, SPIROMICS |
| `chr_bronchitis` | CARDIA, HCHS, MESA, SPIROMICS, WHI |
| `emphysema` | CARDIA, COPDGene, LTRC, MESA, SPIROMICS |
| `stroke_isch_atk` | CARDIA, COPDGene |
| `hist_cor_art_dis` | COPDGene |
| `blood_clots` | COPDGene |

`stroke_isch_atk` and `hist_cor_art_dis` are *not* duplicates of S1's `stroke`
and `hist_cor_angio` — the cohorts that have them use both, against different
source variables, so they're genuinely separate concepts.

**Medication classes** — `tak_adrenergics` (COPDGene),
`tak_antihypertensives` (COPDGene), `tak_cort_steroid_oral` (COPDGene, MESA),
`tak_cort_steroid_resp` (COPDGene). S1 has `tak_steroid` but not the
oral/respiratory split.

**`med_use`** (FHS) — 82 source variables. Looks like a general medication-use
rollup rather than a single harmonized variable; likely out of scope.

**`Interleukin 18 in blood`** (FHS) — was added to S1 in the last review round
and resolves correctly, but has no S4 template row. Add the row, or confirm
it's out of scope for S4.

## Also in the appendix, not for the curator

Six structural entries — `participant`, `person`, `visit`, `research_study`,
`researchstudy`, `demography` — derive non-Observation BDCHM classes and were
never harmonized variables. They need a filter on our side, not a decision from
her. `research_study` vs `researchstudy` is our own naming inconsistency.

## Not asking about

Education level and the FHS fasting-lipid codes both came up this round and
neither affects S4 — they're value-level modeling questions for S6. Noted so
they don't look overlooked.
