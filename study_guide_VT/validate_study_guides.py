"""Validate the study guide TSVs in this directory.

Run: python study_guide_VT/validate_study_guides.py   (exit 1 on any error)

Checks are structural and mechanical only -- they never judge whether a code or definition is
clinically right. Standard library only.

Files are named `<BDC-HM class> <Kind>.tsv` where Kind is Concepts, Variables or Metadata.
Column roles are found by header name (case-insensitive), so every class can use the same rules:
  - the first column of a Concepts or Variables file is the concept name (the key)
  - `CURIE`, `output file`, `target unit`, `data type`, `Example source variable ...` are optional
    columns that are checked when present
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

BDCHM_CLASSES = {
    "Condition", "MeasurementObservation", "MeasurementObservationSet", "DrugExposure",
    "Procedure", "Observation", "ObservationSet", "SdohObservation", "SdohObservationSet",
    "Demography", "Person", "Participant", "Visit", "ResearchStudy", "Questionnaire",
    "QuestionnaireResponse", "Specimen", "Device", "DeviceExposure", "Exposure",
}
KINDS = {"Concepts", "Variables", "Metadata"}
FILE_RE = re.compile(r"^(?P<cls>[A-Za-z]+) (?P<kind>[A-Za-z]+)\.tsv$")
CURIE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]*:[A-Za-z0-9_.\-]+$")
SNAKE_RE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")
ENUM_RE = re.compile(r"^[A-Z0-9]+(_[A-Z0-9]+)*$")
NUMERIC_TYPES = {"decimal", "integer"}
# UCUM spellings seen in these files that are not valid UCUM, with the valid form.
UCUM_FIXES = {"ratio": "{ratio}", "mm/hr": "mm/h", "pack-years": "{pack-years}",
              "mL/min/mm Hg": "mL/min/mm[Hg]", "mmHg": "mm[Hg]", "hr": "h", "%{}": "%"}


def norm(name: str) -> str:
    """How concept names are compared: case, punctuation and spacing are ignored."""
    return re.sub(r"[^a-z0-9]+", " ", (name or "").strip().lower()).strip()


def read(path: Path) -> list[list[str]]:
    text = path.read_bytes().decode("utf-8")
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return [line.split("\t") for line in lines]


def col(header: list[str], *names: str) -> int | None:
    low = [h.strip().lower() for h in header]
    for n in names:
        if n in low:
            return low.index(n)
    return None


def ucum_problem(unit: str) -> str | None:
    if unit in UCUM_FIXES:
        return f"not valid UCUM; use {UCUM_FIXES[unit]!r}"
    if " " in unit.replace("{", "").replace("}", "") and not re.search(r"\{[^}]* [^}]*\}", unit):
        return "contains a space (not valid UCUM)"
    if unit.count("{") != unit.count("}") or unit.count("[") != unit.count("]"):
        return "unbalanced brackets"
    return None


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    tables: dict[tuple[str, str], tuple[Path, list[list[str]]]] = {}

    for path in sorted(HERE.glob("*.tsv")):
        m = FILE_RE.match(path.name)
        if not m or m["kind"] not in KINDS:
            errors.append(f"{path.name}: name must be '<BDC-HM class> <Concepts|Variables|Metadata>.tsv'")
            continue
        if m["cls"] not in BDCHM_CLASSES:
            errors.append(f"{path.name}: '{m['cls']}' is not a BDC-HM class name")
        try:
            rows = read(path)
        except UnicodeDecodeError as exc:
            errors.append(f"{path.name}: not UTF-8 ({exc})")
            continue
        if not rows:
            errors.append(f"{path.name}: empty file")
            continue
        tables[(m["cls"], m["kind"])] = (path, rows)
        header = rows[0]
        width = len(header)
        for i, r in enumerate(rows[1:], 2):
            where = f"{path.name}:{i}"
            if len(r) != width:
                errors.append(f"{where}: {len(r)} columns, header has {width}")
            if not r[0].strip():
                errors.append(f"{where}: first column is blank (every row repeats its concept or slot name)")
            for j, cell in enumerate(r):
                if cell != cell.strip():
                    msg = f"{where}: leading/trailing spaces in column '{header[j] if j < width else j}'"
                    (errors if j == 0 else warnings).append(msg)

        c_curie = col(header, "curie")
        c_out = col(header, "output file")
        c_unit = col(header, "target unit")
        c_type = col(header, "data type")
        c_ex = [j for j, h in enumerate(header) if h.strip().lower().startswith("example source variable")]
        for i, r in enumerate(rows[1:], 2):
            where = f"{path.name}:{i} ({r[0].strip()})"
            get = lambda j: r[j].strip() if j is not None and j < len(r) else ""  # noqa: E731
            if c_curie is not None and get(c_curie):
                for code in [c.strip() for c in get(c_curie).split("|")]:
                    if not CURIE_RE.match(code):
                        errors.append(f"{where}: malformed CURIE {code!r}")
            if c_out is not None and m["kind"] == "Concepts":
                v = get(c_out)
                if not v:
                    errors.append(f"{where}: output file is blank")
                elif not SNAKE_RE.match(v):
                    errors.append(f"{where}: output file {v!r} must be lowercase_with_underscores, no .yaml")
            if c_unit is not None and get(c_unit):
                p = ucum_problem(get(c_unit))
                if p:
                    errors.append(f"{where}: target unit {get(c_unit)!r} {p}")
            if c_type is not None and c_unit is not None and get(c_type).lower() in NUMERIC_TYPES and not get(c_unit):
                errors.append(f"{where}: numeric data type with no target unit")
            for j in c_ex:
                v = get(j)
                if v:
                    items = v.split("|")
                    if any(not x.strip() for x in items):
                        errors.append(f"{where}: empty item in '{header[j]}'")
                    if any(x != x.strip() for x in items):
                        warnings.append(f"{where}: padded item in '{header[j]}'")
            if m["kind"] == "Metadata" and len(r) > 1 and get(1) and not ENUM_RE.match(get(1)):
                errors.append(f"{where}: enum value {get(1)!r} is not UPPER_SNAKE_CASE")

        if m["kind"] in ("Concepts", "Variables") and m["kind"] == "Concepts":
            seen: dict[str, int] = {}
            for i, r in enumerate(rows[1:], 2):
                k = norm(r[0])
                if k in seen:
                    errors.append(f"{path.name}:{i}: concept '{r[0]}' duplicates line {seen[k]}")
                seen.setdefault(k, i)
            for i, r in enumerate(rows[1:], 2):
                if any(ord(ch) > 127 for ch in r[0]):
                    warnings.append(f"{path.name}:{i}: non-ASCII character in concept name '{r[0]}'")

    # Concepts <-> Variables join, per class
    for (cls, kind), (path, rows) in tables.items():
        if kind != "Variables":
            continue
        concepts = tables.get((cls, "Concepts"))
        if not concepts:
            errors.append(f"{path.name}: has no matching '{cls} Concepts.tsv'")
            continue
        cnames = {norm(r[0]): r[0] for r in concepts[1][1:]}
        vnames = {norm(r[0]): r[0] for r in rows[1:]}
        for k, name in sorted(vnames.items()):
            if k not in cnames:
                errors.append(f"{path.name}: concept '{name}' has no row in {concepts[0].name}")
        for k, name in sorted(cnames.items()):
            if k not in vnames and col(concepts[1][0], "curie") is None:
                errors.append(f"{concepts[0].name}: concept '{name}' has no code row in {path.name}")

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"{len(tables)} files checked: {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
