# ADR-0001: Record architecture decisions using ADRs

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-24 |
| Deciders | Hendrick |

---

## Context

Cartographer is a multi-component system with decisions spread across the CLI, plugin, state layer, and standards distribution. Without a structured record of why decisions were made, future contributors face two problems: they repeat the investigation of alternatives already evaluated, and they change things that were deliberately constrained without understanding the constraint.

The project brief (Section 16) calls for ADRs explicitly. A lightweight format is needed that is easy to write, easy to read, and does not require tooling.

---

## Decision

We will use Architecture Decision Records (ADRs) stored as markdown files in `docs/adr/` to record all significant architectural and design decisions. Each ADR is numbered sequentially, append-only, and follows the template in `docs/adr/0000-template.md`.

---

## Options considered

### Option A: Decision log in a single document

A running `DECISIONS.md` file with dated entries.

Tradeoffs: easy to start, hard to navigate as it grows. No structure per decision. Diffs are noisy.

### Option B: ADRs in `docs/adr/` (chosen)

One file per decision, numbered sequentially, following a consistent template.

Tradeoffs: slightly more overhead to write. Each decision is independently linkable, searchable, and diffable. The numbered sequence makes the history readable. Widely understood format.

### Option C: No formal record

Decisions are captured only in commit messages, PR descriptions, or comments.

Tradeoffs: no overhead. Decisions are scattered and hard to find. Context is lost when people leave.

---

## Rationale

Option B provides the right tradeoff for a project that will be worked on by multiple contributors over time. The overhead of writing an ADR is low. The cost of not having one -- re-litigating a settled decision or breaking a deliberate constraint -- is high.

The append-only rule is important. Editing a closed ADR to reflect a changed decision hides the fact that the decision changed. A new ADR that supersedes the old one makes the change explicit and traceable.

---

## Consequences

**Positive:**
- Future contributors can understand why the system is built the way it is.
- Decisions that are revisited can reference the original rationale.
- Breaking changes to contracts (MCP tools, config schema) require a new ADR, which creates a natural review gate.

**Negative / risks:**
- ADRs only provide value if they are written. The risk is that significant decisions are made without one. The PR checklist in `docs/CONTRIBUTING.md` includes an ADR check for breaking changes.

---

## Links

- Template: [0000-template.md](0000-template.md)
- Contributing guide: [CONTRIBUTING.md: Decisions and ADRs](../CONTRIBUTING.md)
