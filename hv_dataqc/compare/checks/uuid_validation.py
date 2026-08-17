"""UUID format validation: C13.

Checks that every associated_participant and associated_visit value in the
harmonized output is a valid UUID string. Malformed values indicate broken
YAML ID expressions -- e.g. a null source PHV propagating through
uuid5(..., str(None) + ':COHORT') to produce a non-UUID string that silently
passes all downstream per-variable checks.

Reads ``uuid_validation`` from the harmonized JSON, populated by
``extract_harmonized_summaries.py``. When the field is absent (older JSON
artifacts), the check skips gracefully.
"""

from __future__ import annotations

from hv_dataqc.compare._common import CheckResult


def check_c13_uuid_format(harmonized: dict) -> list[CheckResult]:
    """C13: Validate UUID format for associated_participant and associated_visit.

    Emits one FAIL per entity class that has invalid UUIDs.
    Emits a single PASS when all entities are clean.
    Emits SKIP when uuid_validation data is absent from the harmonized JSON
    (re-run extract_harmonized_summaries.py to populate it).

    Args:
        harmonized: Top-level harmonized summary dict from
            ``extract_harmonized_summaries.py``.

    Returns:
        List of CheckResult objects.
    """
    uuid_data: dict[str, dict] = harmonized.get("uuid_validation", {})
    if not uuid_data:
        return [CheckResult(
            "C13", "_uuid_format", "SKIP",
            "UUID validation data not present in harmonized JSON -- "
            "re-run extract_harmonized_summaries.py to populate",
        )]

    results: list[CheckResult] = []
    all_ok = True

    for entity in sorted(uuid_data):
        stats = uuid_data[entity]
        n_bad_participant = int(stats.get("n_invalid_participant_uuid", 0))
        n_bad_visit = int(stats.get("n_invalid_visit_uuid", 0))
        n_total = int(stats.get("n_total_rows", 0))

        if n_bad_participant == 0 and n_bad_visit == 0:
            continue

        all_ok = False
        issues: list[str] = []

        if n_bad_participant > 0:
            samples = stats.get("sample_invalid_participant", [])
            sample_str = ", ".join(repr(str(s)) for s in samples[:3])
            issues.append(
                f"associated_participant: {n_bad_participant} malformed UUID(s)"
                + (f" (e.g. {sample_str})" if samples else "")
            )
        if n_bad_visit > 0:
            samples = stats.get("sample_invalid_visit", [])
            sample_str = ", ".join(repr(str(s)) for s in samples[:3])
            issues.append(
                f"associated_visit: {n_bad_visit} malformed UUID(s)"
                + (f" (e.g. {sample_str})" if samples else "")
            )

        results.append(CheckResult(
            "C13",
            f"{entity}_uuid_format",
            "FAIL",
            f"{entity}: {'; '.join(issues)} of {n_total} total rows. "
            "Likely cause: null source PHV in uuid5() expression or missing str() coercion.",
            {
                "entity": entity,
                "n_total_rows": n_total,
                "n_invalid_participant_uuid": n_bad_participant,
                "n_invalid_visit_uuid": n_bad_visit,
                "sample_invalid_participant": stats.get("sample_invalid_participant", []),
                "sample_invalid_visit": stats.get("sample_invalid_visit", []),
            },
        ))

    if all_ok:
        entities = sorted(uuid_data.keys())
        total_rows = sum(int(uuid_data[e].get("n_total_rows", 0)) for e in entities)
        if total_rows == 0:
            # uuid_validation is present but every entity has 0 rows — nothing
            # was actually validated, so "all valid" would be a false PASS.
            results.append(CheckResult(
                "C13",
                "_uuid_format",
                "SKIP",
                "No harmonized rows were available to validate UUIDs "
                f"(0 total rows across {len(entities)} entity class(es): "
                f"{', '.join(entities)})",
                {"entities_checked": entities},
            ))
        else:
            results.append(CheckResult(
                "C13",
                "_uuid_format",
                "PASS",
                f"All associated_participant and associated_visit values are valid UUIDs "
                f"across {len(entities)} entity class(es): {', '.join(entities)}",
                {"entities_checked": entities},
            ))

    return results
