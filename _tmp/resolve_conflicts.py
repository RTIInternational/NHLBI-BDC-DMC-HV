"""
Resolves merge conflicts in priority_variables_transform YAML files.

Strategy:
- Take HEAD content for each conflicted file
- Convert old object_derivations format to new class_derivations/name format
- Apply special overrides where needed
- Write resolved files (do NOT stage/commit)
"""
import subprocess
import os
import re

REPO_ROOT = r"c:\SourceCode\NHLBI-BDC-DMC-HV"

# Files to handle by deletion (our branch deleted them; keep the deletion)
DELETE_FILES = [
    "priority_variables_transform/CARDIA-ingest/bdy_temp.yaml",
    "priority_variables_transform/HCHS-ingest/spirometry_post_bd.yaml",
]

# Files with both-modified conflicts to resolve by taking HEAD + transforming format
BOTH_MODIFIED_FILES = [
    "priority_variables_transform/ARIC-ingest/spirometry.yaml",
    "priority_variables_transform/CARDIA-ingest/spirometry.yaml",
    "priority_variables_transform/CHS-ingest/cysc_bld.yaml",
    "priority_variables_transform/CHS-ingest/spirometry.yaml",
    "priority_variables_transform/COPDGene-ingest/spirometry.yaml",
    "priority_variables_transform/FHS-ingest/bdy_hgt.yaml",
    "priority_variables_transform/FHS-ingest/creat_urin.yaml",
    "priority_variables_transform/FHS-ingest/mch.yaml",
    "priority_variables_transform/FHS-ingest/spirometry.yaml",
    "priority_variables_transform/HCHS-ingest/spirometry.yaml",
    "priority_variables_transform/JHS-ingest/creat_urin.yaml",
    "priority_variables_transform/JHS-ingest/crp.yaml",
    "priority_variables_transform/JHS-ingest/spirometry.yaml",
    "priority_variables_transform/LTRC-ingest/spirometry_post_bd.yaml",
    "priority_variables_transform/LTRC-ingest/spirometry_pre_bd.yaml",
    "priority_variables_transform/MESA-ingest/spirometry.yaml",
    "priority_variables_transform/SPIROMICS-ingest/spirometry_post_bd.yaml",
    "priority_variables_transform/SPIROMICS-ingest/spirometry_pre_bd.yaml",
]


def get_head_content(filepath_rel):
    """Get the HEAD (our branch) version of a file."""
    result = subprocess.run(
        ["git", "show", f"HEAD:{filepath_rel}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git show HEAD failed for {filepath_rel}: {result.stderr}")
    return result.stdout


def transform_yaml_format(text):
    """
    Convert old format:
        object_derivations:
        - class_derivations:
            ClassName:
              [content indented by 2 relative to ClassName]

    To new format:
        class_derivations:
        - name: ClassName
          [content indented by 2 relative to - name, i.e. original content dedented by 4]

    Applied via multiple passes to handle nested occurrences.
    """
    lines = text.split("\n")
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if not stripped:
            result.append(line)
            i += 1
            continue
        indent = len(line) - len(stripped)

        if stripped == "object_derivations:":
            result.append(" " * indent + "class_derivations:")
            i += 1
            # Process list items that follow at the same indent level
            while i < len(lines):
                item_line = lines[i]
                item_stripped = item_line.lstrip()
                if not item_stripped:
                    result.append(item_line)
                    i += 1
                    continue
                item_indent = len(item_line) - len(item_stripped)
                if item_indent < indent:
                    break  # End of object_derivations block

                if item_stripped == "- class_derivations:" and item_indent == indent:
                    i += 1
                    # Skip any blank lines
                    while i < len(lines) and not lines[i].strip():
                        result.append(lines[i])
                        i += 1
                    if i < len(lines):
                        cn_line = lines[i]
                        cn_stripped = cn_line.lstrip()
                        cn_indent = len(cn_line) - len(cn_stripped)
                        # Verify this is a class name: ClassName: (no spaces, ends with :)
                        if (
                            cn_stripped.endswith(":")
                            and cn_indent == indent + 4
                            and not cn_stripped.startswith("-")
                            and " " not in cn_stripped.rstrip(":")
                        ):
                            class_name = cn_stripped[:-1]
                            result.append(" " * indent + "- name: " + class_name)
                            i += 1
                            # Process content under ClassName (dedent by 4)
                            while i < len(lines):
                                cl = lines[i]
                                cls = cl.lstrip()
                                if not cls:
                                    result.append(cl)
                                    i += 1
                                    # Peek ahead to see if still in block
                                    j = i
                                    while j < len(lines) and not lines[j].strip():
                                        j += 1
                                    if j >= len(lines):
                                        break
                                    if len(lines[j]) - len(lines[j].lstrip()) <= indent:
                                        break
                                    continue
                                cl_indent = len(cl) - len(cls)
                                if cl_indent <= indent:
                                    break  # End of this class's content
                                result.append(" " * (cl_indent - 4) + cls)
                                i += 1
                        else:
                            result.append(cn_line)
                            i += 1
                else:
                    break  # Not a list item of object_derivations
        else:
            result.append(line)
            i += 1

    return "\n".join(result)


def transform_all_passes(text):
    """Apply transform_yaml_format repeatedly until stable (handles nesting)."""
    prev = None
    while prev != text:
        prev = text
        text = transform_yaml_format(text)
    return text


def resolve_file(filepath_rel):
    """Resolve a single conflicted file by taking HEAD + transforming format."""
    print(f"  Resolving: {filepath_rel}")
    content = get_head_content(filepath_rel)
    resolved = transform_all_passes(content)
    return resolved


def apply_aric_spirometry_override(text):
    """
    Override: ARIC OMOP:3011505 method_type should be 'spirometry' (not 'calculated').
    This is a specific user request for ARIC spirometry only.
    Only changes method_type within blocks that have observation_type OMOP:3011505.
    """
    # Strategy: find observation blocks with OMOP:3011505 and change their method_type
    # We'll use a careful line-by-line approach
    lines = text.split("\n")
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        # Look for observation_type value OMOP:3011505
        if stripped == 'value: "OMOP:3011505"':
            result.append(line)
            i += 1
            # Look ahead for method_type within the same observation block
            # The method_type should be in the next few lines at the same indent level
            obs_indent = len(lines[i - 1]) - len(lines[i - 1].lstrip()) if i > 0 else 0
            # Find observation block indent (parent of observation_type)
            obs_block_indent = obs_indent
            # Scan forward for method_type at same indent
            j = i
            while j < len(lines):
                jl = lines[j]
                jls = jl.lstrip()
                if not jls:
                    j += 1
                    continue
                ji = len(jl) - len(jls)
                if ji < obs_block_indent:
                    break  # Left the observation block
                if jls.startswith("method_type:"):
                    # Found method_type, check next line for value
                    result.append(jl)
                    j += 1
                    if j < len(lines):
                        vl = lines[j]
                        vls = vl.lstrip()
                        if vls.startswith("value:"):
                            # Replace with spirometry
                            vi = len(vl) - len(vls)
                            result.append(" " * vi + "value: spirometry")
                            j += 1
                        else:
                            result.append(vl)
                            j += 1
                    i = j
                    break
                else:
                    j += 1
            else:
                pass
        else:
            result.append(line)
            i += 1
    return "\n".join(result)


def main():
    print("=== Resolving merge conflicts ===\n")

    # Step 1: Handle deletion conflicts
    print("--- Keeping deletions ---")
    for rel_path in DELETE_FILES:
        abs_path = os.path.join(REPO_ROOT, rel_path)
        if os.path.exists(abs_path):
            os.remove(abs_path)
            print(f"  Deleted: {rel_path}")
        else:
            print(f"  Already absent: {rel_path}")

    print()

    # Step 2: Resolve both-modified conflicts
    print("--- Resolving both-modified conflicts ---")
    for rel_path in BOTH_MODIFIED_FILES:
        try:
            resolved = resolve_file(rel_path)

            # Apply special overrides
            if rel_path == "priority_variables_transform/ARIC-ingest/spirometry.yaml":
                resolved = apply_aric_spirometry_override(resolved)

            abs_path = os.path.join(REPO_ROOT, rel_path)
            with open(abs_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(resolved)
            print(f"  Done: {rel_path}")
        except Exception as e:
            print(f"  ERROR: {rel_path}: {e}")

    print("\n=== Done. Review changes before staging. ===")


if __name__ == "__main__":
    main()
