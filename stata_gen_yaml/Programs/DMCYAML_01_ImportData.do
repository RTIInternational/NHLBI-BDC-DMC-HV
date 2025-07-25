/* -------------------------------------------------------------------------------- */
/* Project: BioDataCatalyst Data Management Core									*/
/* RTI PI: Chris Siege																*/
/* Program: DMCYAML_01_ImportData													*/
/* Programmer: Sabrina McCutchan (CDMS)												*/
/* Date Created: 2025/06/18															*/
/* Date Last Updated: 2025/07/07													*/
/* Description:	This program imports data and standardizes column names.			*/
/*		0. Read in data																*/
/* 		1. Create key of variables (FHS)											*/
/*		2. Use key to drop and rename vars (FHS)									*/
/*		3. Create key of variables (BDCHM_noFHS_noCOPDGene) 						*/
/*		4. Use key to drop and rename vars (BDCHM_noFHS_noCOPDGene)					*/
/*																					*/
/* Notes:  																			*/
/*	- 2025/07/14 Raw data files are downloaded from Google Drive, folder path:		*/
/*	  Task 3 - Data Standards > BDC Harmonization Data Model (BDCHM) > 				*/
/*    Data Modeling and Mapping > Priority Variable Values (Properties)				*/
/*	- 2025/07/14 The "data" files read in here contain metadata about phv variables	*/
/*	  in dbGAP that were mapped during a previous exercise to BDCHM priority vars	*/
/* -------------------------------------------------------------------------------- */


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
	/* yes */replace newname="data_table_name" if varlab=="data_table.name"
	/* yes */replace newname="data_table_descr" if varlab=="data_table.description"
	/* yes */replace newname="data_table_id" if varlab=="data_table.dataset_id"
	/* yes */replace newname="cohort_long" if varlab=="data_table.study_name"
	/* yes */replace newname="var_id" if varlab=="data_table.variable.id"
	/* yes */replace newname="var_type" if varlab=="data_table.variable.calculated_type"
	/* yes */replace newname="var_units" if varlab=="data_table.variable.units"
	/* yes */replace newname="var_desc" if varlab=="data_table.variable.description"
	/* yes */ replace newname="var_comment" if varlab=="data_table.variable.comment"
	/* yes */replace newname="var_name" if varlab=="source_variable_name"
	/* yes*/ replace newname="curator_note" if varlab=="note"

* -- Flag variables to drop, add new variable label and name to key -- *;
gen dropvar=0
/* yes */replace dropvar=1 if inlist(name,"variableaccession","dbgapstudyaccession","datasetaccession","sourcevariabledescription")
/* yes*/ replace dropvar=1 if inlist(varlab,"data_table.variable.total.stats.example.count")
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
}
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

	/*yes */replace newname="cohort_long" if varlab=="var_report.study_name"
	/* yes */ replace newname="data_table_id" if varlab=="var_report.dataset_id"
	/* yes*/ replace newname="data_table_name" if varlab=="var_report.name"
	/* yes*/ replace newname="data_table_descr" if varlab=="var_report.description" 
	/* yes */ replace newname="study_id" if varlab=="var_report.study_id"
	/* yes */replace newname="var_id" if varlab=="var_report.variable.id"
	/* yes */ replace newname="var_name" if varlab=="source_variable_name" 
	/*yes*/replace newname="var_desc" if varlab=="var_report.variable.description"
	/* yes */replace newname="var_units" if varlab=="var_report.variable.units"
	/* yes */replace newname="var_type" if varlab=="var_report.variable.calculated_type"
	/* yes */ replace newname="var_comment" if varlab=="var_report.variable.comment"
	/*yes */replace newname="topmed_varname" if varlab=="topmed_harmonized_variable"
	/* yes */replace newname="curator_note" if varlab=="notes"

* -- Flag variables to drop, add new variable label and name to key -- *;
gen dropvar=0
/* yes */replace dropvar=1 if inlist(name,"firstdata_tablestudy_id","firstdata_tabledataset_id","firstdata_tablevariableid","sourcevariabledescription","bdchmlabelcorrected")
/* yes */replace dropvar=1 if inlist(varlab,"var_report.variable.var_name","var_report.variable.total.stats.example.count")
/*replace dropvar=1 if inlist(varlab,"var_report.variable.var_name","var_report.study_id","var_report.dataset_id")*/
drop varlab1-varlab6

save "$doc\varlist_key_nofhscopd.dta", replace





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