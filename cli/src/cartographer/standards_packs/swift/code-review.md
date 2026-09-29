# Swift Code Review Criteria

## Critical — Block Approval

- **Force unwrap (`!`) in production code**: crashes at runtime when the value is nil. Use `guard let`, `if let`, optional chaining (`?.`), or `?? throw MyError.nilValue`. Force unwrap is only acceptable in tests or with a `// SAFETY:` comment explaining why nil is impossible.
- **`try!` without justification**: crashes if the throwing function fails. Use `do { try ... } catch { ... }` with meaningful error handling. `try!` is acceptable only in test setup or for operations that genuinely cannot fail at that call site, documented with a comment.
- **`as!` force cast without a type check**: crashes if the type is wrong. Use `as?` with a guard or conditional binding.
- **Hardcoded secrets** (API keys, tokens, signing keys) in source code.
- **Sensitive data in `UserDefaults`**: secrets belong in Keychain, not `UserDefaults`. `UserDefaults` is unencrypted and accessible to other tools on the device.
- **ATS disabled globally** (`NSAllowsArbitraryLoads = true` in `Info.plist`): disables HTTPS enforcement for all connections. Use per-domain exceptions with documented justification if a specific host requires HTTP.
- **SQL injection**: string interpolation in SQLite/GRDB queries. Use parameterized queries.
- **Path traversal**: user-controlled paths used in file operations without normalization and sandbox-prefix validation.
- **Empty `catch` block** or `catch { }` that discards errors silently.
- **`try?` discarding errors without logging**: silent failure is worse than a crash in most cases. At minimum, log the error.

## High — Strong Recommendation to Fix

- **Data races**: mutable state shared between concurrent tasks without actor isolation, `Sendable` conformance, or synchronization. Enable Thread Sanitizer (`-sanitize=thread`) to catch these.
- **`@Sendable` violation**: non-`Sendable` type captured in a `@Sendable` closure or passed across actor boundaries. This is a data race waiting to happen.
- **Blocking calls on `@MainActor`**: `Thread.sleep`, `DispatchQueue.sync { }`, or any blocking I/O on the main actor freezes the UI. Use `await` and async APIs.
- **Unstructured `Task { }` without cancellation handling**: tasks started in `onAppear` or `init` that are never cancelled when the owning view/actor is deallocated cause resource leaks.
- **Actor reentrancy bugs**: code that assumes state is unchanged after an `await` inside an actor method. An `await` inside an actor method is a suspension point where other callers can modify state.
- **Missing `@MainActor` for UI updates**: updating `@State`, publishing to ObservableObject, or calling `UIView.setNeedsLayout` from a background thread causes UI rendering bugs or crashes.
- **Retain cycles in closures**: `[weak self]` is required when a closure is stored and captures `self`. Missing `weak` creates a reference cycle that leaks the object.
- **`delegate` properties without `weak`**: strong delegate creates a retain cycle between the delegating object and its delegate. Declare delegate properties as `weak`.
- **Large value type copies**: value types with large stored arrays being passed by value in hot paths. Use `class` or `inout` for large mutable types.

## Medium

- Functions exceeding ~50 lines — extract logic.
- Nesting exceeding 4 levels — flatten with `guard` and early returns.
- `Any` or `AnyObject` at API boundaries where a protocol or generic would provide type safety.
- Missing `Equatable`, `Hashable`, `Codable`, or `Sendable` conformance on types that clearly need them.
- `print()` calls in production code — use `os_log` or `Logger` with appropriate subsystem and category.
- Missing `private` or `internal` access control on types and members — default is `internal`, which may expose too much.

## Approval Criteria

CRITICAL and HIGH findings block approval. Fix or document an accepted exception before merging.
