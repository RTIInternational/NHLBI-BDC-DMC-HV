"""Markdown report generation for the compare pipeline.

Takes a list of CheckResult objects plus context (cohort name, source/harmonized
metadata, optional crosswalk) and produces a Markdown report string.

The renderer is currently coupled to pre-formatted message strings produced by
the check functions (see REFACTOR_PLAN Phase C-prereq). Once checks emit
structured detail instead, much of the per-row formatting here moves to
template-driven logic.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from hv_dataqc.compare._common import CheckResult, md_escape

STATUS_ICONS = {
    "PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]",
    "SKIP": "[SKIP]", "INFO": "[INFO]",
}


def generate_markdown_report(
    results: list[CheckResult],
    cohort: str,
    source_meta: dict,
    harmonized_meta: dict,
    crosswalk: list[dict] | None = None,
    yaml_dir: str | None = None,
) -> str:
    """Generate a human-readable Markdown report."""
    # Extract dbGaP study ID (e.g. phs000280.v8.p2) from source directory names.
    # Two directory naming conventions exist on SB:
    #   BDC TOPMed:   nih-nhlbi-topmed-parent-hchs-sol-phs000810-v2-r1-c1
    #   PilotParent:  parent-CHS_DS-CVD-MDS_-phs000287-v7-p1-c3
    # The TOPMed form uses -r<N>-c<N>; the PilotParent form uses -p<N>-c<N>.
    # Extract the participant-set number from the directory when available rather
    # than hardcoding it.
    study_id_full = ""
    for sd in source_meta.get("source_dirs", []):
        # BDC TOPMed form: phs000810-v2-r1-c1
        m = re.search(r'(phs\d+)[-_]v(\d+)[-_]r\d+[-_]c\d+', sd)
        if m:
            study_id_full = f"{m.group(1)}.v{m.group(2)}.p2"
            break
        # PilotParent form: phs000287-v7-p1-c3
        m = re.search(r'(phs\d+)[-_]v(\d+)[-_]p(\d+)[-_]c\d+', sd)
        if m:
            study_id_full = f"{m.group(1)}.v{m.group(2)}.p{m.group(3)}"
            break
    dbgap_datasets_url = (
        f"https://dbgap.ncbi.nlm.nih.gov/beta/study/{study_id_full}/#phenotype-datasets"
        if study_id_full else ""
    )
    dbgap_list_url = (
        f"https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/GetListOfAllObjects.cgi?"
        f"study_id={study_id_full}&object_type=dataset"
        if study_id_full else ""
    )

    lines = [
        f"# HV-DataQC Comparison Report: {cohort}",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Source:** {source_meta.get('source', '?')}",
    ]
    if source_meta.get("input_file"):
        lines.append(f"**Source file:** `{source_meta['input_file']}`")
    for sd in source_meta.get("source_dirs", []):
        lines.append(f"**Source dir:** `{Path(sd).name}`")
    lines.append(f"**Harmonized:** {harmonized_meta.get('source', '?')}")
    if harmonized_meta.get("input_file"):
        lines.append(f"**Harmonized file:** `{harmonized_meta['input_file']}`")
    for md in harmonized_meta.get("mapped_data_dirs", []):
        # Show the top-level consent-group folder (grandparent of mapped-data),
        # e.g. DMC_parent-CHS_HMB-MDS_-phs000287-v7-p1-c1_CHS_Processed_...
        _p = Path(md)
        _label = _p.parents[1].name if len(_p.parts) >= 3 else _p.name
        lines.append(f"**Harmonized dir:** `{_label}`")
    if yaml_dir:
        lines.append(f"**YAML dir:** `{yaml_dir}`")
    if study_id_full:
        lines.append(
            f"**dbGaP:** [{study_id_full}]({dbgap_datasets_url})"
            f" ([dataset list]({dbgap_list_url}))"
        )
    lines.append("")

    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    lines.append("## Summary")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|--------|-------|")
    for status in ["PASS", "WARN", "FAIL", "SKIP", "INFO"]:
        if counts.get(status, 0) > 0:
            lines.append(f"| {STATUS_ICONS[status]} {status} | {counts[status]} |")
    lines.append(f"| **Total** | **{sum(counts.values())}** |")
    lines.append("")

    # Multi-PHT pooled-source crosswalk audit section.  Lists every harmonized
    # variable whose source side was aggregated across multiple dbGaP tables
    # (typical for longitudinal measurements that appear once per visit).
    if crosswalk:
        pooled_entries = [m for m in crosswalk if len(m.get("_source_phts") or []) > 1]
        if pooled_entries:
            lines.append("## Pooled Source Crosswalk (multi-PHT aggregation)")
            lines.append("")
            lines.append(
                "Harmonized variables whose source side was pooled across multiple "
                "dbGaP tables. The compare tool reports a single combined `n_valid`, "
                "weighted mean, pooled SD and merged value distribution against the "
                "harmonized longitudinal output."
            )
            lines.append("")

            # Group by domain (prefix before the first underscore)
            domain_groups: dict[str, list[dict]] = defaultdict(list)
            for m in pooled_entries:
                hkey = m.get("harmonized_key", "")
                domain = hkey.split("_", 1)[0] if "_" in hkey else "other"
                domain_groups[domain].append(m)

            domain_labels = {
                "measurement": "Measurement",
                "condition": "Condition",
                "observation": "Observation",
                "demog": "Demography",
            }

            for domain in sorted(domain_groups):
                entries = domain_groups[domain]
                label = domain_labels.get(domain, domain.title())
                lines.append(f"<details><summary>{label} ({len(entries)} pooled variables)</summary>")
                lines.append("")
                lines.append(
                    "| Harmonized key | Source column(s) | Contributing PHTs | Pooled n_valid |"
                )
                lines.append(
                    "|----------------|------------------|-------------------|---------------:|"
                )
                for m in entries:
                    hkey = md_escape(m.get("harmonized_key", ""))
                    src_keys = ", ".join(md_escape(s) for s in (m.get("_source_keys") or []))
                    phts = ", ".join(sorted(set(m.get("_source_phts") or [])))
                    pooled_n = (m.get("_resolved_src") or {}).get("n_valid", 0)
                    lines.append(f"| {hkey} | {src_keys} | {phts} | {pooled_n:,} |")
                lines.append("")
                lines.append("</details>")
                lines.append("")

    check_names = {
        "CROSSWALK": "Crosswalk Resolution Failures",
        "C0": "Entity File Coverage",
        "C1": "N Preservation", "C2": "N Loss Detection",
        "C3": "Missing Value Accounting", "C4": "Mean Preservation",
        "C5": "Mean After Conversion", "C6": "SD Preservation",
        "C7": "Categorical Distribution", "C8": "Visit N Distribution",
        "C9": "Clinical Range", "C10": "Cross-Variable Consistency",
        "C11": "Variable Type Consistency",
        "C12": "Value Mapping Coverage",
        "C13": "UUID Format Validation",
        "C14": "Duplicate Row Detection",
    }

    def _render_c2_detail(r: CheckResult) -> list[str]:
        """Render per-PHT source breakdown and harmonized n_total note for C2 FAIL/WARN."""
        if r.status not in ("FAIL", "WARN"):
            return []
        sub: list[str] = []
        breakdown = r.detail.get("per_pht_src_breakdown") or []
        h_n_total = r.detail.get("harmonized_n_total")
        null_rows = r.detail.get("harmonized_null_status_rows", 0)
        if not breakdown and h_n_total is None:
            return sub
        if breakdown:
            has_phv = any(row.get("phv") for row in breakdown)
            has_pht = any(row.get("pht") for row in breakdown)
            sub.append("")
            if has_phv and has_pht:
                sub.append("  | PHV | PHT | Block src n\\_valid |")
                sub.append("  |-----|-----|-------------------:|")
                for row in breakdown:
                    sub.append(
                        f"  | {row.get('phv', '')} | {row.get('pht', '')} | {row['source_n_valid']:,} |"
                    )
            elif has_phv:
                sub.append("  | PHV | Block src n\\_valid |")
                sub.append("  |-----|-------------------:|")
                for row in breakdown:
                    sub.append(f"  | {row.get('phv', '')} | {row['source_n_valid']:,} |")
            else:
                sub.append("  | PHT | Block src n\\_valid |")
                sub.append("  |-----|-------------------:|")
                for row in breakdown:
                    sub.append(f"  | {row.get('pht', '')} | {row['source_n_valid']:,} |")
        if h_n_total is not None:
            harmonized_n = r.detail.get("harmonized_n", 0)
            sub.append(
                f"  _harmonized: n\\_total={h_n_total:,}, n\\_valid={harmonized_n:,}"
                f" ({null_rows:,} null-status rows — check value\\_mappings key types)_"
            )
        return sub

    def _render_c7_detail(r: CheckResult) -> list[str]:
        """Render C7 distribution table and mismatch detail as indented markdown."""
        sub: list[str] = []
        table = r.detail.get("distribution_table", [])
        if not table:
            return sub
        sub.append("")
        mismatch_cats = {m["category"] for m in r.detail.get("mismatches", [])}
        missing_cats = set(r.detail.get("missing_categories", []))
        extra_cats = set(r.detail.get("extra_categories", []))
        # Check if all rows are identical (src == harmonized) to simplify the table
        all_identical = all(
            row.get("source_n") == row.get("harmonized_n")
            and row.get("source_pct") == row.get("harmonized_pct")
            for row in table
        )
        if all_identical:
            sub.append("  | Category | N | % |")
            sub.append("  |----------|------:|------:|")
        else:
            sub.append("  | Category | Src N | Src % | Harmonized N | Harmonized % | Δ% |")
            sub.append("  |----------|------:|------:|------:|------:|---:|")
        for row in table:
            cat = row["category"]
            cat_label = md_escape(cat)
            src_n = f"{row['source_n']:,}" if isinstance(row.get("source_n"), (int, float)) else str(row.get("source_n", ""))
            src_pct = f"{row['source_pct']:.1f}" if row.get("source_pct") is not None else ""
            flag = " ⚠" if cat in mismatch_cats else (
                   " ✗" if cat in missing_cats else (
                   " ＋" if cat in extra_cats else ""))
            if all_identical:
                sub.append(f"  | {cat_label}{flag} | {src_n} | {src_pct} |")
            else:
                harmonized_n = f"{row['harmonized_n']:,}" if isinstance(row.get("harmonized_n"), (int, float)) else str(row.get("harmonized_n", ""))
                harmonized_pct = f"{row['harmonized_pct']:.1f}" if row.get("harmonized_pct") is not None else ""
                if row.get("source_pct") is not None and row.get("harmonized_pct") is not None:
                    delta = f"{row['harmonized_pct'] - row['source_pct']:+.1f}"
                else:
                    delta = ""
                sub.append(f"  | {cat_label}{flag} | {src_n} | {src_pct} | {harmonized_n} | {harmonized_pct} | {delta} |")
        return sub

    _check_descriptions = {
        "C0": (
            "Pre-flight check: verifies that every entity TSV (Visit, Demography, "
            "MeasurementObservation, etc.) produced rows in every consent group. "
            "FAIL means an entity file was empty or missing for some groups while "
            "other groups loaded it successfully — this signals a pipeline failure "
            "(e.g. OOM, crashed run) rather than a data-quality issue. "
            "Requires ``consent_group_file_status`` in the harmonized JSON "
            "(hv-dataqc issue #690); skipped gracefully on older JSON artifacts."
        ),
        "CROSSWALK": (
            "Source-column lookups that the YAML/cache could not resolve to a "
            "single PHT. When a column name appears in multiple source tables "
            "and the YAML doesn't pin the PHV→PHT mapping, the comparison "
            "can't pick one PHT's stats safely — so those variables are "
            "marked FAIL here and skipped from the per-check matrix below. "
            "Resolve by fixing the YAML's `populated_from` to disambiguate, "
            "or by adding multi-PHT aggregation when the source data truly "
            "should be pooled."
        ),
        "C1": (
            "Checks whether the total number of unique participants is preserved "
            "from source to harmonized. A small loss may indicate that the pipeline's "
            "anchor table (e.g. Demographics_Baseline) excludes participants who appear "
            "in other source tables. Investigate with `find_participant_gap.py` on SB."
        ),
        "C2": (
            "Checks per-variable valid-N counts. PASS means the harmonized output has "
            "the same number of non-missing values as the source for that variable. "
            "FAIL means rows were silently lost or gained during transformation."
        ),
        "C3": (
            "Checks that missing-value rates are stable between source and harmonized. "
            "A shift suggests the pipeline is introducing or removing nulls."
        ),
        "C4": (
            "Checks that continuous variable means are preserved (no unit conversion). "
            "Deviations close to zero (d<0.001) are rounding artifacts. Larger deviations "
            "suggest data corruption or unintended filtering."
        ),
        "C5": (
            "Checks continuous means after a known unit conversion factor "
            "(e.g. inches to cm). Skipped when no conversion is expected."
        ),
        "C6": (
            "Checks that standard deviations are preserved. A shift in SD without a "
            "corresponding shift in mean suggests outlier filtering or truncation."
        ),
        "C7": (
            "Compares categorical value distributions after applying YAML value_mappings "
            "(e.g. source code 1/2 mapped to PRESENT/ABSENT). Categories are aggregated "
            "when multiple source values map to one harmonized category."
        ),
        "C8": (
            "Checks that per-visit row counts are preserved. For table-based cohorts "
            "where source files have no visit column, source visit counts are synthesized "
            "from total_rows_by_pht + visit.yaml mappings."
        ),
        "C9": (
            "Checks whether harmonized min/max values fall within clinically plausible "
            "ranges defined in `clinical_ranges.yaml`. This catches sentinel values "
            "(e.g. 0 or 999) that should have been mapped to missing, as well as unit "
            "conversion errors that produce impossible values.\n\n"
            "> **Annotations:** `[out+src]` = outlier exists in both source and harmonized "
            "(pre-existing in raw data, faithfully preserved — not a pipeline bug). "
            "`[out only]` = harmonized exceeds bound but source did not "
            "(the pipeline may have introduced the issue). "
            "`[src only]` = source exceeds bound but harmonized does not "
            "(pipeline corrected or filtered the value)."
        ),
        "C10": (
            "Checks cross-variable consistency rules (e.g. SBP > DBP, FEV1 < FVC). "
            "Rules are defined in `clinical_ranges.yaml`. Formula-based rules "
            "(e.g. BMI consistency) are not yet implemented."
        ),
        "C11": (
            "Checks that source and harmonized agree on variable type "
            "(continuous vs categorical). A mismatch suggests the YAML transform "
            "or the source type inference needs attention."
        ),
        "C12": (
            "Checks that YAML value_mappings cover dbGaP coded values and observed "
            "source categories. This is separate from before/after preservation: an "
            "unmapped code can be expected transform behavior while still being a "
            "YAML completeness issue."
        ),
        "C13": (
            "Checks that every ``associated_participant`` and ``associated_visit`` value "
            "in the harmonized output is a valid UUID string. Malformed values indicate "
            "a broken ID expression in the YAML — e.g. a null source PHV propagating "
            "through ``uuid5()`` to produce a non-UUID string that silently passes all "
            "per-variable checks. Requires ``uuid_validation`` in the harmonized JSON "
            "(hv-dataqc issue #703); skipped gracefully on older JSON artifacts."
        ),
        "C14": (
            "Checks that the harmonized output contains no exact duplicate rows within "
            "each entity class (all non-id columns identical). Duplicates indicate YAML "
            "design issues such as multi-block transforms without a discriminating "
            "condition, or a populated_from table scope that is wider than intended. "
            "Requires ``duplicate_stats`` in the harmonized JSON "
            "(hv-dataqc issue #704); skipped gracefully on older JSON artifacts."
        ),
    }

    def _render_unmatched_source(r: CheckResult) -> list[str]:
        """Render unmatched source variables as a collapsed block."""
        sub: list[str] = []
        keys = r.detail.get("source_keys", [])
        if not keys:
            return sub
        sub.append("")
        sub.append(f"<details><summary>{len(keys)} unmatched source variables</summary>")
        sub.append("")
        for sk in sorted(keys):
            sub.append(f"- `{sk}`")
        sub.append("")
        sub.append("</details>")
        return sub

    for check_id in ["CROSSWALK", "C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "C13", "C14"]:
        check_results = [r for r in results if r.check_id == check_id]
        if not check_results:
            continue
        lines.append(f"## {check_id}: {check_names.get(check_id, check_id)}")
        lines.append("")
        if check_id in _check_descriptions:
            lines.append(_check_descriptions[check_id])
            lines.append("")

        # Separate results by status for collapsing
        fails = [r for r in check_results if r.status == "FAIL"]
        warns = [r for r in check_results if r.status == "WARN"]
        infos = [r for r in check_results if r.status == "INFO"]
        passes = [r for r in check_results if r.status == "PASS"]
        skips = [r for r in check_results if r.status == "SKIP"]

        _COLLAPSE_THRESHOLD = 4  # collapse a status group when it has more than this many items

        def _render_group(group_results: list[CheckResult], label: str, always_collapse: bool = False) -> None:
            """Render a group of results, collapsing if large or always_collapse."""
            if not group_results:
                return
            collapse = always_collapse or len(group_results) > _COLLAPSE_THRESHOLD
            if collapse:
                lines.append("")
                lines.append(f"<details><summary>{len(group_results)} {label} results</summary>")
                lines.append("")
            for r in group_results:
                icon = STATUS_ICONS.get(r.status, r.status)
                lines.append(f"- {icon} **{md_escape(r.variable)}**: {md_escape(r.message)}")
                if check_id == "C2":
                    lines.extend(_render_c2_detail(r))
                if check_id == "C7":
                    lines.extend(_render_c7_detail(r))
                if r.detail.get("direction") == "source_unmatched_summary":
                    lines.extend(_render_unmatched_source(r))
            if collapse:
                lines.append("")
                lines.append("</details>")

        _render_group(fails, "FAIL")
        _render_group(warns, "WARN")
        _render_group(infos, "INFO")
        _render_group(passes, "PASS")
        _render_group(skips, "SKIP", always_collapse=True)

        lines.append("")

    return "\n".join(lines)
