# Study guides -- priority concepts source of record

These files are the source of record for the BDC priority concepts: which concepts we
harmonize, the code each one uses, and the rules for filling each BDC-HM slot. They replace
the V1 and V2 priority-variable spreadsheets, one class at a time.

**DRAFT -- proposed for review. Everything below is open to change.**

## Approval

- `main` is the source of truth. A change is approved when its PR is merged to `main`.
- Commits treated as releases are tagged (for example `study-guides-2026-10`), so a
  pipeline run can name exactly which version it used.
- Work in progress stays on a branch until it is reviewed.

## Files

One set of files per BDC-HM class, named with the exact BDC-HM class name:

| File | Holds |
|---|---|
| `<Class> Concepts.tsv` | one row per concept: name, description, and the columns below |
| `<Class> Variables.tsv` | one row per code: concept name, variable, CURIE, description (several rows per concept are fine) |
| `<Class> Metadata.tsv` | one row per slot or slot value: how to fill each BDC-HM slot, with examples |

Classes so far: `Condition`, `MeasurementObservation`. Others to follow use the same
pattern (`DrugExposure`, `Procedure`, `Observation`, `MeasurementObservationSet`,
`SdohObservation`). There is no `Diagnosis` class in BDC-HM; diagnoses are `Condition`.

## Concept names are the key

The concept name joins the files to each other and to the harmonization pipeline.

1. **Spell each name the same in every file.** Capitalisation, punctuation and extra spaces
   are ignored when names are compared, so `Respiratory Rate` and `respiratory rate` are the
   same concept. Different words or spelling are not: `BNP` and `BNP in blood` are two
   names.
2. **Call out renames in the PR description** (old name -> new name), so downstream users can
   carry the change over.
3. Every row repeats its slot or concept name; a blank cell never means "same as the row
   above".

## Codes

- `Condition` codes are Mondo (preferred) or HPO. A small number of conditions use an OMOP
  code where no suitable Mondo/HPO code exists; currently `Interstitial lung abnormality`
  (OMOP:37472817) and `Carotid plaque` (OMOP:4102124).
- `MeasurementObservation` codes come from OBA, OMOP (LOINC/SNOMED), CMO, EFO, NCIT, etc.
  A concept may list several codes in the Variables file (for example serum vs plasma, or
  sitting vs standing). Use the most specific one the source variable supports.
- Never enter a code that has not been looked up and confirmed in its source ontology.

## Columns

**Condition Concepts:** `concept`, `CURIE`, `description`, `Example source variable labels`,
`Example source variable description`, `output file`.

**MeasurementObservation Concepts:** `Concept`, `Concept Description`, `target unit`,
`other units and conversion`, `output file`, and, for concepts that are easy to confuse,
`Example source variable labels` and `Example source variable description`.

- `target unit` -- the UCUM unit the harmonized data is delivered in.
- `other units and conversion` -- filled only where converting to the target depends on the
  analyte (for example `mmol/L x18.016` for glucose). Blank otherwise.
- `output file` -- the transform YAML file the concept is written to: the bare file name,
  lowercase with underscores, no `.yaml` (for example `blood_pressure`). One file per
  concept; several concepts may share a file. It decides where output goes only; it is never
  the concept's identity.
- Example lists are `|`-separated. Labels and descriptions do not need to line up one to one.
  Example descriptions are copied verbatim from dbGaP, typos included, because they are used
  to match real source text.
