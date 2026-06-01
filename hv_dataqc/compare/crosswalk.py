"""YAML-driven crosswalk builder — backward-compatible shim.

This module has been refactored into five focused sub-modules:

  - :mod:`hv_dataqc.compare.helpers`          — pure utility helpers
  - :mod:`hv_dataqc.compare.cache_maps`       — dbGaP PHV/PHT/type/code maps
  - :mod:`hv_dataqc.compare.match_resolution` — match mode inference and metadata
  - :mod:`hv_dataqc.compare.yaml_crosswalk`   — YAML parsing and key normalisation
  - :mod:`hv_dataqc.compare.expected_summary` — expected post-transform summaries

All public symbols are re-exported here for backward compatibility; existing
callers that import from ``hv_dataqc.compare.crosswalk`` continue to work
unchanged.  Only ``build_variable_crosswalk`` (the top-level orchestrator)
lives here permanently.
"""

from __future__ import annotations

from pathlib import Path

from hv_dataqc.compare._common import AmbiguousColumnError, CrosswalkBuildError
from hv_dataqc.hv_dataqc_common import normalize_category_key

# Sub-module re-exports — all public for backward compat
from hv_dataqc.compare.helpers import (  # noqa: F401
    _build_variables_by_name,
    _canonical_phv_id,
    _codes_are_numeric_or_sentinel,
    _distribution_count_map,
    _is_null_sentinel_code,
    _normalize_code,
    _NULL_SENTINEL_CODES,
    _pick_single_pht_summary,
)
from hv_dataqc.compare.cache_maps import (  # noqa: F401
    _DBGAP_CATEGORICAL_KEYWORDS,
    _DBGAP_CATEGORICAL_TYPES,
    _DBGAP_CONTINUOUS_KEYWORDS,
    _DBGAP_CONTINUOUS_TYPES,
    authoritative_source_type_for_match,
    determine_comparison_type,
    load_phv_name_map,
    load_phv_to_pht_map,
    load_phv_type_map,
    load_phv_value_codes_map,
    _yaml_intent_type_for_match,
)
from hv_dataqc.compare.expected_summary import (  # noqa: F401
    _aggregate_source_summaries,
    _apply_conversion_factor_to_summary,
    _case_branches,
    _categorical_summary_from_counts,
    _CASE_BRANCH_RE,
    _count_from_joint_dist,
    _distribution_count_for_code,
    _expected_summary_for_entry,
    _expected_summary_from_case_entry,
    _expected_summary_from_case_value_exprs,
    _expected_summary_from_concept_value_map,
    _expected_summary_from_value_map,
    _extract_phv_conditions,
    _is_status_transform_entry,
    _looks_like_unresolved_expr,
    _normalize_status_distribution,
    _PHV_EQ_RE,
    _PHV_IN_RE,
    _STATUS_CATEGORY_ALIASES,
    _status_alias_map,
    _strip_expr_literal,
    _unsupported_joint_summary,
    build_expected_summary,
)
from hv_dataqc.compare.yaml_crosswalk import (  # noqa: F401
    _COMMON_UNIT_FACTORS,
    _concept_codes_from_expr,
    _concept_codes_from_value_mappings,
    _CROSSWALK_TO_DISCOVERED,
    _CURIE_BARE_RE,
    _CURIE_QUOTED_RE,
    _extract_conversion_factor,
    _extract_crosswalk_from_class_derivations,
    _extract_value_mappings,
    _norm_obs_type,
    _normalize_harmonized_vars,
    _normalize_method_type_part,
    _SCALAR_MULT_RE,
    _to_discovered_key,
    _TUPLE_KEY_RE,
    _TUPLE_OBS_RE,
    _unit_conversion_factor,
    build_yaml_crosswalk,
)
from hv_dataqc.compare.match_resolution import (  # noqa: F401
    _expected_harmonized_n,
    _infer_match_mode,
    _promote_comparison_metadata,
    _source_phv_details_for_entries,
)

def build_variable_crosswalk(
    variables_by_name: dict[str, dict[str, dict]],
    harmonized_vars: dict,
    yaml_dir: Path,
    cache_dir: Path,
    source_doc: dict | None = None,
    diagnostics_out: dict | None = None,
) -> list[dict]:
    """Build source <-> harmonized variable crosswalk via YAML transforms.

    PHV -> concept code -> entity key.  When multiple YAML blocks (typically
    one per visit / source PHT) emit the SAME harmonized key, all per-PHT
    source summaries are pooled into one combined summary so the
    C2/C3/C4/C6/C7 comparisons see the same longitudinal pool the harmonized
    extractor produces.

    When *source_doc* contains ``variables_by_pht``, each YAML-matched entry
    gains a ``_resolved_src`` field with pooled stats drawn from every
    contributing PHT.  ``_source_phts`` lists the PHTs that contributed and
    ``_per_pht_src`` retains the individual per-PHT summaries for audit /
    diagnostic reporting.

    If *diagnostics_out* is supplied, it is populated with details of YAML
    entries the parser produced that could not be matched (missing source
    column or missing harmonized key) — keyed by harmonized_key for use by
    the unmatched-harmonized FAIL reporter.
    """
    matches: list[dict] = []
    matched_src: set[str] = set()
    matched_harmonized: set[str] = set()

    phv_names = load_phv_name_map(cache_dir)
    phv_to_pht = load_phv_to_pht_map(cache_dir)

    # Hard-fail when the cache directory produced no PHV->name mappings.
    # This catches typo'd paths, wrong-cohort caches, and caches that exist
    # but lack pheno_variable_summaries/*.data_dict.xml.
    if not phv_names:
        raise CrosswalkBuildError(
            f"ERROR: --cache-dir produced 0 PHV-to-name mappings: {cache_dir}. "
            f"Expected layout: {cache_dir}/pheno_variable_summaries/*.data_dict.xml. "
            "Aborting because the YAML crosswalk would be empty."
        )

    variables_by_pht: dict[str, dict] = (
        source_doc.get("variables_by_pht", {}) if source_doc else {}
    )
    joint_dists_by_pht: dict[str, dict] = (
        source_doc.get("joint_distributions_by_pht", {}) if source_doc else {}
    )

    yaml_cw = build_yaml_crosswalk(yaml_dir, phv_names)
    if not yaml_cw:
        raise CrosswalkBuildError(
            f"ERROR: YAML crosswalk produced 0 entries from {yaml_dir.name}. "
            "This usually means the PHV->name map is empty or every YAML "
            "block references PHVs absent from the cache. Check --cache-dir "
            "matches the cohort and contains pheno_variable_summaries/*.data_dict.xml."
        )
    print(f"  YAML crosswalk: {len(yaml_cw)} entries from {yaml_dir.name}")

    # Group YAML entries by harmonized_key, normalising source/harmonized
    # keys against the actual extract dicts.  Track which entries failed to
    # resolve so we can surface diagnostics for the matching FAIL.
    grouped: dict[str, list[dict]] = {}
    unresolved: dict[str, list[dict]] = {}

    for entry in yaml_cw:
        src_key = entry["source_key"]
        harmonized_key = entry["harmonized_key"]

        # Case-insensitive fallback for source key
        resolved_src_key: str | None = None
        if entry.get("is_static"):
            resolved_src_key = "__static__"
        elif src_key in variables_by_name:
            resolved_src_key = src_key
        else:
            for sk in variables_by_name:
                if sk.upper() == src_key.upper():
                    resolved_src_key = sk
                    break

        # Case-insensitive fallback for harmonized key; also normalizes the
        # method_type component (strips commas, lowercases) to handle
        # differences such as YAML ``pre-bronchodilator spirometry`` vs
        # harmonized ``Pre-bronchodilator, spirometry``.
        resolved_harmonized_key: str | None = None
        if harmonized_key in harmonized_vars:
            resolved_harmonized_key = harmonized_key
        else:
            for ok in harmonized_vars:
                if ok.upper() == harmonized_key.upper():
                    resolved_harmonized_key = ok
                    break
        if resolved_harmonized_key is None and "|" in harmonized_key:
            hk_prefix, hk_mt = harmonized_key.split("|", 1)
            norm_mt = _normalize_method_type_part(hk_mt)
            for ok in harmonized_vars:
                if "|" in ok:
                    ok_prefix, ok_mt = ok.split("|", 1)
                    if (
                        ok_prefix.upper() == hk_prefix.upper()
                        and _normalize_method_type_part(ok_mt) == norm_mt
                    ):
                        resolved_harmonized_key = ok
                        break

        # Fallback 1: newer BDC extractors prefix YAML-mapped concept keys
        # with "discovered:" (e.g. "discovered:condition:MONDO:0004981")
        # while the crosswalk generates bare keys ("condition_MONDO:...").
        # Try the discovered: form when the bare form wasn't found.
        if resolved_harmonized_key is None:
            disc_key = _to_discovered_key(harmonized_key)
            if disc_key is not None:
                if disc_key in harmonized_vars:
                    resolved_harmonized_key = disc_key
                else:
                    for ok in harmonized_vars:
                        if ok.upper() == disc_key.upper():
                            resolved_harmonized_key = ok
                            break

        # Fallback 2: Demography slots are emitted by the BDC extractor as
        # "<slot_name>_<visit_N>" (e.g. "annotated_sex_1").  Try stripping
        # the "demog_" prefix and matching against "<slot>_1" then bare
        # "<slot>".
        if resolved_harmonized_key is None and harmonized_key.startswith("demog_"):
            slot_bare = harmonized_key[len("demog_"):]
            for candidate in (f"{slot_bare}_1", slot_bare):
                if candidate in harmonized_vars:
                    resolved_harmonized_key = candidate
                    break
                for ok in harmonized_vars:
                    if ok.upper() == candidate.upper():
                        resolved_harmonized_key = ok
                        break
                if resolved_harmonized_key is not None:
                    break

        # Fallback 3: MeasurementObservation blocks nested inside a
        # MeasurementObservationSet generate a crosswalk key with a
        # ``|<method_type>`` suffix (e.g.
        # ``measurement_OMOP:4241837|Pre-bronchodilator, spirometry``).
        # Some cohort harmonized extractors group by observation_type alone
        # and emit bare keys without the method_type component.  Fall back to
        # the bare key when the suffixed form is absent from harmonized_vars.
        if (
            resolved_harmonized_key is None
            and entry.get("entity_class") == "MeasurementObservation"
            and entry.get("method_type")
            and "|" in harmonized_key
        ):
            bare_key = harmonized_key.split("|", 1)[0]
            if bare_key in harmonized_vars:
                resolved_harmonized_key = bare_key
            else:
                for ok in harmonized_vars:
                    if ok.upper() == bare_key.upper():
                        resolved_harmonized_key = ok
                        break

        # Fallback 4: Crosswalk has a bare key (no method_type in YAML) but
        # the harmonized extractor added a ``|<method_type>`` suffix from
        # pipeline metadata (e.g. blood_pressure.yaml SBP/DBP concepts get
        # ``|automated sphygmomanometer`` from the dm-bip extractor even
        # though blood_pressure.yaml has no method_type slot).  Find any
        # harmonized key that starts with ``bare_key|``.
        if resolved_harmonized_key is None and "|" not in harmonized_key:
            prefix_candidates = [
                ok for ok in harmonized_vars
                if ok.startswith(harmonized_key + "|")
            ]
            if len(prefix_candidates) == 1:
                resolved_harmonized_key = prefix_candidates[0]
            elif len(prefix_candidates) > 1:
                # Multiple method_type variants for the same concept — use the
                # entry's method_type value (if any) to pick the best match.
                mt_val = entry.get("method_type")
                if mt_val:
                    norm_mt = _normalize_method_type_part(mt_val)
                    for pc in prefix_candidates:
                        if _normalize_method_type_part(pc.split("|", 1)[1]) == norm_mt:
                            resolved_harmonized_key = pc
                            break
                if resolved_harmonized_key is None:
                    # Cannot disambiguate; take the first candidate.
                    resolved_harmonized_key = prefix_candidates[0]

        if resolved_harmonized_key is None or resolved_src_key is None:
            # Stash diagnostic — at minimum we still know the YAML claims
            # there is a harmonized key here, even if resolution failed.
            stash_key = resolved_harmonized_key or harmonized_key
            unresolved.setdefault(stash_key, []).append(
                {
                    "yaml_file": entry.get("yaml_file"),
                    "phv_id": entry.get("phv_id"),
                    "concept_code": entry.get("concept_code"),
                    "entity_class": entry.get("entity_class"),
                    "source_key_in_yaml": entry.get("source_key"),
                    "missing_source_column": resolved_src_key is None,
                    "missing_harmonized_key": resolved_harmonized_key is None,
                }
            )
            continue

        # Use a shallow copy so the original yaml_cw entries are not mutated;
        # callers that reuse yaml_cw (e.g. tests) see the original PHV/source keys.
        grouped.setdefault(resolved_harmonized_key, []).append(
            {**entry, "source_key": resolved_src_key, "harmonized_key": resolved_harmonized_key}
        )

    for harmonized_key, entries in grouped.items():
        if harmonized_key in matched_harmonized:
            continue

        # Resolve per-PHT source stats for every contributing entry.
        per_pht_summaries: list[dict] = []
        source_phts: list[str] = []
        source_keys_used: list[str] = []
        phv_ids: list[str] = []
        summaries_by_phv: dict[str, dict] = {}
        ambiguous_columns: list[dict] = []  # {col, phts, role: "source"|"value_expr"}

        for entry in entries:
            src_key = entry["source_key"]
            phv_id = entry.get("phv_id", "")
            if phv_id:
                phv_ids.append(phv_id)

            if entry.get("is_static"):
                static_pht = entry.get("static_pht")
                rows_by_pht = (source_doc or {}).get("total_rows_by_pht", {})
                total = int(rows_by_pht.get(static_pht, 0) or 0)
                if not total:
                    total = int((source_doc or {}).get("total_participants", 0) or 0)
                raw_static_value = entry.get("static_value")
                if _looks_like_unresolved_expr(raw_static_value):
                    static_summary = _unsupported_joint_summary(
                        {
                            "type": "categorical",
                            "n_total": total,
                            "n_valid": total,
                            "n_missing": 0,
                        },
                        "static_yaml_expr",
                        "Static YAML expression requires source row evaluation; aggregate comparison not attempted",
                    )
                else:
                    static_value = normalize_category_key(raw_static_value)
                    static_summary = _categorical_summary_from_counts(
                        {static_value: total},
                        basis="static_yaml_value",
                        confidence="exact",
                        raw={"n_total": total},
                    ) or {}
                entry["_source_summary"] = static_summary
                per_pht_summaries.append(static_summary)
                if static_pht and static_pht not in source_phts:
                    source_phts.append(static_pht)
                continue

            resolved_summary: dict | None = None
            resolved_pht: str | None = None
            if phv_id and variables_by_pht:
                pht_id = phv_to_pht.get(phv_id)
                if pht_id and pht_id in variables_by_pht:
                    pht_vars = variables_by_pht[pht_id]
                    resolved_summary = pht_vars.get(src_key)
                    if resolved_summary is None:
                        for k, v in pht_vars.items():
                            if k.upper() == src_key.upper():
                                resolved_summary = v
                                break
                    if resolved_summary is not None:
                        resolved_pht = pht_id

            if resolved_summary is None:
                # No PHV→PHT route worked. Try name-based lookup, but if the
                # column appears in multiple PHTs we can't safely pick one —
                # record the ambiguity and skip the summary so the caller
                # surfaces a per-variable FAIL.
                try:
                    resolved_summary = _pick_single_pht_summary(
                        variables_by_name, src_key
                    )
                except AmbiguousColumnError as exc:
                    ambiguous_columns.append({
                        "col": exc.col,
                        "phts": sorted(exc.pht_map),
                        "role": "source",
                        "phv_id": phv_id or None,
                    })

            if resolved_summary is not None:
                entry["_source_summary"] = dict(resolved_summary)
                if phv_id:
                    summaries_by_phv[_canonical_phv_id(phv_id)] = dict(resolved_summary)
                per_pht_summaries.append(dict(resolved_summary))
                if resolved_pht and resolved_pht not in source_phts:
                    source_phts.append(resolved_pht)
                if src_key not in source_keys_used:
                    source_keys_used.append(src_key)

            # Also resolve every PHV referenced in value expressions.  This
            # lets the compare derive an expected categorical distribution
            # for split case() blocks without changing the transform YAML.
            for expr_phv in entry.get("source_phvs") or []:
                expr_phv = _canonical_phv_id(expr_phv)
                if not expr_phv or expr_phv in summaries_by_phv:
                    continue
                expr_src_key = phv_names.get(expr_phv, "")
                if not expr_src_key:
                    continue
                expr_summary: dict | None = None
                expr_pht = phv_to_pht.get(expr_phv)
                if expr_pht and expr_pht in variables_by_pht:
                    pht_vars = variables_by_pht[expr_pht]
                    expr_summary = pht_vars.get(expr_src_key)
                    if expr_summary is None:
                        for k, v in pht_vars.items():
                            if k.upper() == expr_src_key.upper():
                                expr_summary = v
                                break
                if expr_summary is None:
                    try:
                        expr_summary = _pick_single_pht_summary(
                            variables_by_name, expr_src_key
                        )
                    except AmbiguousColumnError as exc:
                        ambiguous_columns.append({
                            "col": exc.col,
                            "phts": sorted(exc.pht_map),
                            "role": "value_expr",
                            "phv_id": expr_phv,
                        })
                        continue
                if expr_summary is not None:
                    summaries_by_phv[expr_phv] = dict(expr_summary)

        if not per_pht_summaries and not ambiguous_columns:
            # Couldn't resolve a single contributing summary, and it's not
            # because of ambiguity — record as unresolved YAML so the
            # diagnostics reporter can surface it.
            unresolved.setdefault(harmonized_key, []).extend(
                [
                    {
                        "yaml_file": e.get("yaml_file"),
                        "phv_id": e.get("phv_id"),
                        "concept_code": e.get("concept_code"),
                        "entity_class": e.get("entity_class"),
                        "source_key_in_yaml": e.get("source_key"),
                        "missing_source_column": True,
                        "missing_harmonized_key": False,
                    }
                    for e in entries
                ]
            )
            continue

        # Build the merged crosswalk match using the first entry as a
        # template (preserves yaml_file, phv_id of the first contributor,
        # concept_code, entity_class, value_map, method_type) and overlay
        # the pooled fields.
        merged = dict(entries[0])
        expected_src = build_expected_summary(
            entries, summaries_by_phv, joint_dists_by_pht or None
        )
        merged["_resolved_src"] = expected_src or _aggregate_source_summaries(per_pht_summaries)
        unsupported_joint = any(
            e.get("concept_value_map")
            and _canonical_phv_id(e.get("concept_phv", ""))
            and _canonical_phv_id(e.get("phv_id", ""))
            and _canonical_phv_id(e.get("concept_phv", "")) != _canonical_phv_id(e.get("phv_id", ""))
            for e in entries
        )
        if unsupported_joint and not expected_src:
            merged["_resolved_src"]["_comparison_basis"] = "source_pooled_raw"
            merged["_resolved_src"]["_comparison_confidence"] = "unsupported"
            merged["_resolved_src"]["_comparison_limitations"] = [
                "Concept routing and value mapping use different PHVs; aggregate summaries cannot compute joint counts"
            ]
        merged["_per_pht_src"] = per_pht_summaries
        merged["_source_phts"] = source_phts
        merged["_source_keys"] = source_keys_used
        merged["_phv_ids"] = list(dict.fromkeys(phv_ids))
        if summaries_by_phv:
            merged["_source_summaries_by_phv"] = summaries_by_phv
        if ambiguous_columns:
            merged["_ambiguous_columns"] = ambiguous_columns
        merged["match_mode"] = _infer_match_mode(entries, merged.get("_resolved_src"), per_pht_summaries)
        source_phv_details = _source_phv_details_for_entries(entries, phv_names, phv_to_pht)
        if source_phv_details:
            merged["source_phv_details"] = source_phv_details
        merged["_yaml_entries"] = [
            {
                "yaml_file": e.get("yaml_file"),
                "phv_id": e.get("phv_id"),
                "concept_phv": e.get("concept_phv"),
                "concept_code": e.get("concept_code"),
                "entity_class": e.get("entity_class"),
                "harmonized_key": e.get("harmonized_key"),
                "value_map": e.get("value_map"),
                "concept_value_map": e.get("concept_value_map"),
                "value_exprs": e.get("value_exprs"),
                "source_phv_roles": e.get("source_phv_roles"),
                "source_summary": e.get("_source_summary"),
                "match_mode": merged["match_mode"],
                "source_phv_details": _source_phv_details_for_entries([e], phv_names, phv_to_pht),
            }
            for e in entries
        ]
        if summaries_by_phv:
            merged["_source_phvs"] = sorted(summaries_by_phv)
        if expected_src:
            merged["_comparison_basis"] = expected_src.get("_comparison_basis")
            merged["_comparison_confidence"] = expected_src.get("_comparison_confidence")
            merged["_comparison_limitations"] = expected_src.get("_comparison_limitations")
        _promote_comparison_metadata(merged)
        # Preserve concept_value_map from ANY contributing entry that
        # has one.  Different visit blocks for the same harmonized_key
        # may use a static ``value:`` (no cvm) while one block uses
        # ``value_mappings`` (cvm present); we must not lose the cvm
        # by defaulting to entries[0].
        if not merged.get("concept_value_map"):
            for e in entries:
                cvm = e.get("concept_value_map")
                if cvm:
                    merged["concept_value_map"] = cvm
                    break
        if source_phts:
            # Keep _resolved_pht populated for backward-compat in the
            # console crosswalk listing; show comma-joined list when many.
            merged["_resolved_pht"] = ",".join(source_phts)
        merged["match_method"] = (
            "yaml+pooled" if len(per_pht_summaries) > 1 else "yaml"
        )

        matches.append(merged)
        matched_harmonized.add(harmonized_key)
        for sk in source_keys_used:
            matched_src.add(sk)

    if diagnostics_out is not None:
        diagnostics_out["unresolved_yaml_entries"] = unresolved
        # Record every harmonized key the YAML parser proposed (resolved or
        # not).  The unmatched-FAIL reporter can use this to distinguish
        # "YAML claims this exists but couldn't link source" from "YAML
        # never proposed this key at all".
        diagnostics_out["yaml_proposed_harmonized_keys"] = sorted(
            set(grouped.keys()) | set(unresolved.keys())
        )

    return matches
