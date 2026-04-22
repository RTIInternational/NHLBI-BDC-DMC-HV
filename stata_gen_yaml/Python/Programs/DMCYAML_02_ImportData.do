* This program reads in files containing dbGaP metadata and phv-BDCHV mappings, then compiles them into a single file with consistent column names *; 

/* ----- 0. Read in data ----- */
foreach dtaset in FHS_VariableProperties {
/*import delimited using "$raw/`dtaset'.csv", varnames(1) stringcols(_all) bindquote(strict) favorstrfixed clear*/
import excel using "$raw\\`dtaset'.xlsx", sheet("right_join_full") firstrow case(lower) allstring clear
	foreach x of varlist * {
		replace `x'=subinstr(`x', "`=char(10)'", "`=char(32)'", .) /* replace linebreaks inside cells with a space */
		replace `x'=strtrim(`x')
		replace `x'=stritrim(`x')
		replace `x'=ustrtrim(`x')
		} 
missings dropvars, force
gen cohort="fhs"

replace data_tablestudy_id=dbgapstudyaccession if data_tablestudy_id=="" & dbgapstudyaccession!="" /*n=957 changes*/
replace data_tablevariableid=variableaccession if data_tablevariableid=="" & variableaccession!="" /*n=957 changes*/
replace data_tabledataset_id=datasetaccession if data_tabledataset_id=="" & datasetaccession!="" /*n=957 changes*/
replace data_tablevariabledescription=sourcevariabledescription if data_tablevariabledescription=="" & sourcevariabledescription!="" /*n=957 changes*/

save "$raw\\fhs_$today.dta", replace
}

foreach dtaset in Export_BDCHM_noFHS-noCOPDGene_phv_mappings {
import excel using "$raw\\`dtaset'.xlsx", sheet("Export_BDCHM_noFHS-noCOPDGene_p") firstrow case(lower) allstring clear
	foreach x of varlist * {
		replace `x'=subinstr(`x', "`=char(10)'", "`=char(32)'", .) /* replace linebreaks inside cells with a space */
		replace `x'=strtrim(`x')
		replace `x'=stritrim(`x')
		replace `x'=ustrtrim(`x')
		} 
missings dropvars, force
replace bdchmlabel=bdchmlabelcorrected
save "$raw\\`dtaset'_$today.dta", replace
}



/* ----- 1. Create key of variables (FHS) ----- */
foreach dtaset in fhs_$today {
	descsave using "$raw\\`dtaset'.dta", list(,) saving("$temp/`dtaset'_varlist.dta", replace)
	use "$temp/`dtaset'_varlist.dta", clear

* -- Add new variable label and name to key -- *;
sort varlab
gen newname=""
replace varlab=lower(varlab)
replace varlab=subinstr(varlab," ","_",.)
replace varlab="cohort" if name=="cohort"
split varlab, p(".")

replace newname=varlab1 if varlab2==""
replace newname=varlab2 if varlab1=="data_table" & varlab3==""
replace newname=varlab5+"_"+varlab6 if inlist(varlab5,"stat","enum","example")
	replace newname="data_table_name" if varlab=="data_table.name"
	replace newname="data_table_descr" if varlab=="data_table.description"
	replace newname="data_table_id" if varlab=="data_table.dataset_id"
	replace newname="cohort_long" if varlab=="data_table.study_name"
	replace newname="var_id" if varlab=="data_table.variable.id"
	replace newname="var_type" if varlab=="data_table.variable.calculated_type"
	replace newname="var_units" if varlab=="data_table.variable.units"
	replace newname="var_desc" if varlab=="data_table.variable.description"
	replace newname="var_comment" if varlab=="data_table.variable.comment"
	replace newname="var_name" if varlab=="source_variable_name"
	replace newname="curator_note" if varlab=="note"

* -- Flag variables to drop, add new variable label and name to key -- *;
gen dropvar=0
replace dropvar=1 if inlist(name,"variableaccession","dbgapstudyaccession","datasetaccession","sourcevariabledescription")
replace dropvar=1 if inlist(varlab,"data_table.variable.total.stats.example.count")
drop varlab1-varlab6

save "$doc\varlist_key_fhs.dta", replace
}



/* ----- 2. Use key to drop and rename vars (FHS) ----- */

* -- Rename -- *;
foreach dtaset in fhs_$today {
use "$doc\varlist_key_fhs.dta", clear
keep name newname dropvar	
drop if dropvar==1
count
local nobs = r(N)
forvalues i = 1/`nobs' {
    local name`i' = name[`i']
	local newname`i' = newname[`i']
	}
	
use "$raw\\`dtaset'.dta", clear
forvalues i = 1/`nobs' {
    rename `name`i'' `newname`i''
	}
	save "$temp\\`dtaset'_renamed.dta", replace
}


* -- Drop -- *;
foreach dtaset in fhs_$today {
use "$doc\varlist_key_fhs.dta", clear
keep name newname dropvar	
keep if dropvar==1
count
local mobs = r(N)
forvalues i = 1/`mobs' {
    local drop`i' = name[`i']
	}
use "$temp\\`dtaset'_renamed.dta", clear
forvalues i = 1/`mobs' {
    drop `drop`i''
	}
	save "$temp\\`dtaset'_drop.dta", replace
	}





/* ----- 3. Create key of variables (BDCHM_noFHS_noCOPDGene) ----- */
foreach dtaset in Export_BDCHM_noFHS-noCOPDGene_phv_mappings_$today {
	descsave using "$raw\\`dtaset'.dta", list(,) saving("$temp/`dtaset'_varlist.dta", replace)
	use "$temp/`dtaset'_varlist.dta", clear

* -- Add new variable label and name to key -- *;
gen newname=""
replace varlab=lower(varlab)
replace varlab=subinstr(varlab," ","_",.)
replace varlab=subinstr(varlab,"first[","",.)
replace varlab=subinstr(varlab,"]","",.)
split varlab, p(".")
replace newname=varlab1 if varlab2==""
replace newname=varlab2 if varlab1=="data_table" & varlab3==""
replace newname=varlab5+"_"+varlab6 if inlist(varlab5,"stat","enum","example")

	replace newname="cohort_long" if varlab=="var_report.study_name"
	replace newname="data_table_id" if varlab=="var_report.dataset_id"
	replace newname="data_table_name" if varlab=="var_report.name"
	replace newname="data_table_descr" if varlab=="var_report.description" 
	replace newname="study_id" if varlab=="var_report.study_id"
	replace newname="var_id" if varlab=="var_report.variable.id"
	replace newname="var_name" if varlab=="source_variable_name" 
	replace newname="var_desc" if varlab=="var_report.variable.description"
	replace newname="var_units" if varlab=="var_report.variable.units"
	replace newname="var_type" if varlab=="var_report.variable.calculated_type"
	replace newname="var_comment" if varlab=="var_report.variable.comment"
	replace newname="topmed_varname" if varlab=="topmed_harmonized_variable"
	replace newname="curator_note" if varlab=="notes"
	replace newname="bdchm_label_corrected" if newname=="bdchm_label_(corrected)"

* -- Flag variables to drop, add new variable label and name to key -- *;
gen dropvar=0
replace dropvar=1 if inlist(name,"firstdata_tablestudy_id","firstdata_tabledataset_id","firstdata_tablevariableid","sourcevariabledescription","bdchmlabelcorrected","vlookupresults")
replace dropvar=1 if inlist(varlab,"var_report.variable.var_name","var_report.variable.total.stats.example.count")
drop varlab1-varlab6

save "$doc\varlist_key_nofhscopd.dta", replace
}




/* ----- 4. Use key to drop and rename vars (BDCHM_noFHS_noCOPDGene) ----- */

* -- Rename -- *;
foreach dtaset in Export_BDCHM_noFHS-noCOPDGene_phv_mappings_$today {
use "$doc\varlist_key_nofhscopd.dta", clear
keep name newname dropvar	
drop if dropvar==1
count
local nobs = r(N)
forvalues i = 1/`nobs' {
    local name`i' = name[`i']
	local newname`i' = newname[`i']
	}

use "$raw\\`dtaset'.dta", clear
forvalues i = 1/`nobs' {
    rename `name`i'' `newname`i''
	}
	save "$temp\\`dtaset'_renamed.dta", replace
}


* -- Drop -- *;
foreach dtaset in Export_BDCHM_noFHS-noCOPDGene_phv_mappings_$today {
use "$doc\varlist_key_nofhscopd.dta", clear
keep name newname dropvar	
keep if dropvar==1
count
local mobs = r(N)
forvalues i = 1/`mobs' {
    local drop`i' = name[`i']
	}
use "$temp\\`dtaset'_renamed.dta", clear
forvalues i = 1/`mobs' {
    drop `drop`i''
	}
	save "$temp\\`dtaset'_drop.dta", replace
	}





/* ----- 5. Append & clean data ----- */

* Append *;
clear
foreach dtaset in fhs_$today Export_BDCHM_noFHS-noCOPDGene_phv_mappings_$today {
	append using "$temp\\`dtaset'_drop.dta"
	}
duplicates drop 

* Standardize Variables *;
drop bdchm_variable

foreach var in var_id study_id data_table_id {
	split `var', p(".")
	}
rename var_id1 phv
rename study_id1 phs
rename data_table_id1 pht
drop var_id* study_id* data_table_id*
drop if phv==""

* Values *; 
foreach var of varlist cohort var_units var_desc {
	replace `var'=lower(`var')
	}
replace bdchm_label=lower(bdchm_label) 

* Cohort *;
replace cohort="hchs_sol" if cohort=="hchs/sol"
	
* Units *;
do "$prog\\units.do" var_units
	
* Type *;
replace var_type="categorical" if (enum_!="" | example_code!="")

order cohort bdchm_label phv pht phs
order cohort_long data_table_name data_table_descr, last
order var_desc, after(var_name)
save "$temp\variable_mappings.dta", replace


