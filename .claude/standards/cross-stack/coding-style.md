# Coding Style

- Favor the simplest solution that actually works (KISS). Optimize for clarity over
  cleverness. Avoid premature optimization.
- Extract repeated logic rather than copy-pasting it (DRY). Introduce an abstraction
  when repetition is real, not when it is speculative.
- Do not build features or abstractions before they are needed (YAGNI). Start simple;
  refactor when the pressure is real, not when it is imagined.
- Prefer immutable data over mutation. Return new objects with changes applied rather
  than modifying shared state in place. Mutation causes hidden side effects, makes
  debugging harder, and breaks concurrent safety.
- Keep files small and cohesive: 200–400 lines is typical; 800 lines is the soft
  maintainability ceiling. Source files that exceed 800 lines should have a documented
  reason — test files, generated code, and vendored files may legitimately be larger.
  Organize by feature or domain rather than by type.
- Keep functions focused. Under 50 lines is a useful target. A function that does more
  than one thing is a candidate to split.
- Names should say what a thing holds or does without needing a comment to explain.
  Boolean names should read as claims. Constants and types should be visually distinct
  from ordinary values per your language's convention.
- Handle errors explicitly at every level. Never silently swallow an exception. Provide
  user-friendly messages in UI-facing code and log detailed error context on the server
  side.
- Validate all input at system boundaries with a schema or explicit checks. Fail fast
  with clear error messages. Never trust external data — API responses, user input, and
  file content all count as untrusted.
- Avoid deep nesting. Prefer early returns over nested conditionals. More than four
  levels of indentation is a signal to refactor.
- Use named constants for meaningful thresholds, delays, and limits. A magic number
  that appears more than once, or whose meaning is not obvious, should become a named
  constant.
- Comments should explain why, not what. The code already shows what; the comment
  should explain the reasoning that is not visible from the code alone.
- Async calls that can run in parallel should run in parallel. Sequential awaits on
  independent operations waste latency.
