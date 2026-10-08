"""cartographer.indexing.central: driver selection for the central VDB.

Covers both supported drivers (pgvector, lancedb_s3) and the error paths for
missing credentials/config and unknown driver names. Previously only
exercised indirectly through recall/promote tests with mocked drivers.
"""

from __future__ import annotations

import pytest

from cartographer import config as config_mod
from cartographer.indexing import central
from cartographer.indexing.vdb_lance_s3 import LanceS3Driver
from cartographer.indexing.vdb_pgvector import PgvectorDriver


def _cfg(vdb_driver: str) -> config_mod.CartographerConfig:
    return config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id="proj_1", name="demo"),
        central=config_mod.CentralSection(vdb_driver=vdb_driver),
    )


def test_get_central_vdb_returns_pgvector_driver():
    override = config_mod.LocalOverrideConfig(
        central_vdb=config_mod.CentralVdbConfig(password="s3cr3t"),
    )
    driver = central.get_central_vdb(_cfg("pgvector"), override)
    assert isinstance(driver, PgvectorDriver)
    assert driver.password == "s3cr3t"


def test_get_central_vdb_pgvector_requires_password():
    override = config_mod.LocalOverrideConfig()
    with pytest.raises(ValueError, match="password is not set"):
        central.get_central_vdb(_cfg("pgvector"), override)


def test_get_central_vdb_returns_lance_s3_driver():
    override = config_mod.LocalOverrideConfig(
        central_vdb_s3=config_mod.CentralVdbS3Config(bucket="my-bucket", prefix="vdb", region="us-east-1"),
    )
    driver = central.get_central_vdb(_cfg("lancedb_s3"), override)
    assert isinstance(driver, LanceS3Driver)
    assert driver.bucket == "my-bucket"
    assert driver.prefix == "vdb"
    assert driver.region == "us-east-1"


def test_get_central_vdb_lance_s3_requires_bucket():
    override = config_mod.LocalOverrideConfig()
    with pytest.raises(ValueError, match="bucket is not set"):
        central.get_central_vdb(_cfg("lancedb_s3"), override)


def test_get_central_vdb_unknown_driver_raises_not_implemented():
    override = config_mod.LocalOverrideConfig()
    with pytest.raises(NotImplementedError, match="qdrant"):
        central.get_central_vdb(_cfg("qdrant"), override)
