"""Load, validate, and write `cartographer.toml` (committed) and
`cartographer.local.toml` (gitignored, per-developer).

Schema follows PROJECT_BRIEF.md Section 8. Secrets and machine-specific paths never
go in the committed file (Section 9).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import tomlkit
from pydantic import BaseModel, Field

CONFIG_FILENAME = "cartographer.toml"
LOCAL_CONFIG_FILENAME = "cartographer.local.toml"

Topology = Literal["local", "central"]
PromotionTrigger = Literal["post-merge-hook", "ci", "manual"]
EmbedderDriver = Literal["local", "api"]


class ProjectSection(BaseModel):
    id: str
    name: str


class RetrievalSection(BaseModel):
    preload_tokens: int = 2000
    per_turn_tokens: int = 1000
    top_k: int = 8
    conflict_threshold_seconds: int = 0  # 0 = any updated_at difference counts as conflict
    conflict_notice: bool = True  # set False to suppress notices (local is still returned)


class BackendDriver(BaseModel):
    driver: str


class BackendsSection(BaseModel):
    vdb: BackendDriver = Field(default_factory=lambda: BackendDriver(driver="lancedb"))
    kg: BackendDriver = Field(default_factory=lambda: BackendDriver(driver="kuzu"))
    embedder: BackendDriver = Field(default_factory=lambda: BackendDriver(driver="local"))


class TopologySection(BaseModel):
    mode: Topology = "local"


class PromotionSection(BaseModel):
    trigger: PromotionTrigger = "manual"


class IsolationSection(BaseModel):
    tenant: str = "default"


class StacksSection(BaseModel):
    active: list[str] = Field(default_factory=list)


class CentralSection(BaseModel):
    """Committed config: which central drivers to use (no secrets)."""
    vdb_driver: str = "pgvector"
    kg_driver: str = "neo4j"


class TaxonomySection(BaseModel):
    """Phase 4: pin the edge-type taxonomy version this project expects.

    Deliberately not named [kg] — cartographer.example.toml already has a
    top-level [kg] section (driver selection) that predates this and was
    never actually read by load_config; reusing that name here would just
    create a second, differently-shaped collision with the same dead
    section instead of fixing it. See phase-4-enterprise.md's alignment note.
    """
    version: str = "1.0"


class FederationSection(BaseModel):
    """Phase 4: project_ids whose global scope this project's KG queries
    should also fan out to (read-only), in addition to its own."""
    global_overlays: list[str] = Field(default_factory=list)


class CartographerConfig(BaseModel):
    project: ProjectSection
    topology: TopologySection = Field(default_factory=TopologySection)
    stacks: StacksSection = Field(default_factory=StacksSection)
    promotion: PromotionSection = Field(default_factory=PromotionSection)
    isolation: IsolationSection = Field(default_factory=IsolationSection)
    retrieval: RetrievalSection = Field(default_factory=RetrievalSection)
    backends: BackendsSection = Field(default_factory=BackendsSection)
    central: CentralSection = Field(default_factory=CentralSection)
    taxonomy: TaxonomySection = Field(default_factory=TaxonomySection)
    federation: FederationSection = Field(default_factory=FederationSection)

    def to_toml(self) -> str:
        doc = tomlkit.document()
        doc.add(tomlkit.comment("Cartographer project config. Commit this file; see cartographer.local.toml for secrets."))
        doc["project"] = self.project.model_dump()
        doc["topology"] = self.topology.model_dump()
        doc["stacks"] = self.stacks.model_dump()
        doc["promotion"] = self.promotion.model_dump()
        doc["isolation"] = self.isolation.model_dump()
        doc["retrieval"] = self.retrieval.model_dump()
        doc["backends"] = {
            "vdb": self.backends.vdb.model_dump(),
            "kg": self.backends.kg.model_dump(),
            "embedder": self.backends.embedder.model_dump(),
        }
        doc["central"] = self.central.model_dump()
        doc["taxonomy"] = self.taxonomy.model_dump()
        doc["federation"] = self.federation.model_dump()
        return tomlkit.dumps(doc)


class LocalPathsSection(BaseModel):
    local_index_dir: str = ".cartographer/local"


class CentralVdbConfig(BaseModel):
    """pgvector connection details -- provided by admin, stored in gitignored local override."""
    host: str = "localhost"
    port: int = 5432
    user: str = "cartographer"
    password: str = ""
    database: str = "cartographer"


class CentralKgConfig(BaseModel):
    """Neo4j connection details -- provided by admin, stored in gitignored local override."""
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = ""


class LocalOverrideConfig(BaseModel):
    paths: LocalPathsSection = Field(default_factory=LocalPathsSection)
    central_vdb: CentralVdbConfig = Field(default_factory=CentralVdbConfig)
    central_kg: CentralKgConfig = Field(default_factory=CentralKgConfig)
    promotion_token: str = ""

    def to_toml(self) -> str:
        doc = tomlkit.document()
        doc.add(tomlkit.comment("Local override: per-developer paths and central-backend secrets."))
        doc.add(tomlkit.comment("Never commit this file."))
        doc["paths"] = self.paths.model_dump()
        doc["central_vdb"] = self.central_vdb.model_dump()
        doc["central_kg"] = self.central_kg.model_dump()
        if self.promotion_token:
            doc["promotion_token"] = self.promotion_token
        return tomlkit.dumps(doc)


def config_path(workspace: Path) -> Path:
    return workspace / CONFIG_FILENAME


def local_config_path(workspace: Path) -> Path:
    return workspace / LOCAL_CONFIG_FILENAME


def load_config(workspace: Path) -> CartographerConfig:
    path = config_path(workspace)
    data = tomlkit.parse(path.read_text(encoding="utf-8"))
    backends = data.get("backends", {})
    return CartographerConfig(
        project=ProjectSection(**data["project"]),
        topology=TopologySection(**data.get("topology", {})),
        stacks=StacksSection(**data.get("stacks", {})),
        promotion=PromotionSection(**data.get("promotion", {})),
        isolation=IsolationSection(**data.get("isolation", {})),
        retrieval=RetrievalSection(**data.get("retrieval", {})),
        backends=BackendsSection(
            vdb=BackendDriver(**backends.get("vdb", {"driver": "lancedb"})),
            kg=BackendDriver(**backends.get("kg", {"driver": "kuzu"})),
            embedder=BackendDriver(**backends.get("embedder", {"driver": "local"})),
        ),
        central=CentralSection(**data.get("central", {})),
        taxonomy=TaxonomySection(**data.get("taxonomy", {})),
        federation=FederationSection(**data.get("federation", {})),
    )


def save_config(workspace: Path, config: CartographerConfig) -> Path:
    path = config_path(workspace)
    path.write_text(config.to_toml(), encoding="utf-8")
    return path


def load_local_override(workspace: Path) -> LocalOverrideConfig:
    """Load cartographer.local.toml, then apply CARTO_CENTRAL_VDB_*/
    CARTO_CENTRAL_KG_*/CARTO_PROMOTION_TOKEN environment variable overrides
    on top (Phase 4 CI/CD integration — a CI runner has no local.toml file
    and injects secrets as env vars instead; see _apply_env_overrides).
    Works even when the file doesn't exist at all, for a from-scratch CI
    checkout."""
    path = local_config_path(workspace)
    if path.exists():
        data = tomlkit.parse(path.read_text(encoding="utf-8"))
        override = LocalOverrideConfig(
            paths=LocalPathsSection(**data.get("paths", {})),
            central_vdb=CentralVdbConfig(**data.get("central_vdb", {})),
            central_kg=CentralKgConfig(**data.get("central_kg", {})),
            promotion_token=str(data.get("promotion_token", "")),
        )
    else:
        override = LocalOverrideConfig()
    _apply_env_overrides(override)
    return override


def _apply_env_overrides(override: LocalOverrideConfig) -> None:
    import os

    env = os.environ
    if env.get("CARTO_CENTRAL_VDB_HOST"):
        override.central_vdb.host = env["CARTO_CENTRAL_VDB_HOST"]
    if env.get("CARTO_CENTRAL_VDB_PORT"):
        override.central_vdb.port = int(env["CARTO_CENTRAL_VDB_PORT"])
    if env.get("CARTO_CENTRAL_VDB_USER"):
        override.central_vdb.user = env["CARTO_CENTRAL_VDB_USER"]
    if env.get("CARTO_CENTRAL_VDB_PASSWORD"):
        override.central_vdb.password = env["CARTO_CENTRAL_VDB_PASSWORD"]
    if env.get("CARTO_CENTRAL_VDB_DATABASE"):
        override.central_vdb.database = env["CARTO_CENTRAL_VDB_DATABASE"]

    if env.get("CARTO_CENTRAL_KG_URI"):
        override.central_kg.uri = env["CARTO_CENTRAL_KG_URI"]
    if env.get("CARTO_CENTRAL_KG_USER"):
        override.central_kg.user = env["CARTO_CENTRAL_KG_USER"]
    if env.get("CARTO_CENTRAL_KG_PASSWORD"):
        override.central_kg.password = env["CARTO_CENTRAL_KG_PASSWORD"]

    if env.get("CARTO_PROMOTION_TOKEN"):
        override.promotion_token = env["CARTO_PROMOTION_TOKEN"]


def save_local_override(workspace: Path, override: LocalOverrideConfig) -> Path:
    path = local_config_path(workspace)
    path.write_text(override.to_toml(), encoding="utf-8")
    return path


def config_exists(workspace: Path) -> bool:
    return config_path(workspace).exists()
