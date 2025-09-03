#!/usr/bin/env python3
"""
Generate pre-harmonized data counts by variable and PHV, filtered to Corey's PHV list.
Creates a CSV report compatible with the Data Harmonization Supplementary Data template.
"""

import pandas as pd
from pathlib import Path
from variable_documentation.generate_variable_documentation import load_gsheet_as_df


def load_valid_phvs():
    """Load valid PHV lists from valid-phvs directory."""
    phv_lists = {}
    valid_phvs_dir = Path(__file__).parent / "valid-phvs"
    
    if not valid_phvs_dir.exists():
        print(f"Warning: valid-phvs directory not found at {valid_phvs_dir}")
        return phv_lists
    
    cohort_mapping = {
        'chs-ingest.tsv': 'CHS',
        'copdgene-ingest.tsv': 'COPDGene',
        'fhs-ingest.tsv': 'FHS',
        'hchs-ingest.tsv': 'HCHS/SOL',
        'mesa-ingest.tsv': 'MESA',
        'whi-ingest.tsv': 'WHI'
    }
    
    for filename, cohort in cohort_mapping.items():
        phv_file = valid_phvs_dir / filename
        if phv_file.exists():
            try:
                with open(phv_file, 'r') as f:
                    phvs = [line.strip() for line in f if line.strip()]
                    phv_lists[cohort] = set(phvs)
                    print(f"Loaded {len(phvs)} PHVs for {cohort}")
            except Exception as e:
                print(f"Error loading PHVs for {cohort}: {e}")
        else:
            print(f"Warning: No PHV file found for {cohort} at {phv_file}")
    
    return phv_lists


def parse_stats_column(stats_str):
    """Parse the n value from the stats column."""
    if pd.isna(stats_str) or not stats_str:
        return 0
    
    try:
        return int(float(str(stats_str)))
    except:
        return 0


def load_from_bdchm_sheet():
    """Load data from the BDCHM Google Sheet and return normalized DataFrame."""
    try:
        sheet = load_gsheet_as_df("Export_BDCHM_noFHS-noCOPDGene_phv_mappings", 
                                 "Export_BDCHM_noFHS-noCOPDGene_p")
    except Exception as e:
        print(f"Error loading BDCHM Google Sheet: {e}")
        return None
    
    print(f"Loaded BDCHM sheet with {len(sheet)} rows and columns: {list(sheet.columns)}")

    phv = sheet['First[data_table.variable.id]'] # Col C
    bdch_label = sheet['BDCHM Label'] # Col D
    cohort = sheet['Cohort'] # Col F
    n_stats = sheet['var_report.variable.total.stats.stat.n'].apply(parse_stats_column) # Col U

    normalized_df = pd.DataFrame({'phv': phv, 'bdchm_label': bdch_label, 'cohort': cohort, 'n_stats': n_stats})

    return normalized_df

def load_from_fhs_sheet():
    """Load data from the FHS Google Sheet and return normalized DataFrame."""
    try:
        sheet = load_gsheet_as_df("FHS_VariableProperties",
                                  "right_join_full")
    except Exception as e:
        print(f"Error loading FHS Google Sheet: {e}")
        return None

    print(f"Loaded FHS sheet with {len(sheet)} rows and columns: {list(sheet.columns)}")

    phv = sheet['Variable accession'] # Col H
    phv = phv.str.replace('\..*', '', regex=True)
    bdch_label = sheet['BDCHM Label'] # Col J
    cohort = 'FHS'
    n_stats = sheet['data_table.variable.total.stats.stat.n'].apply(parse_stats_column) # Col U

    normalized_df = pd.DataFrame({'phv': phv, 'bdchm_label': bdch_label, 'cohort': cohort, 'n_stats': n_stats})
    return normalized_df


def load_from_copdgene_sheet():
    """Load data from the COPDGene Google Sheet and return normalized DataFrame."""
    try:
        sheet = load_gsheet_as_df(
            "COPDGene_FullMatchWithManuals_Join_Dedup_XML_BDC Mapped Variables V1",
            "COPDGene_FullMatchWithManuals_J")
    except Exception as e:
        print(f"Error loading FHS Google Sheet: {e}")
        return None

    print(f"Loaded COPDGene sheet with {len(sheet)} rows and columns: {list(sheet.columns)}")

    phv = sheet['First[Variable accession]'] # Col C
    bdch_label = sheet['BDCHM Label'] # Col F
    cohort = sheet['Cohort'] # Col H
    n_stats = sheet['var_report.variable.total.stats.stat.n'].apply(parse_stats_column) # Col AO

    normalized_df = pd.DataFrame({'phv': phv, 'bdchm_label': bdch_label, 'cohort': cohort, 'n_stats': n_stats})
    return normalized_df


def load_source_data():
    """Load and merge data from all source sheets."""
    print("Loading data from Google Sheets...")
    
    # Load from BDCHM sheet
    bdchm_df = load_from_bdchm_sheet()
    fhs_df = load_from_fhs_sheet()
    copdgene_df = load_from_copdgene_sheet()

    combined_df = pd.concat([bdchm_df, fhs_df, copdgene_df], ignore_index=True)

    return combined_df


def generate_report():
    """Generate the pre-harmonized data report."""
    print("Loading PHV lists...")
    valid_phvs = load_valid_phvs()
    
    # Load source data
    sheet = load_source_data()
    if sheet is None:
        return None
    
    # Get unique variables from the template/priority list
    # For now, we'll use all unique BDCHM labels in the data
    priority_variables = sheet['bdchm_label'].dropna().unique()
    print(f"Found {len(priority_variables)} priority variables")
    
    # Initialize result structure
    results = {}
    cohorts_in_data = set()
    cohorts_with_valid_phvs = set(valid_phvs.keys())
    
    # Process each row
    for idx, row in sheet.iterrows():
        variable = row['bdchm_label']
        phv = row['phv']
        cohort = row['cohort']
        n_value = row['n_stats']
        
        if pd.isna(variable) or pd.isna(phv) or pd.isna(cohort):
            continue
            
        cohorts_in_data.add(cohort)
        
        # Skip only if cohort has valid PHV list and PHV not in that list
        if cohort in valid_phvs and phv not in valid_phvs[cohort]:
            continue
        
        # Initialize variable entry
        if variable not in results:
            results[variable] = {}
        
        # Initialize cohort entry for variable
        if cohort not in results[variable]:
            results[variable][cohort] = {'phvs': set(), 'total_n': 0}
        
        # Add PHV and accumulate n
        results[variable][cohort]['phvs'].add(phv)
        results[variable][cohort]['total_n'] += n_value
    
    # Generate CSV data
    csv_rows = []
    all_cohorts = sorted(cohorts_with_valid_phvs.union(cohorts_in_data))
    
    for variable in sorted(priority_variables):
        if variable not in results:
            continue
            
        row_data = {'variable': variable}
        
        for cohort in all_cohorts:
            if variable in results and cohort in results[variable]:
                phv_count = len(results[variable][cohort]['phvs'])
                total_n = results[variable][cohort]['total_n']
                row_data[f'{cohort}_phv'] = phv_count
                row_data[f'{cohort}_n'] = total_n
            else:
                row_data[f'{cohort}_phv'] = ''
                row_data[f'{cohort}_n'] = ''
        
        csv_rows.append(row_data)
    
    # Create DataFrame
    df = pd.DataFrame(csv_rows)
    
    # Save CSV
    output_file = Path(__file__).parent / "preharmonized_qaqc_report.csv"
    df.to_csv(output_file, index=False)
    
    print(f"\nReport saved to: {output_file}")
    print(f"Report contains {len(df)} variables across {len(all_cohorts)} cohorts")
    
    # Print summary info for README
    print(f"\nCohorts in data: {sorted(cohorts_in_data)}")
    print(f"Cohorts with valid-phvs files: {sorted(cohorts_with_valid_phvs)}")
    print(f"Cohorts in data but missing valid-phvs: {sorted(cohorts_in_data - cohorts_with_valid_phvs)}")
    print(f"Cohorts with valid-phvs but not in data: {sorted(cohorts_with_valid_phvs - cohorts_in_data)}")
    
    return df, {
        'cohorts_in_data': sorted(cohorts_in_data),
        'cohorts_with_valid_phvs': sorted(cohorts_with_valid_phvs),
        'missing_valid_phvs': sorted(cohorts_in_data - cohorts_with_valid_phvs),
        'unused_valid_phvs': sorted(cohorts_with_valid_phvs - cohorts_in_data)
    }


if __name__ == "__main__":
    generate_report()