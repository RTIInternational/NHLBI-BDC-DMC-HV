#!/usr/bin/env python3
"""
Generate pre-harmonized data counts by variable and PHV, filtered to Corey's PHV list.
Creates a CSV report compatible with the Data Harmonization Supplementary Data template.
"""

import pandas as pd
import ast
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
    """Parse the var_report.variable.total.stats.stat.n value from column U."""
    if pd.isna(stats_str) or not stats_str:
        return 0
    
    try:
        # Try to parse as literal (dict/list structure)
        stats = ast.literal_eval(str(stats_str))
        
        # Navigate the nested structure: var_report.variable.total.stats.stat.n
        if isinstance(stats, dict):
            variable = stats.get('variable', {})
            total = variable.get('total', {})
            stats_section = total.get('stats', {})
            stat = stats_section.get('stat', {})
            n_value = stat.get('n', 0)
            return int(n_value) if n_value else 0
    except:
        # If parsing fails, try to extract number directly
        try:
            return int(float(str(stats_str)))
        except:
            return 0
    
    return 0


def generate_report():
    """Generate the pre-harmonized data report."""
    print("Loading PHV lists...")
    valid_phvs = load_valid_phvs()
    
    print("Loading data from Google Sheets...")
    try:
        sheet = load_gsheet_as_df("Export_BDCHM_noFHS-noCOPDGene_phv_mappings", 
                                 "Export_BDCHM_noFHS-noCOPDGene_p")
    except Exception as e:
        print(f"Error loading Google Sheet: {e}")
        return None
    
    print(f"Loaded sheet with {len(sheet)} rows and columns: {list(sheet.columns)}")
    
    # Expected columns based on CLAUDE.md description:
    # Col C: PHV
    # Col D: BDCHM Label (variable name)
    # Col F: Study/Cohort
    # Col U: var_report.variable.total.stats.stat.n
    
    # Map column indices to names (0-based)
    col_mapping = {
        'phv': sheet.columns[2],  # Column C
        'bdchm_label': sheet.columns[3],  # Column D  
        'cohort': sheet.columns[5],  # Column F
        'n_stats': sheet.columns[20] if len(sheet.columns) > 20 else None  # Column U
    }
    
    print("Column mapping:")
    for key, col in col_mapping.items():
        print(f"  {key}: {col}")
    
    # Get unique variables from the template/priority list
    # For now, we'll use all unique BDCHM labels in the data
    priority_variables = sheet[col_mapping['bdchm_label']].dropna().unique()
    print(f"Found {len(priority_variables)} priority variables")
    
    # Initialize result structure
    results = {}
    cohorts_in_data = set()
    cohorts_with_valid_phvs = set(valid_phvs.keys())
    
    # Process each row
    for idx, row in sheet.iterrows():
        variable = row[col_mapping['bdchm_label']]
        phv = row[col_mapping['phv']]
        cohort = row[col_mapping['cohort']]
        
        if pd.isna(variable) or pd.isna(phv) or pd.isna(cohort):
            continue
            
        cohorts_in_data.add(cohort)
        
        # Skip if cohort doesn't have valid PHV list or PHV not in valid list
        if cohort not in valid_phvs or phv not in valid_phvs[cohort]:
            continue
        
        # Parse n value
        n_value = 0
        if col_mapping['n_stats'] and col_mapping['n_stats'] in row:
            n_value = parse_stats_column(row[col_mapping['n_stats']])
        
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
    output_file = Path(__file__).parent / "preharmonized_data_report.csv"
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