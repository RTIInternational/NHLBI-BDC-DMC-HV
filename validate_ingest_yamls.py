from pathlib import Path
import yaml

ingest_dir = "./priority_variables_transform"
base_dir = Path(ingest_dir)

yaml_files = list(base_dir.rglob("*.yaml"))
ingest_files = [f for f in yaml_files if any("-ingest" in part for part in f.parts)]

if not ingest_files:
    print(f"No YAML files in directories with '-ingest' found under {base_dir}")

all_valid = True
for file in ingest_files:
    try:
        with file.open("r", encoding="utf-8") as f:
            yaml.safe_load(f)
        print(f"✅ {file} is valid")
    except Exception as e:
        all_valid = False
        print(f"❌ {file} is invalid: {e}")
        pass