# Go Coding Style

- Run `gofmt` and `goimports` on all `.go` files — no style debates, no exceptions. Configure them as post-save hooks in your editor and as a CI gate.
- Accept interfaces, return concrete structs. Functions that accept interface parameters are easier to test and compose; returning concrete types avoids premature abstraction.
- Keep interfaces small — 1 to 3 methods. Large interfaces are hard to satisfy and signal that the abstraction is wrong. Compose small interfaces instead.
- Always wrap errors with context using `fmt.Errorf("failed to create user: %w", err)`. Bare `return err` loses the call site and makes debugging harder. The `%w` verb enables `errors.Is` and `errors.As` unwrapping.
- Never ignore errors with `_`. If discarding an error is genuinely safe, document why in a comment. `_ = writer.Close()` is acceptable only when cleanup is best-effort and errors are logged elsewhere.
- Use `errors.Is(err, target)` to compare errors — not `err == target`. Use `errors.As(err, &target)` to extract typed errors. Direct equality checks break when errors are wrapped.
- Design types so their zero value is immediately usable without initialization. `sync.Mutex`, `bytes.Buffer`, and `sync.WaitGroup` are canonical examples.
- Return early on errors and preconditions. Keep the happy path unindented. Deeply nested `if/else` chains are a sign to restructure.
- Never use `panic` for recoverable errors — return `error` instead. Reserve `panic` for programmer bugs (impossible states) and startup validation where recovery is not meaningful.
- Pass `context.Context` as the first parameter to functions that do I/O, call other services, or need cancellation support. Never store context in a struct field.
- Package names should be short, lowercase, and without underscores or mixed case: `user`, `http`, `json` — not `userService`, `http_handler`, or `JsonParser`.
- Avoid mutable package-level variables. Use constructor functions and dependency injection to make state explicit and testable.
- Use named result values sparingly; avoid naked returns in functions longer than a few lines. Naked returns in long functions obscure what is being returned.
- Be consistent with pointer vs. value receivers on a type. Mixing them without justification confuses the zero-value rule and is a common source of subtle bugs.
