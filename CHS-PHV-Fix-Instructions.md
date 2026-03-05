# CHS PHV Correction Instructions for HV Repo Agent

**Branch:** `csiege_rtiintl/issue348`  
**Repo:** `RTIInternational/NHLBI-BDC-DMC-HV`  
**Base path:** `priority_variables_transform/CHS-ingest/`  
**Date:** 2026-03-05

These are exact edit instructions derived from a comprehensive phv-to-pht audit that cross-referenced every phv in 82 CHS YAML files against the dbGaP data dictionary (phs000287.v7.p1). Apply all edits on the `csiege_rtiintl/issue348` branch.

---

## Fix 1: tak_aceinhib.yaml — Restore pht001474 blocks (3 edits)

**Problem:** Three class_derivation blocks that contain drug_concept phvs belonging to pht001474 (YR10) were incorrectly moved under pht001452 (BASEBOTH). The drug_concept phvs (phv00102002, phv00102093, phv00102094) are correct for pht001474, but the `associated_participant` phv was wrong. The fix is to change `populated_from` back to `pht001474`, update the visit, and fix the Individual_ID.

### Edit 1a: Block with phv00102002

Find this exact text:
```yaml
- class_derivations:
    DrugExposure:
      populated_from: pht001452
      slot_derivations:
        associated_participant:
          populated_from: phv00100285
        associated_visit:
          value: CHS BASELINE BOTH
          range: string
        drug_concept:
          expr: case(({phv00102002} == 1, '''RxCUI:C09A'''))
        expsoure_provenance:
          value: PATIENT SELF-REPORTED MEDICATION
          range: string
```

Replace with:
```yaml
- class_derivations:
    DrugExposure:
      populated_from: pht001474
      slot_derivations:
        associated_participant:
          populated_from: phv00101324
        associated_visit:
          value: CHS YEAR 10
          range: string
        drug_concept:
          expr: case(({phv00102002} == 1, '''RxCUI:C09A'''))
        expsoure_provenance:
          value: PATIENT SELF-REPORTED MEDICATION
          range: string
```

**What changed and why:**
- `populated_from: pht001452` → `pht001474` — phv00102002 (ANYACE) belongs to pht001474 (YR10), not pht001452 (BASEBOTH)
- `associated_participant: phv00100285` → `phv00101324` — phv00100285 is Individual_ID from BASEBOTH; phv00101324 is Individual_ID from YR10
- `associated_visit: CHS BASELINE BOTH` → `CHS YEAR 10` — matches the YR10 dataset

### Edit 1b: Block with phv00102093

Find this exact text:
```yaml
- class_derivations:
    DrugExposure:
      populated_from: pht001452
      slot_derivations:
        associated_participant:
          populated_from: phv00100285
        associated_visit:
          value: CHS BASELINE BOTH
          range: string
        drug_concept:
          expr: case(({phv00102093} == 1, '''RxCUI:C09A'''))
        expsoure_provenance:
          value: PATIENT SELF-REPORTED MEDICATION
          range: string
```

Replace with:
```yaml
- class_derivations:
    DrugExposure:
      populated_from: pht001474
      slot_derivations:
        associated_participant:
          populated_from: phv00101324
        associated_visit:
          value: CHS YEAR 10
          range: string
        drug_concept:
          expr: case(({phv00102093} == 1, '''RxCUI:C09A'''))
        expsoure_provenance:
          value: PATIENT SELF-REPORTED MEDICATION
          range: string
```

**What changed and why:** Same as 1a — phv00102093 (ACE06) belongs to pht001474 (YR10).

### Edit 1c: Block with phv00102094

Find this exact text:
```yaml
- class_derivations:
    DrugExposure:
      populated_from: pht001452
      slot_derivations:
        associated_participant:
          populated_from: phv00100285
        associated_visit:
          value: CHS BASELINE BOTH
          range: string
        drug_concept:
          expr: case(({phv00102094} == 1, '''RxCUI:C09BA'''))
        expsoure_provenance:
          value: PATIENT SELF-REPORTED MEDICATION
          range: string
```

Replace with:
```yaml
- class_derivations:
    DrugExposure:
      populated_from: pht001474
      slot_derivations:
        associated_participant:
          populated_from: phv00101324
        associated_visit:
          value: CHS YEAR 10
          range: string
        drug_concept:
          expr: case(({phv00102094} == 1, '''RxCUI:C09BA'''))
        expsoure_provenance:
          value: PATIENT SELF-REPORTED MEDICATION
          range: string
```

**What changed and why:** Same as 1a — phv00102094 (ACED06) belongs to pht001474 (YR10). Note this one uses `RxCUI:C09BA` (ACE inhibitors with diuretics).

---

## Fix 2: tak_aceinhib.yaml — Restore pht001490 blocks (3 edits)

**Problem:** Three class_derivation blocks that contain drug_concept phvs belonging to pht001490 (YR5NEW) were incorrectly moved under pht001489 (YR4). Same root cause as Fix 1.

### Edit 2a: Block with phv00105627

Find this exact text:
```yaml
- class_derivations:
    DrugExposure:
      populated_from: pht001489
      slot_derivations:
        associated_participant:
          populated_from: phv00104468
        associated_visit:
          value: CHS YEAR 4
          range: string
        drug_concept:
          expr: case(({phv00105627} == 1, '''RxCUI:C09A'''))
        expsoure_provenance:
          value: PATIENT SELF-REPORTED MEDICATION
          range: string
```

Replace with:
```yaml
- class_derivations:
    DrugExposure:
      populated_from: pht001490
      slot_derivations:
        associated_participant:
          populated_from: phv00105099
        associated_visit:
          value: CHS YEAR 5 NEW
          range: string
        drug_concept:
          expr: case(({phv00105627} == 1, '''RxCUI:C09A'''))
        expsoure_provenance:
          value: PATIENT SELF-REPORTED MEDICATION
          range: string
```

**What changed and why:**
- `populated_from: pht001489` → `pht001490` — phv00105627 (ANYACE) belongs to pht001490 (YR5NEW), not pht001489 (YR4)
- `associated_participant: phv00104468` → `phv00105099` — phv00104468 is Individual_ID from YR4; phv00105099 is Individual_ID from YR5NEW
- `associated_visit: CHS YEAR 4` → `CHS YEAR 5 NEW` — matches the YR5NEW dataset

### Edit 2b: Block with phv00106435

Find this exact text:
```yaml
- class_derivations:
    DrugExposure:
      populated_from: pht001489
      slot_derivations:
        associated_participant:
          populated_from: phv00104468
        associated_visit:
          value: CHS YEAR 4
          range: string
        drug_concept:
          expr: case(({phv00106435} == 1, '''RxCUI:C09A'''))
        expsoure_provenance:
          value: PATIENT SELF-REPORTED MEDICATION
          range: string
```

Replace with:
```yaml
- class_derivations:
    DrugExposure:
      populated_from: pht001490
      slot_derivations:
        associated_participant:
          populated_from: phv00105099
        associated_visit:
          value: CHS YEAR 5 NEW
          range: string
        drug_concept:
          expr: case(({phv00106435} == 1, '''RxCUI:C09A'''))
        expsoure_provenance:
          value: PATIENT SELF-REPORTED MEDICATION
          range: string
```

**What changed and why:** Same as 2a — phv00106435 (ACE06) belongs to pht001490 (YR5NEW).

### Edit 2c: Block with phv00106436

Find this exact text:
```yaml
- class_derivations:
    DrugExposure:
      populated_from: pht001489
      slot_derivations:
        associated_participant:
          populated_from: phv00104468
        associated_visit:
          value: CHS YEAR 4
          range: string
        drug_concept:
          expr: case(({phv00106436} == 1, '''RxCUI:C09BA'''))
        expsoure_provenance:
          value: PATIENT SELF-REPORTED MEDICATION
          range: string
```

Replace with:
```yaml
- class_derivations:
    DrugExposure:
      populated_from: pht001490
      slot_derivations:
        associated_participant:
          populated_from: phv00105099
        associated_visit:
          value: CHS YEAR 5 NEW
          range: string
        drug_concept:
          expr: case(({phv00106436} == 1, '''RxCUI:C09BA'''))
        expsoure_provenance:
          value: PATIENT SELF-REPORTED MEDICATION
          range: string
```

**What changed and why:** Same as 2a — phv00106436 (ACED06) belongs to pht001490 (YR5NEW). Note this one uses `RxCUI:C09BA`.

---

## Fix 3: asthma.yaml — Replace YR5NEW phvs in pht001492 (YR6) block

**Problem:** The class_derivation block with `populated_from: pht001492` (YR6) uses three phv references in its `age_at_condition_end` expression that belong to pht001490 (YR5NEW), not pht001492 (YR6). YR6 has equivalent asthma variables that should be used instead.

**Mapping of YR5NEW → YR6 equivalent phvs:**

| YR5NEW phv | Var Name | Description | YR6 Equivalent | Var Name | Description |
|-----------|----------|-------------|----------------|----------|-------------|
| phv00106022 | ASTH57 | ASTHMA | phv00107849 | ASTHMA56 | EVER HAD ASTHMA |
| phv00106023 | ASTHH57 | DO YOU STILL HAVE IT | phv00107850 | ASSTIL56 | STILL HAVE ASTHMA |
| phv00106026 | ASTHST57 | AT WHAT AGE DID IT STOP | phv00107853 | ASSTOP56 | AT WHAT AGE DID ASTHMA STOP |

Find this exact text in `asthma.yaml`:
```yaml
- class_derivations:
    Condition:
      populated_from: pht001492
      slot_derivations:
        associated_participant:
          populated_from: phv00107443
        associated_visit:
          value: CHS YEAR 6
          range: string
        age_at_condition_end:
          expr: case(({phv00106022} == 1, case(({phv00106023} == 0, {phv00106026} * 365))))
        condition_concept:
          value: MONDO:0004979
          range: string
        condition_status:
          expr: case(({phv00107849} == 0, "ABSENT"), ({phv00107850} == 0, "HISTORICAL"),
            (True, "PRESENT"))
        condition_provenance:
          expr: case(({phv00107851} == 1, "CLINICAL_DIAGNOSIS"), ({phv00108215} ==
            1, "CLINICAL_DIAGNOSIS"), ({phv00108216} == 1, "CLINICAL_DIAGNOSIS"),
            (True, "PATIENT_SELF-REPORTED_CONDITION"))
        relationship_to_participant:
          value: ONESELF
          range: string
```

Replace with:
```yaml
- class_derivations:
    Condition:
      populated_from: pht001492
      slot_derivations:
        associated_participant:
          populated_from: phv00107443
        associated_visit:
          value: CHS YEAR 6
          range: string
        age_at_condition_end:
          expr: case(({phv00107849} == 1, case(({phv00107850} == 0, {phv00107853} * 365))))
        condition_concept:
          value: MONDO:0004979
          range: string
        condition_status:
          expr: case(({phv00107849} == 0, "ABSENT"), ({phv00107850} == 0, "HISTORICAL"),
            (True, "PRESENT"))
        condition_provenance:
          expr: case(({phv00107851} == 1, "CLINICAL_DIAGNOSIS"), ({phv00108215} ==
            1, "CLINICAL_DIAGNOSIS"), ({phv00108216} == 1, "CLINICAL_DIAGNOSIS"),
            (True, "PATIENT_SELF-REPORTED_CONDITION"))
        relationship_to_participant:
          value: ONESELF
          range: string
```

**What changed and why:**
Only the `age_at_condition_end` expression changed:
- `{phv00106022}` → `{phv00107849}` — ASTH57 (ASTHMA, YR5NEW) → ASTHMA56 (EVER HAD ASTHMA, YR6)
- `{phv00106023}` → `{phv00107850}` — ASTHH57 (DO YOU STILL HAVE IT, YR5NEW) → ASSTIL56 (STILL HAVE ASTHMA, YR6)
- `{phv00106026}` → `{phv00107853}` — ASTHST57 (AT WHAT AGE DID IT STOP, YR5NEW) → ASSTOP56 (AT WHAT AGE DID ASTHMA STOP, YR6)

Note: the `condition_status` and `condition_provenance` expressions in this block already use correct YR6 phvs (phv00107849, phv00107850, phv00107851, phv00108215, phv00108216).

---

## Fix 4: asthma.yaml — YR5NEW phvs in pht001487 (YR17PH) block ⚠️ NEEDS HUMAN REVIEW

**Problem:** The class_derivation block with `populated_from: pht001487` (YR17PH) and `associated_visit: CHS YEAR 5 NEW` uses two phvs in its `condition_provenance` expression that belong to pht001490 (YR5NEW):
- phv00105885 (ASTHMA — "ASTHMA CONF BY DOCTOR") → belongs to pht001490
- phv00106407 (ASTHCUR — "CURRENT ASTHMA DX BY DOC") → belongs to pht001490

**⚠️ WHY THIS NEEDS HUMAN REVIEW:** The YR17PH dataset contains only **one** asthma variable: phv00103740 (ASTHMA32 — "TOLD BY MD YOU HAD ASTHMA"). There are no YR17PH equivalents for ASTHMA or ASTHCUR. This entire block appears to be a copy-paste error — it's under pht001487 (YR17PH) but the visit says "CHS YEAR 5 NEW" and it uses YR5NEW variables.

**Current content (for reference):**
```yaml
- class_derivations:
    Condition:
      populated_from: pht001487
      slot_derivations:
        associated_participant:
          populated_from: phv00103730
        associated_visit:
          value: CHS YEAR 5 NEW
          range: string
        condition_concept:
          value: MONDO:0004979
          range: string
        condition_status:
          populated_from: phv00103740
          value_mappings:
            '0': '''ABSENT'''
            '1': '''PRESENT'''
        condition_provenance:
          expr: case(({phv00105885} == 1, "CLINICAL_DIAGNOSIS"), ({phv00106407} ==
            1, "CLINICAL_DIAGNOSIS"), (True, "PATIENT_SELF-REPORTED_CONDITION"))
        relationship_to_participant:
          value: ONESELF
          range: string
```

**Options for resolution (pick one):**

**Option A — Change block to pht001490 (YR5NEW):** If this block was meant to represent YR5NEW data, change `populated_from: pht001487` → `populated_from: pht001490` and change `associated_participant: phv00103730` → `phv00105099` (YR5NEW Individual_ID). Also change `condition_status: populated_from: phv00103740` → to use a YR5NEW-specific condition_status variable. This is a bigger structural change.

**Option B — Remove the block entirely:** If this is a redundant/erroneous duplicate of the existing pht001490 block (which already exists in the file at approximately line 480 and properly uses YR5NEW variables), simply delete this entire class_derivation block.

**Option C — Keep as-is and document:** If the cross-dataset references are intentional (using phv00103730 and phv00103740 from YR17PH for subject identity and condition status at the Year 5 visit, with YR5NEW variables for provenance detail), add a comment explaining the cross-reference.

**Recommendation:** Option B (remove the block) is most likely correct. The file already has a proper pht001490 (YR5NEW) block that uses all YR5NEW variables correctly, and this pht001487 block with visit "CHS YEAR 5 NEW" has wrong pht for the visit and mixes phvs from two datasets. Verify with the original mapper's intent before applying.

---

## Summary of All Edits

| File | Fix | Action | Confidence |
|------|-----|--------|------------|
| tak_aceinhib.yaml | 1a | Change pht001452→pht001474, phv00100285→phv00101324, visit→CHS YEAR 10 (block with phv00102002) | **HIGH** — definitive |
| tak_aceinhib.yaml | 1b | Same changes (block with phv00102093) | **HIGH** — definitive |
| tak_aceinhib.yaml | 1c | Same changes (block with phv00102094) | **HIGH** — definitive |
| tak_aceinhib.yaml | 2a | Change pht001489→pht001490, phv00104468→phv00105099, visit→CHS YEAR 5 NEW (block with phv00105627) | **HIGH** — definitive |
| tak_aceinhib.yaml | 2b | Same changes (block with phv00106435) | **HIGH** — definitive |
| tak_aceinhib.yaml | 2c | Same changes (block with phv00106436) | **HIGH** — definitive |
| asthma.yaml | 3 | Replace phv00106022→phv00107849, phv00106023→phv00107850, phv00106026→phv00107853 in pht001492 age_at_condition_end expr | **HIGH** — clear YR6 equivalents exist |
| asthma.yaml | 4 | pht001487 block with YR5NEW visit and phvs — NEEDS HUMAN REVIEW | **MEDIUM** — probably remove the block |

### Verification

After applying all edits, the phv-to-pht audit should show:
- **Before fixes:** 28 phv-in-wrong-pht issues in branch
- **After Fix 1+2:** 22 issues (6 new tak_aceinhib issues resolved)
- **After Fix 3:** 19 issues (3 YR6 asthma phvs resolved)
- **After Fix 4 (if Option B):** 17 issues (2 YR17PH/YR5NEW phvs resolved)
- **Remaining 17 (or 19):** All are cross-dataset age references (AGEBL phv00100487 and AGE01 phv00098799) that need architectural review — not simple phv-correction bugs.
