"""Does a source extract cover every PHV the current specs reference?

An extract made with ``--scope-to-yaml`` summarizes only the PHVs its specs
referenced when it ran, and records them as ``metadata.scoped_to_phvs``.  A
spec edited since then can name a PHV the extract never looked at, and the
S4 join would silently count it with N = 0.  ``run_s4_report.sh`` calls this
to decide whether to re-extract.

Comparing against what the extract *tried* to include (not what resolved)
keeps a column that is genuinely absent from the source from forcing a
re-extract on every run; ``spec_phv_report`` warns about those instead.

Exit status: 0 if the extract is current, 1 if it is stale (reason on stdout).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hv_dataqc.extract_source.scan_yaml_phv_pairs import scan_yaml_for_phvs


def stale_reason(source_doc: dict, spec_phvs: set[str]) -> str | None:
    """Return why the extract doesn't cover *spec_phvs*, or None if it does."""
    meta = source_doc.get("metadata") or {}
    if "scoped_to_phvs" not in meta:
        return "extract predates coverage tracking"
    if meta.get("phv_list"):
        return "extract was limited by --phv-list"
    scoped = meta["scoped_to_phvs"]
    if scoped is None:
        return None  # full extract: every column was summarized
    uncovered = sorted(spec_phvs - set(scoped))
    if not uncovered:
        return None
    shown = ", ".join(uncovered[:5]) + (" ..." if len(uncovered) > 5 else "")
    return f"{len(uncovered)} spec PHV(s) not in extract scope: {shown}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source-json", required=True, type=Path)
    p.add_argument("--yaml-dir", required=True, type=Path,
                   help="The cohort's transform spec dir (<cohort>-ingest).")
    args = p.parse_args(argv)

    reason = stale_reason(json.loads(args.source_json.read_text()),
                          scan_yaml_for_phvs(args.yaml_dir))
    if reason:
        print(reason)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
