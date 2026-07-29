"""Tests for the two things that stopped repeated ingestion finding new jobs.

Before this, the Wuzzuf cache never expired (once the file existed the scraper
never contacted the site again) and Arbeitnow always fetched page 1, so every
run re-ingested the same snapshot and the pool could not grow.
"""

import json
import os
import time

import pytest

from backend.services.ingestion import (
    ArbeitnowIngestionClient,
    WuzzufScraperClient,
)
from backend.services.ingestion_pipeline import PAGE_ROTATION, _build_client, page_for_run


# --- Wuzzuf cache TTL --------------------------------------------------------


@pytest.fixture
def cache_file(tmp_path):
    path = tmp_path / "wuzzuf_scraped.json"
    path.write_text(json.dumps([]), encoding="utf-8")
    return str(path)


def test_fresh_cache_is_used(cache_file):
    client = WuzzufScraperClient(cache_file=cache_file, cache_ttl_seconds=3600)

    assert client._load_cache(10) is not None


def test_stale_cache_is_ignored(cache_file):
    """The bug: without a TTL this returned the cache forever, so repeated
    ingestion runs could never pick up a new posting."""
    os.utime(cache_file, (time.time() - 7200, time.time() - 7200))
    client = WuzzufScraperClient(cache_file=cache_file, cache_ttl_seconds=3600)

    assert client._load_cache(10) is None


def test_zero_ttl_always_refetches(cache_file):
    client = WuzzufScraperClient(cache_file=cache_file, cache_ttl_seconds=0)

    assert client._load_cache(10) is None


def test_none_ttl_keeps_the_permanent_cache(cache_file):
    """Explicit None still means never expire, for callers that want it."""
    os.utime(cache_file, (time.time() - 10**6, time.time() - 10**6))
    client = WuzzufScraperClient(cache_file=cache_file, cache_ttl_seconds=None)

    assert client._load_cache(10) is not None


def test_ttl_comes_from_the_environment(cache_file, monkeypatch):
    monkeypatch.setenv("WUZZUF_CACHE_TTL_SECONDS", "60")

    assert WuzzufScraperClient(cache_file=cache_file).cache_ttl_seconds == 60


def test_default_ttl_is_not_permanent(cache_file, monkeypatch):
    monkeypatch.delenv("WUZZUF_CACHE_TTL_SECONDS", raising=False)

    ttl = WuzzufScraperClient(cache_file=cache_file).cache_ttl_seconds

    assert ttl is not None and ttl > 0


def test_missing_cache_file_is_not_an_error(tmp_path):
    client = WuzzufScraperClient(cache_file=str(tmp_path / "nope.json"))

    assert client._load_cache(10) is None


# --- Arbeitnow paging --------------------------------------------------------


def test_page_is_sent_to_the_api(monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"data": []}

    def _get(url, params=None, **kwargs):
        captured["params"] = params
        return _Resp()

    monkeypatch.setattr("backend.services.ingestion.requests.get", _get)

    ArbeitnowIngestionClient(page=3).get_jobs(limit=5)

    assert captured["params"] == {"page": 3}


def test_page_defaults_to_one_and_is_floored():
    assert ArbeitnowIngestionClient().page == 1
    assert ArbeitnowIngestionClient(page=0).page == 1
    assert ArbeitnowIngestionClient(page=-4).page == 1


# --- page rotation across runs -----------------------------------------------


def test_successive_runs_get_different_pages():
    """The point of the whole change: run N and run N+1 must not fetch the
    same page, or the pool never grows."""
    pages = [page_for_run(i) for i in range(1, PAGE_ROTATION + 1)]

    assert pages == list(range(1, PAGE_ROTATION + 1))
    assert len(set(pages)) == PAGE_ROTATION


def test_rotation_wraps_rather_than_paging_off_the_end():
    assert page_for_run(PAGE_ROTATION + 1) == 1


def test_no_run_id_falls_back_to_page_one():
    assert page_for_run(None) == 1
    assert page_for_run(0) == 1


def test_only_arbeitnow_receives_a_page():
    """Wuzzuf refreshes via its cache TTL and Mock-MENA is a local file, so
    passing a page to either would be a TypeError."""
    assert _build_client("arbeitnow", run_id=3).page == 3
    assert not hasattr(_build_client("wuzzuf", run_id=3), "page")
    assert not hasattr(_build_client("mock_mena", run_id=3), "page")
