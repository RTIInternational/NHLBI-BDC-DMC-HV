"""Add age_at_observation to all pht000040 blocks in diabetes.yaml"""
import re

# Age PHV mapping: exam number -> PHV accession (from pht003099)
age_phv = {}
for e in range(1, 29):
    age_phv[e] = f'phv00{177930 + (e-1)*2}'
age_phv[29] = 'phv00226999'
age_phv[30] = 'phv00227002'
age_phv[31] = 'phv00227005'
age_phv[32] = 'phv00227008'

filepath = r'C:\SourceCode\NHLBI-BDC-DMC-HV\priority_variables_transform\FHS-ingest\diabetes.yaml'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Count original pht000040 blocks
orig_count = content.count('populated_from: pht000040')
print(f'Total pht000040 blocks: {orig_count}')
print(f'Existing age_at_observation: {content.count("age_at_observation")}')

# Pattern: match associated_visit expr line with ORIGINAL EXAM N,
# then insert age_at_observation before condition_concept
# The associated_visit line ends with ")'  followed by the next slot
def add_age(match):
    prefix = match.group(1)
    exam_str = match.group(2)
    suffix = match.group(3)
    exam = int(exam_str)
    phv = age_phv.get(exam)
    if phv is None:
        print(f'  WARNING: No age PHV for exam {exam}')
        return match.group(0)
    age_line = f"        age_at_observation:\n          expr: '{{{phv}}} * 365'\n"
    print(f'  Exam {exam}: {phv}')
    return prefix + age_line + suffix

# Regex: capture everything up to and including the associated_visit expr line,
# then capture the next slot (condition_concept)
pattern = re.compile(
    r"(        associated_visit:\r?\n          expr: '[^']*ORIGINAL EXAM (\d+)[^']*'\r?\n)"
    r"(        condition_concept:)"
)

new_content, count = pattern.subn(add_age, content)
print(f'\nInserted age_at_observation in {count} blocks')

# Verify
print(f'Total age_at_observation now: {new_content.count("age_at_observation")}')

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(new_content)
print('File saved.')
