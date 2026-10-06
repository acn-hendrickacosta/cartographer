# Component Spec: Standards Packs

Standards packs are versioned sets of development standards that Cartographer installs into a project workspace. They are the mechanism by which cross-team practices are distributed and applied consistently, without requiring developers to look them up or remember to follow them.

---

## 1. What a standards pack is

A pack is a directory of markdown files that Claude reads as part of its project context. Once installed into `.claude/standards/<pack-name>/`, the standards are available to Claude in every session without any additional setup. They are not injected by a hook -- they are part of the workspace's permanent Claude configuration.

Packs cover practices that apply at the stack level: how to structure code, how to write specs, how to handle errors, security baselines, review norms. They do not cover project-specific decisions -- those belong in `CLAUDE.md` or the knowledge layer.

---

## 2. Pack inventory

| Pack | Stack | Status | Applied with |
|---|---|---|---|
| `cross-stack` | All projects | Bundled, stable | Always applied at `cartographer init` |
| `python` | Python projects | Bundled, stable | `--stack python` at init or `cartographer stack add python` |
| `react` | React projects | Bundled, stable | `--stack react` at init or `cartographer stack add react` |
| `typescript` | TypeScript projects | Bundled, stable | `--stack typescript` at init or `cartographer stack add typescript` |
| `golang` | Go projects | Bundled, stable | `--stack golang` at init or `cartographer stack add golang` |
| `rust` | Rust projects | Bundled, stable | `--stack rust` at init or `cartographer stack add rust` |
| `java` | Java projects | Bundled, stable | `--stack java` at init or `cartographer stack add java` |
| `kotlin` | Kotlin projects | Bundled, stable | `--stack kotlin` at init or `cartographer stack add kotlin` |
| `angular` | Angular projects | Bundled, stable | `--stack angular` at init or `cartographer stack add angular` |
| `vue` | Vue projects | Bundled, stable | `--stack vue` at init or `cartographer stack add vue` |
| `swift` | Swift projects | Bundled, stable | `--stack swift` at init or `cartographer stack add swift` |
| `dart` | Dart projects | Bundled, stable | `--stack dart` at init or `cartographer stack add dart` |

This table is the authoritative pack list — it must match `KNOWN_PACKS` in `cli/src/cartographer/commands/stack.py` exactly. It previously listed only `cross-stack`, `python`, and `react`, which went stale as the other 9 packs were added without this doc being updated; corrected 2026-10-05 during the Standards Registry phase-doc audit.

More packs are added by contributors. See [CONTRIBUTING.md](../CONTRIBUTING.md) for how to add one.

---

## 3. Pack structure

Each pack is a directory containing at minimum:

```
standards/
  <pack-name>/
    README.md         What this pack covers and who it is for
    standards.md      The standards content
    CHANGELOG.md      Version history; one entry per version

cli/src/cartographer/standards_packs/
  <pack-name>/
    standards.md      Bundled copy shipped with the CLI (kept in sync with standards/)
```

The `standards/` directory is the canonical source. The `cli/src/cartographer/standards_packs/` copy is what the CLI installs into workspaces. They must be identical.

### Optional pack contents

A pack may also include:

| File | Purpose |
|---|---|
| `hooks-addition.json` | Additional hook entries the pack contributes (e.g. a lint hook for the stack) |
| `skills/` | Additional skills the pack contributes specific to the stack |

These are merged additively into the workspace at `stack add` time, following the same deduplication rules as the core plugin registration.

---

## 4. Pack content: cross-stack

The cross-stack pack is always applied. It covers practices that are independent of the technology stack and that every project using Cartographer should follow.

| Section | Content |
|---|---|
| Git hygiene | Commit message format, branch naming, when to squash |
| Spec-driven workflow | How to write a spec, the relationship between spec and code, how to reference a spec from code |
| Review standards | What a code review must check, minimum review criteria, how to handle disagreements |
| Security baseline | Input validation at boundaries, secrets never in code, dependency hygiene |
| Claude Code usage norms | When to use a skill vs a hook, how to write a useful CLAUDE.md, prompt hygiene |

### cross-stack `standards.md` structure

```markdown
# Cross-stack development standards

## Git hygiene
...

## Spec-driven workflow
...

## Review standards
...

## Security baseline
...

## Claude Code usage norms
...
```

---

## 5. Pack content: python

The Python pack covers practices specific to Python projects using Cartographer.

| Section | Content |
|---|---|
| Project structure | Package layout, `pyproject.toml` requirements, src layout vs flat layout |
| Type hints | Where type hints are required, how to use `Protocol` and `TypeVar`, avoiding `Any` |
| Error handling | Typed exceptions, result types vs raising, logging vs re-raising |
| Testing | `pytest` conventions, fixture scope, when to use `unittest.mock` vs real instances |
| Dependency management | Pinning, optional extras, how to declare dev dependencies |
| Async | When to use async, avoiding blocking calls in async contexts |

---

## 6. Pack content: react

The React pack covers practices specific to React projects using Cartographer.

| Section | Content |
|---|---|
| Component structure | File naming, co-location of styles and tests, component vs container split |
| State management | When to use local state vs context vs external store |
| Props and types | TypeScript prop types, avoiding `any`, discriminated unions for variant props |
| Hooks | Custom hook naming and extraction rules, dependency array discipline |
| Testing | Testing Library conventions, what to test vs what to leave to Storybook |
| Accessibility | Required ARIA attributes, keyboard navigation, contrast requirements |

---

## 7. Versioning

Each pack has an independent version following semantic versioning (`MAJOR.MINOR.PATCH`).

| Change type | Version bump |
|---|---|
| New section or new standard added | MINOR |
| Wording clarification with no behavior change | PATCH |
| Standard removed or substantially changed in a way that may require code changes | MAJOR |
| Cross-stack pack change that may affect all projects | MAJOR |

Version is recorded in `CHANGELOG.md` per pack. The bundled CLI ships a specific version of each pack; the version is recorded in `cli/src/cartographer/standards_packs/<pack-name>/VERSION`.

A project may pin to a specific pack version via `stacks.version` in `cartographer.toml` once OQ-06 (pack versioning and pinning) is resolved. Until then, `stack add` always installs the version bundled in the installed CLI.

---

## 8. Distribution: current vs planned

| State | How packs reach a project | Source of truth |
|---|---|---|
| Current (done) | Bundled inside the CLI at `cli/src/cartographer/standards_packs/`. Changing a standard requires a CLI release and a PR. | CLI release |
| Planned: Standards Registry | A versioned, cloud-hosted index (S3). The CLI fetches the latest published version at `stack add` or `init` time. Falls back to bundled versions when the registry is unreachable. | Registry; bundled as fallback |

The Standards Registry and the web app that populates it are deferred. See the standards distribution track in [ROADMAP.md](../ROADMAP.md) and open questions OQ-08 through OQ-10 in [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md).

---

## 9. Where packs are installed

`cartographer init` and `cartographer stack add` copy pack content into the project workspace:

```
.claude/
  standards/
    cross-stack/
      standards.md
    python/
      standards.md
    react/
      standards.md    (if react pack applied)
```

Claude reads everything under `.claude/` as part of its project configuration. The standards are available in every session without any hook injection.

`.claude/standards/` is committed to the repository so all developers on a project share the same standards. When a pack is updated and a developer runs `cartographer stack add <name>` again, the updated content replaces the previous version in `.claude/standards/`.

---

## 10. Relationship to the knowledge layer

Standards packs are static configuration -- they are read by Claude as part of its workspace setup. They are not stored in the VDB or KG and are not retrieved by the recall hooks.

The knowledge layer (VDB and KG) stores project-specific artifacts: code, specs, and documentation. Standards are cross-project practices that apply universally within a stack. Putting them in the knowledge layer would mix universal practices with project-specific knowledge, degrading the quality of recall results.

---

## 11. Contributing a pack

See [CONTRIBUTING.md: Adding a standards pack](../CONTRIBUTING.md). The short version:

1. Create `standards/<pack-name>/` with `README.md`, `standards.md`, and `CHANGELOG.md`.
2. Copy `standards.md` to `cli/src/cartographer/standards_packs/<pack-name>/standards.md`.
3. Register the pack name in the CLI's `SUPPORTED_PACKS` list.
4. Update `docs/CONFIGURATION.md`, this document, and `README.md`.
5. Open a PR.

---

*For how packs are fetched from the planned Standards Registry, see [ARCHITECTURE.md: Standards distribution](../ARCHITECTURE.md). For the web app that will populate the registry, see [standards-webapp.md](standards-webapp.md) once that phase is scheduled.*
