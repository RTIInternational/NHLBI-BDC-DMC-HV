# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current Focus: generate_variable_documentation.py

This script generates variable documentation from Google Sheets data. The script:
- Loads data from "BDCHM Variable Mapping" Google Sheet
- Filters for MeasurementObservation, Demography, and SdohObservation elements
- Generates a markdown file with the variable documentation

### Changes needed
Instead of tabular display, generate prettier documentation

### Dependencies
- pandas
- gspread (for Google Sheets access)
- gspread_dataframe

### Google Sheets Authentication
Requires credentials in ~/.config/gspread/service_account.json and the sheet must be shared with the service account email.