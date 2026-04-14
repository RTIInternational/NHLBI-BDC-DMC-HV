/* This program reads in BDC harmonized variable definitions, the contextual variables key, and the unit key.
 Input file sources:
	- bdchv_defs is tab "BDCHM Harmonized Variables V1" from the sheet "BDCHM Variable Mapping", at url https://docs.google.com/spreadsheets/d/1hxbZxSxR88HnBXjcgdeJD1AOj-pzlxMrnx5n_YLkEF0/edit?gid=2039879463#gid=2039879463
	- contextual_variables_key is tab "contextual variables V2" from the sheet "BDCHM Variable Mapping"
	- unit_key was created by Sabrina
*/
	

/* ----- Read in BDC HV definitions ----- */
foreach sheet in bdchv_defs {
import delimited using "$doc\\`sheet'.csv", varnames(1) case(lower) stripquotes(yes) stringcols(_all) clear
	foreach x of varlist * {
		replace `x'=subinstr(`x', "`=char(10)'", "`=char(32)'", .) /* replace linebreaks inside cells with a space */
		replace `x'=strtrim(`x')
		replace `x'=stritrim(`x')
		replace `x'=ustrtrim(`x')
		} 
missings dropvars, force

gen onto_id=obacurie
replace onto_id=omop if obacurie==""
drop omop obacurie

gen merge_bdchm_label=lower(bdchm_varlabel) 	
replace merge_bdchm_label=subinstr(merge_bdchm_label," ","",.)
sort merge_bdchm_label

save "$doc\\`sheet'.dta", replace
}




/* ----- Read in contextual variables for visits and participants ----- */
import delimited using "$doc\\contextual_variables_key.csv", varnames(1) case(lower) stripquotes(yes) stringcols(_all) clear
	foreach x of varlist * {
		replace `x'=subinstr(`x', "`=char(10)'", "`=char(32)'", .) /* replace linebreaks inside cells with a space */
		replace `x'=strtrim(`x')
		replace `x'=stritrim(`x')
		replace `x'=ustrtrim(`x')
		} 
missings dropvars, force

drop if pht==""
foreach var of varlist associatedvisit {
  replace `var'=upper(`var')
  }
drop datatablename
rename notes contextvars_notes
sort pht
duplicates drop

save "$doc\\contextual_variables_key.dta", replace






/* ----- Read in unit harmonization key----- */
foreach tab in unit_key conversions equivalencies ucum {
import excel using "$doc\unit_key.xlsx", sheet("`tab'") firstrow allstring clear
save "$temp\\`tab'.dta", replace
}

* Write code to standardize how units are written based on unit_harmonization crosswalk *;
use "$temp\\unit_key.dta", clear
drop note
drop if standard_value==""
sort standard_value
drop if source_value==standard_value
gen item=`"`=char(34)'"'+source_value+`"`=char(34)'"'+","
gen rep_value=`"`=char(34)'"'+standard_value+`"`=char(34)'"'
keep rep_value item
duplicates drop
sort rep_value
by rep_value: gen count=_n
summ count
local numitems = "item`r(max)'"
reshape wide item, i(rep_value) j(count)
egen items=concat(item1-`numitems')
replace items=substr(items, 1, strlen(items) - 1)

gen code="replace `=char(96)'x`=char(39)'="+rep_value+" if inlist(`=char(96)'x`=char(39)',"+items+")"

keep code
outfile code using "$prog\units.txt", nolabel noquote wide replace
/* Manual step:  paste output into units.do as codelines*/


* UCUM *;
use "$temp\ucum.dta", replace
gen valid_ucum=1
gen this_unit=ucum_code
gen that_unit=ucum_code
save "$doc\ucum.dta", replace


* Unit conversion key *;
use "$temp\\conversions.dta", clear
gen unit_merge_key=this_unit+"_"+that_unit
drop if conversion_condition!=""
sort unit_merge_key
sort this_unit
merge m:1 this_unit using "$doc\ucum.dta", keepusing(valid_ucum)
drop if _merge==2
drop _merge
rename valid_ucum source_unit_valid
sort that_unit
merge m:1 that_unit using "$doc\ucum.dta", keepusing(valid_ucum)
drop if _merge==2
drop _merge
rename valid_ucum target_unit_valid
rename this_unit source_unit
rename that_unit target_unit
gen both_valid_ucums=1 if source_unit_valid==1 & target_unit_valid==1
save "$doc\conversions.dta", replace


* Unit equivalencies key *;
use "$temp\\equivalencies.dta", clear	
keep if equivalency_always=="1"
gen unit_merge_key=this_unit+"_"+that_unit
sort unit_merge_key
keep unit_merge_key
gen equivalent_units=1
save "$doc\equivalencies.dta", replace