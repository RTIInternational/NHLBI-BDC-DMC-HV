# CHS Semantic Validator Summary v2026-06-19

**Generated:** 2026-06-19
**Mapreview CSV:** `CHS_curie_mapreview.csv`
**Review MD:** `CHS_Semantic_Review_Final-Reviewer-2026-05-31.md`

---

## Overview

| Metric | Count |
| :---- | ----: |
| Total rows in mapreview CSV | 1581 |
| Admin variables skipped | 0 |
| Substantive variables reviewed | 1581 |
| Unique CURIEs validated | 121 |
| Unique YAML files referenced | 77 |
| Final Confirmed Findings rows | 35 |
| Anne Review Required rows | 5 |

## YAML Spot-Check

| Result | Count |
| :---- | ----: |
| Matches (✓) | 1178 |
| Mismatches (⚠) | 133 |
| Not checked (admin / no YAML) | 270 |

**133 mismatch(es) require correction:**

| Variable | YAML File | CSV CURIE | YAML CURIE |
| :---- | :---- | :---- | :---- |
| GEND01 | demography.yaml | `OMOP:45880900` | `[10 mappings]` |
| ROTHER01 | demography.yaml | `OMOP:45880900` | `[10 mappings]` |
| HISP01 | demography.yaml | `OMOP:45880900` | `[10 mappings]` |
| RACE01 | demography.yaml | `OMOP:45880900` | `[10 mappings]` |
| FAST30 | hdl.yaml | `OMOP:4041720` | `[3 mappings]` |
| HDL44 | hdl.yaml | `OMOP:4041720` | `[3 mappings]` |
| STKTYPE | stroke.yaml | `HP:0002140` | `[50 mappings]` |
| STKTYPE | stroke.yaml | `MONDO:0013792` | `[50 mappings]` |
| ACED06 | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| ACED06 | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| ACED06 | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| ANYACE | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| ACED06 | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| ACED06 | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| ACED06 | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| ACED06 | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| ACED06 | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| ACED06 | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| ACED06 | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| ACED06 | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| ACED06 | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| aced | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| aced2 | tak_aceinhib.yaml | `ATC:C09BA` | `ATC:C09A` |
| ALPHAD06 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| ALPHAD06 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| ALPHAD06 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| ALPHAD06 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| ALPHAD06 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| ALPHAD06 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| ALPHAD06 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| ALPHAD06 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| ALPHAD06 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| ALPHAD06 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| ALPHAD06 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| ALPHAD06 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| alphad | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| alphad2 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| BETA11 | tak_betablk.yaml | `RxCUI:151549` | `[2 mappings]` |
| BETA11 | tak_betablk.yaml | `RxCUI:151890` | `[2 mappings]` |
| BETA11 | tak_betablk.yaml | `RxCUI:152413` | `[2 mappings]` |
| BETA11 | tak_betablk.yaml | `RxCUI:203344` | `[2 mappings]` |
| betad | tak_betablk.yaml | `ATC:C07D` | `[2 mappings]` |
| AMLOD06 | tak_calchanblk.yaml | `RxCUI:17767` | `NDFRT:N0000175421` |
| DLTIR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| DLTSR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| VERIR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| VERSR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| AMLOD06 | tak_calchanblk.yaml | `RxCUI:17767` | `NDFRT:N0000175421` |
| DLTIR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| DLTSR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| VERIR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| VERSR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| AMLOD06 | tak_calchanblk.yaml | `RxCUI:17767` | `NDFRT:N0000175421` |
| DLTIR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| DLTSR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| VERIR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| VERSR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| AMLOD06 | tak_calchanblk.yaml | `RxCUI:17767` | `NDFRT:N0000175421` |
| DLTIR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| DLTSR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| VERIR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| VERSR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| AMLOD06 | tak_calchanblk.yaml | `RxCUI:17767` | `NDFRT:N0000175421` |
| DLTIR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| DLTSR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| VERIR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| VERSR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| AMLOD06 | tak_calchanblk.yaml | `RxCUI:17767` | `NDFRT:N0000175421` |
| DLTIR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| DLTSR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| VERIR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| VERSR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| AMLOD06 | tak_calchanblk.yaml | `RxCUI:17767` | `NDFRT:N0000175421` |
| DLTIR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| DLTSR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| VERIR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| VERSR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| AMLOD06 | tak_calchanblk.yaml | `RxCUI:17767` | `NDFRT:N0000175421` |
| DLTIR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| DLTSR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| VERIR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| VERSR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| AMLOD06 | tak_calchanblk.yaml | `RxCUI:17767` | `NDFRT:N0000175421` |
| DLTIR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| DLTSR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| VERIR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| VERSR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| AMLOD06 | tak_calchanblk.yaml | `RxCUI:17767` | `NDFRT:N0000175421` |
| DLTIR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| DLTSR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| VERIR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| VERSR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| AMLOD06 | tak_calchanblk.yaml | `RxCUI:17767` | `NDFRT:N0000175421` |
| DLTIR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| DLTSR06 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| VERIR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| VERSR06 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| ccb | tak_calchanblk.yaml | `ATC:C08` | `NDFRT:N0000175421` |
| amlod2 | tak_calchanblk.yaml | `RxCUI:17767` | `NDFRT:N0000175421` |
| dltir2 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| dltsr2 | tak_calchanblk.yaml | `RxCUI:3443` | `NDFRT:N0000175421` |
| verir2 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| versr2 | tak_calchanblk.yaml | `RxCUI:11170` | `NDFRT:N0000175421` |
| VASO06 | tak_vasodil.yaml | `ATC:C01D` | `ATC:C04` |
| VASOD06 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C04` |
| VASO06 | tak_vasodil.yaml | `ATC:C01D` | `ATC:C04` |
| VASOD06 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C04` |
| VASO06 | tak_vasodil.yaml | `ATC:C01D` | `ATC:C04` |
| VASOD06 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C04` |
| VASO06 | tak_vasodil.yaml | `ATC:C01D` | `ATC:C04` |
| VASOD06 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C04` |
| VASO06 | tak_vasodil.yaml | `ATC:C01D` | `ATC:C04` |
| VASOD06 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C04` |
| VASO06 | tak_vasodil.yaml | `ATC:C01D` | `ATC:C04` |
| VASOD06 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C04` |
| VASO06 | tak_vasodil.yaml | `ATC:C01D` | `ATC:C04` |
| VASOD06 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C04` |
| VASO06 | tak_vasodil.yaml | `ATC:C01D` | `ATC:C04` |
| VASOD06 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C04` |
| VASO06 | tak_vasodil.yaml | `ATC:C01D` | `ATC:C04` |
| VASOD06 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C04` |
| VASO06 | tak_vasodil.yaml | `ATC:C01D` | `ATC:C04` |
| VASOD06 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C04` |
| VASO06 | tak_vasodil.yaml | `ATC:C01D` | `ATC:C04` |
| VASOD06 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C04` |
| VASO06 | tak_vasodil.yaml | `ATC:C01D` | `ATC:C04` |
| VASOD06 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C04` |
| vaso | tak_vasodil.yaml | `ATC:C01D` | `ATC:C04` |
| vasod | tak_vasodil.yaml | `ATC:C02L` | `ATC:C04` |
| vaso2 | tak_vasodil.yaml | `ATC:C01D` | `ATC:C04` |
| vasod2 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C04` |
| FAST30 | triglyc_bld.yaml | `OMOP:4041722` | `[3 mappings]` |
| TRIG44 | triglyc_bld.yaml | `OMOP:4041722` | `[3 mappings]` |

## Agent Coverage by Entity Type

| Entity Type | Unique vars | MONDO | HPO | OMOP/LOINC | No suggestion |
| :---- | ----: | ----: | ----: | ----: | ----: |
| Condition | 51 | 51 | 0 | 0 | 0 |
| Condition (HPO) | 11 | 0 | 11 | 0 | 0 |
| Measurement | 315 | 0 | 0 | 315 | 0 |
| Person | 3 | 0 | 0 | 0 | 3 |
| ValueEnum | 16 | 0 | 0 | 0 | 16 |
| **Total** | **396** | | | | **19** |

**Coverage: 377/396 unique variable-slot pairs have at least one agent suggestion (95%).**

## Agent vs CSV CURIE Alignment

Agent suggestions differ from the current CSV CURIE in **354** variable-slot pair(s).

### Potential Improvements (325 — YAML confirms CSV, agent suggests different)

These cases have a YAML-confirmed CSV CURIE but the agent suggests a different concept.
Review whether the agent suggestion is more specific or accurate.

| Variable | Slot | Entity Type | CSV / YAML CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| ANG37 | condition_concept | Condition | `HP:0001681` | `MONDO:0006576` |
| ASTHAG57 | condition_concept | Condition | `MONDO:0004979` | `MONDO:0011743` |
| ASTHDR57 | condition_concept | Condition | `MONDO:0004979` | `MONDO:0010922` |
| ASTHH57 | condition_concept | Condition | `MONDO:0004979` | `MONDO:0019355` |
| ASTHST57 | condition_concept | Condition | `MONDO:0004979` | `MONDO:0020121` |
| ATHH07 | condition_concept | Condition | `MONDO:0004979` | `MONDO:0019355` |
| ATHST07 | condition_concept | Condition | `MONDO:0004979` | `MONDO:0020121` |
| ATHT07 | condition_concept | Condition | `MONDO:0004979` | `MONDO:0011743` |
| BP07 | condition_concept | Condition | `HP:0000822` | `MONDO:0005044` |
| BP37 | condition_concept | Condition | `HP:0000822` | `MONDO:0005044` |
| BP39 | condition_concept | Condition | `HP:0000822` | `MONDO:0005044` |
| HIBP01 | condition_concept | Condition | `HP:0000822` | `MONDO:0005044` |
| HIBP29 | condition_concept | Condition | `HP:0000822` | `MONDO:0005044` |
| HIBP59 | condition_concept | Condition | `HP:0000822` | `MONDO:0005044` |
| NEWCHF29 | condition_concept | Condition | `MONDO:0005009` | `MONDO:0018684` |
| NEWCHF39 | condition_concept | Condition | `MONDO:0005009` | `MONDO:0018684` |
| NEWCHF59 | condition_concept | Condition | `MONDO:0005009` | `MONDO:0018684` |
| NEWSTK29 | condition_concept | Condition | `HP:0001297` | `MONDO:0003040` |
| NEWSTK39 | condition_concept | Condition | `HP:0001297` | `MONDO:0003040` |
| NEWSTK59 | condition_concept | Condition | `HP:0001297` | `MONDO:0003040` |
| STK37 | condition_concept | Condition | `HP:0001297` | `MONDO:0005098` |
| STKBASE | condition_concept | Condition | `HP:0001297` | `MONDO:1060198` |
| STROKE01 | condition_concept | Condition | `HP:0001297` | `MONDO:0005098` |
| THROMB | condition_concept | Condition | `HP:0002625` | `MONDO:0026777` |
| THROMB29 | condition_concept | Condition | `HP:0002625` | `MONDO:0043361` |
| THROMB57 | condition_concept | Condition | `HP:0002625` | `MONDO:0043361` |
| THROMB59 | condition_concept | Condition | `HP:0002625` | `MONDO:0043361` |
| CLTLEG07 | condition_concept | Condition (HPO) | `MONDO:0005399` | `HP:0002625` |
| CLTLUN | condition_concept | Condition (HPO) | `MONDO:0005279` | `HP:0002204` |
| CLTLUN07 | condition_concept | Condition (HPO) | `MONDO:0005279` | `HP:0002204` |
| INCSTRK | condition_concept | Condition (HPO) | `HP:0001297` | `HP:0034732` |
| NEWANG29 | condition_concept | Condition (HPO) | `HP:0001681` | `HP:0033678` |
| NEWANG39 | condition_concept | Condition (HPO) | `HP:0001681` | `HP:0033678` |
| NEWANG59 | condition_concept | Condition (HPO) | `HP:0001681` | `HP:0033678` |
| NEWMI29 | condition_concept | Condition (HPO) | `MONDO:0005068` | `HP:6001239` |
| NEWMI39 | condition_concept | Condition (HPO) | `MONDO:0005068` | `HP:6001239` |
| NEWMI59 | condition_concept | Condition (HPO) | `MONDO:0005068` | `HP:6001239` |
| NEWTIA39 | condition_concept | Condition (HPO) | `MONDO:0005264` | `HP:0001773` |
| AG50WT59 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| AGE01 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:56068-0` |
| AGE01 | observation_type | Measurement | `OMOP:4282779` | `LOINC:56068-0` |
| AGEBL | observation_type | Measurement | `OBA:2050068` | `LOINC:56847-7` |
| AGEBL | observation_type | Measurement | `OMOP:4282779` | `LOINC:56847-7` |
| AGEY10 | observation_type | Measurement | `OMOP:35609491` | `LOINC:30525-0` |
| AGEY10 | observation_type | Measurement | `OMOP:4282779` | `LOINC:30525-0` |
| AGEY11 | observation_type | Measurement | `OMOP:35609491` | `LOINC:30525-0` |
| AGEY11 | observation_type | Measurement | `OMOP:4282779` | `LOINC:30525-0` |
| AGEY4 | observation_type | Measurement | `OMOP:35609491` | `LOINC:56847-7` |
| AGEY4 | observation_type | Measurement | `OMOP:4282779` | `LOINC:56847-7` |
| AGEY5 | observation_type | Measurement | `OBA:2050068` | `LOINC:56847-7` |
| AGEY5 | observation_type | Measurement | `OMOP:4282779` | `LOINC:56847-7` |
| AGEY6 | observation_type | Measurement | `OMOP:35609491` | `LOINC:56847-7` |
| AGEY6 | observation_type | Measurement | `OMOP:4282779` | `LOINC:56847-7` |
| AGEY7 | observation_type | Measurement | `OMOP:35609491` | `LOINC:56847-7` |
| AGEY7 | observation_type | Measurement | `OMOP:4282779` | `LOINC:56847-7` |
| AGEY8 | observation_type | Measurement | `OMOP:4282779` | `LOINC:56847-7` |
| AGEY8 | observation_type | Measurement | `OBA:1001087` | `LOINC:56847-7` |
| AGEY9 | observation_type | Measurement | `OBA:2050068` | `LOINC:56847-7` |
| AGEY9 | observation_type | Measurement | `OMOP:4282779` | `LOINC:56847-7` |
| AGE_S1 | observation_type | Measurement | `OBA:2040171` | `LOINC:30525-0` |
| ALB44 | observation_type | Measurement | `OBA:2050068` | `LOINC:100158-5` |
| ALCOH | observation_type | Measurement | `OMOP:35609491` | `LOINC:9800-4` |
| AVGHR46 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| BEAT14 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| BLSPO269 | observation_type | Measurement | `OBA:2045443` | `LOINC:64103-5` |
| BMI | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| CACSCORE | observation_type | Measurement | `OMOP:42872742` | `LOINC:76640-2` |
| CCA_FWME | observation_type | Measurement | `OMOP:4138462` | `LOINC:20073-3` |
| CHOLADJ | observation_type | Measurement | `OBA:VT0000180` | `LOINC:96913-9` |
| CRPBLADJ | observation_type | Measurement | `OMOP:4208414` | `LOINC:16503-5` |
| CRPYR5 | observation_type | Measurement | `OMOP:4208414` | `LOINC:16503-5` |
| CYSTATC | observation_type | Measurement | `OBA:2052375` | `LOINC:89066-5` |
| DDIMER | observation_type | Measurement | `OMOP:37393605` | `LOINC:64103-5` |
| D_DIMER | observation_type | Measurement | `OMOP:37393605` | `LOINC:55083-0` |
| EXSPO269 | observation_type | Measurement | `OBA:2045443` | `LOINC:59408-5` |
| F744 | observation_type | Measurement | `OBA:2041535` | `LOINC:10395-2` |
| F7NC | observation_type | Measurement | `OBA:2041535` | `LOINC:10395-2` |
| F844 | observation_type | Measurement | `OBA:2041536` | `LOINC:10395-2` |
| FAST30 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:57123-2` |
| FIB44 | observation_type | Measurement | `OBA:0000061` | `LOINC:3255-7` |
| FMAX141 | observation_type | Measurement | `OMOP:4138462` | `LOINC:52492-6` |
| FMAX155 | observation_type | Measurement | `OMOP:4138462` | `LOINC:97490-7` |
| FMAX541 | observation_type | Measurement | `OMOP:4138462` | `LOINC:52492-6` |
| FMAX555 | observation_type | Measurement | `OMOP:4138462` | `LOINC:97490-7` |
| FRUITF25 | observation_type | Measurement | `OMOP:21493059` | `LOINC:66681-8` |
| GLU44 | observation_type | Measurement | `OMOP:4156660` | `LOINC:63382-6` |
| GRADE01 | observation_type | Measurement | `OMOP:4022643` | `LOINC:72081-3` |
| HDL44 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:105517-7` |
| HEMATO23 | observation_type | Measurement | `OBA:2045381` | `LOINC:4544-3` |
| HEMOGL23 | observation_type | Measurement | `OBA:2060175` | `LOINC:718-7` |
| HIP13 | observation_type | Measurement | `OBA:1000032` | `LOINC:62409-8` |
| HRATE42 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| HRATEA17 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| HRATEB17 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| HRSWD02 | observation_type | Measurement | `OBA:2040171` | `LOINC:65578-7` |
| HRSWE02 | observation_type | Measurement | `OBA:2040171` | `LOINC:65578-7` |
| ICAM1 | observation_type | Measurement | `OMOP:4284103` | `LOINC:64103-5` |
| ICA_FWME | observation_type | Measurement | `OMOP:4138462` | `LOINC:60949-5` |
| IL6BL | observation_type | Measurement | `OBA:2052890` | `LOINC:51051-1` |
| INCOME59 | observation_type | Measurement | `OMOP:4076114` | `LOINC:9347-6` |
| INS44 | observation_type | Measurement | `OBA:2060174` | `LOINC:64103-5` |
| Individual_ID | observation_type | Measurement | `OMOP:42872742` | `LOINC:97851-0` |
| K44 | observation_type | Measurement | `OBA:VT0002668` | `LOINC:57379-0` |
| LDLADJ | observation_type | Measurement | `OBA:VT0000181` | `LOINC:61132-7` |
| LPPLA2 | observation_type | Measurement | `OMOP:3041450` | `LOINC:64103-5` |
| LPPLA2AC | observation_type | Measurement | `OMOP:36305170` | `LOINC:64103-5` |
| NMAX141 | observation_type | Measurement | `OMOP:4138462` | `LOINC:52492-6` |
| NMAX155 | observation_type | Measurement | `OMOP:4138462` | `LOINC:35998-4` |
| NMAX541 | observation_type | Measurement | `OMOP:4138462` | `LOINC:52492-6` |
| NMAX555 | observation_type | Measurement | `OMOP:4138462` | `LOINC:35998-4` |
| PLATE23 | observation_type | Measurement | `OMOP:4267147` | `LOINC:777-3` |
| POST27 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| PRE27 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| PSTEN141 | observation_type | Measurement | `OMOP:43021859` | `LOINC:52492-6` |
| PSTEN241 | observation_type | Measurement | `OMOP:43020498` | `LOINC:52492-6` |
| PULSE21 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| QRSINT42 | observation_type | Measurement | `OBA:1001086` | `LOINC:8632-2` |
| SMOKE | observation_type | Measurement | `OMOP:4282779` | `LOINC:111839-7` |
| SMOKE29 | observation_type | Measurement | `OMOP:4282779` | `LOINC:63900-5` |
| SMOKE59 | observation_type | Measurement | `OMOP:4282779` | `LOINC:63900-5` |
| SODIUM65 | observation_type | Measurement | `OMOP:606729` | `LOINC:12907-2` |
| SPLT9069 | observation_type | Measurement | `OBA:2045443` | `LOINC:59408-5` |
| STDPUL16 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| STHT13 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| SUPPUL16 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| TRIG44 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:12951-0` |
| VEGF25 | observation_type | Measurement | `OMOP:4042886` | `LOINC:65486-3` |
| WAIST13 | observation_type | Measurement | `OBA:1001085` | `LOINC:8280-0` |
| WBLD23 | observation_type | Measurement | `OBA:VT0000217` | `LOINC:67750-0` |
| WEIGHT13 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| WGT50 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| WGT5008 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| WGT5058 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| YEAR | observation_type | Measurement | `OMOP:42872742` | `LOINC:89066-5` |
| YRNA | observation_type | Measurement | `OMOP:606729` | `LOINC:12907-2` |
| aavbnbh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| aavbnoh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| aavbrbh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| aavbroh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ahiov50 | observation_type | Measurement | `OMOP:37396400` | `LOINC:69990-0` |
| beer15 | observation_type | Measurement | `OMOP:35609491` | `LOINC:61544-3` |
| bmi_s2 | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| cai0p | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cai4p | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cai4pa | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnba | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnba2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnba3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnba4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnba5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnbp | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnbp2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnbp3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnbp4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnbp5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnoa | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnoa2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnoa3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnoa4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnoa5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnop | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnop2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnop3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnop4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardnop5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrba | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrba2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrba3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrba4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrba5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrbp | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrbp2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrbp3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrbp4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrbp5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardroa | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardroa2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardroa3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardroa4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardroa5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrop | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrop2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrop3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrop4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| cardrop5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90553-9` |
| davbnbh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| davbnoh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| davbrbh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| davbroh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| evsmok15 | observation_type | Measurement | `OMOP:4282779` | `LOINC:64216-5` |
| havbnbh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| havbnoh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| havbrbh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| havbroh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hrswd02 | observation_type | Measurement | `OBA:2040171` | `LOINC:65578-7` |
| hrswe02 | observation_type | Measurement | `OBA:2040171` | `LOINC:65578-7` |
| hwlghr10 | observation_type | Measurement | `OBA:2040171` | `LOINC:65526-6` |
| oahi | observation_type | Measurement | `OMOP:37396400` | `LOINC:90563-8` |
| oai0p | observation_type | Measurement | `OMOP:37396400` | `LOINC:70002-1` |
| oai4p | observation_type | Measurement | `OMOP:37396400` | `LOINC:70002-1` |
| oai4pa | observation_type | Measurement | `OMOP:37396400` | `LOINC:70002-1` |
| oardnba | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnba2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnba3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnba4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnba5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnbp | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnbp2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnbp3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnbp4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnbp5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnoa | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnoa2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnoa3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnoa4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnoa5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnop | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnop2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnop3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnop4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardnop5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrba | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrba2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrba3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrba4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrba5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrbp | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrbp2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrbp3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrbp4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrbp5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardroa | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardroa2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardroa3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardroa4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardroa5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrop | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrop2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrop3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrop4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| oardrop5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90560-4` |
| pm207 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| rdi0p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi0pa | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi0pns | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi0ps | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi2p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi2pa | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi2pns | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi2ps | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi3p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi3pa | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi3pns | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi3ps | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi4p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi4pa | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi4pns | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi4ps | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi5p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi5pa | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi5pns | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdi5ps | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdinba | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinba2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinba3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinba4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinba5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinbp | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinbp2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinbp3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinbp4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinbp5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinoa | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinoa2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinoa3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinoa4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinoa5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinop | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinop2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinop3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinop4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinop5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdinr0p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdinr2p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdinr3p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdinr4p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdinr5p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdirba | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirba2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirba3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirba4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirba5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirbp | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirbp2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirbp3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirbp4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirbp5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirem0p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdirem2p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdirem3p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdirem4p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdirem5p | observation_type | Measurement | `OMOP:37396400` | `LOINC:71103-6` |
| rdiroa | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdiroa2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdiroa3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdiroa4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdiroa5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirop | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirop2 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirop3 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirop4 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| rdirop5 | observation_type | Measurement | `OMOP:37396400` | `LOINC:90555-4` |
| savbnbh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| savbnoh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| savbrbh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| savbroh | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| sh328 | observation_type | Measurement | `OMOP:35609491` | `LOINC:42619-7` |
| sh329 | observation_type | Measurement | `OMOP:35609491` | `LOINC:71962-5` |
| sh330 | observation_type | Measurement | `OMOP:35609491` | `LOINC:93125-3` |
| shots15 | observation_type | Measurement | `OMOP:35609491` | `LOINC:61544-3` |
| slp_time | observation_type | Measurement | `OBA:2040171` | `LOINC:98933-5` |
| slpprdp | observation_type | Measurement | `OBA:2040171` | `LOINC:97892-4` |
| smknow15 | observation_type | Measurement | `OMOP:4282779` | `LOINC:64217-3` |
| smokstat_s2 | observation_type | Measurement | `OMOP:4282779` | `LOINC:55111-9` |
| wine15 | observation_type | Measurement | `OMOP:35609491` | `LOINC:67653-6` |

### Unverified Misalignments (29 — no YAML confirmation)

| Variable | Slot | Entity Type | CSV CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| STKTYPE | condition_concept | Condition | `HP:0002140` | `MONDO:0005098` |
| AGE01 | observations | Measurement | `OMOP:4152194` | `LOINC:56068-0` |
| AGEBL | observations | Measurement | `OMOP:4152194` | `LOINC:56847-7` |
| AGEY10 | observations | Measurement | `OMOP:4152194` | `LOINC:30525-0` |
| AGEY11 | observations | Measurement | `OMOP:4152194` | `LOINC:30525-0` |
| AGEY3 | observations | Measurement | `OMOP:4152194` | `LOINC:56847-7` |
| AGEY4 | observations | Measurement | `OMOP:4152194` | `LOINC:56847-7` |
| AGEY5 | observations | Measurement | `OMOP:4152194` | `LOINC:56847-7` |
| AGEY6 | observations | Measurement | `OMOP:4152194` | `LOINC:56847-7` |
| AGEY7 | observations | Measurement | `OMOP:4152194` | `LOINC:56847-7` |
| AGEY9 | observations | Measurement | `OMOP:4152194` | `LOINC:56847-7` |
| AVEDIA | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| AVESYS | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| AVZMDIA | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| AVZMSYS | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| FEV118 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| FEVPCT18 | observations | Measurement | `OMOP:3002094` | `LOINC:65656-1` |
| FEVPRD18 | observations | Measurement | `OMOP:3002094` | `LOINC:65656-1` |
| FVC18 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| FVCPCT18 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| FVCPRD18 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| RATIO18 | observations | Measurement | `OMOP:3002094` | `LOINC:20157-4` |
| RATPCT18 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| RATPRD18 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| age_s2 | observations | Measurement | `OMOP:4152194` | `LOINC:56847-7` |
| avg23bpd_s2 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| avg23bps_s2 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| sdiast40 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| ssyst40 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |

## Vocab/Slot Validation

Agent suggestions suppressed as vocabulary/slot mismatches (evaluated but not surfaced as findings): **44**

| Slot | Invalid vocab proposed | Suppressed count | Rule |
| :---- | :---- | ----: | :---- |
| `observation_type` | LOINC | 44 | Valid: OBA, OMOP |
| **Total** | | **44** | |

_These are not errors — they confirm the existing CURIEs are correct for their slots. The agent proposed codes from a vocabulary the bdchm slot is not typed for (e.g. OMOP in a MONDO-typed slot, LOINC in an OBA-typed slot). See `_SLOT_VOCAB_RULES` in `generate_semantic_review.py` for the full rule definitions._

## Error Cases Requiring Fix

### YAML Mismatches — 133 must be corrected
See the YAML Spot-Check section above.

No unexpected missing suggestions — all substantive variable-slot pairs either have an agent suggestion or are in a slot type with no agent routing (ValueEnum, Demography, DrugExposure without RxNorm match).
