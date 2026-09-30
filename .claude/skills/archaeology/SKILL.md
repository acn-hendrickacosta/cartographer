# Skill: archaeology

## Purpose

Bootstrap the knowledge base for an existing project that has not yet been indexed by Cartographer. Run this once on an existing codebase so the ingestion hooks can maintain it incrementally going forward.

This skill is deliberate and one-time per project. It is not an always-on hook. The user invokes it explicitly or you invoke it when you determine the knowledge base is empty.

## Trigger

The user says something like:
- "index this codebase"
- "bootstrap the knowledge base"
- "run archaeology"
- `/archaeology`

Or you determine the local VDB is empty and suggest running this skill.

## Steps

1. **Check prerequisites**
   - Confirm `cartographer.toml` exists in the workspace root. If not, tell the user to run `cartographer init` first.
   - Check that the local index is provisioned (`.cartographer/local/vdb.lance` and `.cartographer/local/kg.kuzu` exist).
   - Check that fastembed is available by running `python -c "from fastembed import TextEmbedding"`. If it fails, tell the user to install it.

2. **Determine scope**
   - Identify the workspace root from `cartographer.toml`.
   - List the top-level directories and file types to understand the project structure.
   - Note any existing documentation directories (docs/, wiki/, etc.) for doc-first ingestion.

3. **Ingest documentation first**
   - Run `cartographer seed <docs-dir>` for any documentation directories (docs/, wiki/, confluence_export/, etc.).
   - Documentation is highest-signal for recall; ingest it before code.

4. **Ingest code and specs**
   - Run `cartographer seed <workspace-root>` to ingest the full workspace.
   - The pipeline automatically classifies files as code, doc, or spec based on name and extension.

5. **Verify ingestion**
   - Run `cartographer recall "project overview"` to confirm the VDB has results.
   - Run a KG query via the cartographer-kg MCP tool to confirm nodes were created.
   - Report chunk, node, and edge counts.

6. **Infer spec relationships**
   - Look for spec files (SPEC*.md, ADR-*.md, RFC-*.md, DESIGN*.md) and review their contents.
   - For each spec, identify which source files implement it based on:
     - File name co-location (e.g., `auth_service.py` and `AUTH_SPEC.md` in the same directory) — high confidence
     - Explicit comment references (`# per SPEC-101`, `# implements RFC-3`) — high confidence
     - Function names that match spec section headings — medium confidence
     - Shared domain vocabulary in both spec and code — low confidence, note as uncertain
   - Upsert `implements_spec` edges for confirmed and high-confidence relationships only.
   - Note uncertain relationships in your response without asserting them as edges.

7. **Report**
   Report the following:
   - Files processed and skipped
   - Chunk, node, and edge counts
   - Spec-to-implementation edges created and why
   - Any files that failed and why
   - What the user should do next (run doctor, browse with `cartographer ui`, etc.)

## Idempotency

This skill is safe to re-run. The ingestion pipeline upserts by artifact identity (file path + symbol); re-running on an already-indexed project updates stale entries rather than duplicating them.

## Failure modes

- **fastembed not installed**: Cannot embed. Tell the user to install it.
- **Binary files present**: `.docx`, `.pptx`, `.pdf` files are skipped outside Claude Code. They are already in a Claude Code session when this skill runs, but `cartographer seed` from a plain terminal will skip them.
- **Large codebase**: The flush hook processes at most 20 files per turn. For very large codebases, archaeology may need multiple passes. The `cartographer seed` command processes all files in a single pass and is preferred for initial ingestion.
- **No cartographer.toml**: Refuse to proceed. Direct the user to `cartographer init`.

## Output format

End your report with a structured summary block:

```
Archaeology complete
  Files processed : <n>
  Files skipped   : <n>
  Chunks          : <n>
  KG nodes        : <n>
  KG edges        : <n>
  Spec edges      : <n>
  Duration        : ~<N> seconds
```
