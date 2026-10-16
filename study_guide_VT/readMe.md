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
- `other units and conversion` -- the source units seen and the factor to the target unit
  (for example `mmol/L x18.016` for glucose, which depends on the analyte). Blank when none
  is needed.
- `output file` -- the transform YAML file the concept is written to: the bare file name,
  lowercase with underscores, no `.yaml` (for example `blood_pressure`). One file per
  concept; several concepts may share a file. It decides where output goes only; it is never
  the concept's identity. When the file HV currently writes a concept to disagrees with this
  column, the guide column wins and the existing blocks move. Exceptions still pending Anne's
  decision are noted on the concept row (today: Cardiovascular disease, and the spirometry
  concepts). "Use when" sentences that tell sibling concepts apart go in the `VT notes` column
  where the file has one, and otherwise in the concept description, tagged as below.
- Example lists are `|`-separated. Labels and descriptions do not need to line up one to one.
  Example descriptions are copied verbatim from dbGaP, typos included, because they are used
  to match real source text.

- `VT notes` -- an optional last column for the harmonization (virtual) team's notes, added only
  where needed (today: `Condition Concepts.tsv` and `MeasurementObservation Variables.tsv`).
  Notes are a few short plain sentences, with no tabs, newlines or pipes. Each note starts with
  its source: `[Anne F###]` (or `[Anne F###, F###]`) where it states one of Anne's rulings
  (F### is the finding it came from), `[Anne #NNN]` where it states a ruling she gave in HV
  issue or PR NNN, or `[DRAFT]` where it is the team's draft for her review. A tag covers its
  sentence and the sentences after it, up to the next tag, the next numbered rule such as
  `(2)`, or the end of the cell. Text no tag covers is Anne's. The readMe itself states the
  agreed conventions and is not tagged. Existing `Notes` and team notes columns are left
  untouched, and the empty trailing `DrugExposure Concepts` columns are kept.
- `[DRAFT for Anne]` -- the same marker inside other cells: drafted target units and
  conversions, and team sentences in description or Metadata text (in files with no `VT notes`
  column). An `[Anne F###]` tag inside such text marks a sentence that states her ruling. Tag
  scope is as defined in the `VT notes` bullet above. On acceptance, strip the marker.

## Enum values: name or meaning CURIE

For a BDC-HM enum keyed by CURIE (sex, race, ethnicity, vital status, severity, family
relationship, smoking, education, occupation, SDOH type, drug route, procedure and measurement
type) the transform spec may hold the permissible-value title, where the enum has one (for
example `MALE`, `DEAD`), or its CURIE key (for example `OMOP:8507`). Procedure, measurement type
and occupation values have no title: write the CURIE. The ingest is expected to emit the CURIE
(dm-bip name-to-CURIE translation to be confirmed by a test). An enum keyed by
name, such as `ProvenanceEnum` or the condition status, takes the value name only; several
provenance values have no CURIE.

Retired codes are replaced: unknown sex, race and ethnicity use `OMOP:45877986` (not
`OMOP:8552`, which other enums, such as occupation, still use); the retired severity code
`OMOP:3272197` is replaced by `MODERATE` (`OMOP:4285732`).

## Missing vs UNKNOWN

This applies to every class, including existing specs.

- A missing code (a period, `M` or `Missing`) writes no row. On a one-record-per-participant
  class (Person, Demography) it leaves the slot empty.
- Refused, do not know, and any asked-but-unanswered value write `UNKNOWN`
  (`UNKNOWN_IF_EVER_SMOKED` for smoking), so a researcher can see the question was asked.
- [DRAFT for Anne] A slot with no `UNKNOWN` value (`vital_status`, numeric values) is left
  empty when the answer is not known; `cause_of_death` follows its own rule (5) in Person
  Metadata. Still to settle: this bullet, and the family income bracket text.

## Specimen

Choose the code from the variable name and description. If the source says blood or whole
blood, or does not name the specimen, use the generic blood code. Use a serum or plasma code
only when the variable says serum or plasma. Existing specs are to be swept for this.
