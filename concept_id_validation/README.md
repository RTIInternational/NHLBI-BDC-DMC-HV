# OMOP Concept ID Validation

Validates OMOP concept IDs in the [BDCHM Priority
Variables](https://docs.google.com/spreadsheets/d/1G-AIk2m4UCDfh1OvFID3bewQXqxExeKNNmVxaswLT8E/edit?gid=2039879463#gid=2039879463)
spreadsheet against the OHDSI vocabulary via the [ATLAS
WebAPI](https://github.com/OHDSI/WebAPI).

## Source data

Google Sheet: **DO NOT EDIT BDCHM Prioritization Information**,
worksheet: **BDCHM Priority Variables**

Columns used:
| Column | Spreadsheet column |
|--------|--------------------|
| A | DOMAIN |
| F | Variable (Label) |
| G | Variable (Machine Readable Name) |
| P | OMOP Standard Concept ID |
| Q | target_vocab_id |

## How it works

1. Loads the spreadsheet via `gspread` (service account credentials at
   `~/.config/gspread/service_account.json`)
2. Extracts rows with numeric concept IDs (rows with values like `?` or
   `434489 or 4306655` are skipped and reported)
3. Looks up each unique concept ID via
   `GET https://atlas-demo.ohdsi.org/WebAPI/vocabulary/OHDSIEVIDNET/concept/{id}`
4. Compares source values against the OMOP vocabulary and writes
   `concept_id_validation.csv`

## Output columns

The CSV groups comparisons in blocks separated by blank columns (`_1`, `_2`, `_3`):

| Column | Description |
|--------|-------------|
| `concept_id` | OMOP concept ID from spreadsheet |
| `OMOP_std` | OMOP `standard_concept` field (`S` = Standard, `C` = Classification, `N` = Non-standard, `NOT FOUND` = ID doesn't exist) |
| `src_concept_name` | Variable (Label) from spreadsheet |
| `OMOP_concept_name` | `CONCEPT_NAME` from OMOP |
| `name_diff` | `DIFF` if names differ (case-insensitive) |
| `src_domain` | DOMAIN from spreadsheet |
| `OMOP_domain_id` | `DOMAIN_ID` from OMOP |
| `domain_diff` | `DIFF` if domains differ (case-insensitive) |
| `src_vocabulary_id` | target_vocab_id from spreadsheet |
| `OMOP_vocabulary_id` | `VOCABULARY_ID` from OMOP |
| `vocab_diff` | `DIFF` if vocabularies differ (case-insensitive) |
| `src_var_name` | Variable (Machine Readable Name) from spreadsheet |

## Usage

```bash
uv run python concept_id_validation/validate_concept_ids.py
```

## What to look for in the output

- **`OMOP_std` != `S`** -- concept exists but is not a standard concept
  (Classification or Non-standard). These may need to be replaced with
  standard equivalents.
- **`NOT FOUND`** -- concept ID doesn't exist in the OMOP vocabulary.
- **`domain_diff` = `DIFF`** -- worth reviewing. Some are expected naming
  differences (e.g., DIAGNOSIS vs Condition, MEDICATION vs Drug). Others
  may indicate a concept was assigned to the wrong domain.
- **`vocab_diff` = `DIFF`** -- minor formatting differences (e.g., CPT-4 vs
  CPT4) or actual mismatches.
- **`name_diff` = `DIFF`** -- expected in most cases since the spreadsheet uses
  short labels while OMOP has formal clinical terms. Useful for spotting
  cases where the wrong concept was selected.
