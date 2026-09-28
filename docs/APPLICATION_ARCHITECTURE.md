# Cartographer: Application Architecture

This document covers two applications: the CLI (`cartographer`) and the Standards web app. For the CLI it describes internal module structure and the execution flow of every command. For the web app it describes user roles, screen inventory, navigation, and the state transitions that govern the authoring, review, and publish lifecycle.

The high-level system architecture (layers, topologies, AWS reference deployment) is in [ARCHITECTURE.md](ARCHITECTURE.md). The data schemas are in [DATA_MODEL.md](DATA_MODEL.md).

---

## Part 1: CLI Application Architecture

### 1.1 Module structure

```
cli/
  src/cartographer/
    cli.py                  Entry point. Registers all Click command groups.
    commands/
      init.py               cartographer init
      detect.py             cartographer detect
      stack_add.py          cartographer stack add
      promote.py            cartographer promote
      recall.py             cartographer recall
      seed.py               cartographer seed
      doctor.py             cartographer doctor
    config/
      loader.py             Load and merge cartographer.toml + local override
      schema.py             Config schema and validation
      writer.py             Write config and local override files
    workspace/
      detector.py           Detect existing .claude, CLAUDE.md, .mcp.json, settings.json
      merger.py             Merge Cartographer config additively into existing workspace files
      scaffolder.py         Write the .claude baseline, CLAUDE.md, and mcp entries
    index/
      provisioner.py        Provision VDB collections and KG namespaces for a project
      registry.py           Read and write the local project registry (registry.db)
    ingestion/
      pipeline.py           Orchestrate extract -> chunk -> embed -> VDB upsert + KG upsert
      text_extractor.py     Extract plain text from a file by format:
                              plain (.md .rst .txt .adoc): read directly
                              binary (.docx .pptx .pdf): delegate to Claude (local)
                              via MCP tool call; no external model or API
      chunker.py            Split extracted text into chunks by artifact type
      embedder.py           Embed chunks using the configured embedder driver
      graph_extractor.py    Extract KG nodes and edges from extracted text and chunks
    drivers/
      vdb/
        base.py             VDB driver interface (abstract)
        lancedb.py          Local LanceDB driver
        qdrant.py           Qdrant driver (central)
        pgvector.py         pgvector driver (central)
      kg/
        base.py             KG driver interface (abstract)
        kuzu.py             Local Kuzu driver
        neo4j.py            Neo4j driver (central)
        neptune.py          Neptune driver (central)
      embedder/
        base.py             Embedder interface (abstract)
        fastembed.py        Local fastembed driver (default)
        api.py              API embedder driver (opt-in)
    standards_packs/        Bundled cross-stack, python, and react packs
    ui/
      server.py             FastAPI app; mounts static files and API routes
      static/               Single-page HTML/JS/CSS; no build step required
        index.html          Shell page; loads views and D3.js from CDN
        app.js              View routing and API calls
        graph.js            Force-directed KG graph using D3.js
```

### 1.2 Configuration loading sequence

Every command starts by loading config before doing any work.

```
CLI command invoked
  -> loader.py: locate cartographer.toml in project root (walk up from cwd)
  -> loader.py: load and validate cartographer.toml via schema.py
  -> loader.py: locate .cartographer.local.toml in same directory (gitignored)
  -> loader.py: merge local override on top of project config (local wins on conflict)
  -> loader.py: overlay environment variables (CARTO_* prefix, highest precedence)
  -> Return merged Config object to the command
```

If `cartographer.toml` is not found and the command requires it, the CLI exits with a clear message directing the developer to run `cartographer init` first. `detect` and `init` are the only commands that run without an existing config.

### 1.3 Command flows

#### `cartographer detect`

Dry run. Never writes anything.

```
Load environment (no config required)
  -> detector.py: scan workspace root for:
       .claude/             (directory and its contents)
       CLAUDE.md
       .mcp.json
       .claude/settings.json
       cartographer.toml
  -> For each found file: report what it contains and what init would do with it
  -> For each missing file: report what init would create
  -> Print report to stdout. Exit 0.
```

#### `cartographer init`

The most complex command. Idempotent.

```
Load environment (no existing config required)
  -> Assign or load project_id (generate UUID on first run, reuse on re-run)
  -> detector.py: scan workspace (same as detect)
  -> merger.py: compute merge plan
       If CLAUDE.md exists: plan additive merge of Cartographer project-knowledge section
       If .claude/settings.json exists: plan additive merge of hook entries
       If .mcp.json exists: plan additive merge of MCP server entries, deduplicate
       If none exist: plan fresh create for all
  -> Prompt user to confirm merge plan (or --yes to skip)
  -> scaffolder.py: execute plan
       Write or merge CLAUDE.md
       Write or merge .claude/settings.json (hooks, permissions)
       Write or merge .mcp.json (VDB and KG MCP server entries)
       Write cross-stack standards baseline into .claude/standards/
  -> If --stack <name> flags given: run stack add logic for each (see below)
  -> If --seed-docs <path> given: run seed logic for the path (see below)
  -> config/writer.py: write cartographer.toml and .cartographer.local.toml stub
  -> index/provisioner.py: provision local VDB collection and KG namespace
       VDB driver: ensure_collection(project_id, scope=local)
       KG driver:  ensure_namespace(project_id, scope=local)
  -> index/registry.py: upsert project record into ~/.cartographer/registry.db
  -> Print summary of every file written, merged, or left unchanged. Exit 0.
```

#### `cartographer stack add <name>`

```
Load config
  -> Resolve pack name against bundled standards_packs/ directory
       If Standards Registry is configured: fetch from registry, fall back to bundled on failure
       If not configured: use bundled pack
  -> Copy pack markdown into .claude/standards/<name>/
  -> If pack includes optional skills or hooks: merge them into .claude/ additively
  -> Update cartographer.toml: add <name> to active_stacks if not present
  -> Print what was written. Exit 0.
```

#### `cartographer seed <path>`

```
Load config
  -> Resolve <path> to a list of files (directory walk, glob, or single file)
  -> Filter to supported doc types: .md, .rst, .txt, .adoc, .docx, .pptx, .pdf
  -> ingestion/pipeline.py: for each file:
       extractor.py: extract plain text from the file
         Plain text formats (.md, .rst, .txt, .adoc): read directly
         Binary formats (.docx, .pptx, .pdf): invoke Claude (local) to extract
           structured text content -- section headings, body text, speaker notes
           (pptx), and table content. Claude is called via the MCP tool interface
           already available in the session; no external model or API is used.
       chunker.py:  split extracted text into chunks at heading or section boundaries
       embedder.py: embed each chunk using configured embedder driver
       extractor.py: extract KG nodes (type: doc) and edges (type: documents)
       VDB driver:  upsert chunks to local scope
       KG driver:   upsert nodes and edges to local scope
  -> Print count of files ingested, chunks written, nodes and edges upserted. Exit 0.
```

#### `cartographer promote`

```
Load config
  -> Validate topology is central (exit with message if local-only)
  -> Validate central backend is reachable (API key check)
  -> Identify artifacts changed since last promotion
       Strategy: compare last_indexed_at in registry against git log --since
       Fall back to full re-promotion if last_indexed_at is absent
  -> ingestion/pipeline.py: re-ingest changed artifacts against global scope
       VDB driver:  upsert chunks to global scope (idempotent)
       KG driver:   upsert nodes and edges to global scope (idempotent)
  -> registry.py: update last_promoted_at for this project
  -> Print count of artifacts promoted. Exit 0.
```

#### `cartographer recall <query>`

```
Load config
  -> registry.py: list projects in registry, filtered by current tenant
  -> For each matching project:
       VDB driver: query(text=<query>, k=5, scope=local)
       If central topology: VDB driver: query(text=<query>, k=5, scope=global)
       KG driver:  query(pattern derived from <query>, scope=local)
  -> Merge and rank results, tag each by project and origin
  -> Print ranked results to stdout. Exit 0.
```

This command is a debugging aid. The primary recall path is the UserPromptSubmit hook injecting results automatically per turn.

#### `cartographer doctor`

```
Load config
  -> Check cartographer.toml is valid (schema validation)
  -> Check .claude/settings.json contains expected hook entries
  -> Check .mcp.json contains expected MCP server entries
  -> VDB driver: ping local backend
  -> KG driver:  ping local backend
  -> If central topology configured:
       VDB driver: ping central backend with configured API key
       KG driver:  ping central backend with configured API key
  -> registry.py: verify this project is registered
  -> Print pass/fail for each check. Exit 0 if all pass, 1 if any fail.
```

---

## Part 2: Standards Web App

### 2.1 Purpose and scope

The Standards web app is a separate application from the CLI and the plugin. It lets SMEs author, review, and publish standards pack versions into the Standards Registry (an S3 bucket) without needing repo access or a CLI release.

This application is a deferred phase. This document defines the screen inventory and flows so the implementation phase can begin from an agreed spec.

### 2.2 User roles

| Role | Who | Permissions |
|---|---|---|
| Author | A subject matter expert who writes standards content | Create and edit draft pack versions; submit a draft for review; view all published versions |
| Reviewer | A designated approver | View and comment on drafts in review; approve or reject a draft |
| Admin | Platform owner | Manage users and role assignments; create new pack names; deprecate packs |

A user can hold more than one role. An Author cannot approve their own draft.

### 2.3 Pack version lifecycle

```
DRAFT -> IN REVIEW -> APPROVED -> PUBLISHED
                  \-> REJECTED -> DRAFT (revised)
```

| State | Meaning |
|---|---|
| DRAFT | Being edited by an Author. Not visible to CLI fetches. |
| IN REVIEW | Submitted by an Author. Locked for editing. Awaiting Reviewer decision. |
| APPROVED | Approved by a Reviewer. Ready to publish. Not yet in the registry. |
| PUBLISHED | Written as an immutable version to the S3 registry. Available to CLI fetches. |
| REJECTED | Reviewer returned it to the Author with comments. Author may revise and resubmit. |

A published version is immutable. Corrections require a new draft with a new version number.

### 2.4 Screen inventory

| Screen | Path | Role access |
|---|---|---|
| Login | `/login` | All |
| Dashboard | `/` | All |
| Pack detail | `/packs/:packName` | All |
| Pack editor | `/packs/:packName/drafts/:draftId/edit` | Author |
| Review queue | `/review` | Reviewer |
| Review screen | `/review/:draftId` | Reviewer |
| Version history | `/packs/:packName/versions` | All |
| Admin: user management | `/admin/users` | Admin |
| Admin: pack management | `/admin/packs` | Admin |

### 2.5 Screen flows

#### Login

```
/login
  -> Cognito hosted UI (or embedded Cognito form)
  -> On success: redirect to /
  -> On failure: display error, remain on /login
```

#### Dashboard

```
/
  Shows: list of all pack names with their latest published version,
         pending draft count per pack (if user is Author or Reviewer),
         review queue badge count (if user is Reviewer)

  Actions:
    [Open pack]       -> /packs/:packName
    [Review queue]    -> /review          (Reviewer only)
    [Admin]           -> /admin/packs     (Admin only)
```

```
Dashboard
+--------------------------------------------------+
|  Cartographer Standards                 [Admin]  |
+--------------------------------------------------+
|  Pack             Latest version  Drafts         |
|  ------------------------------------------------|
|  cross-stack      v1.4.0          1 in review    |
|  python           v2.1.0          --             |
|  react            v1.0.2          1 draft        |
+--------------------------------------------------+
|  [+ New pack]  (Admin only)                      |
+--------------------------------------------------+
```

#### Pack detail

```
/packs/:packName
  Shows: pack description, current published version content (read-only),
         active draft if one exists for this user's role,
         link to version history

  Actions:
    [Edit / New draft]    -> /packs/:packName/drafts/:draftId/edit
                             Creates a new draft if none exists for this user.
                             Opens existing draft if one is already in progress.
    [Version history]     -> /packs/:packName/versions
    [Submit for review]   -> Transitions draft from DRAFT to IN REVIEW
                             (visible only when a DRAFT exists and the user is its Author)
```

```
Pack detail: python
+------------------------------------------------------+
|  < Back to dashboard                                 |
|  python  v2.1.0 (published 2026-08-10)               |
+------------------------------------------------------+
|  [Content]  [Version history]                        |
|  --------------------------------------------------- |
|  ## Python standards                                 |
|  ...published content rendered here...               |
+------------------------------------------------------+
|  YOUR DRAFT: v2.2.0 (last edited 2026-09-20)         |
|  [Edit draft]  [Submit for review]                   |
+------------------------------------------------------+
```

#### Pack editor

```
/packs/:packName/drafts/:draftId/edit
  Shows: split-pane markdown editor (left: edit, right: preview),
         version number field (auto-incremented, editable),
         save status indicator,
         diff toggle against the current published version

  Actions:
    [Save]              -> Auto-save on change; explicit save button
    [Show diff]         -> Toggle diff view against current published version
    [Submit for review] -> Validate version number is higher than current published.
                           Transition draft to IN REVIEW. Lock editor. Redirect to /packs/:packName.
    [Discard draft]     -> Confirm dialog. Deletes the draft. Redirect to /packs/:packName.
```

```
Pack editor: python / draft v2.2.0
+-----------------------------+-----------------------------+
|  EDIT                       |  PREVIEW                    |
|-----------------------------|-----------------------------+
|  ## Python standards        |  Python standards           |
|  ...                        |  ...                        |
|                             |                             |
+-----------------------------+-----------------------------+
|  Version: [2.2.0]  [Show diff]  [Save]  [Submit for review]  [Discard] |
+-------------------------------------------------------------------------+
```

#### Review queue

```
/review
  Shows: list of drafts in IN REVIEW state, ordered by submission date,
         pack name, version, Author name, submission date for each

  Actions:
    [Open]  -> /review/:draftId
```

```
Review queue
+------------------------------------------------------+
|  Pending review (2)                                  |
+------------------------------------------------------+
|  Pack         Version  Author    Submitted           |
|  ----------------------------------------------------|
|  cross-stack  v1.5.0   J. Smith  2026-09-18   [Open] |
|  python       v2.2.0   A. Patel  2026-09-20   [Open] |
+------------------------------------------------------+
```

#### Review screen

```
/review/:draftId
  Shows: side-by-side diff of draft version (right) against current published version (left),
         metadata: pack name, version, Author, submission date,
         comment thread (inline comments and general comments),
         approve / reject controls

  Actions:
    [Add comment]   -> Inline or general comment, saved immediately
    [Approve]       -> Confirm dialog. Transition to APPROVED.
                       Publish dialog appears immediately after (see below).
    [Reject]        -> Require a comment. Transition to REJECTED. Notify Author.
```

```
Review: python v2.2.0
+----------------------------+----------------------------+
|  CURRENT: v2.1.0           |  DRAFT: v2.2.0             |
|----------------------------|----------------------------+
|  ## Python standards       |  ## Python standards       |
|  ...unchanged lines...     |  ...unchanged lines...     |
|                             +  ### New section           |
|                             +  ...added content...       |
+----------------------------+----------------------------+
|  Comments                                               |
|  [Add comment]                                          |
+------------------------------------------------------+
|                       [Reject]  [Approve]              |
+------------------------------------------------------+
```

#### Publish confirmation (modal, triggered after Approve)

```
After Approve:
  Modal: "Publish python v2.2.0 to the Standards Registry?"
  Shows: pack name, version number, summary of changes (line count diff)
  Actions:
    [Publish]   -> Write immutable version object to S3 registry.
                   Transition draft to PUBLISHED.
                   Redirect to /packs/python.
    [Publish later] -> Transition to APPROVED but do not publish yet.
                       An Admin or Reviewer can publish from the pack detail screen later.
```

#### Version history

```
/packs/:packName/versions
  Shows: table of all published versions, newest first:
         version number, published date, published by, changelog summary (if provided)

  Actions:
    [View]   -> Read-only view of that version's content
    [Diff]   -> Diff any two versions side by side
```

---

## Part 3: Runtime hook flows

The plugin hooks are not part of the CLI or the web app but they interact with the same ingestion pipeline the CLI uses. Their flows are documented here for completeness.

### 3.1 Ingest hook (PostToolUse + Stop)

```
PostToolUse fires (Write or Edit tool)
  -> Read $CARTOGRAPHER_DIRTY_QUEUE path from env (set by SessionStart hook)
  -> Append changed file path and artifact_type to the queue file
  -> Exit immediately (observe-only, must not block the turn)

Stop event fires (or git commit hook triggers)
  -> Read dirty queue
  -> If queue is empty: exit
  -> ingestion/pipeline.py: for each queued file:
       text_extractor.py: extract plain text (Claude used for binary formats)
       chunker.py + embedder.py + graph_extractor.py: chunk, embed, extract graph
       VDB driver + KG driver: upsert to local scope
  -> Clear dirty queue
```

### 3.2 Preload hook (SessionStart)

```
SessionStart fires
  -> Load config (cartographer.toml for the project root)
  -> Write project_id, scope config, and dirty queue path to $CLAUDE_ENV_FILE
  -> KG driver:  neighborhood query for files in the current git working set
  -> VDB driver: query for top-k relevant chunks scoped to current branch context
  -> Format results as a compact context block within the configured token budget
  -> Inject into session context via stdout
```

### 3.3 Retrieve hook (UserPromptSubmit)

```
UserPromptSubmit fires
  -> Read the submitted prompt text
  -> VDB driver: query(text=prompt, k=configured_k, scope=local)
  -> If central topology: VDB driver: query(text=prompt, k=configured_k, scope=global)
  -> KG driver:  neighborhood query for artifacts referenced in the prompt
  -> Merge results, deduplicate by artifact identity, tag by origin
  -> Format as a compact context block within the configured token budget
  -> Inject into prompt context via stdout
```

---

*For configuration of token budgets, chunk sizes, and backend drivers, see [CONFIGURATION.md](CONFIGURATION.md). For the VDB and KG MCP tool contracts, see [contracts/vdb-tools.md](contracts/vdb-tools.md) and [contracts/kg-tools.md](contracts/kg-tools.md).*
