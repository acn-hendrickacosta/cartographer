# Swift Coding Style

- Enforce SwiftFormat and SwiftLint in CI. SwiftFormat handles deterministic formatting; SwiftLint enforces idioms and architectural rules. Both must pass on every PR — formatting disagreements are resolved by the tools, not in reviews.
- Prefer `let` over `var`. Change to `var` only when the compiler requires it. Immutability is the default; mutability is an explicit choice.
- Default to `struct` with value semantics. Use `class` only when you need reference semantics, identity equality, or Objective-C interoperability. Classes require explicit justification.
- Follow Apple's API Design Guidelines: optimize for clarity at the point of use, omit needless words, name for roles not types (`remove(at:)` not `removeElement(atIndex:)`).
- Use typed throws (Swift 6+): `func load() throws(NetworkError) -> Data`. This makes error handling exhaustive — callers can `switch` on the error type without `as?` casts. Untyped `throws` is still valid for generic/library code where the error set is open.
- Mark value types (structs, enums) as `Sendable` when they cross actor boundaries. The compiler enforces this in Swift 6 strict concurrency mode. For reference types, use actors instead of manual locking.
- Use structured concurrency (`async`/`await`, `Task`, `async let`, `TaskGroup`) for all concurrent work. Avoid `DispatchQueue`, `OperationQueue`, and completion handlers in new code — they do not participate in Swift's structured concurrency model.
- Limit function length to ~30 lines. Extract complex logic to named helper methods or standalone functions. Deeply nested closures should be extracted to named methods or broken up with `async let`.
- Avoid force unwrap (`!`) and `try!` in production code. Use `guard let ... else { throw/return }` or optional chaining (`?.`). Force try/force unwrap is acceptable only in tests or in a `// SAFETY:` comment explaining why nil/throw is impossible.
