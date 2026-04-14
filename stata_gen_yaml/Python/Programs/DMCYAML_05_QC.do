

/* ----- 1. Output "bad" phvs to a spreadsheet ----- */

clear
local entity = "MeasurementObservation"

foreach cohort in aric cardia fhs jhs whi {	
use "$der\shortdata_$today.dta", clear
keep if row_good==0 | (has_visit!=1 & has_visit_expr!=1)
keep if bdchm_entity=="`entity'"
keep if cohort=="`cohort'"
foreach var in bad_map add_map add_var_units unit_expr_custom unit_casestmt_custom fix_key_note {
	gen `var'=""
	}
order unit_expr_custom, after(unit_expr)
order unit_casestmt_custom, after(unit_casestmt)
sort bdchm_label var_desc phv
save "$out\\`cohort'\fixed\fix_bdchm_mappings_$today.dta", replace
export delimited using "$out\\`cohort'\fixed\fix_bdchm_mappings_$today.csv", nolabel quote replace
}




/* ----- 2. Manually curate "bad" phvs ----- */
/* Manually review the output from previous step. Append new rows with changes to the cohort's master key of fixes: fix_bdchm_mappings_`cohort'.csv . 
 
Curators review each phv in the spreadsheet to remediate failed YAML-readiness validation checks.
Curators may need to consult online documentation from dbGAP or a cohort-maintained website to locate correct metadata values.

Make one or more of the following changes to rows to enable it to pass validation checks:
	1. If source var_units are missing or incorrect:
			1a. Look up the phv in source documentation to identify correct unit
			1b. Enter the standardized UCUM representation of the unit in the var_units column for the phv
			1c. Enter a value of "1" in the column "add_var_units"
	2. If the phv should not have been mapped to the BDCHV identified in column bdchm_varname:
			2a. Enter a value of "1" in the column "bad_map"
			2b. Note: if dbGap reports "no data was collected for this variable", the phv is considered a bad map
			2c. Enter a note in the column fix_key_note
	3. If source var_units are present and correct, but units could not be mapped to the BDC HV units, do one of the following :
			3a. Enter a conversion expression in column "unit_expr_custom"
			3b. Enter a case statement reliant on another phv in column "unit_casestmt_custom"
			3c. Update the documentation file "unit_key" with an equivalency or conversion to handle the unit transformation
	4. If a different phv is discovered corresponding to the BDCHV and that phv is not currently present in the curation pipeline:
			4a. Create a new blank row in the spreadsheet
			4b. Populate columns
			4c. Enter a value of "1" in the column "add_map"
	5. Sometimes a phv mapped to the correct BDCHV may require more complicated YAML code to correctly perform the conversion. In these cases, add the value "manually fixed" to the column "fix_key_note". This will result in the row being output in a "bad" YAML code output. It can then be manually fixed by a curator.
	6. If fields from the contextual_variables_key are missing, then either:
			6a. Update contextual_variables_key with correct information for those phts (if values for contextual variables are the same for all phvs within a single pht)
			6b. Update the contextual variables columns in the spreadsheet with correct values or syntax (if values for contextual variables differ for phvs within a single pht) 
	
- If a GitHub issue was opened related to the phv, add the GitHub issue number to the column "note"
- Save all changes made to the file "fixed_bdchm_mappings_`cohort'.csv"
- Re-run the program tree from the start to pull in all manually fixed values
*/




/* ----- 3. Compile all "fixed_bdchm_mappings" spreadsheets for each cohort ----- */

foreach cohort in aric cardia jhs whi fhs {
import delimited using "$out\\`cohort'\fixed\fixed_bdchm_mappings_`cohort'.csv", varnames(1) case(preserve) emptylines(skip) bindquotes(strict) stringcols(_all) clear
drop if fix_key_note=="manually fixed"
missings dropobs, force
save "$temp\\`cohort'\fixed_bdchm_mappings.dta", replace
}


* -- Compile -- *;
clear
foreach cohort in aric cardia jhs whi fhs {
append using "$temp\\`cohort'\fixed_bdchm_mappings.dta"
}
sort phv bdchm_label
gen pair_id=phv+bdchm_label
duplicates drop
missings dropobs, force
save "$temp\fixed_bdchm_mappings.dta", replace /*n=1017*/
/*unit_expr_custom unit_casestmt_custom - these are new variables created after source vars*/


* -- Create key of fixed mappings -- *;
use "$temp\fixed_bdchm_mappings.dta", clear
drop if add_map=="1"
foreach var of varlist var_units participantidphv associatedvisit associatedvisit_expr ageinyearsphv conversion_rule {
	rename `var' `var'_fixed
	}
keep pair_id bad_map *fixed unit_expr_custom unit_casestmt_custom
duplicates drop
save "$doc\fixed_bdchm_mappings.dta", replace /*n=1001*/


* -- Create key of phvs added during manual review -- *;
use "$temp\fixed_bdchm_mappings.dta", clear
keep if add_map=="1"
keep cohort bdchm_label bdchm_varname bdchm_unit phv pht participantidphv associatedvisit ageinyearsphv var_desc var_units
foreach var of varlist bdchm_varname bdchm_unit participantidphv associatedvisit ageinyearsphv {
	rename `var' `var'_fixed
	}
save "$doc\add_phvs.dta", replace /*n=16*/








/* ----- 4. Output unit mismatches for improvements to units.do ----- */
/* output mismatched unit rows to manually review for conversion rules */
/*use "$der\alldata_$today.dta", clear*/
use "$der\shortdata_$today.dta", clear
keep if bdchm_entity=="MeasurementObservation" /*n=5,691*/
keep bdchm_label phv var_desc var_units bdchm_unit conversion_rule cohort
sort var_units bdchm_unit phv
duplicates drop /*n=5722*/
drop if var_units=="" /*n=3198*/
drop if var_units==bdchm_unit /*n=801*/
drop if conversion_rule!="" /*n=405*/
tab var_units
sort bdchm_label var_units
export excel using "$doc\units_toreview_$today.xlsx", sheet("unit_key") first(var) nolabel keepcellfmt replace




/* Manual step: 
A. open the exported excel file. Do one or more of the following things with var_units values:
	1. If var_units just needs to be rewritten as a standard unit representation: 
		1a. Copy/paste var_units values into source_value col of "$doc\unit_harmonization.xlsx", sheet("unit_key")
		1b. Add the standard representation of the value to the standard_value column.
	2. If var_units (also) needs to be converted:
		2a. Copy/paste the standardized representations of the var_units that are being converted into this_unit col & that_unit col of "$doc\unit_harmonization.xlsx", sheet("conversions")
		2b. Write the YAML language conversion operation in conversion_rule column
		2c. If the conversion relies on other information, such as the biological substance being converted, then add the formula to the conversion_formula column
	3. If var_units are equivalent to another unit, then:
		3a. Add the equivalent units to the "equivalencies" tab.
		3b. Note any conditions that govern the equivalency, e.g. these are only equivalent when the noted condition is true
B. some unit representations or conversions may be dependent on the specific variable. these cases are not handled currently.
	1. conversion example: the entity eosinophils can be converted from a % to a total count if the total white blood cell count is known
	2. representation example: num/min can be validly represented as bpm instead only when the entity is heart rate
	3. IU/dL to percentage: 1 IU/dL equals 1% for some substances (e.g. factor viii) but not for others (e.g. vitamins or hormones)
C. some unit representations cannot be converted to the standard unit. these cases are not handled currently.
	1. data quality issues with var_units extracted from dbgap is sometimes the underlying root cause of this issue. 
	
*/