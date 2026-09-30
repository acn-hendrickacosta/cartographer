# Review

- A reviewer's job is to find correctness problems first, then reuse and
  simplification, then style. Do not spend the first pass on formatting.
- State the concrete failure scenario for anything flagged as a bug: what input or
  state triggers it, and what goes wrong. A vague "this looks risky" is not a
  finding.
- Prefer fewer, high-confidence comments over an exhaustive list of low-confidence
  ones. A review that flags everything is as useless as one that flags nothing.
- Approve changes that are correct and reasonably scoped even if you would have
  written them differently. Style disagreements are not blockers unless a
  documented convention says otherwise.
- Do not ask for speculative generalization. A change should be reviewed against
  what it actually needs to do, not against imagined future requirements.

## Review Categories

Apply the following checklist across seven dimensions:

| Category | What to Check |
|---|---|
| **Correctness** | Logic errors, off-by-ones, null handling, edge cases, race conditions |
| **Type Safety** | Type mismatches, unsafe casts, `any` usage, missing generics |
| **Pattern Compliance** | Naming, file structure, error handling, imports match project conventions |
| **Security** | Injection, auth gaps, secret exposure, SSRF, path traversal, XSS |
| **Performance** | N+1 queries, missing indexes, unbounded loops, memory leaks |
| **Completeness** | Missing tests, missing error handling, incomplete migrations |
| **Maintainability** | Dead code, magic numbers, deep nesting, unclear naming |

## Severity Levels

| Level | Meaning | Action |
|---|---|---|
| **CRITICAL** | Security vulnerability or data loss risk | Block — must fix before merge |
| **HIGH** | Bug or logic error likely to cause issues | Should fix before merge |
| **MEDIUM** | Code quality issue or unexplained exception to conventions | Consider fixing |
| **LOW** | Style nit or minor suggestion | Optional |

## Quality Triggers

Before marking code ready to review, authors should verify: functions are under
50 lines, source files are under 800 lines (or have a documented reason to be
larger), nesting depth is at most 4 levels, no debug statements or dead
`console.log` calls, and new functionality has test coverage.

## Security Review Triggers

Give extra scrutiny to any change that touches authentication or authorization,
user input handling, database queries, file system operations, external API
calls, cryptographic operations, or payment logic. These areas warrant a full
security lens even if the change appears minor.
