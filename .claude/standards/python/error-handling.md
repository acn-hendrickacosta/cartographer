# Python: Error handling

- Raise specific exception types with messages that state what was expected and what was found. `ValueError("expected a positive integer, got -3")` is useful. `ValueError("invalid input")` is not.
- Do not catch broad exceptions (`except Exception`, `except BaseException`) except at a boundary where you must convert failures into a user-facing report — a CLI command, an HTTP handler, a hook script. At those boundaries, log the full traceback and emit a clean message to the user.
- Use custom exception classes when callers need to distinguish failure reasons. Name them after what went wrong, not after the module: `TenantIsolationViolation` beats `CartographerError`.
- Do not swallow exceptions silently. If you catch an exception and cannot handle it, re-raise it. An exception that disappears leaves a system in an unknown state.
- Use `contextlib.suppress` only for truly ignorable errors (e.g., `FileNotFoundError` on a best-effort cleanup). Add a comment explaining why the error is ignorable.
- Represent expected failure states as return values or typed results where callers will routinely check them. Reserve exceptions for conditions a caller should not ignore.
- Avoid exception-as-flow-control: do not use `try/except` as an if/else for non-exceptional conditions.
