"""Phase 4: kg_search — translate a natural-language question into Cypher via
a direct Claude API call, execute it, and retry on failure.

Design constraint (from the Phase 4 planning doc): this is a direct
`anthropic` SDK call using the key in cartographer.local.toml, not a
recursive call back into Claude Code over MCP — kg_search is itself an MCP
tool other agent sessions call; having it in turn drive another agent loop
would risk the exact reentrant-deadlock pattern documented in the MCP server
implementation notes.

Requires the anthropic SDK: pip install "cartographer[kg-search]".
"""

from __future__ import annotations

import re

MODEL = "claude-haiku-4-5-20251001"
MAX_RETRIES = 3
MAX_TOKENS = 500

SCHEMA_DESCRIPTION = """The knowledge graph has Artifact nodes and RelatesTo edges.

Artifact properties: id, project_id, scope, type, path, attrs.
RelatesTo properties: type (e.g. calls, imports, extends, implements_spec, depends_on, supersedes), scope, attrs.

scope is "local" or "global". type on Artifact is one of: module, symbol, spec, doc."""

_CYPHER_FENCE_RE = re.compile(r"```(?:cypher)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class KgSearchError(Exception):
    """Raised when Claude could not produce an executable Cypher query within MAX_RETRIES attempts."""


def _extract_cypher(text: str) -> str:
    match = _CYPHER_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _build_prompt(
    question: str,
    allowed_projects: list[str] | None,
    prior_cypher: str | None,
    prior_error: str | None,
) -> str:
    overlay_instruction = ""
    if allowed_projects is not None:
        overlay_instruction = (
            "\nThis query runs against a shared graph containing multiple projects' data. "
            "You MUST include a filter equivalent to `AND a.project_id IN $allowed_projects` "
            "in your WHERE clause (using whatever variable name you bind the Artifact node "
            "to), using exactly that parameter name — the actual list of allowed ids is "
            "supplied separately at execution time, do not inline specific project ids "
            "yourself."
        )
    prompt = (
        f"{SCHEMA_DESCRIPTION}\n\n"
        "Translate this question into a single read-only Cypher query "
        "(MATCH/RETURN only, no write clauses). Respond with ONLY the Cypher "
        f"query in a code block, no explanation.{overlay_instruction}\n\n"
        f"Question: {question}"
    )
    if prior_cypher and prior_error:
        prompt += (
            f"\n\nYour previous attempt failed:\n{prior_cypher}\n\n"
            f"Error: {prior_error}\n\nFix the query and try again."
        )
    return prompt


def generate_cypher(
    question: str,
    api_key: str,
    model: str = MODEL,
    allowed_projects: list[str] | None = None,
    prior_cypher: str | None = None,
    prior_error: str | None = None,
) -> str:
    """One call to Claude; returns the extracted Cypher text. Does not execute it."""
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError(
            'kg_search requires the anthropic SDK. Install with: pip install "cartographer[kg-search]"'
        ) from exc

    prompt = _build_prompt(question, allowed_projects, prior_cypher, prior_error)
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(getattr(block, "text", "") for block in response.content)
    cypher = _extract_cypher(text)

    if allowed_projects is not None and "$allowed_projects" not in cypher:
        raise KgSearchError(
            "generated query did not reference $allowed_projects, required for scope='global' project isolation"
        )
    return cypher


def run_kg_search(
    question: str,
    api_key: str,
    query_fn,
    model: str = MODEL,
    allowed_projects: list[str] | None = None,
    max_retries: int = MAX_RETRIES,
) -> tuple[str, list[dict]]:
    """Generate and execute Cypher, retrying on failure up to max_retries times.

    query_fn(cypher: str, params: dict) -> list[dict] must raise on a failed
    query, not swallow and return [] — see kg_neo4j.Neo4jDriver.query_raising,
    which exists specifically so this loop can tell "the query failed" apart
    from "the query succeeded and legitimately found nothing."

    Injected rather than hardcoded so this module stays testable without a
    real database and without knowing whether it's talking to local Kuzu or
    central Neo4j — the caller (kg_server.py's kg_search tool) decides that
    and supplies the project_id-scoping params.

    Returns (final_cypher, rows). Raises KgSearchError if every attempt fails.
    """
    params: dict = {"allowed_projects": allowed_projects} if allowed_projects is not None else {}
    prior_cypher: str | None = None
    prior_error: str | None = None
    last_exc: Exception | None = None

    for _attempt in range(max_retries):
        cypher = generate_cypher(
            question, api_key, model=model, allowed_projects=allowed_projects,
            prior_cypher=prior_cypher, prior_error=prior_error,
        )
        try:
            rows = query_fn(cypher, params)
            return cypher, rows
        except Exception as exc:  # noqa: BLE001 - deliberately broad: any failure triggers a retry with the error fed back to Claude
            last_exc = exc
            prior_error = str(exc)
            prior_cypher = cypher

    raise KgSearchError(f"failed to produce a working Cypher query after {max_retries} attempts: {last_exc}")
