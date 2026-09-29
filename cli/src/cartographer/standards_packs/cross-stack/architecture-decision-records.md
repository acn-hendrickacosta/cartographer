# Architecture Decision Records

- Record significant architectural decisions as numbered ADR files in `docs/adr/`.
  Significant means: framework or library choice, database selection, API design
  strategy, authentication approach, deployment model, or any other choice where
  understanding the rationale matters six months later.
- Trivial decisions (variable naming, code formatting, minor refactors) do not need
  ADRs.
- Use the lightweight Nygard format. Each ADR includes: context (the situation and
  constraints that motivated the decision), the decision itself, alternatives that
  were considered and why they were rejected, and consequences (both positive and
  negative trade-offs).
- The rationale matters more than the decision. Future developers need to know what
  was weighed, not just what was chosen. An ADR that says "we just picked it" provides
  no value.
- Keep ADRs short. A well-written ADR is readable in two minutes. If the context
  section exceeds ten lines, it is too long.
- Write in present tense: "We use PostgreSQL" not "We will use PostgreSQL."
- Assign a sequential number (`ADR-0001`, `ADR-0002`) and use a descriptive filename:
  `0001-use-postgres-as-primary-database.md`.
- Maintain a `docs/adr/README.md` index with a table of all ADRs, their status,
  and their dates.
- ADR lifecycle: `proposed` (under discussion), `accepted` (in effect), `deprecated`
  (no longer relevant), `superseded by ADR-NNNN` (replaced by a newer decision).
  Superseded ADRs must link to their replacement.
- When a decision is reversed or replaced, create a new ADR rather than editing the
  old one. History is valuable; the original context should remain readable.
- Record past decisions retroactively when they surface during development ("why did
  we choose X?"). Mark the original date in the context section so readers know it
  was recorded after the fact.
- Flag PRs that introduce architectural changes without a corresponding ADR. The PR
  may be correct, but the reasoning should be persisted somewhere more durable than
  a PR comment.
