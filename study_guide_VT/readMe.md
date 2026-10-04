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

Classes covered: `Condition`, `MeasurementObservation`, `MeasurementObservationSet`,
`DrugExposure`, `Procedure`, `Observation`, `SdohObservation`, `Demography`, `Person`.
Every class uses the same pattern. A class whose concepts each have one code may put the
`CURIE` in its Concepts file and skip the Variables file. There is no `Diagnosis` class in
BDC-HM; diagnoses are `Condition`.

## Checking the files

`python study_guide_VT/validate_study_guides.py` checks the files mechanically (names match
across files, no blank key cells, well-formed codes, valid output file names, UCUM-looking
units, numeric concepts have a unit). It runs automatically on every PR that touches this
folder and must pass before merge. It does not judge whether content is clinically right --
that is what review is for.

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

- `DrugExposure` codes are ATC classes or RxNorm ingredients (see the open question on
  which BDC-HM accepts). `Procedure`, `Observation`, `SdohObservation`, `Demography` and
  `Person` codes or enum values must be valid on BDC-HM `main`.
- A concept may list a second code that HV production already uses (a "variant"), so
  existing transform files stay valid. The first code listed is the preferred one.

## Columns

Concepts files use these columns where they apply (a class with no quantities omits the unit
columns):

- `Concept` (or `concept`) -- the name, which is the key.
- `CURIE` -- the code, when the class has no Variables file.
- `Concept Description` -- what it is, plus "Use when ...; not for ..." rules for concepts that
  are easy to confuse, and notes where the definition changed over time (for example diabetes
  or hypertension thresholds).
- `data type` -- decimal, integer, enum, boolean or string.
- `target unit` -- the UCUM unit the harmonized data is delivered in. Required for decimal and
  integer concepts.
- `other units and conversion` -- filled only where converting to the target depends on the
  analyte (for example `mmol/L x18.016` for glucose). Blank otherwise. Plain conversions (lb
  to kg, mg/L to mg/dL) are left to UCUM and never written here.
- `conversion source` -- the citation for each factor (for example the molar mass with its
  PubChem ID). A factor without a source is not used.
- `Members` (MeasurementObservationSet only) -- the MeasurementObservation concept names in
  the set, `|`-separated, spelled exactly as in the MeasurementObservation files.
- `output file` -- the transform YAML file the concept is written to: the bare file name,
  lowercase with underscores, no `.yaml` (for example `blood_pressure`). One file per
  concept; several concepts may share a file. It decides where output goes only; it is never
  the concept's identity.
- Example lists are `|`-separated. Labels and descriptions do not need to line up one to one.
  Example descriptions are copied verbatim from dbGaP, typos included, because they are used
  to match real source text.

Metadata files use `bdchm slot`, `bdchm value enum`, `description`,
`Example source variable description`: one row per slot, and one row per enum value of that
slot, each row repeating the slot name.

## Fasting and bronchodilator status

Fasting and bronchodilator status are recorded as Context on the measurement
(`activity_type` FASTING or BRONCHODILATOR_MEDICATION_USE, with `relative_timing` and
`time_duration`), including when the concept name itself says fasting or post-bronchodilator.
No Context means the status is unknown, never "not fasting" or "pre-bronchodilator".
(Whether the separate "- fasting" and "post bronchodilator" concepts stay is an open question.)
