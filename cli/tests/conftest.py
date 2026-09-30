"""Shared pytest fixtures and hooks for the Cartographer test suite."""

import pytest


@pytest.fixture(autouse=True)
def _clear_kg_db_cache():
    """Release all cached Kuzu Database handles between tests.

    The kg module caches Database objects so a process holds at most one handle
    per path. Each test gets a fresh tmp_path, so without this fixture the cache
    accumulates many handles across the test run — each Kuzu Database reserves
    up to 8 TB of virtual address space by default, exhausting it after a handful
    of tests.
    """
    from cartographer.indexing.kg import clear_db_cache
    clear_db_cache()
    yield
    clear_db_cache()
