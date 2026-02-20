# Validator Enhancement Recommendations
**For:** `C:\SourceCode\dm-bip\tests\pipeline\mapping_integrity\remote_mapping_audit.py`  
**Date:** February 19, 2026  
**Context:** FHS v33→v35 migration validation results

---

## Current Behavior

The validator reports **14 non-critical warnings** for legitimate cross-table references:
- condition_status PHVs from related lookup tables (6 instances)
- value_enum PHVs from enumeration tables (3 instances)
- associated_visit PHVs from centralized visit tables (4 instances)

These are **expected patterns** in normalized relational databases, not data quality issues.

---

## Problem Statement

The current validation logic treats **all cross-table PHV references as potential errors**, marking them as "NO" (non-critical) but still cluttering reports with false positives. This makes it harder to identify genuine data quality issues.

---

## Recommended Changes

### 1. Add Allowlist for Known Cross-Table Reference Patterns

**Rationale:** Certain slot types are **designed** to reference PHVs from other tables (e.g., visits, condition statuses, enumerations).

**Implementation:**

```python
# Add after imports
ALLOWED_CROSS_TABLE_SLOTS = {
    'associated_visit',      # Visit IDs often from centralized visit tables
    'condition_status',      # Status values from lookup/metadata tables
    'value_enum',           # Enumeration values from reference tables
    'condition_provenance', # Provenance metadata
    'method_type',          # Method descriptions from metadata
}

# Modify validation logic
def validate_phv_in_table(phv, pht, slot_name):
    """Check if PHV belongs to the specified table."""
    
    # Skip validation for slots that commonly cross-reference
    if slot_name in ALLOWED_CROSS_TABLE_SLOTS:
        return {
            'valid': True,
            'critical': False,
            'reason': 'ALLOWED_CROSS_REFERENCE',
            'message': f'{slot_name} is permitted to reference external tables'
        }
    
    # Continue with normal validation for other slots
    if phv in table_phv_mapping.get(pht, []):
        return {'valid': True, 'critical': False}
    
    # Critical error for slots that MUST be in same table
    return {
        'valid': False,
        'critical': True if slot_name == 'associated_participant' else False,
        'reason': 'PHV_NOT_IN_TABLE'
    }
```

---

### 2. Add Centralized Table Recognition

**Rationale:** Certain tables are **centralized reference tables** used across multiple phenotype tables (e.g., pht001039 for visits, pht003099 for exam metadata).

**Implementation:**

```python
# Configuration
CENTRALIZED_REFERENCE_TABLES = {
    'pht001039': 'Visit/Exam identifiers',
    'pht003099': 'Exam attendance and ages',
    'pht000039': 'Participant demographics',
}

# Modify validation
def is_valid_cross_reference(source_pht, target_phv, target_pht, slot_name):
    """Determine if cross-table reference is valid."""
    
    # Allow references to centralized tables
    if target_pht in CENTRALIZED_REFERENCE_TABLES:
        return True
    
    # Allow specific slot types (from allowlist above)
    if slot_name in ALLOWED_CROSS_TABLE_SLOTS:
        return True
    
    return False
```

---

### 3. Add Severity Levels to Output

**Rationale:** Not all validation issues have the same impact. Distinguish between:
- **CRITICAL**: Must be fixed (e.g., associated_participant PHV not in table)
- **WARNING**: Review recommended (e.g., unexpected cross-reference)
- **INFO**: Expected pattern, no action needed (e.g., visit from pht001039)

**Implementation:**

```python
# Enhance CSV output
def write_audit_results(results, output_file):
    """Write validation results with severity levels."""
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'SEVERITY',      # CRITICAL, WARNING, INFO
            'CRITICAL',      # Legacy YES/NO field
            'Remote_YAML',
            'PHT',
            'Slot',
            'Invalid_PHV',
            'Target_PHT',    # NEW: Where the PHV actually lives
            'Reason',        # NEW: Why this was flagged
            'Study_Context'
        ])
        
        for result in results:
            severity = determine_severity(result)
            writer.writerow([
                severity,
                'YES' if result['critical'] else 'NO',
                result['yaml_file'],
                result['source_pht'],
                result['slot_name'],
                result['phv'],
                result.get('actual_pht', 'UNKNOWN'),
                result.get('reason', 'PHV_NOT_IN_TABLE'),
                result['study']
            ])

def determine_severity(result):
    """Assign severity level to validation result."""
    
    if result.get('reason') == 'ALLOWED_CROSS_REFERENCE':
        return 'INFO'
    
    if result['slot_name'] == 'associated_participant' and not result['valid']:
        return 'CRITICAL'
    
    if result['critical']:
        return 'CRITICAL'
    
    if result.get('actual_pht') in CENTRALIZED_REFERENCE_TABLES:
        return 'INFO'
    
    return 'WARNING'
```

---

### 4. Add Configuration File Support

**Rationale:** Different studies may have different cross-reference patterns. Make allowlists configurable per study.

**Implementation:**

Create `validation_config.yaml`:

```yaml
studies:
  Framingham:
    centralized_tables:
      pht001039: "Visit/Exam identifiers"
      pht003099: "Exam attendance metadata"
      pht000039: "Participant demographics"
    
    allowed_cross_table_slots:
      - associated_visit
      - condition_status
      - value_enum
      - condition_provenance
      - method_type
    
    critical_slots:
      - associated_participant
      - unique_id
  
  # Other studies...
```

Load in script:

```python
import yaml

def load_validation_config(config_path='validation_config.yaml'):
    """Load study-specific validation rules."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

# Use in validation
config = load_validation_config()
study_config = config['studies'].get(study_name, {})
allowed_slots = set(study_config.get('allowed_cross_table_slots', []))
```

---

### 5. Add Summary Statistics to Output

**Rationale:** Help users quickly understand validation results without reading every line.

**Implementation:**

```python
def print_validation_summary(results):
    """Print summary of validation results."""
    
    by_severity = defaultdict(int)
    by_reason = defaultdict(int)
    
    for result in results:
        severity = determine_severity(result)
        by_severity[severity] += 1
        by_reason[result.get('reason', 'UNKNOWN')] += 1
    
    print("\n" + "="*70)
    print("VALIDATION SUMMARY")
    print("="*70)
    print(f"Total issues found: {len(results)}")
    print(f"\nBy Severity:")
    print(f"  CRITICAL: {by_severity['CRITICAL']} (requires immediate fix)")
    print(f"  WARNING:  {by_severity['WARNING']} (review recommended)")
    print(f"  INFO:     {by_severity['INFO']} (expected patterns)")
    
    print(f"\nBy Reason:")
    for reason, count in sorted(by_reason.items()):
        print(f"  {reason}: {count}")
    
    if by_severity['CRITICAL'] == 0:
        print("\n✓ No critical issues found!")
    else:
        print(f"\n⚠ {by_severity['CRITICAL']} critical issues require attention")
    print("="*70)
```

---

## Example Updated CSV Output

**Before:**
```csv
CRITICAL,Remote_YAML,PHT,Slot,Invalid_PHV,Study_Context
NO,creat_bld.yaml,pht000742,associated_visit,phv00080751,Framingham Cohort
```

**After:**
```csv
SEVERITY,CRITICAL,Remote_YAML,PHT,Slot,Invalid_PHV,Target_PHT,Reason,Study_Context
INFO,NO,creat_bld.yaml,pht000742,associated_visit,phv00080751,pht001039,ALLOWED_CROSS_REFERENCE,Framingham Cohort
```

---

## Testing Recommendations

### Test Cases to Add:

1. **Valid associated_participant in same table** → Should pass
2. **Invalid associated_participant in different table** → Should be CRITICAL
3. **associated_visit from pht001039** → Should be INFO (expected)
4. **condition_status from related table** → Should be INFO (expected)
5. **value_enum from different table** → Should be INFO (expected)
6. **Unexpected cross-reference** → Should be WARNING

### Sample Test:

```python
def test_cross_reference_validation():
    """Test validation of cross-table references."""
    
    # Test 1: Critical error - participant from wrong table
    result = validate_phv_in_table('phv00010767', 'pht009761', 'associated_participant')
    assert result['critical'] == True
    assert determine_severity(result) == 'CRITICAL'
    
    # Test 2: Expected cross-reference - visit from centralized table
    result = validate_phv_in_table('phv00080751', 'pht000742', 'associated_visit')
    assert result['valid'] == True
    assert determine_severity(result) == 'INFO'
    
    # Test 3: Expected cross-reference - condition status from lookup
    result = validate_phv_in_table('phv00001339', 'pht000012', 'condition_status')
    assert result['valid'] == True
    assert determine_severity(result) == 'INFO'
```

---

## Benefits of These Changes

1. **Reduced Noise:** INFO-level entries can be filtered out for routine reviews
2. **Better Prioritization:** CRITICAL issues stand out immediately
3. **Flexibility:** Configuration file allows study-specific rules
4. **Documentation:** Reason codes explain why each issue was flagged
5. **Maintainability:** Centralized allowlists are easier to update than scattered logic

---

## Migration Path

1. **Phase 1:** Add SEVERITY column and determine_severity() function
2. **Phase 2:** Implement ALLOWED_CROSS_TABLE_SLOTS allowlist
3. **Phase 3:** Add CENTRALIZED_REFERENCE_TABLES recognition
4. **Phase 4:** Create validation_config.yaml for study-specific rules
5. **Phase 5:** Add summary statistics output

Each phase is **backwards compatible** - existing CSV consumers will continue to work.

---

## Files to Update

1. **remote_mapping_audit.py** - Main validation logic
2. **validation_config.yaml** - NEW: Configuration file
3. **test_remote_mapping_audit.py** - NEW: Test cases
4. **README.md** - Update documentation with new severity levels

---

## Example Complete Implementation Snippet

```python
# Constants
ALLOWED_CROSS_TABLE_SLOTS = {
    'associated_visit',
    'condition_status',
    'value_enum',
    'condition_provenance',
    'method_type',
}

CENTRALIZED_REFERENCE_TABLES = {
    'pht001039': 'Visit/Exam identifiers',
    'pht003099': 'Exam attendance metadata',
}

def validate_phv_reference(phv, source_pht, slot_name, study='Framingham'):
    """
    Validate if a PHV reference is correct.
    
    Returns:
        dict with keys: valid, critical, severity, reason, actual_pht
    """
    # Find which table actually contains this PHV
    actual_pht = find_phv_table(phv, study)
    
    # Check if PHV is in the expected table
    is_in_source = (actual_pht == source_pht)
    
    # Determine if cross-reference is allowed
    if not is_in_source:
        if slot_name in ALLOWED_CROSS_TABLE_SLOTS:
            return {
                'valid': True,
                'critical': False,
                'severity': 'INFO',
                'reason': 'ALLOWED_CROSS_REFERENCE',
                'actual_pht': actual_pht
            }
        
        if actual_pht in CENTRALIZED_REFERENCE_TABLES:
            return {
                'valid': True,
                'critical': False,
                'severity': 'INFO',
                'reason': 'CENTRALIZED_TABLE_REFERENCE',
                'actual_pht': actual_pht
            }
        
        # Unexpected cross-reference
        is_critical = (slot_name == 'associated_participant')
        return {
            'valid': False,
            'critical': is_critical,
            'severity': 'CRITICAL' if is_critical else 'WARNING',
            'reason': 'UNEXPECTED_CROSS_REFERENCE',
            'actual_pht': actual_pht
        }
    
    # PHV is in expected table
    return {
        'valid': True,
        'critical': False,
        'severity': 'OK',
        'reason': 'VALID_REFERENCE',
        'actual_pht': actual_pht
    }
```

---

## Questions for Discussion

1. Should we make the allowlist more granular (e.g., specific PHT→PHT pairs)?
2. Should INFO-level results be written to a separate file?
3. Do we need different rules for different cohorts (Original, Offspring, Omni)?
4. Should we add automatic allowlist learning from validated datasets?

---

**End of Recommendations**

*These recommendations were generated based on analysis of FHS v35 validation results. Adapt as needed for your specific validation framework.*
