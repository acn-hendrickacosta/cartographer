from pathlib import Path

from cartographer import config as config_mod


def test_config_round_trip(tmp_path: Path) -> None:
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id="proj_abc123", name="demo"),
        topology=config_mod.TopologySection(mode="local"),
        stacks=config_mod.StacksSection(active=["cross-stack", "python"]),
    )
    config_mod.save_config(tmp_path, cfg)

    assert config_mod.config_exists(tmp_path)
    loaded = config_mod.load_config(tmp_path)

    assert loaded.project.id == "proj_abc123"
    assert loaded.project.name == "demo"
    assert loaded.topology.mode == "local"
    assert loaded.stacks.active == ["cross-stack", "python"]
    assert loaded.promotion.trigger == "manual"
    assert loaded.retrieval.top_k == 8
    assert loaded.backends.vdb.driver == "lancedb"
    assert loaded.backends.kg.driver == "kuzu"


def test_local_override_round_trip(tmp_path: Path) -> None:
    override = config_mod.LocalOverrideConfig()
    override.central_vdb.host = "pg.example.com"
    override.central_vdb.password = "s3cr3t"
    override.central_kg.uri = "bolt://neo4j.example.com:7687"
    override.promotion_token = "tok-abc123"
    config_mod.save_local_override(tmp_path, override)

    loaded = config_mod.load_local_override(tmp_path)
    assert loaded.central_vdb.host == "pg.example.com"
    assert loaded.central_vdb.password == "s3cr3t"
    assert loaded.central_kg.uri == "bolt://neo4j.example.com:7687"
    assert loaded.promotion_token == "tok-abc123"
    assert loaded.paths.local_index_dir == ".cartographer/local"


def test_local_override_defaults_when_absent(tmp_path: Path) -> None:
    loaded = config_mod.load_local_override(tmp_path)
    assert loaded.paths.local_index_dir == ".cartographer/local"
    assert loaded.central_vdb.host == "localhost"
    assert loaded.central_vdb.password == ""
    assert loaded.central_vdb_s3.bucket == ""
    assert loaded.central_vdb_s3.prefix == "vdb"
    assert loaded.promotion_token == ""


def test_local_override_round_trip_central_vdb_s3(tmp_path: Path) -> None:
    override = config_mod.LocalOverrideConfig()
    override.central_vdb_s3.bucket = "cartographer-standards-registry-983883745126"
    override.central_vdb_s3.prefix = "vdb"
    override.central_vdb_s3.region = "us-east-1"
    config_mod.save_local_override(tmp_path, override)

    loaded = config_mod.load_local_override(tmp_path)
    assert loaded.central_vdb_s3.bucket == "cartographer-standards-registry-983883745126"
    assert loaded.central_vdb_s3.prefix == "vdb"
    assert loaded.central_vdb_s3.region == "us-east-1"
