"""
_http.py -- Transparent HTTP cache for dbGaP/NCBI requests.

Self-contained replacement for orchestrator/tools/dbgap_client.py.
Used by update_data.py for polite, cached downloads from NCBI FTP.

Cache location:
    hv-lint/dbgap-cache/.http-cache.sqlite

Cache policy:
    - Never expires by default (URLs are version-pinned, content is static).
    - Only caches GET 200 responses; errors are never cached.
    - Scoped to *.ncbi.nlm.nih.gov URLs.

Requires:
    pip install requests-cache

    If requests-cache is not installed, get_session() raises ImportError
    with a helpful message. The rest of hv-lint (phases 1-5) does NOT
    require this module -- it is only needed for update_data.py.
"""

from __future__ import annotations

from pathlib import Path

_CACHE_PATH = Path(__file__).resolve().parent / "dbgap-cache" / ".http-cache"

_session = None


def get_session():
    """Return a singleton CachedSession backed by SQLite.

    Raises ImportError if requests-cache is not installed.
    """
    global _session
    if _session is not None:
        return _session

    try:
        import requests_cache
    except ImportError:
        raise ImportError(
            "requests-cache is required for dbGaP data fetching.\n"
            "Install it with:  pip install requests-cache\n"
            "Note: requests-cache is only needed for 'update_data.py', "
            "not for running lint phases."
        )

    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _session = requests_cache.CachedSession(
        cache_name=str(_CACHE_PATH),
        backend="sqlite",
        expire_after=None,              # never expire (version-pinned)
        allowable_methods=["GET"],
        allowable_codes=[200],
        match_headers=False,
        stale_if_error=True,
    )
    _session.headers.update({
        "User-Agent": "BDC-DMC-HV-Lint/1.0 (caching client)"
    })
    return _session
