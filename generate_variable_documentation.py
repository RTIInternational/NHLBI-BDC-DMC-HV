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
        for grp, grp_df in by_element:
            md = pd.DataFrame.to_markdown(grp_df, index=False)
            f.write(f"# {grp}\n")
            f.write(md)
            f.write('\n')

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