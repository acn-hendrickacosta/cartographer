"""Phase 4: kg_search — NL-to-Cypher translation and retry logic.

The anthropic SDK is not installed in this test environment (it's an
optional dependency, cartographer[kg-search]) — that's deliberately
exercised directly (test_generate_cypher_requires_anthropic_sdk) and then
worked around for the rest via a fake module injected into sys.modules,
rather than adding a real dependency just to mock it.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from cartographer.kg_search import KgSearchError, _extract_cypher, generate_cypher, run_kg_search


# ---------------------------------------------------------------------------
# _extract_cypher
# ---------------------------------------------------------------------------

def test_extract_cypher_strips_fenced_block():
    text = "Here you go:\n```cypher\nMATCH (a) RETURN a\n```"
    assert _extract_cypher(text) == "MATCH (a) RETURN a"


def test_extract_cypher_strips_plain_fence():
    text = "```\nMATCH (a) RETURN a\n```"
    assert _extract_cypher(text) == "MATCH (a) RETURN a"


def test_extract_cypher_handles_unfenced_text():
    assert _extract_cypher("MATCH (a) RETURN a") == "MATCH (a) RETURN a"


# ---------------------------------------------------------------------------
# generate_cypher: anthropic SDK absence
# ---------------------------------------------------------------------------

def test_generate_cypher_requires_anthropic_sdk():
    sys.modules.pop("anthropic", None)
    with pytest.raises(ImportError, match="kg-search"):
        generate_cypher("what calls foo?", api_key="sk-fake")


# ---------------------------------------------------------------------------
# generate_cypher / run_kg_search with a fake anthropic module
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_anthropic(monkeypatch):
    """Inject a minimal fake `anthropic` module so generate_cypher's
    `import anthropic` resolves without the real SDK installed. Yields the
    mock client instance so tests can configure .messages.create's behavior."""
    mock_client = MagicMock()
    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = MagicMock(return_value=mock_client)
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    yield mock_client


def _response_with_text(text: str):
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def test_generate_cypher_returns_extracted_query(fake_anthropic):
    fake_anthropic.messages.create.return_value = _response_with_text(
        "```cypher\nMATCH (a:Artifact) WHERE a.path CONTAINS 'foo' RETURN a.path\n```"
    )
    cypher = generate_cypher("what calls foo?", api_key="sk-fake")
    assert cypher == "MATCH (a:Artifact) WHERE a.path CONTAINS 'foo' RETURN a.path"


def test_generate_cypher_global_scope_requires_allowed_projects_reference(fake_anthropic):
    fake_anthropic.messages.create.return_value = _response_with_text(
        "```cypher\nMATCH (a:Artifact) RETURN a.path\n```"
    )
    with pytest.raises(KgSearchError, match="allowed_projects"):
        generate_cypher("what calls foo?", api_key="sk-fake", allowed_projects=["proj_a"])


def test_generate_cypher_global_scope_accepts_query_with_allowed_projects(fake_anthropic):
    fake_anthropic.messages.create.return_value = _response_with_text(
        "```cypher\nMATCH (a:Artifact) WHERE a.project_id IN $allowed_projects RETURN a.path\n```"
    )
    cypher = generate_cypher("what calls foo?", api_key="sk-fake", allowed_projects=["proj_a"])
    assert "$allowed_projects" in cypher


def test_generate_cypher_feeds_prior_error_back_into_prompt(fake_anthropic):
    fake_anthropic.messages.create.return_value = _response_with_text("```cypher\nMATCH (a) RETURN a\n```")
    generate_cypher(
        "what calls foo?", api_key="sk-fake",
        prior_cypher="MATCH (a RETURN a", prior_error="syntax error at RETURN",
    )
    prompt = fake_anthropic.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "syntax error at RETURN" in prompt
    assert "MATCH (a RETURN a" in prompt


# ---------------------------------------------------------------------------
# run_kg_search: retry loop
# ---------------------------------------------------------------------------

def test_run_kg_search_succeeds_first_try(fake_anthropic):
    fake_anthropic.messages.create.return_value = _response_with_text("```cypher\nMATCH (a) RETURN a\n```")
    query_fn = MagicMock(return_value=[{"path": "foo.py"}])

    cypher, rows = run_kg_search("what calls foo?", "sk-fake", query_fn)

    assert cypher == "MATCH (a) RETURN a"
    assert rows == [{"path": "foo.py"}]
    query_fn.assert_called_once_with("MATCH (a) RETURN a", {})


def test_run_kg_search_retries_on_failure_then_succeeds(fake_anthropic):
    fake_anthropic.messages.create.side_effect = [
        _response_with_text("```cypher\nBAD QUERY\n```"),
        _response_with_text("```cypher\nMATCH (a) RETURN a\n```"),
    ]
    query_fn = MagicMock(side_effect=[Exception("syntax error"), [{"path": "foo.py"}]])

    cypher, rows = run_kg_search("what calls foo?", "sk-fake", query_fn, max_retries=3)

    assert cypher == "MATCH (a) RETURN a"
    assert query_fn.call_count == 2


def test_run_kg_search_raises_after_exhausting_retries(fake_anthropic):
    fake_anthropic.messages.create.return_value = _response_with_text("```cypher\nBAD QUERY\n```")
    query_fn = MagicMock(side_effect=Exception("syntax error"))

    with pytest.raises(KgSearchError, match="3 attempts"):
        run_kg_search("what calls foo?", "sk-fake", query_fn, max_retries=3)

    assert query_fn.call_count == 3


def test_run_kg_search_passes_allowed_projects_param(fake_anthropic):
    fake_anthropic.messages.create.return_value = _response_with_text(
        "```cypher\nMATCH (a) WHERE a.project_id IN $allowed_projects RETURN a\n```"
    )
    query_fn = MagicMock(return_value=[])

    run_kg_search("what calls foo?", "sk-fake", query_fn, allowed_projects=["proj_a", "proj_b"])

    query_fn.assert_called_once_with(
        "MATCH (a) WHERE a.project_id IN $allowed_projects RETURN a",
        {"allowed_projects": ["proj_a", "proj_b"]},
    )


# ---------------------------------------------------------------------------
# kg_search MCP tool wrapper
# ---------------------------------------------------------------------------

def test_kg_search_tool_requires_api_key(tmp_path):
    import json
    from cartographer import config as config_mod
    from cartographer.runtime.mcp_servers import kg_server

    workspace = tmp_path / "proj"
    workspace.mkdir()
    config_mod.save_config(workspace, config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id="proj_x", name="x"),
    ))

    result = kg_server.kg_search(question="what calls foo?", workspace=str(workspace))
    data = json.loads(result)
    assert "error" in data
    assert "api key" in data["error"].lower()


def test_kg_search_tool_local_scope_dispatch(tmp_path, monkeypatch, fake_anthropic):
    import json
    from cartographer import config as config_mod
    from cartographer.indexing import kg as kg_driver
    from cartographer.runtime.mcp_servers import kg_server

    workspace = tmp_path / "proj"
    workspace.mkdir()
    config_mod.save_config(workspace, config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id="proj_x", name="x"),
    ))
    config_mod.save_local_override(workspace, config_mod.LocalOverrideConfig(anthropic_api_key="sk-fake"))

    kg_path = workspace / ".cartographer" / "local" / "kg.kuzu"
    kg_driver.ensure_namespace(kg_path)

    fake_anthropic.messages.create.return_value = _response_with_text(
        "```cypher\nMATCH (a:Artifact) RETURN a.path AS path LIMIT 5\n```"
    )

    result = kg_server.kg_search(question="list artifacts", workspace=str(workspace), scope="local")
    data = json.loads(result)

    assert data["scope"] == "local"
    assert "cypher" in data
    assert data["results"] == []


def test_kg_search_tool_global_scope_passes_overlays(tmp_path, monkeypatch, fake_anthropic):
    import json
    from unittest.mock import MagicMock, patch
    from cartographer import config as config_mod
    from cartographer.runtime.mcp_servers import kg_server

    workspace = tmp_path / "proj"
    workspace.mkdir()
    config_mod.save_config(workspace, config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id="proj_x", name="x"),
        topology=config_mod.TopologySection(mode="central"),
        federation=config_mod.FederationSection(global_overlays=["design-system"]),
    ))
    config_mod.save_local_override(workspace, config_mod.LocalOverrideConfig(
        anthropic_api_key="sk-fake",
        central_kg=config_mod.CentralKgConfig(password="x"),
    ))

    fake_anthropic.messages.create.return_value = _response_with_text(
        "```cypher\nMATCH (a:Artifact) WHERE a.project_id IN $allowed_projects RETURN a.path AS path\n```"
    )

    mock_central_kg = MagicMock()
    mock_central_kg.is_reachable.return_value = True
    mock_central_kg.query_raising.return_value = [{"path": "shared.py"}]

    with patch("cartographer.indexing.central.get_central_kg", return_value=mock_central_kg):
        result = kg_server.kg_search(question="what uses shared.py?", workspace=str(workspace), scope="global")

    data = json.loads(result)
    assert data["scope"] == "global"
    assert data["results"] == [{"path": "shared.py"}]
    call_args = mock_central_kg.query_raising.call_args.args
    assert call_args[1]["allowed_projects"] == ["proj_x", "design-system"]
