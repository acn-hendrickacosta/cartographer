# Skill: recall

## Purpose

Cross-project recall: retrieve relevant knowledge from one or more other registered projects on this machine. Enforces tenant isolation as a hard gate before any query fires.

This skill is deliberate and user-invoked. The always-on recall for the current project is handled by the `UserPromptSubmit` hook; this skill is for cross-project lookups that the user explicitly requests.

## Trigger

The user says something like:
- "recall from my other projects"
- "what did we do about X in the API project"
- "check other projects for examples of Y"
- `/recall <query>`

## Steps

1. **Read the current project config**
   - Load `cartographer.toml` from the workspace root.
   - Note `project.id` and `isolation.tenant`.

2. **Tenant isolation gate (hard gate — never skip)**
   - List all registered projects via the registry.
   - **Only query projects with the same `tenant` value as the current project.**
   - If any project in the query set has a different tenant, log a warning and exclude it. Never query across a tenant boundary under any circumstances.
   - If no other projects share the current tenant, tell the user there are no cross-project matches available.

3. **Resolve target projects**
   - If the user named a specific project, find it by name or project_id in the registry.
   - If the user did not name a project, query all same-tenant projects (excluding the current one).

4. **Embed the query**
   - Use the local fastembed embedder to embed the user's query text.
   - If fastembed is not available, report that semantic recall is unavailable and offer KG-only recall.

5. **Query each target project**
   - For each target project, open its local VDB at `<project_location>/.cartographer/local/vdb.lance`.
   - Run a VDB query with the embedded query, k=8.
   - Also run a KG path query for nodes matching the query terms.
   - If the target project has `topology.mode = "central"`, also query the central (global) scope:
     - Query the central VDB for the same embedding.
     - Merge local and global results: local shadows global for the same artifact path.
     - Tag each result with its origin: `local` or `global`.
   - Tag each result with the origin project name, id, and scope origin.

6. **Merge and rank results**
   - Merge results across projects, keeping local-first order within each project.
   - De-duplicate by artifact path: local always shadows global for the same path, regardless of score.

7. **Apply token budget**
   - Respect the `retrieval.per_turn_tokens` budget from the current project config (default 1000 tokens ≈ 4000 chars).
   - Truncate the result set to stay within budget.

8. **Report**
   - Present results in a structured format, grouped by origin project.
   - Each result shows: origin project name, artifact type, file path, symbol (if any), and a text excerpt.

## Isolation rules (non-negotiable)

- NEVER query a project with a different `tenant` than the current project.
- NEVER log, store, or return the absolute path of another project's workspace unless the user explicitly asked for it.
- If the registry is unavailable or returns an error, report the failure and return zero results. Do not fall through to an unchecked query.

## Output format

```
Recall: "<query>"
Searching <n> project(s) in tenant <tenant>

[Project: <project-name>]
  [code] src/auth/service.py :: authenticate
  "... relevant text excerpt ..."
  Score: 0.87

[Project: <project-name>]
  [spec] docs/AUTH_SPEC.md :: Section 3
  "... relevant text excerpt ..."
  Score: 0.81

---
<n> result(s) from <m> project(s). Tenant: <tenant>.
```

If no results are found:
```
Recall: "<query>"
No cross-project results found in tenant <tenant>.
```

If the isolation gate blocks a query:
```
[blocked] Project "<name>" has tenant "<other-tenant>" — skipped. Cross-tenant recall is not permitted.
```
