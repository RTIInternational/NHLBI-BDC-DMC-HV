# CARDIA Final Reviewer Packet — 2026-05-31

## Coverage

Current CARDIA ingest inventory is 92 YAML files under `C:\SourceCode\BDC-DMC-CROSSTESTING-LOCAL\NHLBI-BDC-DMC-HV\priority_variables_transform\CARDIA-ingest`; `.asthma.yaml.swp` is ignored. Reconciled against the fresh blind ledger, prior consolidated report, re-review summary, current transforms, local CARDIA dbGaP cache, visit cache, and local MONDO terminology cache. No YAML edits were made.

## Final Confirmed Findings

| Priority | File | Final issue | Evidence to confirm | Recommended action | Confidence | Reviewer | Source alignment |
|---|---|---|---|---|---|---|---|
| P0 | insulin_blood.yaml | Insulin observations emit no measured value because every `value_quantity` block is commented out. | Current YAML has only `observation_type` and `method_type`; dbGaP PHVs `phv00113698`, `phv00117565`, and `phv00117566` are numeric insulin variables with `uU/ML` units. | Restore guarded `value_quantity` mappings and document unit/conversion policy. | Confirmed | Engineer | Both reviews |
| P0 | tak_statin.yaml | Missing sentinel `M` and multiple non-statin drugs can be emitted as statin/lipid exposure. | `phv00117471` is free-text cholesterol medication name; current YAML maps lowercased `"m"` to `RxCUI:6472` while `exposure_status` nulls raw `M`. Free-text branches also include non-statins/non-lipid drugs under the statin file. | Null `M`/unknown before matching; split true statins from non-statin lipid drugs and unrelated drugs. | Confirmed | Curator | Both reviews |
| P0 | potassium.yaml | Dietary potassium intake is modeled as blood potassium. | `phv00117627` and `phv00117741` are FFQ potassium variables in `MG`; current YAML uses `method_type: blood assay` and `unit: mmol/L`. | Remap as dietary potassium intake with FFQ method and milligram intake unit, or remove from blood-potassium scope. | Confirmed | Curator | Re-review confirmed |
| P0 | cig_smok.yaml | Year 15 smoking status uses a household smoker count instead of participant smoking status. | Current pht001818 block uses `phv00120073`; dbGaP defines it as `# CIGARETTE SMOKERS YOU LIVE WITH`, integer 0-20. Same table has `phv00120080` = `SMOKING STATUS`. | Replace Year 15 status source with verified `F10SMOKE` coding; model `F10LVHME` separately only if environmental smoke exposure is in scope. | Confirmed | Anne | Fresh-only |
| P0 | emphysema.yaml | Emphysema conditions use the wrong MONDO concept. | Current YAML uses `MONDO:0004848`; local MONDO cache labels it `ulcerative stomatitis`. `MONDO:0004849` is locally labeled `pulmonary emphysema`; source PHVs are emphysema variables. | Replace with a verified pulmonary emphysema concept. | Confirmed | Curator | Re-review confirmed |
| P0 | chr_bronchitis.yaml; emphysema.yaml | `8 = Not sure` is mapped to `ABSENT` in respiratory condition status mappings. | Current Y7/Y10/Y15 mappings include `'8': ABSENT`; local dbGaP var reports show code `8` as `Not sure` for chronic bronchitis and emphysema variables. | Map `8` to `UNKNOWN` or null; preserve `1 = ABSENT`, `2 = PRESENT`. | Confirmed | Engineer | Both reviews |
| P0 | alcohol_servings.yaml | Derived total alcohol observations emit unit-only quantities; Year 0 also emits beer/wine/liquor and total under the same observation type. | Current total blocks have `value_decimal` commented out while `unit` remains; first three Year 0 blocks each use `OMOP:35609491` for beverage components. | Restore guarded total expressions or remove empty total shells; decide component-specific vs total output. | Confirmed | Engineer | Both reviews |
| P0 | hyperten.yaml; angina.yaml; hist_my_inf.yaml; stroke.yaml | `age_at_condition_start` uses bare PHVs inside `case()` guards, so status variables are not interpolated. | Current expressions include patterns such as `case((phv00114385 == 2, {phv00114386} * 365))`; same pattern appears in multiple condition files. | Replace bare guard PHVs with braced references and sweep all `case((phv` occurrences. | Confirmed | Engineer | Re-review confirmed |
| P1 | hyperten.yaml | The Year 2 HBP table block is anchored to `CARDIA YEAR 0`. | pht001606 is `B2F09HBP`; `phv00114385` is `B09HBPG1`. Current associated visit uses `:CARDIA YEAR 0`. | Change the pht001606 hypertension block to `CARDIA YEAR 2`. | Confirmed | Engineer | Fresh-only |
| P1 | cause_of_death.yaml | Legacy raw death-cause mapping conflicts with structured Person cause-of-death mapping. | `cause_of_death.yaml` maps `phv00121685` directly to `Person.cause_of_death`; `person.yaml` uses structured `CauseOfDeath` objects from ICD-9 fields in DEATH06. | Remove/deprecate the legacy transform or convert it to the structured pattern after verifying pht001872 intent. | High | Architect | Re-review confirmed |
| P1 | tak_diuret.yaml | A weight-loss behavior question is modeled as therapeutic diuretic exposure. | `phv00119422` is `DOUBLE DIURETICS TO LOSE WEIGHT`; current YAML emits `ATC:C03` DrugExposure when code 2 is present. | Remove from therapeutic diuretic exposure, or model explicitly as a medication misuse/behavior item if in scope. | High | Anne | Re-review confirmed |
| P1 | tak_insulin.yaml | A composite “insulin or oral drugs” question maps to insulin only. | `phv00118386` is `CURRENTLY TAKING INSULIN OR ORAL DRUGS?`; current YAML emits only `MeSH:D007328`. | Use a broader diabetes-medication exposure or split only if a source variable distinguishes insulin from oral agents. | High | Anne | Re-review confirmed |

## Anne Review Required

| Priority | File | Question | Evidence | Decision needed |
|---|---|---|---|---|
| P0 | stroke.yaml | What verified concept should represent combined “stroke or TIA” CARDIA sources? | Source PHVs in current blocks describe `STROKE OR TIA`; current concept is `HP:0001681`, also used by angina, but no local HPO cache was available for final replacement verification. | Choose and verify the harmonized stroke/TIA concept before remediation. |
| P0 | glucose_bld.yaml | Should the Year 7 glucose source unit be treated as a dbGaP unit typo? | `phv00117552` data dict says `ug/dL`, but variable name/ranges are glucose-like; current YAML converts `ug/dL` to `mg/dL`, which would downscale if the unit is taken literally. | Decide whether to override the published unit and document rationale. |
| P1 | albumin_urine.yaml | What is the true source unit for urinary albumin? | dbGaP omits a unit for `FL1UALB`; ratio formula evidence supports one interpretation, but prior reviewers flagged plausibility concerns. | Confirm source unit and conversion policy before fixing. |
| P1 | blood_pressure.yaml | Should CARDIA BP coverage expand beyond current Y0/Y5 sources, and which BP series should be canonical? | Fresh review found standard exam SBP/DBP variables in additional CARDIA tables; current file covers only Y0 and pht001650. | Select standard exam averages vs ancillary BP sources and define repeat/protocol handling. |
| P1 | spirometry.yaml | Should raw spirometry trials be retained or summarized as best/preferred measures? | Current Y2/Y5/Y10 sets emit many FVC/FEV1 observations with identical concepts and no trial discriminator. | Decide best-of-N, raw-trial retention, and pre/post-bronchodilator policy. |
| P1 | pad.yaml | Should PAD endpoint variables alone drive Condition rows, with subcriteria represented as evidence? | Current pht001869/pht001871 blocks emit many `MONDO:0005386` rows from endpoint and subcriterion PHVs. | Decide endpoint-vs-evidence architecture for PAD and related event-review tables. |
| P1 | visit.yaml | What is the CARDIA policy for standard Y20/Y25/Y30 visits versus HeartGO/GENEVA substudy visits? | Current visit.yaml has standard visits through Y15 plus HeartGO/GENEVA Y20 ID spaces; Y25/Y30 are absent. | Confirm transform scope and ID-space strategy before broad visit expansion. |

## Stale / Unsupported Prior Findings to Ignore

| Prior finding | Resolution | Evidence |
|---|---|---|
| `chf.yaml` uses a broad heart-disease concept instead of CHF. | Ignore as false. | Local MONDO cache labels `MONDO:0005009` as `congestive heart failure`. |
| `chr_bronchitis.yaml` uses generic bronchitis rather than chronic bronchitis. | Ignore as false. | Local MONDO cache labels `MONDO:0005607` as `chronic bronchitis`. |
| `fibrin.yaml` has the `phv00117552` glucose-like unit issue. | Ignore as misfiled. | Current `glucose_bld.yaml` uses `phv00117552`; dbGaP defines it as `DL7GLU`, Year 7 glucose. |
| Synthetic `CARDIA MEDICAL HISTORY` / `CARDIA HOSPITALIZATIONS DIAGNOSIS` visit labels are orphaned. | Ignore as stale. | Current `visit.yaml` defines both synthetic visit names with UUID patterns. |
| CARDIA visit.yaml lacks required names/uuid pattern. | Ignore as stale. | Current visit blocks include `name` and deterministic `uuid5` IDs. |
| DEXA body-weight no-conversion is a bug solely because adjacent weight blocks convert pounds. | Ignore unless Anne finds contrary source documentation. | Prior report itself verified DEXA weight source as kg; visual inconsistency alone is not a defect. |
| Broad OBA/OMOP “verify this CURIE” notes without local terminology evidence. | Do not carry into remediation tickets. | Final packet keeps only locally verified terminology defects or moves unresolved concept choices to Anne review. |

## Reviewer Checklist

- Confirm the 12 final findings against the current CARDIA YAML before ticketing.
- For each remediation ticket, cite the exact PHV/PHT source evidence listed here.
- Do not remediate stroke/TIA, Year 7 glucose units, urinary albumin units, BP expansion, spirometry trial handling, PAD evidence modeling, or Y20/Y25/Y30 visits until Anne decides the policy question.
- Treat stale findings above as closed unless new evidence is produced.
- After fixes, run all HV-Lint phases and add lint-gap triage entries for deterministic defects not currently caught.

## Reconciliation Notes

Fresh blind findings were promoted when current YAML and dbGaP metadata directly supported them. Prior findings were retained only when re-review or direct inspection confirmed they are still live. CURIE findings were included only when locally verified; stroke/TIA remains Anne-required because the replacement concept was not locally verified in this pass. Coverage-only and age-at-observation gaps were mostly excluded unless they caused empty observations, wrong visits, or duplicated indistinguishable clinical rows. No participant-level data was used or included.
