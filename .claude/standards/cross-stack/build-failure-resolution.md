# Build Failure Resolution

- Fix build failures incrementally, one error at a time. Attempting to fix everything
  at once without verifying each fix often introduces new errors faster than old ones
  are resolved.
- Read error messages fully before touching code. The root cause is often stated
  explicitly; acting on a symptom (e.g., a missing import) without understanding what
  caused it (e.g., a renamed export) produces a different error on the next run.
- Group errors by file and fix in dependency order. Errors in shared types or utility
  modules cascade into many consumers. Fixing the source of a type error removes
  multiple downstream errors at once.
- After each fix, re-run the build to verify the error is gone and no new errors were
  introduced. A fix that resolves one error and introduces two others is not progress.
- Stop and escalate if the same error persists after three targeted attempts, if a fix
  introduces more errors than it resolves, or if the root cause requires architectural
  changes beyond the scope of a build fix.

## Common Failure Patterns and Responses

| Situation | Response |
|---|---|
| Missing module or import | Verify the package is installed and the import path is correct before writing code |
| Type mismatch | Read both type definitions; narrow the type at the correct layer rather than casting |
| Circular dependency | Trace the import cycle; extract shared types or utilities to break it |
| Version conflict | Check lock files and dependency manifests for version constraints |
| Build tool misconfiguration | Read the config file; compare with working defaults or recent working state |

## Guardrails

- Do not refactor while fixing a build. Behavioral changes mixed with structural fixes
  obscure whether a remaining error is new or pre-existing.
- Do not suppress type errors with casts or `@ts-ignore` as a build fix. Type errors
  exist because the types are wrong; suppressing them hides real bugs.
- If missing dependencies are the cause, install them through the project's package
  manager and commit the updated lock file rather than manually modifying manifests.
