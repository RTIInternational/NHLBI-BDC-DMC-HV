"""Concurrency regression test for mondo_agent's local response cache.

generate_curie_mapreview.py drives get_mondo_id_with_score() through a
ThreadPoolExecutor (10 workers by default). Reported 2026-08-28: two races
in _save_cache_entry -- json.dumps() iterating the shared _cache dict while
another thread mutates it, and every thread writing the same fixed tmp path
before os.replace, so one thread's rename could pull the file out from under
another's (reproduced as FileNotFoundError in ~48% of concurrent calls,
which _agent_suggestion's broad except Exception swallows silently -- the
practical effect was roughly half of condition_concept rows silently coming
back with no MONDO suggestion).
"""
import concurrent.futures
import importlib
import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mondo_agent(tmp_path, monkeypatch):
    """Fresh mondo_agent module instance per test, cache pointed at tmp_path,
    so tests never touch the real terminology-cache file or its in-memory
    module-level cache."""
    import mondo_agent as _m
    importlib.reload(_m)
    monkeypatch.setattr(_m, "_CACHE_PATH", tmp_path / "mondo-index.json")
    monkeypatch.setattr(_m, "_cache", None)
    return _m


def _fake_response(query: str):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {
        "response": {
            "docs": [
                {
                    "obo_id": "MONDO:0000001",
                    "label": query,
                    "description": [""],
                    "exact_synonyms": [],
                }
            ]
        }
    }
    return resp


class TestConcurrentCacheWrites:
    def test_200_distinct_queries_across_10_workers_no_exceptions(self, mondo_agent):
        queries = [f"condition {i}" for i in range(200)]

        with patch.object(mondo_agent.requests, "get", side_effect=lambda url, timeout: _fake_response(url)):
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(mondo_agent.get_mondo_id_with_score, q) for q in queries]
                results = []
                errors = []
                for f in concurrent.futures.as_completed(futures):
                    try:
                        results.append(f.result())
                    except Exception as e:  # noqa: BLE001 - want to see every exception type
                        errors.append(e)

        assert errors == [], f"{len(errors)} of {len(queries)} calls raised: {errors[:3]}"
        assert len(results) == len(queries)

    def test_cache_file_is_valid_json_after_concurrent_writes(self, mondo_agent):
        queries = [f"condition {i}" for i in range(200)]

        with patch.object(mondo_agent.requests, "get", side_effect=lambda url, timeout: _fake_response(url)):
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                list(executor.map(mondo_agent.get_mondo_id_with_score, queries))

        on_disk = json.loads(mondo_agent._CACHE_PATH.read_text(encoding="utf-8"))
        assert len(on_disk) == len(queries)

    def test_no_leftover_tmp_files(self, mondo_agent):
        queries = [f"condition {i}" for i in range(200)]

        with patch.object(mondo_agent.requests, "get", side_effect=lambda url, timeout: _fake_response(url)):
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                list(executor.map(mondo_agent.get_mondo_id_with_score, queries))

        leftover = list(mondo_agent._CACHE_PATH.parent.glob("*.tmp.*.json"))
        assert leftover == []
