"""
LinkML-Map Transformation Script
Transforms priority_variable format to class_derivations format

Usage:
    python linkml_transform.py input_file.yaml [output_file.yaml]
    python linkml_transform.py --batch input_directory/ output_directory/
"""

import argparse
# import re
import sys
# import os
from pathlib import Path
from typing import Dict, List, Any, Optional
# import yaml

class LinkMLTransformer:
    """Transforms LinkML-Map files from priority_variable to class_derivations format"""
    
    def __init__(self):
        self.unit_conversions = {
            'pounds_to_kg': 0.453592,
            'multiply_by_10': 10,
        }
    
    def parse_source_yaml(self, content: str) -> Dict[str, Any]:
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
                
            elif stripped in ['MeasurementObservation:', 'Condition:', 'DrugExposure:', 'MeasurementObservationSet:'] and current_value_set is not None:
                current_class = {
                    'type': stripped.rstrip(':'),
                    'properties': {}
                }
                current_value_set['classes'].append(current_class)
                
            elif current_class is not None and ':' in stripped and not stripped.startswith('#'):
                if not any(stripped.startswith(x) for x in ['value:', 'function:', 'MeasurementObservation:', 'Condition:', 'DrugExposure:']):
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
    
    def extract_concept_id(self, concept_str: str) -> str:
        """Extract concept ID from string, handling comments"""
        if not concept_str:
            return ""
        
        # Remove comments
        concept = concept_str.split('#')[0].strip()
        return concept
    
    def detect_unit_conversion(self, function_text: str, phv: str) -> Optional[str]:
        """Detect if unit conversion is needed based on function text"""
        func_lower = function_text.lower()
        
        if 'pound' in func_lower and 'kg' in func_lower:
            return f"{{{phv}}} * 0.453592"
        elif '* 10' in func_lower or 'multiply' in func_lower and '10' in func_lower:
            return f"{{{phv}}} * 10"
        elif 'transform' in func_lower or 'convert' in func_lower:
            # Generic transform - might need specific handling
            return f"{{{phv}}}"
        
        return None
    
    def generate_case_expression(self, phv: str, value_mappings: List[Dict]) -> str:
        """Generate case expression for value mappings"""
        cases = []
        for mapping in value_mappings:
            value = mapping['value']
            status = mapping.get('status', 'UNKNOWN')
            
            if value == 'default' or value == '':
                continue
                
            cases.append(f"({{{phv}}} == {value}, \"'{status}'\")")
        
        if cases:
            return f"case({', '.join(cases)})"
        return f"{{{phv}}}"
    
    def should_skip_function(self, function_text: str) -> bool:
        """Check if function indicates we should skip this entry"""
        skip_phrases = ['do nothing', 'skip', 'omit']
        return any(phrase in function_text.lower() for phrase in skip_phrases)
    
    def generate_measurement_observation(self, variable: Dict, phv_entry: Dict, value_set: Dict, class_obj: Dict) -> List[str]:
        """Generate MeasurementObservation class derivation"""
        if self.should_skip_function(value_set.get('function', '')):
            return []
            
        lines = [
            'class_derivations:',
            '  MeasurementObservation:',
            '    populated_from: FHS',
            '    slot_derivations:'
        ]
        
        # Handle value_decimal
        if 'value_decimal' in class_obj['properties'] or phv_entry['input_data_type'] in ['decimal', 'integer']:
            lines.append('      value_decimal:')
            
            # Check for unit conversion
            conversion = self.detect_unit_conversion(value_set.get('function', ''), phv_entry['phv'])
            if conversion and conversion != f"{{{phv_entry['phv']}}}":
                lines.extend([
                    '        populated_from:',
                    f'          expr: {conversion}'
                ])
            else:
                lines.append(f'        populated_from: {phv_entry["phv"]}')
        
        # Handle observation_type
        obs_type = class_obj['properties'].get('observation_type', '')
        if obs_type:
            concept = self.extract_concept_id(obs_type)
            lines.extend([
                '      observation_type:',
                f'        expr: "\'{concept}\'"'
            ])
        
        # Handle value_quantity.unit
        unit = class_obj['properties'].get('unit', '')
        if unit:
            lines.extend([
                '      value_quantity.unit:',
                f'        expr: "\'{unit}\'"'
            ])
        
        # Handle range constraints
        if 'range_low' in class_obj['properties']:
            range_val = class_obj['properties']['range_low']
            lines.extend([
                '      range_low:',
                f'        value_decimal: {range_val}',
                f'        unit: {unit}' if unit else '        unit: "unit"'
            ])
        
        # Handle value_concept for enum types
        if (phv_entry['input_data_type'] == 'enum' and 
            value_set.get('value') not in ['', 'default'] and
            'value_enum' in class_obj['properties']):
            
            enum_val = class_obj['properties']['value_enum']
            lines.extend([
                '      value_concept:',
                '        populated_from:',
                f'          expr: case(({{{phv_entry["phv"]}}} == {value_set["value"]}, "\'{enum_val}\'"))'
            ])
        
        return lines
    
    def generate_condition(self, variable: Dict, phv_entry: Dict, value_set: Dict, class_obj: Dict) -> List[str]:
        """Generate Condition class derivation"""
        if self.should_skip_function(value_set.get('function', '')):
            return []
            
        lines = [
            'class_derivations:',
            '  Condition:',
            '    populated_from: FHS',
            '    slot_derivations:'
        ]
        
        # Handle condition_concept
        concept = class_obj['properties'].get('condition_concept', '')
        if concept:
            concept_id = self.extract_concept_id(concept)
            lines.extend([
                '      condition_concept:',
                f'        expr: "\'{concept_id}\'"'
            ])
        
        # Handle condition_status
        status = class_obj['properties'].get('condition_status', '')
        if status:
            lines.extend([
                '      condition_status:',
                f'        expr: "\'{status}\'"'
            ])
        
        # Handle condition_provenance
        provenance = class_obj['properties'].get('condition_provenance', '')
        if provenance:
            lines.extend([
                '      condition_provenance:',
                f'        expr: "\'{provenance}\'"'
            ])
        
        return lines
    
    def generate_drug_exposure(self, variable: Dict, phv_entry: Dict, value_set: Dict, class_obj: Dict) -> List[str]:
        """Generate DrugExposure class derivation"""
        if self.should_skip_function(value_set.get('function', '')):
            return []
            
        lines = [
            'class_derivations:',
            '  DrugExposure:',
            '    populated_from: FHS',
            '    slot_derivations:'
        ]
        
        # Handle drug_concept
        concept = class_obj['properties'].get('drug_concept', '')
        if concept:
            concept_id = self.extract_concept_id(concept)
            lines.extend([
                '      drug_concept:',
                f'        expr: "\'{concept_id}\'"'
            ])
        
        # Handle exposure_provenance (note: source sometimes has typo "expsoure_provenance")
        provenance = (class_obj['properties'].get('exposure_provenance') or 
                     class_obj['properties'].get('expsoure_provenance', ''))
        if provenance:
            # Clean up provenance string
            clean_prov = provenance.replace(' ', '_').replace('-', '_').upper()
            lines.extend([
                '      exposure_provenance:',
                f'        expr: "\'{clean_prov}\'"'
            ])
        
        return lines
    
    def transform_file(self, content: str) -> str:
        """Transform a single file's content"""
        parsed = self.parse_source_yaml(content)
        output_lines = []
        
        for variable in parsed['variables']:
            for phv_entry in variable['phv_entries']:
                for value_set in phv_entry['value_sets']:
                    for class_obj in value_set['classes']:
                        class_type = class_obj['type']
                        
                        if class_type == 'MeasurementObservation':
                            lines = self.generate_measurement_observation(variable, phv_entry, value_set, class_obj)
                        elif class_type == 'Condition':
                            lines = self.generate_condition(variable, phv_entry, value_set, class_obj)
                        elif class_type == 'DrugExposure':
                            lines = self.generate_drug_exposure(variable, phv_entry, value_set, class_obj)
                        else:
                            # Handle other types like MeasurementObservationSet
                            lines = [
                                'class_derivations:',
                                f'  {class_type}:',
                                '    populated_from: FHS',
                                '    slot_derivations:',
                                '      # TODO: Add specific mappings for this type'
                            ]
                        
                        if lines:
                            output_lines.extend(lines)
                            output_lines.append('')  # Add blank line between derivations
        
        return '\n'.join(output_lines)


usage_examples = """Example usage:
    # Transform a single file and output to stdout
    python linkml_transform.py input_file.yaml

    # Transform a single file and save to output file
    python linkml_transform.py input_file.yaml output_file.yaml

    # Batch process an entire directory
    python linkml_transform.py --batch input_directory/ output_directory/

    # Verbose output to see what's being processed
    python linkml_transform.py --batch --verbose source_files/ transformed_files/"""


def main():
    parser = argparse.ArgumentParser(
        description='Transform LinkML-Map files from priority_variable to class_derivations format',
        epilog=usage_examples,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('input', help='Input file or directory')
    parser.add_argument('output', nargs='?', help='Output file or directory')
    parser.add_argument('--batch', action='store_true', help='Process directory of files')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()
    
    transformer = LinkMLTransformer()
    
    if args.batch:
        # Batch processing
        input_dir = Path(args.input)
        output_dir = Path(args.output) if args.output else input_dir / 'transformed'
        
        if not input_dir.is_dir():
            print(f"Error: {input_dir} is not a directory", file=sys.stderr)
            return 1
        
        output_dir.mkdir(exist_ok=True)
        
        yaml_files = list(input_dir.glob('*.yaml')) + list(input_dir.glob('*.yml'))
        
        if args.verbose:
            print(f"Processing {len(yaml_files)} files from {input_dir} to {output_dir}")
        
        for input_file in yaml_files:
            try:
                with open(input_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check if it's a source format file (contains priority_variable)
                if 'priority_variable:' not in content:
                    if args.verbose:
                        print(f"Skipping {input_file.name} (not source format)")
                    continue
                
                transformed = transformer.transform_file(content)
                
                output_file = output_dir / input_file.name
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(transformed)
                
                if args.verbose:
                    print(f"Transformed {input_file.name} -> {output_file.name}")
                    
            except Exception as e:
                print(f"Error processing {input_file}: {e}", file=sys.stderr)
    
    else:
        # Single file processing
        input_file = Path(args.input)
        
        if not input_file.exists():
            print(f"Error: {input_file} does not exist", file=sys.stderr)
            return 1
        
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if 'priority_variable:' not in content:
                print(f"Warning: {input_file} does not appear to be in source format", file=sys.stderr)
            
            transformed = transformer.transform_file(content)
            
            if args.output:
                output_file = Path(args.output)
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(transformed)
                
                if args.verbose:
                    print(f"Transformed {input_file} -> {output_file}")
            else:
                print(transformed)
                
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
