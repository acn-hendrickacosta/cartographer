"""Phase 4: CI/CD freshness integration — environment variable overrides for
central backend credentials and the CI templates themselves.

A CI runner has no cartographer.local.toml (that file is gitignored,
per-developer) and injects secrets as environment variables instead. This
was a real prerequisite discovered while implementing the CI templates: the
templates specify CARTO_CENTRAL_VDB_*/CARTO_CENTRAL_KG_* env vars, but
nothing in the codebase read them — not even the env var names the existing
error messages already (incorrectly) promised.
"""

from __future__ import annotations

from pathlib import Path

from cartographer import config as config_mod


def test_env_overrides_apply_when_no_local_toml_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("CARTO_CENTRAL_VDB_HOST", "ci-pgvector")
    monkeypatch.setenv("CARTO_CENTRAL_VDB_PORT", "5555")
    monkeypatch.setenv("CARTO_CENTRAL_VDB_PASSWORD", "ci-secret-vdb")
    monkeypatch.setenv("CARTO_CENTRAL_KG_URI", "bolt://ci-neo4j:7687")
    monkeypatch.setenv("CARTO_CENTRAL_KG_PASSWORD", "ci-secret-kg")
    monkeypatch.setenv("CARTO_PROMOTION_TOKEN", "ci-token")

    override = config_mod.load_local_override(tmp_path)

    assert override.central_vdb.host == "ci-pgvector"
    assert override.central_vdb.port == 5555
    assert override.central_vdb.password == "ci-secret-vdb"
    assert override.central_kg.uri == "bolt://ci-neo4j:7687"
    assert override.central_kg.password == "ci-secret-kg"
    assert override.promotion_token == "ci-token"


def test_env_overrides_take_precedence_over_file(tmp_path, monkeypatch):
    override_file = config_mod.LocalOverrideConfig(
        central_vdb=config_mod.CentralVdbConfig(password="file-password"),
        promotion_token="file-token",
    )
    config_mod.save_local_override(tmp_path, override_file)

    monkeypatch.setenv("CARTO_CENTRAL_VDB_PASSWORD", "env-password")

    override = config_mod.load_local_override(tmp_path)
    assert override.central_vdb.password == "env-password"
    assert override.promotion_token == "file-token"  # unset in env, file value preserved


def test_env_overrides_apply_for_central_vdb_s3(tmp_path, monkeypatch):
    monkeypatch.setenv("CARTO_CENTRAL_VDB_S3_BUCKET", "ci-vdb-bucket")
    monkeypatch.setenv("CARTO_CENTRAL_VDB_S3_PREFIX", "ci-vdb")
    monkeypatch.setenv("CARTO_CENTRAL_VDB_S3_REGION", "us-west-2")

    override = config_mod.load_local_override(tmp_path)

    assert override.central_vdb_s3.bucket == "ci-vdb-bucket"
    assert override.central_vdb_s3.prefix == "ci-vdb"
    assert override.central_vdb_s3.region == "us-west-2"


def test_no_env_vars_and_no_file_returns_defaults(tmp_path, monkeypatch):
    for var in ("CARTO_CENTRAL_VDB_HOST", "CARTO_CENTRAL_VDB_PASSWORD", "CARTO_PROMOTION_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    override = config_mod.load_local_override(tmp_path)
    assert override.central_vdb.password == ""
    assert override.promotion_token == ""


# ---------------------------------------------------------------------------
# CI template files exist and reference the real commands/env vars
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_github_actions_template_exists_and_is_consistent():
    content = (_REPO_ROOT / "docs" / "ci-templates" / "github-actions.yml").read_text(encoding="utf-8")
    assert "cartographer seed --diff" in content
    assert "cartographer promote --diff" in content
    assert "CARTO_CENTRAL_VDB_PASSWORD" in content
    assert "CARTO_CENTRAL_KG_PASSWORD" in content
    assert "CARTO_PROMOTION_TOKEN" in content


def test_gitlab_ci_template_exists_and_is_consistent():
    content = (_REPO_ROOT / "docs" / "ci-templates" / "gitlab-ci.yml").read_text(encoding="utf-8")
    assert "cartographer seed --diff" in content
    assert "cartographer promote --diff" in content
    assert "CARTO_CENTRAL_VDB_PASSWORD" in content
    assert "CARTO_CENTRAL_KG_PASSWORD" in content
    assert "CARTO_PROMOTION_TOKEN" in content
