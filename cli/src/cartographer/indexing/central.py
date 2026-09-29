"""Factory functions for central backend drivers.

Returns the configured central VDB or KG driver from the merged config + local
override. Raises clearly if the driver is not installed or the config is missing.
"""

from __future__ import annotations

from cartographer.config import CartographerConfig, LocalOverrideConfig
from cartographer.indexing.vdb_pgvector import PgvectorDriver
from cartographer.indexing.kg_neo4j import Neo4jDriver


def get_central_vdb(cfg: CartographerConfig, override: LocalOverrideConfig) -> PgvectorDriver:
    driver_name = cfg.central.vdb_driver
    if driver_name != "pgvector":
        raise NotImplementedError(f"Central VDB driver '{driver_name}' is not yet implemented.")
    c = override.central_vdb
    if not c.password:
        raise ValueError(
            "Central VDB password is not set. "
            r"Add \[central_vdb] password to .cartographer.local.toml or set CARTO_VDB_PASSWORD."
        )
    return PgvectorDriver(
        host=c.host,
        port=c.port,
        user=c.user,
        password=c.password,
        database=c.database,
    )


def get_central_kg(cfg: CartographerConfig, override: LocalOverrideConfig) -> Neo4jDriver:
    driver_name = cfg.central.kg_driver
    if driver_name != "neo4j":
        raise NotImplementedError(f"Central KG driver '{driver_name}' is not yet implemented.")
    c = override.central_kg
    if not c.password:
        raise ValueError(
            "Central KG password is not set. "
            r"Add \[central_kg] password to .cartographer.local.toml or set CARTO_KG_PASSWORD."
        )
    return Neo4jDriver(uri=c.uri, user=c.user, password=c.password)
