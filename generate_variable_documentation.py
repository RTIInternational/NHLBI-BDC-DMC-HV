import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe, get_as_dataframe

def root_dir():
    # this script is currently in the root directory, so
    return '.'

def main():
    # reading from:
    # https://docs.google.com/spreadsheets/d/1hxbZxSxR88HnBXjcgdeJD1AOj-pzlxMrnx5n_YLkEF0/edit?gid=2039879463#gid=2039879463
    sheet = load_gsheet_as_df("BDCHM Variable Mapping", "BDCHM Harmonized Variables V1")
    # table = pd.DataFrame.to_markdown(sheet.head())

    df = pd.DataFrame({
        'BDCHM element':            sheet['BDCHM.Element.Attribute'].str.split('.', n=1).str[0],
        'variable label':           sheet['Variable (Label)'],
        'machine-readable label':   sheet['Variable (Machine Readable Name)'],
        'datatype':                 sheet['Standardized Data Type'],
        'unit':                     sheet['Standardized Unit'],
        'OMOP concept id as CURIE': 'OMOP:' + sheet['OMOP Standard Concept ID'].astype(str),
        'OMOP UCUM id as CURIE':    sheet['OMOP UCUM CURIE'],
        'OBA CURIE':                sheet['OBA CURIE'],
        'UCUM unit':                sheet['UCUM unit'],
        'Text definition':          sheet['Text definition'],
    })

    # only keep MeasurementObservation, Demography, SdohObservation
    df = df[df['BDCHM element'].isin(['MeasurementObservation', 'Demography', 'SdohObservation'])]

    by_element = df.groupby('BDCHM element')

    with open(f'{root_dir()}/VARIABLE_DOCUMENTATION.md', 'w') as f:
        f.write("# BDCHM Variable Documentation\n\n")
        
        for grp, grp_df in by_element:
            f.write(f"## {grp}\n\n")
            
            for _, row in grp_df.iterrows():
                f.write(f"### {row['variable label']}\n\n")
                f.write(f"**Machine-readable name:** `{row['machine-readable label']}`\n\n")
                
                if row['Text definition']:
                    f.write(f"{row['Text definition']}\n\n")
                
                f.write("**Properties:**\n")
                f.write(f"- **Datatype:** {row['datatype']}\n")
                if row['unit']:
                    f.write(f"- **Unit:** {row['unit']}\n")
                if row['UCUM unit']:
                    f.write(f"- **UCUM Unit:** {row['UCUM unit']}\n")
                
                f.write("\n**Ontology References:**\n")
                if row['OMOP concept id as CURIE'] and not row['OMOP concept id as CURIE'].endswith('nan'):
                    f.write(f"- **OMOP:** {row['OMOP concept id as CURIE']}\n")
                if row['OBA CURIE']:
                    f.write(f"- **OBA:** {row['OBA CURIE']}\n")
                if row['OMOP UCUM id as CURIE']:
                    f.write(f"- **OMOP UCUM:** {row['OMOP UCUM id as CURIE']}\n")
                
                f.write("\n---\n\n")

    pass

def load_gsheet_as_df(spreadsheet_name: str, worksheet_name: str) -> pd.DataFrame:
    """
    Needs to find credentials in ~/.config/gspread/service_account.json.
    And you have to share the google sheet with the service account email address
    Instructions: https://docs.gspread.org/en/v6.1.3/oauth2.html
    """
    gc = gspread.service_account()
    spreadsheet = gc.open(spreadsheet_name)
    worksheet = spreadsheet.worksheet(worksheet_name)
    df = get_as_dataframe(worksheet).dropna(how='all').dropna(axis=1, how='all')
    df = df.fillna('')
    return df

if __name__ == "__main__":
    main()