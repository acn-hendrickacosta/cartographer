# Component Spec: Plugin Package

The Cartographer plugin is a Claude Code plugin package that bundles the skills, hooks, and MCP server definitions needed to run the knowledge layer inside a Claude Code session. It is installed once from a git-based marketplace and registered per-project by `cartographer init`.

The plugin owns reusable runtime capability. The CLI owns per-project setup and state provisioning. A project needs both.

---

## 1. Responsibilities

| Responsibility | Component |
|---|---|
| Define and register hook scripts | `hooks/hooks.json` |
| Provide the archaeology and recall skills | `skills/` |
| Define and start the VDB and KG MCP servers | `mcp-servers/` |
| Expose hook scripts that are portable across machines | `scripts/` |

The plugin does not provision the index, scaffold the workspace, or manage config files. Those are CLI responsibilities.

---

## 2. Package layout

```
cartographer-plugin/
  .claude-plugin/
    plugin.json             Plugin manifest
  skills/
    archaeology/
      SKILL.md              Archaeology skill definition
    recall/
      SKILL.md              Recall skill definition
  hooks/
    hooks.json              Hook event registrations
  mcp-servers/
    vdb_server.py           VDB MCP server entry point
    kg_server.py            KG MCP server entry point
  scripts/
    ingest_enqueue.py       PostToolUse hook script
    ingest_flush.py         Stop hook script
    preload.py              SessionStart hook script
    retrieve.py             UserPromptSubmit hook script
  README.md                 Plugin-level usage notes
```

---

## 3. Plugin manifest (`plugin.json`)

The manifest declares the plugin identity, version, and the components it provides. Claude Code reads this file when the plugin is installed.

```json
{
  "name": "cartographer",
  "version": "0.1.0",
  "description": "Persistent knowledge layer for Claude Code projects",
  "author": "Cartographer contributors",
  "components": {
    "skills": [
      "skills/archaeology/SKILL.md",
      "skills/recall/SKILL.md"
    ],
    "hooks": "hooks/hooks.json",
    "mcpServers": [
      "mcp-servers/vdb_server.py",
      "mcp-servers/kg_server.py"
    ]
  },
  "minClaudeCodeVersion": "1.0.0"
}
```

### Version policy

The plugin and CLI are versioned independently. A plugin version is compatible with any CLI version that implements the same MCP tool contract versions. Incompatibility between plugin and CLI versions is surfaced by `cartographer doctor`.

---

## 4. Installation

The plugin is installed from a git URL via the Claude Code plugin marketplace:

```bash
claude plugin install <repo-url>/cartographer-plugin
```

Or pinned to a version:

```bash
claude plugin install <repo-url>/cartographer-plugin@v0.1.0
```

`cartographer init` verifies the plugin is installed and writes the MCP server entries and hook registrations into the project's `.mcp.json` and `.claude/settings.json`. If the plugin is not installed when `cartographer init` runs, the CLI prints the install command and exits with an error.

---

## 5. Hook registration

Hooks are registered in `hooks/hooks.json`. The full specification of each hook's behavior, portability rules, and failure handling is in [hooks.md](hooks.md). The registration file itself is minimal.

```json
{
  "hooks": [
    {
      "name": "cartographer-ingest-enqueue",
      "event": "PostToolUse",
      "tools": ["Write", "Edit"],
      "command": "python ${CLAUDE_PLUGIN_ROOT}/scripts/ingest_enqueue.py"
    },
    {
      "name": "cartographer-ingest-flush",
      "event": "Stop",
      "command": "python ${CLAUDE_PLUGIN_ROOT}/scripts/ingest_flush.py"
    },
    {
      "name": "cartographer-preload",
      "event": "SessionStart",
      "command": "python ${CLAUDE_PLUGIN_ROOT}/scripts/preload.py"
    },
    {
      "name": "cartographer-retrieve",
      "event": "UserPromptSubmit",
      "command": "python ${CLAUDE_PLUGIN_ROOT}/scripts/retrieve.py"
    }
  ]
}
```

When `cartographer init` merges these entries into `.claude/settings.json`, it deduplicates by `name`. Re-running `init` does not add duplicate hook registrations.

---

## 6. MCP server registration

MCP servers are registered in `.mcp.json` at the project root by `cartographer init`. The server entries reference the plugin scripts via `${CLAUDE_PLUGIN_ROOT}` so they resolve correctly on any machine where the plugin is installed.

```json
{
  "mcpServers": {
    "cartographer-vdb": {
      "command": "python",
      "args": ["${CLAUDE_PLUGIN_ROOT}/mcp-servers/vdb_server.py"],
      "env": {
        "CARTO_PROJECT_DIR": "${CLAUDE_PROJECT_DIR}",
        "CARTO_CONFIG_PATH": "${CLAUDE_PROJECT_DIR}/cartographer.toml"
      }
    },
    "cartographer-kg": {
      "command": "python",
      "args": ["${CLAUDE_PLUGIN_ROOT}/mcp-servers/kg_server.py"],
      "env": {
        "CARTO_PROJECT_DIR": "${CLAUDE_PROJECT_DIR}",
        "CARTO_CONFIG_PATH": "${CLAUDE_PROJECT_DIR}/cartographer.toml"
      }
    }
  }
}
```

For the full MCP server behavior specification, see [mcp-servers.md](mcp-servers.md).

---

## 7. Skills

Skills are Claude Code skill definitions. Each is a `SKILL.md` file that Claude reads and follows when the skill is invoked. Skills are not scripts -- they are natural language instructions for Claude, referencing MCP tools by name.

| Skill | Invocation | Full spec |
|---|---|---|
| `archaeology` | `/archaeology` | [skills.md: archaeology](skills.md) |
| `recall` | `/recall <query>` | [skills.md: recall](skills.md) |

Skills do not require the plugin to be installed separately -- they travel with the plugin package and are available to Claude once the plugin is installed and the project is initialized.

---

## 8. Portability

All plugin components follow the portability rules defined in [hooks.md](hooks.md):

- Scripts reference their own location via `${CLAUDE_PLUGIN_ROOT}`.
- Project root is read from `$CLAUDE_PROJECT_DIR`.
- Session state is passed between hooks via `$CLAUDE_ENV_FILE`.
- No absolute paths anywhere in the plugin package.

This means the plugin works correctly whether it is installed at `~/.claude/plugins/cartographer-plugin/` on one machine or at a different path on another. `cartographer doctor` verifies that `${CLAUDE_PLUGIN_ROOT}` resolves correctly and that the script files are present and executable.

---

## 9. Updating the plugin

To update the plugin to a new version:

```bash
claude plugin update cartographer
```

After updating, run `cartographer doctor` to verify that the new plugin version is compatible with the project's CLI version and that all hook and MCP server entries in `.claude/settings.json` and `.mcp.json` are still valid.

If the update introduces new hook entries or MCP server entries, run `cartographer init --yes` to merge them into the project config.

---

## 10. Compatibility matrix

| Plugin version | CLI version | Notes |
|---|---|---|
| 0.1.x | 0.1.x | Initial release. Local topology only. |

This table is updated with each release. Breaking changes in the MCP tool contract require a major version bump in both the plugin and the CLI, and a new ADR.

---

## 11. What the plugin does not do

| Out of scope | Where it is handled |
|---|---|
| Provision the VDB collection or KG namespace | `cartographer init` (CLI) |
| Write or merge `cartographer.toml` | `cartographer init` (CLI) |
| Manage API keys or secrets | `.cartographer.local.toml` and environment variables |
| Run outside a Claude Code session | CLI commands run independently of the plugin |
| Support Claude Code Cowork Desktop hooks | Platform limitation; see [hooks.md: Cowork Desktop limitation](hooks.md) |

---

*For the hook behavior spec, see [hooks.md](hooks.md). For the MCP server spec, see [mcp-servers.md](mcp-servers.md). For the skill specs, see [skills.md](skills.md).*
