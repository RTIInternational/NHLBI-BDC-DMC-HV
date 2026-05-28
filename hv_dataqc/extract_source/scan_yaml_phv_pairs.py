"""scan_yaml_phv_pairs.py — pre-scan HV transform YAML files for multi-PHV pairs.

Identifies which PHV accession pairs appear together in multi-PHV ``case()``
branch conditions so the source extractor can pre-compute pairwise crosstabs
for those pairs.  Used by ``extract_source_summaries.py --yaml-dir``.

The pre-scan is intentionally line-oriented and does not fully parse YAML —
it only needs to detect whether two or more ``{phvXXXXXX}`` references appear
on the same logical line (a ``when:`` value or inline ``case()`` call).  YAML
multi-line blocks that split a single condition across two physical lines are
not captured; this is acceptable because production HV transforms always keep
a single branch condition on one line.
"""
from __future__ import annotations

import re
from pathlib import Path

# Matches any {phvXXXXXX} reference (case-insensitive, no version suffix)
_PHV_REF_RE = re.compile(r"\{(phv\d+)\}", re.IGNORECASE)


def scan_yaml_for_phv_pairs(yaml_dir: Path) -> list[tuple[str, str]]:
    """Return deduplicated canonical (phv_a, phv_b) pairs from multi-PHV conditions.

    Scans all ``*.yaml`` files under *yaml_dir* for lines that reference two or
    more distinct PHV accessions in the same expression (typically a ``when:``
    branch or an inline ``case()`` call).  Returns every unique pair with PHV
    accessions in alphabetically-sorted canonical order.

    Only pairs (not triples or higher) are returned; three-way joint
    distributions are not yet supported by the compare engine.

    Parameters
    ----------
    yaml_dir:
        Root directory to search recursively for ``*.yaml`` files.

    Returns
    -------
    list[tuple[str, str]]
        Sorted, deduplicated list of ``(phv_a, phv_b)`` tuples where
        ``phv_a < phv_b`` lexicographically.
    """
    pairs: set[frozenset[str]] = set()

    for yaml_file in sorted(yaml_dir.rglob("*.yaml")):
        try:
            text = yaml_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for line in text.splitlines():
            # Only scan lines that could contain PHV references
            if "{phv" not in line.lower():
                continue

            phvs = [m.group(1).lower() for m in _PHV_REF_RE.finditer(line)]
            distinct = sorted(set(phvs))
            if len(distinct) < 2:
                continue

            # Record every unique pair from this line
            for i in range(len(distinct)):
                for j in range(i + 1, len(distinct)):
                    pairs.add(frozenset({distinct[i], distinct[j]}))

    return sorted(tuple(sorted(p)) for p in pairs)
