"""Factory functions for central backend drivers.

Returns the configured central VDB or KG driver from the merged config + local
override. Raises clearly if the driver is not installed or the config is missing.
"""

from __future__ import annotations

from cartographer.config import CartographerConfig, LocalOverrideConfig
from cartographer.indexing.vdb_pgvector import PgvectorDriver
from cartographer.indexing.vdb_lance_s3 import LanceS3Driver
from cartographer.indexing.kg_neo4j import Neo4jDriver


def get_central_vdb(cfg: CartographerConfig, override: LocalOverrideConfig) -> PgvectorDriver | LanceS3Driver:
    driver_name = cfg.central.vdb_driver
    if driver_name == "pgvector":
        c = override.central_vdb
        if not c.password:
            raise ValueError(
                "Central VDB password is not set. "
                r"Add \[central_vdb] password to cartographer.local.toml, or set CARTO_CENTRAL_VDB_PASSWORD (CI)."
            )
        return PgvectorDriver(
            host=c.host,
            port=c.port,
            user=c.user,
            password=c.password,
            database=c.database,
        )
    if driver_name == "lancedb_s3":
        c = override.central_vdb_s3
        if not c.bucket:
            raise ValueError(
                "Central VDB S3 bucket is not set. "
                r"Add \[central_vdb_s3] bucket to cartographer.local.toml, or set CARTO_CENTRAL_VDB_S3_BUCKET (CI)."
            )
        return LanceS3Driver(bucket=c.bucket, prefix=c.prefix, region=c.region)
    raise NotImplementedError(f"Central VDB driver '{driver_name}' is not yet implemented.")


def get_central_kg(cfg: CartographerConfig, override: LocalOverrideConfig) -> Neo4jDriver:
    driver_name = cfg.central.kg_driver
    if driver_name != "neo4j":
        raise NotImplementedError(f"Central KG driver '{driver_name}' is not yet implemented.")
    c = override.central_kg
    if not c.password:
        raise ValueError(
            "Central KG password is not set. "
            r"Add \[central_kg] password to cartographer.local.toml, or set CARTO_CENTRAL_KG_PASSWORD (CI)."
        )
    return Neo4jDriver(uri=c.uri, user=c.user, password=c.password)
