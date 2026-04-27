#!/usr/bin/env python3
"""Find participants present in some COPDGene PHT tables but not others.

Run on Seven Bridges to investigate the 12-participant gap between source
(10,731 unique IDs across 4 PHTs) and harmonized (10,719 anchored on
Demographics_Baseline / pht016246).

Outputs only aggregate counts and PHT-membership patterns -- safe to export.
"""

from __future__ import annotations

import argparse
import gzip
from collections import Counter, defaultdict
from pathlib import Path


PHT_LABELS = {
    "pht002237": "Subject",
    "pht002239": "Subject_Phenotypes",
    "pht002259": "Subject_Images",
    "pht016246": "Demographics_Baseline",
}


def load_ids(path: Path, id_col: str = "dbGaP_Subject_ID") -> set[str]:
    """Read a dbGaP gzipped TSV; return the set of IDs in id_col.

    dbGaP files start with a comment block prefixed by '#'. The header is the
    first line not starting with '#'.
    """
    ids: set[str] = set()
    open_fn = gzip.open if path.suffix == ".gz" else open
    with open_fn(path, "rt", encoding="utf-8", errors="replace") as fh:
        header: list[str] | None = None
        idx: int | None = None
        for line in fh:
            if line.startswith("#"):
                continue
            if header is None:
                header = line.rstrip("\n").split("\t")
                if id_col not in header:
                    raise ValueError(f"{id_col!r} not in header of {path.name}: {header[:5]}...")
                idx = header.index(id_col)
                continue
            parts = line.rstrip("\n").split("\t")
            if idx is not None and idx < len(parts):
                val = parts[idx].strip()
                if val:
                    ids.add(val)
    return ids


def find_pht_files(source_root: Path) -> dict[str, list[Path]]:
    """Discover {pht: [files...]} under source_root, across consent groups."""
    pht_files: dict[str, list[Path]] = defaultdict(list)
    for cg_dir in sorted(p for p in source_root.iterdir() if p.is_dir()):
        for f in cg_dir.iterdir():
            if not f.is_file():
                continue
            for pht in PHT_LABELS:
                if pht in f.name and f.name.endswith(".txt.gz"):
                    pht_files[pht].append(f)
                    break
    return dict(pht_files)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--source-root",
        type=Path,
        default=Path("/sbgenomics/project-files/PilotParentStudies_NoDRS/COPDGene"),
        help="Directory containing copdgene_phs000179_v7_r1_c1, _c2, etc.",
    )
    args = ap.parse_args()

    pht_files = find_pht_files(args.source_root)
    missing = [p for p in PHT_LABELS if p not in pht_files]
    if missing:
        raise SystemExit(f"Missing PHT files for: {missing}")

    print("Loading IDs from each PHT (across consent groups)...")
    pht_ids: dict[str, set[str]] = {}
    for pht, files in pht_files.items():
        ids: set[str] = set()
        for f in files:
            ids |= load_ids(f)
        pht_ids[pht] = ids
        print(f"  {pht} ({PHT_LABELS[pht]}): {len(ids):,} unique IDs across {len(files)} file(s)")

    all_ids = set().union(*pht_ids.values())
    demog = pht_ids["pht016246"]
    gap = all_ids - demog
    print()
    print(f"Union of all PHTs:           {len(all_ids):,}")
    print(f"In Demographics_Baseline:    {len(demog):,}")
    print(f"GAP (missing from baseline): {len(gap):,}")

    # Per-PHT membership pattern for the gap participants -- no IDs leave
    print()
    print("Membership pattern of GAP participants (which PHTs they DO appear in):")
    pattern_counts: Counter[tuple[str, ...]] = Counter()
    for pid in gap:
        pattern = tuple(
            sorted(pht for pht, ids in pht_ids.items() if pid in ids)
        )
        pattern_counts[pattern] += 1
    for pattern, n in pattern_counts.most_common():
        labels = " + ".join(PHT_LABELS[p] for p in pattern)
        print(f"  {n:>5}  in: {labels}")


if __name__ == "__main__":
    main()
