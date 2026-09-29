# Kotlin Patterns

- Prefer `val` over `var` everywhere. Mutability is a deliberate choice that requires justification, not the default.
- Use `data class` for value objects that need structural equality, `copy()`, and `componentN` destructuring. Use `value class` (`@JvmInline`) for typed wrappers that enforce domain constraints at zero runtime cost.
- Model domain states with `sealed class` or `sealed interface`. Exhaustive `when` expressions on sealed types are compiler-checked — no `else` needed when all cases are covered. Never use nullable Boolean or string flags to represent state.

```kotlin
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Failure(val error: Throwable) : Result<Nothing>()
}
```

- Use scope functions appropriately: `let` for null-safe chaining, `apply` for builder-style initialization, `also` for logging/debugging side effects, `run`/`with` to compute a value from an object. Do not nest scope functions — extract to a named function instead.
- Prefer extension functions over utility classes. Name them for what they do, not the class they extend. Keep extension functions in files named by the type they extend (`StringExtensions.kt`).
- Use `require(condition) { "message" }` for precondition checks on function arguments and `check(condition) { "message" }` for invariant checks. Both throw appropriate exceptions with the message on failure.
- Use `runCatching { ... }.fold(onSuccess = ..., onFailure = ...)` for wrapping calls that can throw into `Result`. Prefer returning `Result<T>` over throwing exceptions across API boundaries.
- Prefer named arguments for functions with more than two parameters of the same type. This eliminates silent argument-order bugs.
- Delegate lazy initialization with `by lazy { ... }` for expensive properties computed once. Use `by Delegates.observable(initial) { _, old, new -> ... }` to react to property changes without explicit setter logic.
- Use Kotlin's collection builder functions (`buildList`, `buildMap`, `buildSet`) instead of mutable collections that are immediately returned. Sequences (`asSequence()`) are appropriate for large collections with multiple transformation steps to avoid intermediate allocations.
