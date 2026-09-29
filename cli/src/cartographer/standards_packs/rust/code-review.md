# Rust Code Review

A prioritized checklist for reviewing Rust code changes. Run `cargo clippy -- -D warnings`, `cargo fmt --check`, and `cargo test` before manual review.

## CRITICAL — Safety (block merge)

- **`unwrap()`/`expect()` in production paths**: Every `.unwrap()` or `.expect()` in non-test code is a potential panic. Use `?` or handle the error explicitly.
- **`unsafe` without justification**: Every `unsafe` block must have a `// SAFETY:` comment documenting all invariants that make it sound. Absence of a safety comment is grounds for blocking.
- **SQL injection**: String interpolation into SQL queries is never acceptable — use parameterized queries (sqlx `.bind()`, diesel, sea-orm).
- **Command injection**: User-controlled input must not be interpolated into `std::process::Command` shell arguments.
- **Path traversal**: User-controlled paths must be canonicalized and verified to have the expected base prefix.
- **Hardcoded secrets**: API keys, passwords, or tokens in source code are a critical finding.
- **Insecure deserialization**: Deserializing untrusted data without size limits can enable denial-of-service or worse.

## CRITICAL — Error Handling (block merge)

- **Silenced errors**: `let _ = result;` on a `Result` or `#[must_use]` type discards the error entirely. The value must be handled or explicitly documented as intentionally ignored.
- **Missing error context**: `return Err(e)` without `.context()` or `.map_err()` loses call-site information. Add context at every propagation point.
- **Panic for recoverable errors**: `panic!()`, `todo!()`, or `unreachable!()` in production paths must not be used for error cases — use `Result`.
- **`Box<dyn Error>` in libraries**: Libraries should use `thiserror` to define typed, matchable error enums. `Box<dyn Error>` prevents callers from handling specific variants.

## HIGH — Ownership and Lifetimes (should fix)

- **Unnecessary cloning**: `.clone()` to satisfy the borrow checker without understanding the root cause masks a design issue. Investigate whether the data model needs restructuring.
- **`String` instead of `&str`**: Functions taking `String` when they only need to read the value should take `&str` or `impl AsRef<str>`.
- **`Vec<T>` instead of `&[T]`**: Functions taking `Vec<T>` when they only need to iterate should take `&[T]`.
- **Lifetime over-annotation**: Explicit lifetime annotations where the elision rules apply add noise without clarity. Simplify where the compiler does not require them.

## HIGH — Concurrency (should fix)

- **Blocking in async context**: `std::thread::sleep`, synchronous `std::fs`, or any blocking call inside `async fn` blocks the executor thread. Use `tokio::time::sleep`, `tokio::fs`, and `tokio::task::spawn_blocking` for CPU-bound work.
- **Unbounded channels**: `tokio::sync::mpsc::unbounded_channel()` and `std::sync::mpsc::channel()` have no backpressure. Justify their use or switch to a bounded channel.
- **`Mutex` poisoning ignored**: `.lock().unwrap()` panics if another thread panicked while holding the lock. Use `.lock().expect("mutex poisoned")` and ensure poisoning is handled or impossible.
- **Missing `Send`/`Sync` bounds**: Types shared across threads must implement `Send` and `Sync`. Check that generic parameters have these bounds where required.
- **Wildcard match on business enums**: `_ =>` in a `match` on an application-domain enum hides the impact of adding new variants. Use exhaustive matching.

## HIGH — Code Quality (should fix)

- **Functions over 50 lines**: Decompose into well-named helper functions.
- **Nesting depth over 4 levels**: Use early returns, `?`, and helper functions to flatten.
- **Dead code**: Unused functions, imports, and variables that are not caught by the compiler should be removed.

## MEDIUM — Performance (consider fixing)

- **Unnecessary allocation in hot paths**: `to_string()`, `to_owned()`, and `format!()` allocate. Use borrowed forms where possible.
- **Missing `with_capacity`**: `Vec::new()` when the final size is known should be `Vec::with_capacity(n)`.
- **Excessive cloning in iterators**: `.cloned()` or `.clone()` inside iterator chains often signals a borrowing issue worth resolving at the data model level.
- **N+1 queries**: Database calls inside loops that iterate over query results need to be batched.

## MEDIUM — Best Practices (note)

- **Suppressed Clippy warnings**: `#[allow(clippy::...)]` without a justification comment should be challenged.
- **Public API without docs**: `pub` items (functions, types, constants) missing `///` documentation make the API harder to use and generate poor rustdoc output.
- **`format!()` for simple concatenation**: Use `push_str`, `concat!`, or `+` for simple string concatenation — `format!` allocates unconditionally.
- **Derive order**: Follow `Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize` consistently across the codebase.

## CI Commands

```bash
cargo clippy -- -D warnings
cargo fmt --check
cargo test
cargo audit
cargo deny check   # If deny.toml is present
```

## Approval Criteria

| Verdict | Condition |
|---------|-----------|
| Approve | No CRITICAL or HIGH issues |
| Approve with notes | MEDIUM issues only |
| Block | Any CRITICAL or HIGH issue |
