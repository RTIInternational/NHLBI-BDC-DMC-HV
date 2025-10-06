from pathlib import Path
import yaml

ingest_dir = "./priority_variables_transform"
base_dir = Path(ingest_dir)

yaml_files = list(base_dir.rglob("*.yaml"))
ingest_files = [f for f in yaml_files if any("-ingest" in part for part in f.parts)]

if not ingest_files:
    print(f"No YAML files in directories with '-ingest' found under {base_dir}")

all_valid = True
invalid_files = []
for file in ingest_files:
    try:
        with file.open("r", encoding="utf-8") as f:
            yaml.safe_load(f)
        # print(f"✅ {file} is valid")
    except Exception as e:
        all_valid = False
        invalid_files.append(file)
        print(f"❌ {file} is invalid: {e}")

print(f"\n{'='*80}")
print(f"Summary: {len(ingest_files) - len(invalid_files)}/{len(ingest_files)} files valid")
if invalid_files:
    print(f"\n❌ {len(invalid_files)} invalid file(s):")
    for file in invalid_files:
        print(f"  - {file}")
    print(f"{'='*80}")
    exit(1)
else:
    print(f"✅ All files valid!")
    print(f"{'='*80}")
    exit(0)