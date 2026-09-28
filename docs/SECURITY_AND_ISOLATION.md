# Cartographer: Security and Isolation

This document defines the security model, isolation guarantees, and data governance rules for Cartographer. These are hard requirements. They govern what data may leave a developer's machine, who may query which indexes, and how secrets are handled across every component.

---

## 1. Threat model

Cartographer handles source code, specifications, and project documentation -- artifacts that are frequently confidential, client-specific, or subject to regulatory constraints. The threats this model is designed to address are:

| Threat | Description |
|---|---|
| Cross-tenant data leakage | A recall query for project A returns results from project B, which belongs to a different client or tenant |
| Unintended code egress | Source code is sent to an external embedding API without the team's explicit knowledge or consent |
| Secret exposure | API keys, passwords, or tokens end up in the KG, the VDB, a log file, or a committed config file |
| Unmerged work leakage | A developer's working state (unmerged code, draft specs) is visible to other developers before it is merged |
| Scope creep in recall | A recall query returns global results when the developer intended only local results, or vice versa |

---

## 2. Tenant isolation

Tenant isolation is a hard boundary. No query ever crosses a tenant boundary, under any circumstances.

### 2.1 How it works

Every project record in the registry carries a `tenant` field, set at `cartographer init` via `project.tenant` in `cartographer.toml`. Every VDB collection and KG namespace is scoped to a single project. The recall skill and the UserPromptSubmit hook enforce the following rules before any query fires:

```
Cross-project recall requested
  -> Load target project record from registry
  -> Compare target project.tenant to current project.tenant
  -> If tenants differ: abort query, return empty result, log the blocked attempt
  -> If tenants match: proceed with recall
```

This check happens at the application layer, in the recall skill and the CLI `recall` command. It is not delegated to the backend driver. Even if the VDB or KG backend does not enforce namespace isolation, the application layer blocks the query before it reaches the driver.

### 2.2 What the tenant field means

| Value | When to use |
|---|---|
| `"internal"` | Projects owned by the team itself, with no client confidentiality constraint |
| `"<client-slug>"` | A specific client or engagement. Use a consistent slug across all projects for that client. |

There is no global `"all"` tenant. There is no mechanism to query across tenants. Cross-tenant recall is not a deferred feature -- it is a deliberate non-feature.

### 2.3 Isolation in central topology

When a central backend is configured, each project's VDB collection and KG namespace carries the `project_id` in its name (`carto_<project_id>_global`). This means:

- A developer with an API key for project A cannot query the collection for project B, because the collection name is derived from project B's `project_id`, which they do not know.
- The central backend should additionally enforce that each API key is scoped to a specific set of collection or namespace names. This is configured at the backend level, outside Cartographer, as a defense-in-depth measure.

---

## 3. Data egress

### 3.1 Default: no egress

By default, source code and documentation never leave the developer's machine for embedding. The default embedder driver is `fastembed`, which runs a local model in-process. No network call is made during embedding.

### 3.2 API embedder opt-in

Switching the embedder driver to `"api"` causes source code to be sent to an external endpoint for embedding. This is an explicit opt-in with the following guardrails:

- The CLI prints a one-time warning on first use of the API embedder: `"Source code will be sent to <api_url> for embedding. Confirm this is acceptable for this project [y/N]."` The response is recorded in the local override file. The warning does not repeat after confirmation.
- The `api_url` is set in `.cartographer.local.toml` (gitignored), not in `cartographer.toml`. This prevents the API embedder from being silently enabled for all developers by a single config commit.
- The API key is never logged.

Teams working on client code or regulated data should not use the API embedder without explicit approval from whoever owns the data governance policy for that engagement.

### 3.3 Promotion and egress

Promotion (local to global) sends artifact text to the central backend for storage. This is intentional and expected when central topology is configured. Teams must ensure the central backend endpoint is:

- Operated under an appropriate data handling agreement for the project's data classification.
- Accessible only to developers who are authorized to work on that project.
- Not shared between tenants.

Only merged artifacts are eligible for promotion. Unmerged working state is never sent to the central backend.

### 3.4 Binary document extraction

When a binary document (`.docx`, `.pptx`, `.pdf`) is ingested, Claude (local, running on the developer's machine) is invoked to extract text content. This extraction happens entirely on the developer's machine via the MCP tool interface already in the session. No document content is sent to an external service for extraction.

---

## 4. Secret handling

### 4.1 Where secrets live

| Secret type | Correct location | Forbidden locations |
|---|---|---|
| VDB API key | `.cartographer.local.toml` or `CARTO_VDB_API_KEY` env var | `cartographer.toml`, KG, VDB, log output |
| KG API key | `.cartographer.local.toml` or `CARTO_KG_API_KEY` env var | `cartographer.toml`, KG, VDB, log output |
| Embedder API key | `.cartographer.local.toml` or `CARTO_EMBEDDER_API_KEY` env var | `cartographer.toml`, KG, VDB, log output |
| Standards Registry API key | `.cartographer.local.toml` or `CARTO_STANDARDS_REGISTRY_API_KEY` env var | `cartographer.toml`, KG, VDB, log output |
| Database passwords (central backend) | AWS Secrets Manager (server side) | Any client-side file, KG, VDB, log output |

### 4.2 Secret scanning in committed config

`cartographer doctor` scans `cartographer.toml` for strings matching common secret patterns before allowing the CLI to proceed with a central topology operation. Patterns checked include substrings: `key`, `token`, `password`, `secret`, `credential`, `bearer`. If a match is found, the CLI exits with an error and a message identifying the suspicious field.

This check is not a substitute for a proper secret scanning tool in CI (e.g., `trufflehog`, `gitleaks`). It is a last-resort catch for the most common accident.

### 4.3 Secrets in the knowledge stores

The ingestion pipeline strips API keys, tokens, and password-pattern strings from chunk text before embedding and storing. Stripping is regex-based and best-effort. It is not a guarantee. Do not intentionally ingest files that contain production secrets.

---

## 5. Working state isolation

### 5.1 Local scope is private

The local VDB collection and KG namespace (`carto_<project_id>_local`) live on the developer's machine, inside the project directory (`.cartographer/`). They are not shared with other developers, not replicated to the central backend, and not accessible via the API key the team uses for the central backend.

Unmerged code, draft specs, and seeded documentation that has not been promoted remain entirely local.

### 5.2 Promotion boundary enforces the local/global split

Only `cartographer promote` (or its CI equivalent) may write to the global scope. No hook, skill, or MCP tool writes directly to global scope except through the promotion path. This is enforced in the driver interface: the `scope` argument on every write operation is validated; a write to `scope=global` from any path other than the promotion command is rejected.

### 5.3 Read tagging

When a recall hook or the recall skill returns results from both local and global scope, each result is tagged with its origin (`local` or `global`). Claude and the developer can see which results come from merged canonical state and which come from the developer's own unmerged working state. Results are never mixed silently.

---

## 6. Access control

### 6.1 CLI and local index

The local VDB and KG are file-based stores in `.cartographer/` within the project directory. Access is controlled by the operating system filesystem permissions on that directory. No authentication layer is added on top of local drivers.

### 6.2 Central backend

The central backend is protected by API key authentication over HTTPS. Each developer holds their own API key, configured in `.cartographer.local.toml` or the environment. Keys are provisioned and revoked at the central backend's management layer, outside Cartographer.

Recommended practices for central backend access control:

| Practice | Reason |
|---|---|
| Issue one API key per developer, not one shared team key | Allows individual revocation without rotating a shared secret |
| Scope each key to a specific project's collections and namespaces | Limits blast radius if a key is compromised |
| Rotate keys when a developer leaves the project | Revoke promptly; unrevoked keys retain full access to the project's global index |
| Use short-lived keys issued by an identity provider where the backend supports it | Preferred over long-lived static keys for high-sensitivity projects |

### 6.3 Standards web app

The Standards web app uses Cognito for authentication. Role assignment (Author, Reviewer, Admin) is managed by an Admin in the Cognito user pool. Access to the web app does not grant access to the central VDB or KG backends; those are separate credentials.

---

## 7. Compliance and data classification

Cartographer does not enforce a data classification policy. Teams are responsible for:

- Confirming the data classification of each project's source code and documentation before configuring a central backend.
- Ensuring the central backend endpoint is operated under a data handling agreement appropriate for that classification.
- Obtaining approval before enabling the API embedder for projects involving confidential or regulated data.
- Not ingesting production secrets, PII, or regulated data into the knowledge layer without appropriate controls at the storage layer.

These responsibilities should be documented in the project's own security review, not assumed to be covered by Cartographer's isolation model.

---

## 8. Audit and logging

| Event | Logged | Log destination |
|---|---|---|
| Recall query blocked by tenant isolation check | Yes | Local log file (`~/.cartographer/audit.log`) |
| API embedder first-use confirmation | Yes | `.cartographer.local.toml` (confirmation field) |
| Promotion run: artifact count, scope, project_id | Yes | stdout and local log |
| Central backend auth failure | Yes | stderr |
| Secret pattern detected in `cartographer.toml` | Yes | stderr, CLI exits non-zero |

Logs never contain chunk text, embedding vectors, API keys, or artifact content. They contain metadata only: timestamps, project IDs, operation names, counts, and error messages.

---

*For configuration of API keys and driver endpoints, see [CONFIGURATION.md](CONFIGURATION.md). For the promotion mechanics and scope rules, see [DATA_MODEL.md](DATA_MODEL.md).*
