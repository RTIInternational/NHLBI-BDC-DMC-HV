# CARDIA Semantic Validator Summary v2026-06-19

**Generated:** 2026-06-19
**Mapreview CSV:** `CARDIA_curie_mapreview.csv`
**Review MD:** `CARDIA_Semantic_Review_Final_Reviewer-2026-05-31.md`

---

## Overview

| Metric | Count |
| :---- | ----: |
| Total rows in mapreview CSV | 688 |
| Admin variables skipped | 35 |
| Substantive variables reviewed | 653 |
| Unique CURIEs validated | 110 |
| Unique YAML files referenced | 80 |
| Final Confirmed Findings rows | 38 |
| Anne Review Required rows | 15 |

## YAML Spot-Check

| Result | Count |
| :---- | ----: |
| Matches (✓) | 514 |
| Mismatches (⚠) | 22 |
| Not checked (admin / no YAML) | 117 |

**22 mismatch(es) require correction:**

| Variable | YAML File | CSV CURIE | YAML CURIE |
| :---- | :---- | :---- | :---- |
| A05PLATL | platelet_ct.yaml | `OMOP:4267147` | `OBA:VT0003179` |
| E48NIAC | tak_nstat_med.yaml | `RxCUI:7393` | `ATC:C10A` |
| F48NIAC | tak_nstat_med.yaml | `RxCUI:7393` | `ATC:C10A` |
| C09CHNM | tak_statin.yaml | `RxCUI:202582` | `ATC:C10A` |
| C09CHNM | tak_statin.yaml | `RxCUI:202999` | `ATC:C10A` |
| C09CHNM | tak_statin.yaml | `RxCUI:2053495` | `ATC:C10A` |
| C09CHNM | tak_statin.yaml | `RxCUI:6472` | `ATC:C10A` |
| C09CHNM | tak_statin.yaml | `RxCUI:7393` | `ATC:C10A` |
| C09CHNM | tak_statin.yaml | `RxCUI:8699` | `ATC:C10A` |
| D09CHNM | tak_statin.yaml | `RxCUI:202582` | `ATC:C10A` |
| D09CHNM | tak_statin.yaml | `RxCUI:202908` | `ATC:C10A` |
| D09CHNM | tak_statin.yaml | `RxCUI:202999` | `ATC:C10A` |
| D09CHNM | tak_statin.yaml | `RxCUI:316175` | `ATC:C10A` |
| D09CHNM | tak_statin.yaml | `RxCUI:5487` | `ATC:C10A` |
| D09CHNM | tak_statin.yaml | `RxCUI:6472` | `ATC:C10A` |
| E09CHNM | tak_statin.yaml | `RxCUI:151533` | `ATC:C10A` |
| E09CHNM | tak_statin.yaml | `RxCUI:196503` | `ATC:C10A` |
| E09CHNM | tak_statin.yaml | `RxCUI:203333` | `ATC:C10A` |
| E09CHNM | tak_statin.yaml | `RxCUI:316343` | `ATC:C10A` |
| E09CHNM | tak_statin.yaml | `RxCUI:4719` | `ATC:C10A` |
| E09CHNM | tak_statin.yaml | `RxCUI:6472` | `ATC:C10A` |
| E09CHNM | tak_statin.yaml | `RxCUI:6918` | `ATC:C10A` |

## Agent Coverage by Entity Type

| Entity Type | Unique vars | MONDO | HPO | OMOP/LOINC | No suggestion |
| :---- | ----: | ----: | ----: | ----: | ----: |
| Condition | 26 | 26 | 0 | 0 | 0 |
| Condition (HPO) | 6 | 0 | 6 | 0 | 0 |
| Condition (OMOP fallback) | 149 | 0 | 0 | 149 | 0 |
| Demography | 3 | 0 | 0 | 2 | 1 |
| DrugExposure | 12 | 0 | 0 | 0 | 12 |
| Measurement | 263 | 0 | 0 | 246 | 17 |
| Person | 6 | 0 | 0 | 0 | 6 |
| Procedure | 1 | 0 | 0 | 1 | 0 |
| ValueEnum | 1 | 0 | 0 | 0 | 1 |
| **Total** | **467** | | | | **37** |

**Coverage: 430/467 unique variable-slot pairs have at least one agent suggestion (92%).**

## Agent vs CSV CURIE Alignment

Agent suggestions differ from the current CSV CURIE in **418** variable-slot pair(s).

### Potential Improvements (366 — YAML confirms CSV, agent suggests different)

These cases have a YAML-confirmed CSV CURIE but the agent suggests a different concept.
Review whether the agent suggestion is more specific or accurate.

| Variable | Slot | Entity Type | CSV / YAML CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| A09ANGIN | condition_concept | Condition | `HP:0001681` | `MONDO:0006021` |
| A09CHFAG | condition_concept | Condition | `MONDO:0004995` | `MONDO:0020402` |
| A09DIBST | condition_concept | Condition | `MONDO:0005015` | `MONDO:0012819` |
| A09RHDAG | condition_concept | Condition | `MONDO:0006955` | `MONDO:0005854` |
| B08DIAB | condition_concept | Condition | `MONDO:0005015` | `MONDO:0010950` |
| C08HBP | condition_concept | Condition | `HP:0000822` | `MONDO:0001641` |
| D08HBP | condition_concept | Condition | `HP:0000822` | `MONDO:0001641` |
| D08OTHHT | condition_concept | Condition | `MONDO:0005267` | `MONDO:0000453` |
| E08HBP | condition_concept | Condition | `HP:0000822` | `MONDO:0001641` |
| F08HBP | condition_concept | Condition | `HP:0000822` | `MONDO:0001641` |
| F08OTHHT | condition_concept | Condition | `MONDO:0005267` | `MONDO:0000453` |
| Y01ANGIN | condition_concept | Condition | `HP:0001681` | `MONDO:0006805` |
| Y01DMOTH | condition_concept | Condition | `MONDO:0005015` | `MONDO:0012819` |
| Y01MI | condition_concept | Condition | `MONDO:0005010` | `MONDO:0005068` |
| Y01PADDG | condition_concept | Condition | `MONDO:0005386` | `MONDO:0100091` |
| Y01VTD | condition_concept | Condition | `MONDO:0005399` | `MONDO:0013144` |
| C08ANGIN | condition_concept | Condition (HPO) | `HP:0001681` | `HP:0005110` |
| D08ANGIN | condition_concept | Condition (HPO) | `HP:0001681` | `HP:0005110` |
| D08PVD | condition_concept | Condition (HPO) | `MONDO:0005386` | `HP:0004950` |
| E08PVD | condition_concept | Condition (HPO) | `MONDO:0005386` | `HP:0004950` |
| F08ANGIN | condition_concept | Condition (HPO) | `HP:0001681` | `HP:0005110` |
| F08PVD | condition_concept | Condition (HPO) | `MONDO:0005386` | `HP:0004950` |
| A09ANGAG | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:4265453` |
| A09ANGST | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:4119942` |
| A09HBPAG | condition_concept | Condition (OMOP fallback) | `HP:0000822` | `OMOP:4265453` |
| A09HBPG1 | condition_concept | Condition (OMOP fallback) | `HP:0000822` | `OMOP:4231970` |
| A09HBPST | condition_concept | Condition (OMOP fallback) | `HP:0000822` | `OMOP:41963254` |
| A09HRTAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005068` | `OMOP:3022304` |
| A09VHDAG | condition_concept | Condition (OMOP fallback) | `MONDO:0002869` | `OMOP:3022304` |
| A12ASAGE | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:4265453` |
| A12ASDOC | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:40766909` |
| A12ASSTL | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:4294899` |
| A12ASTHM | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:40767110` |
| A12CBDOC | condition_concept | Condition (OMOP fallback) | `MONDO:0005607` | `OMOP:40766900` |
| A12CBRON | condition_concept | Condition (OMOP fallback) | `MONDO:0005607` | `OMOP:256451` |
| A12CBSTL | condition_concept | Condition (OMOP fallback) | `MONDO:0005607` | `OMOP:4294899` |
| A12EMDOC | condition_concept | Condition (OMOP fallback) | `MONDO:0004848` | `OMOP:40766905` |
| A12EMPH | condition_concept | Condition (OMOP fallback) | `MONDO:0004848` | `OMOP:40766903` |
| A12EMSTL | condition_concept | Condition (OMOP fallback) | `MONDO:0004848` | `OMOP:4294899` |
| A21ASMA | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:21499046` |
| B09ANGAG | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:4265453` |
| B09ANGIN | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:4169826` |
| B09ANGST | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:36308207` |
| B09CHD | condition_concept | Condition (OMOP fallback) | `MONDO:0005453` | `OMOP:21499005` |
| B09CHFAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005009` | `OMOP:4265453` |
| B09DIBAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:4265453` |
| B09DIBST | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:45879799` |
| B09HBPAG | condition_concept | Condition (OMOP fallback) | `HP:0000822` | `OMOP:3022304` |
| B09HBPG1 | condition_concept | Condition (OMOP fallback) | `HP:0000822` | `OMOP:4231970` |
| B09HBPST | condition_concept | Condition (OMOP fallback) | `HP:0000822` | `OMOP:41963254` |
| B09HRTAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005068` | `OMOP:4265453` |
| B09HRTAK | condition_concept | Condition (OMOP fallback) | `MONDO:0005068` | `OMOP:36769336` |
| B09RHDAG | condition_concept | Condition (OMOP fallback) | `MONDO:0006955` | `OMOP:4265453` |
| B09VHDAG | condition_concept | Condition (OMOP fallback) | `MONDO:0002869` | `OMOP:3022304` |
| B12ASAGE | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:4265453` |
| B12ASDOC | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:45877009` |
| B12ASSTL | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:41963254` |
| B12ASTHM | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:317009` |
| C08ANGAG | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:3022304` |
| C08DIAB | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:45879799` |
| C08DIBAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:4265453` |
| C08HBPAG | condition_concept | Condition (OMOP fallback) | `HP:0000822` | `OMOP:3022304` |
| C08HRTAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005068` | `OMOP:3022304` |
| C08HRTAK | condition_concept | Condition (OMOP fallback) | `MONDO:0005068` | `OMOP:36308337` |
| C08OTHAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005267` | `OMOP:4265453` |
| C08OTHHT | condition_concept | Condition (OMOP fallback) | `MONDO:0005267` | `OMOP:35913478` |
| C08RHD | condition_concept | Condition (OMOP fallback) | `MONDO:0006955` | `OMOP:319825` |
| C08RHDAG | condition_concept | Condition (OMOP fallback) | `MONDO:0006955` | `OMOP:3022304` |
| D08ANGAG | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:4265453` |
| D08ASTAG | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:4265453` |
| D08ASTH | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:317009` |
| D08ASTYR | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:317009` |
| D08BRON | condition_concept | Condition (OMOP fallback) | `MONDO:0005607` | `OMOP:45882678` |
| D08DIAB | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:45879799` |
| D08DIBAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:4265453` |
| D08EMPH | condition_concept | Condition (OMOP fallback) | `MONDO:0004848` | `OMOP:4169883` |
| D08HBPAG | condition_concept | Condition (OMOP fallback) | `HP:0000822` | `OMOP:4265453` |
| D08HRTAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005068` | `OMOP:4265453` |
| D08HRTAK | condition_concept | Condition (OMOP fallback) | `MONDO:0005068` | `OMOP:36308337` |
| D08OTHAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005267` | `OMOP:4265453` |
| D08PVDAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005386` | `OMOP:4265453` |
| D08RHD | condition_concept | Condition (OMOP fallback) | `MONDO:0006955` | `OMOP:319825` |
| D08RHDAG | condition_concept | Condition (OMOP fallback) | `MONDO:0006955` | `OMOP:3022304` |
| D08TIA | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:36210384` |
| D21ASMA | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:4116678` |
| D21CARD5 | condition_concept | Condition (OMOP fallback) | `MONDO:0004995` | `OMOP:4266015` |
| E08ANGAG | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:3022304` |
| E08ANGIN | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:37079329` |
| E08ASTAG | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:4265453` |
| E08ASTH | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:45877009` |
| E08ASTYR | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:45877009` |
| E08BRON | condition_concept | Condition (OMOP fallback) | `MONDO:0005607` | `OMOP:256451` |
| E08DIAB | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:45879799` |
| E08DIBAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:3022304` |
| E08EMPH | condition_concept | Condition (OMOP fallback) | `MONDO:0004848` | `OMOP:36769994` |
| E08HBPAG | condition_concept | Condition (OMOP fallback) | `HP:0000822` | `OMOP:4265453` |
| E08HRTAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005068` | `OMOP:3022304` |
| E08HRTAK | condition_concept | Condition (OMOP fallback) | `MONDO:0005068` | `OMOP:36308337` |
| E08OTHAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005267` | `OMOP:3022304` |
| E08OTHHT | condition_concept | Condition (OMOP fallback) | `MONDO:0005267` | `OMOP:35911085` |
| E08PVDAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005386` | `OMOP:3022304` |
| E08RHD | condition_concept | Condition (OMOP fallback) | `MONDO:0006955` | `OMOP:319825` |
| E08RHDAG | condition_concept | Condition (OMOP fallback) | `MONDO:0006955` | `OMOP:3022304` |
| E08TIA | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:36210384` |
| ER2SFOCI | condition_concept | Condition (OMOP fallback) | `OMOP:4102124` | `OMOP:4035621` |
| F08ANGAG | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:4265453` |
| F08ASTAG | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:3022304` |
| F08ASTH | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:45877009` |
| F08ASTYR | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:45877009` |
| F08BRON | condition_concept | Condition (OMOP fallback) | `MONDO:0005607` | `OMOP:45882678` |
| F08DIAB | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:45879799` |
| F08DIBAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:3022304` |
| F08EMPH | condition_concept | Condition (OMOP fallback) | `MONDO:0004848` | `OMOP:36769994` |
| F08EMPYR | condition_concept | Condition (OMOP fallback) | `MONDO:0004848` | `OMOP:4169883` |
| F08HBPAG | condition_concept | Condition (OMOP fallback) | `HP:0000822` | `OMOP:4265453` |
| F08HRTAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005068` | `OMOP:4265453` |
| F08HRTAK | condition_concept | Condition (OMOP fallback) | `MONDO:0005068` | `OMOP:36308337` |
| F08OTHAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005267` | `OMOP:3022304` |
| F08POAGE | condition_concept | Condition (OMOP fallback) | `MONDO:0005607` | `OMOP:4265453` |
| F08PVDAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005386` | `OMOP:4265453` |
| F08RHD | condition_concept | Condition (OMOP fallback) | `MONDO:0006955` | `OMOP:319825` |
| F08RHDAG | condition_concept | Condition (OMOP fallback) | `MONDO:0006955` | `OMOP:4265453` |
| F08TIA | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:36210384` |
| FY096AGA | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:45881107` |
| FY096BPA | condition_concept | Condition (OMOP fallback) | `HP:0000822` | `OMOP:4265453` |
| FY096DBA | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:4265453` |
| FY096DBT | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:45879799` |
| FY096HAK | condition_concept | Condition (OMOP fallback) | `MONDO:0005068` | `OMOP:36769336` |
| FY096HBP | condition_concept | Condition (OMOP fallback) | `HP:0000822` | `OMOP:4328749` |
| FY096TAA | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:3022304` |
| FY096TIA | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:36210384` |
| FY108AGA | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:36879674` |
| FY108DBT | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:45879799` |
| FY108HAK | condition_concept | Condition (OMOP fallback) | `MONDO:0005068` | `OMOP:36769336` |
| FY108TIA | condition_concept | Condition (OMOP fallback) | `MONDO:0005264` | `OMOP:36210384` |
| Y00ASTHM | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:317009` |
| Y00CHF | condition_concept | Condition (OMOP fallback) | `MONDO:0005009` | `OMOP:319835` |
| Y00DIAB | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:45879799` |
| Y00MI | condition_concept | Condition (OMOP fallback) | `MONDO:0005010` | `OMOP:4329847` |
| Y00PAD | condition_concept | Condition (OMOP fallback) | `MONDO:0005386` | `OMOP:21498362` |
| Y00STROK | condition_concept | Condition (OMOP fallback) | `MONDO:0005264` | `OMOP:36210384` |
| Y01ANGDR | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:32577` |
| Y01ANGEC | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:4264145` |
| Y01ANGHS | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:36662553` |
| Y01ANGOB | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:4093906` |
| Y01ANGSM | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:42690755` |
| Y01ANGTR | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:41970602` |
| Y01ASOTH | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:45878142` |
| Y01ASTDR | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:317009` |
| Y01ASTMD | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:317009` |
| Y01CHFEP | condition_concept | Condition (OMOP fallback) | `MONDO:0005009` | `OMOP:319835` |
| Y01DMDR | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:45879799` |
| Y01DMMED | condition_concept | Condition (OMOP fallback) | `MONDO:0005015` | `OMOP:45879799` |
| Y01DVTDD | condition_concept | Condition (OMOP fallback) | `HP:0002625` | `OMOP:21498461` |
| Y01DVTDG | condition_concept | Condition (OMOP fallback) | `HP:0002625` | `OMOP:21498755` |
| Y01DVTDR | condition_concept | Condition (OMOP fallback) | `HP:0002625` | `OMOP:4294698` |
| Y01DVTIS | condition_concept | Condition (OMOP fallback) | `HP:0002625` | `OMOP:4143312` |
| Y01DVTPE | condition_concept | Condition (OMOP fallback) | `MONDO:0005399` | `OMOP:45201853` |
| Y01DVTPG | condition_concept | Condition (OMOP fallback) | `HP:0002625` | `OMOP:4098516` |
| Y01DVTVG | condition_concept | Condition (OMOP fallback) | `HP:0002625` | `OMOP:4346843` |
| Y01MIEP | condition_concept | Condition (OMOP fallback) | `MONDO:0005010` | `OMOP:4329847` |
| Y01PADDR | condition_concept | Condition (OMOP fallback) | `MONDO:0005386` | `OMOP:4236179` |
| Y01PADEP | condition_concept | Condition (OMOP fallback) | `MONDO:0005386` | `OMOP:4031511` |
| Y01PADLG | condition_concept | Condition (OMOP fallback) | `MONDO:0005386` | `OMOP:4236179` |
| Y01PADPL | condition_concept | Condition (OMOP fallback) | `MONDO:0005386` | `OMOP:4236179` |
| Y01PADSG | condition_concept | Condition (OMOP fallback) | `MONDO:0005386` | `OMOP:4236179` |
| Y01PEANG | condition_concept | Condition (OMOP fallback) | `MONDO:0005279` | `OMOP:45883963` |
| Y01PEDG | condition_concept | Condition (OMOP fallback) | `HP:0002625` | `OMOP:42538094` |
| Y01PEDR | condition_concept | Condition (OMOP fallback) | `MONDO:0005279` | `OMOP:4294698` |
| Y01PESCN | condition_concept | Condition (OMOP fallback) | `MONDO:0005279` | `OMOP:4163858` |
| Z33ECHD | condition_concept | Condition (OMOP fallback) | `MONDO:0005010` | `OMOP:4082018` |
| RACE | race | Demography | `OMOP:8516` | `OMOP:8527` |
| A05HCT | observation_type | Measurement | `OBA:2045381` | `LOINC:4544-3` |
| A05HGB | observation_type | Measurement | `OBA:2060175` | `LOINC:718-7` |
| A05LYMPH | observation_type | Measurement | `OBA:VT0000717` | `LOINC:26474-7` |
| A05NEUTR | observation_type | Measurement | `OMOP:37208698` | `LOINC:26499-4` |
| A05RBC | observation_type | Measurement | `OBA:2045301` | `LOINC:106763-6` |
| A05WBC | observation_type | Measurement | `OBA:VT0000717` | `LOINC:67750-0` |
| A06FRU0300 | observation_type | Measurement | `OMOP:21493059` | `LOINC:60408-2` |
| A06FRU0400 | observation_type | Measurement | `OMOP:21493059` | `LOINC:80458-3` |
| A06FRU0500 | observation_type | Measurement | `OMOP:21493059` | `LOINC:61294-5` |
| A06FRU0600 | observation_type | Measurement | `OMOP:21493059` | `LOINC:36973-6` |
| A06FRUIT | observation_type | Measurement | `OMOP:21493059` | `LOINC:52591-5` |
| A06SODUM | observation_type | Measurement | `OMOP:606729` | `LOINC:77243-4` |
| A06VEG0300 | observation_type | Measurement | `OMOP:4042886` | `LOINC:61474-3` |
| A06VEG0400 | observation_type | Measurement | `OMOP:4042886` | `LOINC:61553-4` |
| A06VEG0450 | observation_type | Measurement | `OMOP:4042886` | `LOINC:52483-5` |
| A06VEG0500 | observation_type | Measurement | `OMOP:4042886` | `LOINC:80460-9` |
| A06VEG0600 | observation_type | Measurement | `OMOP:4042886` | `LOINC:52483-5` |
| A06VEG0800 | observation_type | Measurement | `OMOP:4042886` | `LOINC:90722-0` |
| A06VEG0900 | observation_type | Measurement | `OMOP:4042886` | `LOINC:36973-6` |
| A07BEER | observation_type | Measurement | `OMOP:35609491` | `LOINC:105999-7` |
| A07LIQR | observation_type | Measurement | `OMOP:35609491` | `LOINC:105999-7` |
| A07WINE | observation_type | Measurement | `OMOP:35609491` | `LOINC:105999-7` |
| A10SMOKE | observation_type | Measurement | `OMOP:4282779` | `LOINC:105045-9` |
| A12TEMP | observation_type | Measurement | `OBA:VT0005535` | `LOINC:29042-9` |
| A20BMI | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| A20HIP | observation_type | Measurement | `OBA:1000032` | `LOINC:60949-5` |
| A20HIPS1 | observation_type | Measurement | `OBA:1000032` | `LOINC:15294-2` |
| A20HIPS2 | observation_type | Measurement | `OBA:1000032` | `LOINC:15294-2` |
| A20WST | observation_type | Measurement | `OBA:1001085` | `LOINC:60949-5` |
| A20WST1 | observation_type | Measurement | `OBA:1001085` | `LOINC:15294-2` |
| A20WST2 | observation_type | Measurement | `OBA:1001085` | `LOINC:15294-2` |
| A22HRPRE | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| A22HRS1 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| A22HRS2 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| A22HRS3 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| A22HRS4 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| A22HRS5 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| A22HRS6 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| A22HRS7 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| A22HRS8 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| A22HRS9 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| AL1CHOL | observation_type | Measurement | `OBA:VT0000180` | `LOINC:110258-1` |
| AL1HDL | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| AL1LDL | observation_type | Measurement | `OBA:VT0000181` | `LOINC:14155-6` |
| AL1NTRIG | observation_type | Measurement | `OBA:VT0002644` | `LOINC:30570-6` |
| AL3ALBUM | observation_type | Measurement | `OBA:2050068` | `LOINC:100158-5` |
| AL3TBILI | observation_type | Measurement | `OMOP:4230543` | `LOINC:42719-5` |
| AL3_GLU | observation_type | Measurement | `OBA:VT0000188` | `LOINC:105272-9` |
| AL3_SGOT | observation_type | Measurement | `OMOP:4263457` | `LOINC:56644-8` |
| AV6SODUM | observation_type | Measurement | `OMOP:606729` | `LOINC:77243-4` |
| B12AGE | observation_type | Measurement | `OBA:VT0001253` | `LOINC:30525-0` |
| B12HGT | observation_type | Measurement | `OBA:VT0001253` | `LOINC:17003-5` |
| B12TEMP | observation_type | Measurement | `OBA:VT0005535` | `LOINC:98151-4` |
| B20HGT | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| B20WGT | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| BLEFACT7 | observation_type | Measurement | `OBA:2041535` | `LOINC:10395-2` |
| BLEFIBR | observation_type | Measurement | `OBA:0000061` | `LOINC:3255-7` |
| BLEVWANT | observation_type | Measurement | `OBA:2052741` | `LOINC:48593-8` |
| BN_NA | observation_type | Measurement | `OMOP:606729` | `LOINC:89270-3` |
| C03INCOM | observation_type | Measurement | `OMOP:4076114` | `LOINC:67695-7` |
| C12HGT | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| C12TEMP | observation_type | Measurement | `OBA:VT0005535` | `LOINC:29042-9` |
| C20BMI | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| C20HGT | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| C20HIPS1 | observation_type | Measurement | `OBA:1000032` | `LOINC:45716-8` |
| C20WGT | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| C20WST1 | observation_type | Measurement | `OBA:1001085` | `LOINC:56115-9` |
| C31BNPTS | observation_type | Measurement | `OBA:2045303` | `LOINC:9800-4` |
| C36SCORE | observation_type | Measurement | `OMOP:36303297` | `LOINC:100787-1` |
| C42CHOUR | observation_type | Measurement | `OBA:2040171` | `LOINC:57123-2` |
| C42_HRTE | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| C42_MAP | observation_type | Measurement | `OBA:VT2000000` | `LOINC:60949-5` |
| CL1CHOL | observation_type | Measurement | `OBA:VT0000180` | `LOINC:110258-1` |
| CL1HDL | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| CL1LDL | observation_type | Measurement | `OBA:VT0000181` | `LOINC:14155-6` |
| CL1NTRIG | observation_type | Measurement | `OBA:VT0002644` | `LOINC:30570-6` |
| CL6FIBR | observation_type | Measurement | `OBA:0000061` | `LOINC:3255-7` |
| CLEFACT7 | observation_type | Measurement | `OBA:2041535` | `LOINC:10395-2` |
| CLEFACT8 | observation_type | Measurement | `OBA:2041536` | `LOINC:10395-2` |
| CLEFIBR | observation_type | Measurement | `OBA:0000061` | `LOINC:3255-7` |
| CLEVWACT | observation_type | Measurement | `OBA:2052741` | `LOINC:48593-8` |
| CLEVWANT | observation_type | Measurement | `OBA:2052741` | `LOINC:48593-8` |
| D03INCOM | observation_type | Measurement | `OMOP:4076114` | `LOINC:67695-7` |
| D06FRU0300 | observation_type | Measurement | `OMOP:21493059` | `LOINC:60408-2` |
| D06FRU0400 | observation_type | Measurement | `OMOP:21493059` | `LOINC:80458-3` |
| D06FRU0500 | observation_type | Measurement | `OMOP:21493059` | `LOINC:61294-5` |
| D06FRU0600 | observation_type | Measurement | `OMOP:21493059` | `LOINC:36973-6` |
| D06FRUIT | observation_type | Measurement | `OMOP:21493059` | `LOINC:52591-5` |
| D06POTSM | observation_type | Measurement | `OBA:VT0002668` | `LOINC:57379-0` |
| D06SODUM | observation_type | Measurement | `OMOP:606729` | `LOINC:77243-4` |
| D06VEG0300 | observation_type | Measurement | `OMOP:4042886` | `LOINC:61474-3` |
| D06VEG0400 | observation_type | Measurement | `OMOP:4042886` | `LOINC:61553-4` |
| D06VEG0450 | observation_type | Measurement | `OMOP:4042886` | `LOINC:52483-5` |
| D06VEG0500 | observation_type | Measurement | `OMOP:4042886` | `LOINC:80460-9` |
| D06VEG0600 | observation_type | Measurement | `OMOP:4042886` | `LOINC:52483-5` |
| D06VEG0800 | observation_type | Measurement | `OMOP:4042886` | `LOINC:90722-0` |
| D06VEG0900 | observation_type | Measurement | `OMOP:4042886` | `LOINC:36973-6` |
| D20BMI | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| D20HGT | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| D20HIP | observation_type | Measurement | `OBA:1000032` | `LOINC:60949-5` |
| D20HIPS1 | observation_type | Measurement | `OBA:1000032` | `LOINC:45716-8` |
| D20HIPS2 | observation_type | Measurement | `OBA:1000032` | `LOINC:45716-8` |
| D20WGT | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| D20WST1 | observation_type | Measurement | `OBA:1001085` | `LOINC:56115-9` |
| D20WST2 | observation_type | Measurement | `OBA:1001085` | `LOINC:56115-9` |
| D22HRPRE | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| D22HRS1 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| D22HRS2 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| D22HRS3 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| D22HRS4 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| D22HRS5 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| D22HRS6 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| D22HRS7 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| D22HRS8 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| D22HRS9 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| D22SUPIN | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| D46X3WGT | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| D46X4WGT | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| DDXPTHT | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| DDXPTWT | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| DDXSPAGE | observation_type | Measurement | `OBA:VT0001253` | `LOINC:97801-5` |
| DL1HDL | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| DL1LDL | observation_type | Measurement | `OBA:VT0000181` | `LOINC:14155-6` |
| DL1NTRIG | observation_type | Measurement | `OBA:VT0002644` | `LOINC:30570-6` |
| DL6CRPBN | observation_type | Measurement | `OMOP:4208414` | `LOINC:21695-2` |
| DL7GLU | observation_type | Measurement | `OBA:VT0000188` | `LOINC:52492-6` |
| DLEF7ANT | observation_type | Measurement | `OBA:2041535` | `LOINC:65644-7` |
| DLEFACT7 | observation_type | Measurement | `OBA:2041535` | `LOINC:10395-2` |
| DLEFACT8 | observation_type | Measurement | `OBA:2041536` | `LOINC:10395-2` |
| DLEFIBR | observation_type | Measurement | `OBA:0000061` | `LOINC:3255-7` |
| DLEFIBR2 | observation_type | Measurement | `OBA:0000061` | `LOINC:21695-2` |
| DLEVWACT | observation_type | Measurement | `OBA:2052741` | `LOINC:48593-8` |
| DLEVWANT | observation_type | Measurement | `OBA:2052741` | `LOINC:48593-8` |
| DV6POTSM | observation_type | Measurement | `OBA:VT0002668` | `LOINC:57379-0` |
| DV6SODUM | observation_type | Measurement | `OMOP:606729` | `LOINC:77243-4` |
| E03INCOM | observation_type | Measurement | `OMOP:4076114` | `LOINC:67695-7` |
| E12AGE | observation_type | Measurement | `OBA:VT0001253` | `LOINC:30525-0` |
| E12HGT | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| E12TEMP | observation_type | Measurement | `OBA:VT0005535` | `LOINC:29042-9` |
| E20BMI | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| E20HGT | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| E20HIP | observation_type | Measurement | `OBA:1000032` | `LOINC:60949-5` |
| E20HIPS1 | observation_type | Measurement | `OBA:1000032` | `LOINC:45716-8` |
| E20HIPS2 | observation_type | Measurement | `OBA:1000032` | `LOINC:45716-8` |
| E20WGT | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| E20WST1 | observation_type | Measurement | `OBA:1001085` | `LOINC:56115-9` |
| E20WST2 | observation_type | Measurement | `OBA:1001085` | `LOINC:56115-9` |
| E36SCORE | observation_type | Measurement | `OMOP:36303297` | `LOINC:100787-1` |
| E46X4WGT | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| E46X5WGT | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| E53AGE | observation_type | Measurement | `OBA:VT0001253` | `LOINC:30525-0` |
| E53HEIGT | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| E53WGT | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| EHT | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| EL1HDL | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| EL1LDL | observation_type | Measurement | `OBA:VT0000181` | `LOINC:14155-6` |
| EL1NTRIG | observation_type | Measurement | `OBA:VT0002644` | `LOINC:30570-6` |
| EL7CREAT | observation_type | Measurement | `OBA:2050096` | `LOINC:14682-9` |
| EL7GLU | observation_type | Measurement | `OMOP:4156660` | `LOINC:89066-5` |
| EL8RATIO | observation_type | Measurement | `OMOP:4154347` | `LOINC:10385-3` |
| EL8UALB | observation_type | Measurement | `OBA:VT0002871` | `LOINC:69280-6` |
| EL8UCRET | observation_type | Measurement | `OBA:VT0010540` | `LOINC:28239-2` |
| ER2TSCOR | observation_type | Measurement | `OMOP:42872742` | `LOINC:100279-9` |
| F03INCOM | observation_type | Measurement | `OMOP:4076114` | `LOINC:67695-7` |
| F10LVHME | observation_type | Measurement | `OMOP:4282779` | `LOINC:92290-6` |
| F20BMI | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| F20HGT | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| F20WGT | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| F20WST1 | observation_type | Measurement | `OBA:1001085` | `LOINC:56115-9` |
| F36SCORE | observation_type | Measurement | `OMOP:36303297` | `LOINC:100787-1` |
| F67SLPHR | observation_type | Measurement | `OBA:2040171` | `LOINC:80430-2` |
| FL1CREAT | observation_type | Measurement | `OBA:VT0010540` | `LOINC:28239-2` |
| FL1HDL | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| FL1LDL | observation_type | Measurement | `OBA:VT0000181` | `LOINC:14155-6` |
| FL1NTRIG | observation_type | Measurement | `OBA:VT0002644` | `LOINC:30570-6` |
| FL1RATIO | observation_type | Measurement | `OMOP:4154347` | `LOINC:10385-3` |
| FL1UALB | observation_type | Measurement | `OBA:VT0002871` | `LOINC:28239-2` |
| FL1UCRET | observation_type | Measurement | `OBA:VT0010540` | `LOINC:62811-5` |
| FL6CRP | observation_type | Measurement | `OMOP:4208414` | `LOINC:16503-5` |
| FL6IL6 | observation_type | Measurement | `OBA:2052890` | `LOINC:17115-7` |
| FL7CREAT | observation_type | Measurement | `OBA:2050096` | `LOINC:14682-9` |
| FL7GLU | observation_type | Measurement | `OMOP:4156660` | `LOINC:63382-6` |
| FLFISOP | observation_type | Measurement | `OMOP:3011888` | `LOINC:90782-4` |
| FR3PHS11 | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| FR3PHS21 | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| FR3SCR11 | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| FR3SCR21 | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| FR3SCR31 | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| FR3SCR41 | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| FRSHR1 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| FRSHR2 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| FRSHRAVG | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| FY096WGT | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| Y01TROPR | observation_type | Measurement | `OMOP:4021291` | `LOINC:42757-5` |

### Unverified Misalignments (52 — no YAML confirmation)

| Variable | Slot | Entity Type | CSV CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| A02DBP | observations | Measurement | `OMOP:4152194` | `LOINC:60949-5` |
| A02SBP | observations | Measurement | `OMOP:4152194` | `LOINC:60949-5` |
| A05PLATL | observation_type | Measurement | `OMOP:4267147` | `LOINC:777-3` |
| A12FE1 | observations | Measurement | `OMOP:4176265` | `LOINC:20150-9` |
| A12FVC | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| B12FEV11 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| B12FEV12 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| B12FEV13 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| B12FEV14 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| B12FEV15 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| B12FEV16 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| B12FVC | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| B12FVC1 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| B12FVC2 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| B12FVC3 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| B12FVC4 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| B12FVC5 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| B12FVC6 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| C12FEV11 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| C12FEV12 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| C12FEV13 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| C12FEV14 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| C12FEV15 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| C12FVC | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| C12FVC1 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| C12FVC2 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| C12FVC3 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| C12FVC4 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| C12FVC5 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| C1MDBP | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| C1MSBP | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| E128E1 | observations | Measurement | `OMOP:4176265` | `LOINC:20150-9` |
| E128VC | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| E12AGE | observations | Measurement | `OMOP:4176265` | `LOINC:30525-0` |
| E12FE1 | observations | Measurement | `OMOP:4176265` | `LOINC:20150-9` |
| E12FEV11 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| E12FEV12 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| E12FEV13 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| E12FEV14 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| E12FEV15 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| E12FEV16 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| E12FEV17 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| E12FEV18 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| E12FVC | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| E12FVC1 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| E12FVC2 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| E12FVC3 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| E12FVC4 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| E12FVC5 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| E12FVC6 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| E12FVC7 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| E12FVC8 | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |

## Vocab/Slot Validation

Agent suggestions suppressed as vocabulary/slot mismatches (evaluated but not surfaced as findings): **54**

| Slot | Invalid vocab proposed | Suppressed count | Rule |
| :---- | :---- | ----: | :---- |
| `condition_concept` | LOINC, OMOP, SNOMED | 5 | Valid: HP, MONDO |
| `observation_type` | LOINC | 49 | Valid: OBA, OMOP |
| **Total** | | **54** | |

_These are not errors — they confirm the existing CURIEs are correct for their slots. The agent proposed codes from a vocabulary the bdchm slot is not typed for (e.g. OMOP in a MONDO-typed slot, LOINC in an OBA-typed slot). See `_SLOT_VOCAB_RULES` in `generate_semantic_review.py` for the full rule definitions._

## Error Cases Requiring Fix

### YAML Mismatches — 22 must be corrected
See the YAML Spot-Check section above.

### Missing Agent Suggestions — 29 variable-slot pair(s)

These substantive variables received no suggestion from any agent.
Investigate whether a suitable ontology term exists or the slot routing needs updating.

| Variable | Slot | Entity Type | Description |
| :---- | :---- | :---- | :---- |
| A20HGT | observation_type | Measurement | PT&#39;S HGT, CM. Q 1 |
| A20WGT | observation_type | Measurement | PT&#39;S WGT, LBS. Q 2 |
| B20BMI | observation_type | Measurement | B20BMI |
| A09YRSQT | observation_type | Measurement | EX-SMOKER: HOW LONG AGO QUIT SMOKING? Q 2.01 |
| FL6CRPBN | observation_type | Measurement | RERUN CRP (uG/ml - BNII METHOD) |
| A06FRU0700 | observation_type | Measurement | FRUIT-BASED SAVORY SNACK |
| D06FRU0700 | observation_type | Measurement | FRUIT-BASED SAVORY SNACK |
| Individual_ID | drug_concept | DrugExposure | Subject Identifier |
| A09MDNOW | drug_concept | DrugExposure | TAKING MED NOW? |
| sICAM1 | observation_type | Measurement | SICAM1 |
| B28MAP1 | observation_type | Measurement | PRE-INSTRUCTION BASELINE MAP #1 |
| E50DIUR | drug_concept | DrugExposure | DOUBLE DIURETICS TO LOSE WEIGHT. Q 12 |
| E05INSUL | drug_concept | DrugExposure | CURRENTLY TAKING INSULIN OR ORAL DRUGS? Q 14 |
| E48NIAC | drug_concept | DrugExposure | TAKEN NIACIN? Q 4 |
| F48NIAC | drug_concept | DrugExposure | TAKEN NIACIN? Q 2 |
| C08CHNOW | drug_concept | DrugExposure | CURRENTLY TAKING CHOLESTEROL MEDICATION. Q 11 |
| C09CHNM | drug_concept | DrugExposure | NAME OF CHOL LOWERING MEDICATION. Q 11a |
| D09CHNM | drug_concept | DrugExposure | NAME OF CHOL LOWERING MEDICATION. Q 23a |
| E09CHNM | drug_concept | DrugExposure | NAME OF CHOL LOWERING MED. Q 25a |
| Y01HCHMD | drug_concept | DrugExposure | HYPERCHOLESTEROLEMIA BASED ON CHOL LOWERING MEDS |
| E05STERD | drug_concept | DrugExposure | USING STEROIDS? Q 15 |
| A06VEG0100 | observation_type | Measurement | DARK-GREEN VEGETABLES |
| A06VEG0200 | observation_type | Measurement | DEEP-YELLOW VEGETABLES |
| A06VEG0700 | observation_type | Measurement | LEGUMES (COOKED DRIED BEANS) |
| A06FMC0100 | observation_type | Measurement | VEGETABLE-BASED SAVORY SNACK |
| D06VEG0100 | observation_type | Measurement | DARK-GREEN VEGETABLES |
| D06VEG0200 | observation_type | Measurement | DEEP-YELLOW VEGETABLES |
| D06VEG0700 | observation_type | Measurement | LEGUMES (COOKED DRIED BEANS) |
| D06FMC0100 | observation_type | Measurement | VEGETABLE-BASED SAVORY SNACK |
