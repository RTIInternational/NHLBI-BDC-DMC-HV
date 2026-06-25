#!/usr/bin/env python3
"""
Generate pre-harmonized data counts by variable and PHV, filtered to Corey's PHV list.
Creates a CSV report compatible with the Data Harmonization Supplementary Data template.
"""

import argparse
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


def find_transform_comment_column(df):
    """Find the Transform Comment column (case-insensitive)."""
    for col in df.columns:
        if col.lower() == 'transform comment':
            return col
    return None


def load_from_bdchm_sheet():
    """Load data from the BDCHM Google Sheet and return normalized DataFrame."""
    try:
        sheet = load_gsheet_as_df("Export_BDCHM_noFHS-noCOPDGene_phv_mappings",
                                 "Export_BDCHM_noFHS-noCOPDGene_p")
    except Exception as e:
        print(f"Error loading BDCHM Google Sheet: {e}")
        return None

    print(f"Loaded BDCHM sheet with {len(sheet)} rows and columns: {list(sheet.columns)}")

    # Filter out rows where Transform Comment is "out of scope"
    transform_comment_col = find_transform_comment_column(sheet)
    if transform_comment_col:
        before_count = len(sheet)
        sheet = sheet[sheet[transform_comment_col].str.lower() != 'out of scope']
        print(f"Filtered out {before_count - len(sheet)} 'out of scope' rows from BDCHM")

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

    # Filter out rows where Transform Comment is "out of scope"
    transform_comment_col = find_transform_comment_column(sheet)
    if transform_comment_col:
        before_count = len(sheet)
        sheet = sheet[sheet[transform_comment_col].str.lower() != 'out of scope']
        print(f"Filtered out {before_count - len(sheet)} 'out of scope' rows from FHS")

    phv = sheet['Variable accession'] # Col H
    phv = phv.str.replace(r'\..*', '', regex=True)
    bdch_label = sheet['BDCHM Label'] # Col J
    cohort = 'FHS'
    n_stats = sheet['data_table.variable.total.stats.stat.n'].apply(parse_stats_column) # Col U

    normalized_df = pd.DataFrame({
        'phv': phv,
        'bdchm_label': bdch_label,
        'cohort': cohort,
        'n_stats': n_stats,
        # Source-level provenance, carried through only to power --debug-variable.
        'src_name': sheet['Source Variable name'],
        'src_desc': sheet['Source Variable description'],
        'src_units': sheet['data_table.variable.units'],
        'src_min': sheet['data_table.variable.total.stats.stat.min'],
        'src_max': sheet['data_table.variable.total.stats.stat.max'],
    })
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


def debug_variable(sheet, valid_phvs, variable, cohort):
    """Dump the phvs S4 counts for one variable/cohort, stage by stage.

    Mirrors the filter the main loop in generate_report() applies (the
    dropna guard and the valid-phvs membership test) so the dump cannot
    drift from the counts the report actually emits.  Note the 'out of
    scope' Transform Comment rows are already removed upstream in the
    per-sheet loaders, so they never reach *sheet* — what prints here is
    everything that survived that earlier drop.
    """
    print("\n" + "=" * 70)
    print(f"  DEBUG: variable={variable!r}  cohort={cohort!r}")
    print("=" * 70)

    match = sheet[
        (sheet['bdchm_label'] == variable) & (sheet['cohort'] == cohort)
    ].copy()

    # Same row-level guard the main loop uses before counting a row.
    valid = match.dropna(subset=['bdchm_label', 'phv', 'cohort'])
    dropped_na = len(match) - len(valid)

    valid_list = valid_phvs.get(cohort)
    if valid_list is not None:
        in_list = valid[valid['phv'].isin(valid_list)]
        not_in_list = valid[~valid['phv'].isin(valid_list)]
    else:
        in_list = valid
        not_in_list = valid.iloc[0:0]

    print(f"rows matching {variable!r}/{cohort}: {len(match)} "
          f"(dropped {dropped_na} for NaN bdchm_label/phv/cohort)")
    print(f"valid-phvs list for {cohort}: "
          f"{'present (' + str(len(valid_list)) + ' phvs)' if valid_list is not None else 'NONE — all phvs counted'}")

    def _first(rows, col):
        """First non-null source value for a phv group, or '' if absent."""
        if col not in rows.columns:
            return ''
        vals = rows[col].dropna()
        return str(vals.iloc[0]) if len(vals) else ''

    counted = sorted(in_list['phv'].unique())
    print(f"\nFINAL COUNTED phvs ({len(counted)}):")
    for p in counted:
        rows = in_list[in_list['phv'] == p]
        n = int(rows['n_stats'].sum())
        print(f"  {p}   n={n:,}")
        name, units = _first(rows, 'src_name'), _first(rows, 'src_units')
        smin, smax = _first(rows, 'src_min'), _first(rows, 'src_max')
        desc = _first(rows, 'src_desc')
        if any([name, units, smin, smax, desc]):
            print(f"      name={name!r}  units={units!r}  src_min={smin}  src_max={smax}")
            if desc:
                print(f"      desc={desc[:120]!r}")

    if valid_list is not None and len(not_in_list):
        excluded = sorted(not_in_list['phv'].unique())
        print(f"\nEXCLUDED by valid-phvs filter ({len(excluded)}):")
        for p in excluded:
            n = int(not_in_list[not_in_list['phv'] == p]['n_stats'].sum())
            print(f"  {p}   n={n:,}")
    print("=" * 70 + "\n")


def generate_report(debug_variable_name=None, debug_cohort='FHS'):
    """Generate the pre-harmonized data report."""
    print("Loading PHV lists...")
    valid_phvs = load_valid_phvs()

    # Load source data
    sheet = load_source_data()
    if sheet is None:
        return None

    if debug_variable_name:
        debug_variable(sheet, valid_phvs, debug_variable_name, debug_cohort)
    
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--debug-variable", metavar="LABEL", default=None,
        help="Dump the phvs counted for this BDCHM label (e.g. 'AST SGOT') "
             "stage by stage, then still generate the full report.",
    )
    parser.add_argument(
        "--debug-cohort", metavar="COHORT", default="FHS",
        help="Cohort to inspect with --debug-variable (default: FHS).",
    )
    args = parser.parse_args()
    generate_report(
        debug_variable_name=args.debug_variable,
        debug_cohort=args.debug_cohort,
    )