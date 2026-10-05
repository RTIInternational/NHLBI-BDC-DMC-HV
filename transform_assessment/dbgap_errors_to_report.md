# dbGaP metadata errors to report

Errors found in dbGaP study metadata (data dictionaries, variable labels, units) while
building or reviewing the harmonized transform specs. Requested in #822 item 7. Append a row
when a new one is found.

Rules for a row:

- Cite the dbGaP accession (phs version, pht, phv) and what the dictionary literally says.
- Evidence is metadata or aggregate only (dictionary text, var_report counts/means). No
  participant-level data.
- `status` is one of: `found` (listed here, not yet sent), `reported` (sent to dbGaP or the
  study, with date and channel), `acknowledged` (dbGaP or the study confirmed it).
- A spec fix in this repo does not change the status; the row tracks the dbGaP side.

Versions checked: FHS phs000007.v35.p16, ARIC phs000280.v9, HCHS/SOL phs000810.v2.

| id | cohort | phs / pht / phv | variable | what dbGaP says | what is true + aggregate evidence | HV issue | status |
|---|---|---|---|---|---|---|---|
| 1 | FHS | phs000007.v35 / pht001045 / phv00081030 | WBC | Unit `mm3 (1,000,000/microliter)` | White cell count is in thousands per microliter. The unit text is copied from the RBC row above it (phv00081029, `mm3 (1,000,000 per microliter)`), where it is correct. var_report: WBC mean 6.89, range 2.2-51.5 (a 10^3/uL scale); RBC mean 4.50. | #822 | found |
| 2 | FHS | phs000007.v35 / pht000103 / phv00022597, phv00022598, phv00022601, phv00022603, phv00022604, phv00022605 | FVC_B, FEV1_B, FEV3_B, PEFR_B, MMEF_B, FEF25_B | Descriptions say "TRIAL 1" | These `_B` variables are trial 2. The rest of the `_B` set in the same table (AST_B phv00022599, RAT1_B phv00022600) says "TRIAL 2"; only the suffix distinguishes trial 1 from trial 2. | #822 | found |
| 3 | HCHS/SOL | phs000810.v2 / pht004715 / phv00253218 | ANTA4 | Description "Weight (kg) (ANTA4)", unit `kg/m2` | Unit is kg. `kg/m2` is copied from the adjacent BMI row (phv00226255), where it is correct. var_report: mean 78.6, range 34.5-189.2 (a body weight in kg). | #822 | found |
| 4 | ARIC | phs000280.v9 / pht004064 / phv00204841; pht012813 / phv00511964 | ECGMI32 (Visit 3), ECGMI41 (Visit 4) | "Prevalent myocardial infarction from adjudicated ECG": codes `0 = Yes`, `1 = No`, `T = Missing` | The labels are inverted: 0 = No, 1 = Yes. var_report v9: ECGMI32 0 = 11,904, 1 = 144; ECGMI41 0 = 10,784, 1 = 96. A prior MI in about 98% of ARIC is not possible. The sibling variable MACHMI31 (phv00204842) is labelled `0 = No` (11,891), `1 = Yes` (152), which matches expected prevalence. | #869 | found |
| 5 | FHS | phs000007.v35 / pht000016 / phv00002416; pht000017 / phv00002654 | FG312 (Original Exam 14), FH331 (Original Exam 15) | "BLOOD ANALYSIS, CREATININE", unit `MG/100 ML` (= mg/dL) | Values are in tenths of mg/dL. var_report: FG312 n=2,681, mean 10.11, range 3-110; FH331 n=2,419, mean 11.32, range 4-61. The same exams in pht007777 (CREAT14 phv00369801, CREAT15 phv00369802, unit mg/dL) have the same n and means 1.011 and 1.132, a factor of 10 lower. | #143 | found |
| 6 | FHS | phs000007.v35 / pht000024 / phv00004962; pht000026 / phv00006134, phv00006135 | FO109 (Original Exam 22), FQ149, FQ150 (Original Exam 24) | FO109, FQ149: "MEDICATION USE: ALPHA-1 AGONIST (CLONIDINE, WYTENSIN, GUANABENZ)". FQ150: "MEDICATION USE - ALPHA-2 AGONIST (PRAZOSIN, TERAZOSIN, DOXAZOSIN)" | The class names are swapped and FQ150's class is wrong in kind. Clonidine, Wytensin (guanabenz) and guanabenz are centrally acting alpha-2 agonists; prazosin, terazosin and doxazosin are alpha-1 blockers (antagonists). The drug lists inside each label are what the variables collect. FHS `med_use.yaml` follows the wrong class names; `tak_cenactag.yaml` and `tak_alphablk.yaml` follow the drug lists. | #785 | found |
