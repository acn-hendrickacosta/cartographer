# Contributing to Cartographer

This document covers how to contribute to Cartographer: adding a standards pack, contributing to the CLI or plugin, submitting a bug report, and the conventions all contributions must follow.

---

## 1. What you can contribute

| Contribution type | Where it lands |
|---|---|
| New standards pack | `standards/<pack-name>/` and `cli/src/cartographer/standards_packs/` |
| Cross-stack standards update | `standards/cross-stack/` |
| New VDB or KG backend driver | `cli/src/cartographer/drivers/vdb/` or `cli/src/cartographer/drivers/kg/` |
| CLI command improvement or bug fix | `cli/src/cartographer/commands/` |
| Plugin hook or skill improvement | `cartographer-plugin/scripts/` or `cartographer-plugin/skills/` |
| Documentation correction | `docs/` |
| Bug report or open question | GitHub issue or `docs/OPEN_QUESTIONS.md` PR |

Before starting significant work, open an issue or discussion first. This avoids building something that conflicts with a decision already recorded in the open questions or roadmap.

---

## 2. Adding a standards pack

Adding a standards pack is the most common contribution. It does not require deep knowledge of the CLI or plugin internals.

### 2.1 Pack structure

Each pack lives in two places: the canonical source in `standards/` and the bundled copy in the CLI package.

```
standards/
  <pack-name>/
    README.md           # what this pack covers and who it is for
    standards.md        # the standards content itself
    CHANGELOG.md        # version history

cli/src/cartographer/standards_packs/
  <pack-name>/
    standards.md        # copy of the pack content (kept in sync manually)
```

The `standards/` directory is the canonical source. The `cli/src/cartographer/standards_packs/` copy is what ships with the CLI and is what `cartographer stack add` and `cartographer init` install into a workspace. Keep them in sync when submitting a PR.

### 2.2 Pack content requirements

A standards pack must satisfy the following before it is accepted:

| Requirement | Detail |
|---|---|
| Scoped to a specific stack or concern | Do not mix concerns in one pack. Python standards go in the Python pack, not in cross-stack. |
| Actionable, not aspirational | Each standard must describe a concrete, enforceable practice. Avoid "write clean code." Write "functions must have a single return type; use a result type or raise a specific exception rather than returning None on error." |
| Self-contained | A developer reading the pack must understand what to do without needing to cross-reference other documents. |
| No external links as requirements | External links as references are fine. Requiring a developer to read an external document to understand a standard is not. |
| Versioned from the start | The `CHANGELOG.md` must exist with an initial entry for the first version. |

### 2.3 Naming convention

Pack names are lowercase, hyphen-separated, and match the primary technology or concern:

- `python`, `react`, `typescript`, `go`, `rust`
- `api-design`, `observability`, `security-baseline`

Cross-stack standards go in updates to the existing `cross-stack` pack, not a new pack.

### 2.4 Registering the pack with the CLI

1. Add the pack directory under `cli/src/cartographer/standards_packs/<pack-name>/`.
2. Register the pack name in `cli/src/cartographer/commands/stack_add.py` in the `SUPPORTED_PACKS` list.
3. Add the pack to the `[stacks]` documentation in `docs/CONFIGURATION.md`.
4. Add an entry to the standards packs table in `docs/components/standards-packs.md`.
5. Update the pack list in `README.md`.

### 2.5 Testing a new pack

```bash
# Install the CLI in development mode
pip install -e "cli/[embed]"

# Initialize a test project
mkdir /tmp/test-project && cd /tmp/test-project
git init
cartographer init --stack <pack-name> --yes

# Verify the pack was written
ls .claude/standards/<pack-name>/

# Verify doctor passes
cartographer doctor
```

---

## 3. Adding a backend driver

Adding a new VDB or KG driver allows teams to use a different backend with Cartographer without changing anything else.

### 3.1 VDB driver

1. Create `cli/src/cartographer/drivers/vdb/<driver-name>.py`.
2. Implement all methods defined in `cli/src/cartographer/drivers/vdb/base.py`. Every method is required; no partial implementations.
3. Register the driver in `cli/src/cartographer/drivers/vdb/__init__.py` under the key that will appear in `vdb.driver` in `cartographer.toml`.
4. Add the driver's dependencies to `cli/pyproject.toml` as an optional extra:
   ```toml
   [project.optional-dependencies]
   <driver-name> = ["<package>>=<version>"]
   ```
5. Document the driver's config requirements (endpoint format, API key, any driver-specific options) in `docs/CONFIGURATION.md` under the `[vdb]` section.
6. Write an ADR recording the decision to add the driver. See `docs/adr/0000-template.md`.
7. Add integration tests that run the full VDB tool contract against the new driver.

### 3.2 KG driver

Same steps as VDB driver, using `cli/src/cartographer/drivers/kg/` and the KG base class.

### 3.3 Driver contract compliance

Both the VDB and KG drivers have implementation requirements listed in their contract documents. A driver PR will not be merged unless all requirements are met:

- [contracts/vdb-tools.md: Driver implementation requirements](contracts/vdb-tools.md)
- [contracts/kg-tools.md: Driver implementation requirements](contracts/kg-tools.md)

---

## 4. CLI and plugin contributions

### 4.1 Development setup

```bash
# Clone the repo
git clone <repo-url>
cd cartographer

# Install the CLI in editable mode with all extras
pip install -e "cli/[embed,dev]"

# Run the test suite
cd cli && pytest
```

### 4.2 Code conventions

| Convention | Detail |
|---|---|
| Python version | 3.11 or later |
| Type hints | Required on all public functions and methods |
| Docstrings | One-line summary only. No multi-paragraph docstrings. |
| Comments | Only for non-obvious invariants or workarounds. Not for describing what the code does. |
| Error handling | Validate at system boundaries (user input, driver calls, file I/O). Do not add defensive checks for conditions that cannot occur. |
| No new config knobs without docs | Every new config key must be documented in `docs/CONFIGURATION.md` and added to `cartographer.example.toml`. |

### 4.3 Command changes

Any change to a CLI command's behavior -- new flags, changed defaults, changed exit codes, changed output format -- must be reflected in:

- `docs/components/cli.md` (the component spec)
- `cartographer.example.toml` (if the change adds or modifies a config key)
- `docs/CONFIGURATION.md` (same)

### 4.4 Hook changes

Any change to a hook's behavior -- event filter, output format, env file keys -- must be reflected in `docs/components/hooks.md`. Hook changes have a high risk of silent breakage (hooks fail gracefully) so they require extra care in testing.

### 4.5 MCP tool contract changes

MCP tool contracts are a public interface. Adding a new tool or adding optional fields to an existing tool is backwards-compatible. Changing a tool's name, removing a field, or changing an error code is a breaking change and requires an ADR before the PR is opened.

---

## 5. Documentation contributions

- Corrections and clarifications to existing documents: open a PR directly.
- New documents: open an issue first to confirm where the document fits in the existing set.
- Writing style: human-sounding prose, no em dashes, dense and tabular for technical content. Match the style of the existing documents. See `PROJECT_BRIEF.md` Section 15 for the full writing conventions.

---

## 6. Bug reports

Open a GitHub issue with:

1. The command that failed, with its full arguments.
2. The output (stdout and stderr).
3. The relevant sections of `cartographer.toml` (omit secrets and endpoints).
4. The output of `cartographer doctor`.
5. Platform: OS, Python version, CLI version (`cartographer --version`).

---

## 7. Pull request checklist

Before opening a PR, confirm:

- [ ] All tests pass (`pytest` in `cli/`).
- [ ] `cartographer doctor` passes on a test project initialized with the changes.
- [ ] Any new config keys are documented in `docs/CONFIGURATION.md` and `cartographer.example.toml`.
- [ ] Any new commands or command changes are documented in `docs/components/cli.md`.
- [ ] Any new pack is registered in the CLI and documented.
- [ ] Any breaking change to an MCP tool contract has an ADR.
- [ ] The PR description explains why the change is made, not just what it does.

---

## 8. Decisions and ADRs

Significant decisions -- new drivers, new tools, changes to the data model, changes to the promotion protocol -- must be recorded as Architecture Decision Records (ADRs) in `docs/adr/`. Use `docs/adr/0000-template.md` as the template.

ADRs are append-only. A decision that supersedes an earlier one gets its own ADR with a reference to the one it replaces. Do not edit a closed ADR.

---

*For the project roadmap and phase scope, see [ROADMAP.md](ROADMAP.md). For open questions that may affect your contribution, see [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).*
