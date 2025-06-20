import yaml
import pandas as pd
import re
from typing import Dict, List, Any, Optional

"""
Got code from https://claude.ai/share/53d2ec25-c243-4d4b-9276-d3ed342eb18f
"""


class YAMLTransformer:
    def __init__(self, csv_file_path: str):
        """Initialize with CSV lookup table"""
        self.lookup_df = pd.read_csv(csv_file_path)
        # Clean column names
        self.lookup_df.columns = self.lookup_df.columns.str.strip()

    def get_visit_info(self, pht: str) -> tuple:
        """Get participant ID and visit info from CSV based on pht"""
        row = self.lookup_df[self.lookup_df['data table pht'] == pht]
        if not row.empty:
            participant_phv = row.iloc[0]['participant ID phv']
            visit = row.iloc[0]['associated visit']
            return participant_phv, visit
        return None, None

    def extract_condition_concept(self, value_sets: List) -> tuple:
        """Extract condition concept and comment from value_sets"""
        # Look for MONDO or HP codes in comments
        for value_set in value_sets:
            for class_obj in value_set.get('classes', []):
                if class_obj.get('type') == 'Condition':
                    concept_line = class_obj.get('properties', {}).get('condition_concept', '')
                    if concept_line and '#' in concept_line:
                        parts = concept_line.split('#', 1)
                        concept = parts[0].strip()
                        comment = parts[1].strip() if len(parts) > 1 else None
                        return concept, comment
                    elif concept_line:
                        return concept_line.strip(), None

        # Default to asthma if not found
        return "MONDO:0004979", "asthma"

    def extract_condition_provenance(self, value_sets: List) -> str:
        """Determine condition provenance from patterns"""
        # Look for explicit provenance in the conditions
        for value_set in value_sets:
            for class_obj in value_set.get('classes', []):
                if class_obj.get('type') == 'Condition':
                    prov = class_obj.get('properties', {}).get('condition_provenance', '')
                    if prov and prov != '':
                        return prov

        # Default based on common patterns
        return "PATIENT_SELF-REPORTED_CONDITION"

    def create_value_mappings(self, value_sets: List) -> Dict[str, str]:
        """Create value mappings for condition_status"""
        mappings = {}

        for value_set in value_sets:
            value = value_set.get('value', '')

            # Handle empty/default values - use dot
            if value == '' or value == 'default':
                value = '.'

            # Look for Condition classes in this value_set
            for class_obj in value_set.get('classes', []):
                if class_obj.get('type') == 'Condition':
                    status = class_obj.get('properties', {}).get('condition_status', '')
                    if status:
                        mappings[value] = status
                        break

            # Handle special cases with complex conditional logic
            if value not in mappings:
                function_text = value_set.get('function', '')

                # Extract status from complex conditional statements
                if 'look at' in function_text.lower():
                    # This indicates complex conditional logic - use a default mapping
                    # These will need manual review
                    if 'ABSENT' in function_text:
                        mappings[value] = 'ABSENT'
                    elif 'PRESENT' in function_text:
                        mappings[value] = 'PRESENT'
                    elif 'HISTORICAL' in function_text:
                        mappings[value] = 'HISTORICAL'
                    else:
                        mappings[value] = 'UNKNOWN'

        return mappings

    def transform_raw_variable(self, phv_id: str, phv_entry: Dict) -> Dict:
        """Transform a single raw variable to class_derivation format"""
        pht = phv_entry.get('identifiers', {}).get('pht', '')
        participant_phv, visit = self.get_visit_info(pht)

        if not participant_phv or not visit:
            print(f"Warning: Could not find visit info for pht {pht}")
            return None

        value_sets = phv_entry.get('value_sets', [])
        concept, comment = self.extract_condition_concept(value_sets)
        provenance = self.extract_condition_provenance(value_sets)
        value_mappings = self.create_value_mappings(value_sets)

        # Build the concept expression with comment
        concept_expr = concept
        if comment:
            concept_expr += f"   #{comment}"

        class_derivation = {
            "class_derivations": {
                "Condition": {
                    "populated_from": "FHS",
                    "slot_derivations": {
                        "associated_participant": {
                            "populated_from": participant_phv
                        },
                        "associated_visit": {
                            "expr": visit
                        },
                        "condition_concept": {
                            "expr": concept_expr
                        },
                        "condition_status": {
                            "populated_from": phv_id,
                            "value_mappings": value_mappings
                        },
                        "condition_provenance": {
                            "expr": provenance
                        },
                        "relationship_to_participant": {
                            "expr": "ONESELF"
                        }
                    }
                }
            }
        }

        # Check for special visit handling (like "12 months before assoc visit")
        special_visit_pattern = self._check_for_special_visit_logic(value_sets)
        if special_visit_pattern:
            # Add a comment or special handling note
            class_derivation["# SPECIAL_VISIT_LOGIC"] = special_visit_pattern

        return class_derivation

    def _check_for_special_visit_logic(self, value_sets: List) -> Optional[str]:
        """Check if the value_sets contain special visit timing logic"""
        for value_set in value_sets:
            function_text = value_set.get('function', '')
            if '12 months before' in function_text:
                return "Contains 12 months before visit calculation"
            elif 'age at previous visit' in function_text:
                return "Contains previous visit age calculation"
        return None

    def transform_yaml_file(self, input_file: str, output_file: str):
        """Transform the entire YAML file"""
        # Load original YAML using the custom parser
        with open(input_file, 'r') as f:
            content = f.read()

        # Clean the content first to make it parseable
        cleaned_content = clean_linkml_map_for_yaml(input_file)

        # Parse using the custom parser from linkml_transform_script
        original_data = parse_source_yaml(cleaned_content)

        transformed_derivations = []

        # Process the parsed structure
        self._process_parsed_variables(original_data, transformed_derivations)

        # Write output file
        with open(output_file, 'w') as f:
            for i, derivation in enumerate(transformed_derivations):
                if i > 0:
                    f.write('\n')
                yaml.dump(derivation, f, default_flow_style=False, sort_keys=False)

        print(f"Transformed {len(transformed_derivations)} raw variables")
        print(f"Output written to {output_file}")

        # Generate summary report
        self._generate_summary_report(transformed_derivations, f"{output_file}_summary.txt")

        return transformed_derivations

    def _process_parsed_variables(self, parsed_data: Dict, transformed_derivations: List):
        """Process the parsed data structure from parse_source_yaml"""
        for variable in parsed_data.get('variables', []):
            for phv_entry in variable.get('phv_entries', []):
                phv_id = phv_entry.get('phv', '')

                # Only process if this entry has Condition classes
                has_condition = False
                for value_set in phv_entry.get('value_sets', []):
                    for class_obj in value_set.get('classes', []):
                        if class_obj.get('type') == 'Condition':
                            has_condition = True
                            break
                    if has_condition:
                        break

                if has_condition and phv_id:
                    transformed = self.transform_raw_variable(phv_id, phv_entry)
                    if transformed:
                        transformed_derivations.append(transformed)

    def _generate_summary_report(self, transformed_derivations: List, report_file: str):
        """Generate a summary report of the transformation"""
        with open(report_file, 'w') as f:
            f.write("YAML Transformation Summary Report\n")
            f.write("=" * 50 + "\n\n")

            f.write(f"Total transformations: {len(transformed_derivations)}\n\n")

            # Count by condition concepts
            concepts = {}
            provenances = {}
            special_logic_count = 0

            for derivation in transformed_derivations:
                if "class_derivations" in derivation:
                    slots = derivation["class_derivations"]["Condition"]["slot_derivations"]

                    concept = slots["condition_concept"]["expr"].strip("'")
                    concepts[concept] = concepts.get(concept, 0) + 1

                    provenance = slots["condition_provenance"]["expr"].strip("'")
                    provenances[provenance] = provenances.get(provenance, 0) + 1

                    if "# SPECIAL_VISIT_LOGIC" in derivation:
                        special_logic_count += 1

            f.write("Condition Concepts:\n")
            for concept, count in concepts.items():
                f.write(f"  {concept}: {count}\n")

            f.write("\nCondition Provenances:\n")
            for provenance, count in provenances.items():
                f.write(f"  {provenance}: {count}\n")

            f.write(f"\nTransformations with special visit logic: {special_logic_count}\n")

            if special_logic_count > 0:
                f.write("\nNote: Variables with special visit logic may need manual review\n")
                f.write("for proper age_at_condition_start and age_at_condition_end calculations.\n")

        print(f"Summary report written to {report_file}")


def parse_source_yaml(content: str) -> Dict[str, Any]:
    """Parse the source YAML structure"""
    lines = content.split('\n')
    result = {'variables': []}

    current_variable = None
    current_phv_entry = None
    current_value_set = None
    current_class = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith('priority_variable:'):
            current_variable = {'name': '', 'phv_entries': []}
            result['variables'].append(current_variable)

        elif stripped.startswith('name:') and current_variable is not None:
            current_variable['name'] = stripped.split(':', 1)[1].strip()

        elif (stripped.startswith('phv:') or stripped.startswith('raw_variable:')) and current_variable is not None:
            phv_id = stripped.split(':', 1)[1].strip()
            current_phv_entry = {
                'phv': phv_id,
                'identifiers': {},
                'input_data_type': '',
                'value_sets': []
            }
            current_variable['phv_entries'].append(current_phv_entry)

        elif stripped.startswith('phs:') and current_phv_entry is not None:
            current_phv_entry['identifiers']['phs'] = stripped.split(':', 1)[1].strip()

        elif stripped.startswith('pht:') and current_phv_entry is not None:
            current_phv_entry['identifiers']['pht'] = stripped.split(':', 1)[1].strip()

        elif stripped.startswith('input_data_type:') and current_phv_entry is not None:
            current_phv_entry['input_data_type'] = stripped.split(':', 1)[1].strip()

        elif stripped.startswith('value:') and current_phv_entry is not None:
            value_str = stripped[6:].strip() if len(stripped) > 6 else 'default'
            current_value_set = {
                'value': value_str,
                'function': '',
                'classes': []
            }
            current_phv_entry['value_sets'].append(current_value_set)

        elif stripped.startswith('function:') and current_value_set is not None:
            # Handle multi-line functions
            func_text = stripped.split(':', 1)[1].strip()
            j = i + 1
            while j < len(lines) and not lines[j].strip().endswith(':') and not lines[j].strip().startswith('value:'):
                if lines[j].strip() and not lines[j].strip().startswith('#'):
                    func_text += ' ' + lines[j].strip()
                j += 1
            current_value_set['function'] = func_text
            i = j - 1

        elif stripped in ['MeasurementObservation:', 'Condition:', 'DrugExposure:',
                          'MeasurementObservationSet:'] and current_value_set is not None:
            current_class = {
                'type': stripped.rstrip(':'),
                'properties': {}
            }
            current_value_set['classes'].append(current_class)

        elif current_class is not None and ':' in stripped and not stripped.startswith('#'):
            if not any(stripped.startswith(x) for x in
                       ['value:', 'function:', 'MeasurementObservation:', 'Condition:', 'DrugExposure:']):
                key_val = stripped.split(':', 1)
                if len(key_val) == 2:
                    key, val = key_val
                    key = key.strip()
                    val = val.strip()

                    # Handle nested properties like value_quantity
                    if key in current_class['properties']:
                        if isinstance(current_class['properties'][key], dict):
                            # This is a continuation of a nested property
                            pass
                        else:
                            current_class['properties'][key] = val
                    else:
                        current_class['properties'][key] = val

        i += 1

    return result


def clean_linkml_map_for_yaml(file_path):
    """
    Remove empty field lines (lines ending with just ':') from LinkML-map files
    to make them compatible with yaml.safe_load.
    Only removes lines where the next non-empty line is NOT more indented.
    """
    with open(file_path, 'r') as f:
        content = f.read()

    lines = content.split('\n')
    cleaned_lines = []

    for i, line in enumerate(lines):
        # Check if line is just indentation + word + colon (potential empty field)
        if re.match(r'^\s+\w+:\s*$', line):
            current_indent = len(line) - len(line.lstrip())

            # Look at the next non-empty line to check its indentation
            should_keep = False
            for j in range(i + 1, len(lines)):
                next_line = lines[j]
                if next_line.strip():  # Found next non-empty line
                    next_indent = len(next_line) - len(next_line.lstrip())
                    if next_indent > current_indent:
                        # Next line is more indented, so this is a parent with children
                        should_keep = True
                    break

            if should_keep:
                cleaned_lines.append(line)
            # If should_keep is False, we skip this line (don't append it)
        else:
            cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)


def main():
    """Main function to run the transformation"""
    import sys

    # Check command line arguments
    if len(sys.argv) >= 3:
        input_file = sys.argv[1]
        output_file = sys.argv[2]
        csv_file = sys.argv[3] if len(sys.argv) > 3 else 'BDCHM Variable Mapping - contextual variables V2.csv'
    else:
        # Use default files
        input_file = 'asthma.yaml'
        output_file = 'asthma_transformed.yaml'
        csv_file = 'BDCHM Variable Mapping  contextual variables V2.csv'

    try:
        # Initialize transformer with CSV lookup file
        transformer = YAMLTransformer(csv_file)

        # Transform the YAML file
        results = transformer.transform_yaml_file(input_file, output_file)

        print(f"\nTransformation completed successfully!")
        print(f"Input: {input_file}")
        print(f"Output: {output_file}")
        print(f"Summary: {output_file}_summary.txt")

    except FileNotFoundError as e:
        print(f"Error: File not found - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error during transformation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


# Example usage functions for different scenarios
def transform_single_file(input_yaml: str, output_yaml: str, csv_lookup: str):
    """Transform a single YAML file"""
    transformer = YAMLTransformer(csv_lookup)
    return transformer.transform_yaml_file(input_yaml, output_yaml)


def batch_transform(input_files: List[str], output_dir: str, csv_lookup: str):
    """Transform multiple YAML files"""
    import os
    transformer = YAMLTransformer(csv_lookup)

    results = []
    for input_file in input_files:
        basename = os.path.basename(input_file)
        name_without_ext = os.path.splitext(basename)[0]
        output_file = os.path.join(output_dir, f"{name_without_ext}_transformed.yaml")

        print(f"Transforming {input_file} -> {output_file}")
        result = transformer.transform_yaml_file(input_file, output_file)
        results.append((input_file, output_file, len(result)))

    return results


if __name__ == "__main__":
    # main()
    batch_transform([
        '../../asthma.yaml',
        '../../cig_smok.yaml',
        '../../afib.yaml',
        '../../alcohol_servings.yaml',
        '../../aspirin.yaml',
    ], 'output', 'BDCHMVariableMappingContextualVariablesV2.csv')