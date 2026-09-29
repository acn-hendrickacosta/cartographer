# Go Code Review

A prioritized checklist for reviewing Go code changes. Run `go vet ./...` and `staticcheck ./...` before manual review.

## CRITICAL — Security (block merge)

- **SQL injection**: Check all `database/sql` calls. String concatenation into a query string (`"SELECT ... WHERE name = '" + name + "'"`) is always wrong — use parameterized queries.
- **Command injection**: Check `os/exec` calls. Never interpolate user input via `sh -c`; pass arguments as a list.
- **Path traversal**: User-controlled file paths must be sanitized with `filepath.Clean` and verified to have the expected prefix.
- **Race conditions**: Shared mutable state (maps, slices, struct fields) accessed from multiple goroutines without a mutex or `sync/atomic` is a data race.
- **Hardcoded secrets**: API keys, passwords, or tokens in source code are a critical finding regardless of whether the file is "internal."
- **Insecure TLS**: `InsecureSkipVerify: true` disables certificate verification — never acceptable in production.
- **`unsafe` package**: Any use of `unsafe` requires explicit justification and must be reviewed carefully.

## CRITICAL — Error Handling (block merge)

- **Ignored errors**: `result, _ := f()` discards the error entirely. If ignoring is intentional, document why.
- **Missing error wrapping**: `return err` without `fmt.Errorf("context: %w", err)` makes errors hard to diagnose. Every error return should add call-site context.
- **Panic for recoverable errors**: `panic(err)` in a function that could return `error` is wrong. Reserve `panic` for truly unrecoverable situations (programmer bugs).
- **Wrong error comparison**: `err == sql.ErrNoRows` breaks if the error is wrapped — use `errors.Is(err, sql.ErrNoRows)`.

## HIGH — Concurrency (should fix)

- **Goroutine leaks**: Goroutines that write to an unbuffered channel with no guarantee of a receiver, or that never check `ctx.Done()`, can leak indefinitely.
- **Missing `WaitGroup`**: Starting goroutines without coordinating their completion means the caller cannot know when work is done or whether it errored.
- **Mutex misuse**: `mu.Lock()` without an immediate `defer mu.Unlock()` is fragile — a panic or early return will leave the mutex locked.
- **Unbuffered channel deadlock**: Sending to an unbuffered channel blocks until a receiver is ready. Ensure the goroutine model guarantees a receiver exists.

## HIGH — Code Quality (should fix)

- **Functions over 50 lines**: Long functions should be decomposed. Exceptions require justification (e.g., a long switch statement that must be together).
- **Nesting depth over 4 levels**: Invert conditions and return early to flatten control flow.
- **Non-idiomatic `if/else`**: Replace `if err != nil { ... } else { ... }` with an early `return` on error.
- **Mutable package-level variables**: Global mutable state makes tests order-dependent and is a source of races.
- **Unused interface abstractions**: An interface with only one implementation (outside of tests) is premature abstraction.

## MEDIUM — Performance (consider fixing)

- **String concatenation in loops**: Use `strings.Builder` or `strings.Join`. `s += part` in a loop is O(n²).
- **Unpreallocated slices**: When the result length is known, use `make([]T, 0, len(input))` to avoid repeated reallocations.
- **N+1 queries**: A database call inside a loop that iterates over query results is a classic N+1 problem — batch instead.

## MEDIUM — Best Practices (note)

- **Context not first**: `context.Context` must be the first parameter of any function that accepts one.
- **Tests not table-driven**: Functions with multiple input/output scenarios should use table-driven tests.
- **Error messages**: Error strings should be lowercase and not end with punctuation (they are often concatenated).
- **Package names**: Must be short, lowercase, no underscores. `httphandler` or `jsonparser` are wrong; use `handler` and `parser`.
- **`defer` in a loop**: `defer` in a loop does not execute until the function returns, not at the end of each iteration — use a closure or extract a helper.

## CI Commands

```bash
go vet ./...
staticcheck ./...
golangci-lint run
go build -race ./...
go test -race ./...
govulncheck ./...
```

## Approval Criteria

| Verdict | Condition |
|---------|-----------|
| Approve | No CRITICAL or HIGH issues |
| Approve with notes | MEDIUM issues only |
| Block | Any CRITICAL or HIGH issue |
