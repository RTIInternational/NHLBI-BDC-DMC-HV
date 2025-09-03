# Pre-harmonized Data QA/QC Report

This directory contains scripts and files for generating pre-harmonized data counts by variable and PHV, filtered to Corey's PHV validation lists.

## Files

- `preharmonized_qaqc_report.py`: Main script to generate the report
- `preharmonized_qaqc_report.csv`: Generated CSV output (created when script runs)
- `valid-phvs/`: Directory containing PHV validation lists for each cohort
- `CLAUDE.md`: Instructions and requirements for the report generation

## Data Sources

### Input Data
- **Description**: Contains pre-harmonized variable mappings with PHV identifiers, cohort assignments, and observation counts
- **Sources**: 
  - [Export_BDCHM_noFHS-noCOPDGene_phv_mappings: Export_BDCHM_noFHS-noCOPDGene_p](https://docs.google.com/spreadsheets/d/1Fg6YFMldjDJWXTjFLJc4eVyXpOWeGoHJyg68i7u0LC4/edit?gid=1528582058#gid=1528582058)
  - [FHS_VariableProperties](https://docs.google.com/spreadsheets/d/1a1JgdRlhdcPfy7uETJiU7GhdB9cDK4ZbeBIIii8os1Q/edit?gid=1781777648#gid=1781777648)
  - [COPDGene_FullMatchWithManuals_Join_Dedup_XML_BDC Mapped Variables V1](https://docs.google.com/spreadsheets/d/1bpRKs73p5nQqFoJECrCGFy7GEkxOZ4nP/edit?gid=308728753#gid=308728753)


### Output Template Reference
- **Template**: [Data Harmonization Supplementary Data - Table S4](https://docs.google.com/spreadsheets/d/1PDaX266_H0haa0aabMYQ6UNtEKT5-ClMarP0FvNntN8/edit?gid=1605543644#gid=1605543644)
- **Description**: Template format for the final publication table with merged cells and multiple header lines

## Generated Output

The script generates `preharmonized_qaqc_report.csv` with the following structure:

- **Columns**: `variable`, `ARIC_phv`, `ARIC_n`, `CARDIA_phv`, `CARDIA_n`, `CHS_phv`, `CHS_n`, etc.
- **PHV columns**: Count of unique PHVs for each variable/cohort combination (after filtering)
- **N columns**: Sum of observation counts for each variable/cohort combination (after filtering)

## Usage Instructions

### Running the Script
```bash
poetry run python preharmonized_qaqc_report.py
```

### Using the Output with the Template
1. Open the [template spreadsheet](https://docs.google.com/spreadsheets/d/1PDaX266_H0haa0aabMYQ6UNtEKT5-ClMarP0FvNntN8/edit?gid=1605543644#gid=1605543644)
2. Copy all rows from `preharmonized_qaqc_report.csv` **except the header row**
3. Paste the data starting at **line 5** of the template (after the merged header section)
4. The template's merged cells and formatting will automatically apply to create the publication-ready Table S4

## Cohort Status

Based on the latest run:

### Cohorts in Input Data
- ARIC, CARDIA, CHS, HCHS/SOL, JHS, MESA, WHI

### Cohorts with PHV Validation Lists
- CHS, COPDGene, FHS, HCHS/SOL, MESA, WHI

### Missing PHV Validation Lists
The following cohorts appear in the input data but don't have PHV validation files:
- **ARIC**: No `valid-phvs/aric-ingest.tsv` file found
- **CARDIA**: No `valid-phvs/cardia-ingest.tsv` file found  
- **JHS**: No `valid-phvs/jhs-ingest.tsv` file found

*Note: Data for these cohorts is included without PHV filtering (all PHVs counted) since no validation lists exist.*

### Unused PHV Validation Lists
The following cohorts have PHV validation files but don't appear in the input data:
- **COPDGene**: Has `valid-phvs/copdgene-ingest.tsv` but no data rows
- **FHS**: Has `valid-phvs/fhs-ingest.tsv` but no data rows

## Filtering Logic

For each priority variable and cohort combination:
1. Find all rows matching the variable name (BDCHM Label column)
2. Filter to rows for the specific cohort
3. **If a validation list exists** (`valid-phvs/{cohort}-ingest.tsv`): exclude PHVs not in the list
4. **If no validation list exists**: include all PHVs for that cohort
5. Count unique PHVs remaining after filtering
6. Sum the observation counts (`var_report.variable.total.stats.stat.n`) for remaining rows

## Notes

- The script handles special cohort name mappings (e.g., "HCHS/SOL" → `hchs-ingest.tsv`)
- Empty cells in the CSV indicate no valid data for that variable/cohort combination
- PHV counts represent unique PHVs per variable/cohort after validation filtering
- Observation counts (n) are cumulative across all valid PHVs for each variable/cohort