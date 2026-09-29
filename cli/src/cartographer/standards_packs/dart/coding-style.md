# Dart / Flutter Coding Style

- Run `dart format --set-exit-if-changed .` in CI. All Dart files must be formatted. Formatting is not a review concern — the tool decides.
- Prefer `final` for local variables and `const` for compile-time constants. Use `const` constructors wherever all fields are `final`. Return `List.unmodifiable()` and `Map.unmodifiable()` from public APIs that return collections — callers must not mutate returned collections.
- Naming: `camelCase` for variables, parameters, and named constructors; `PascalCase` for classes, enums, typedefs, and extensions; `snake_case` for file and library names; `SCREAMING_SNAKE_CASE` for top-level `const` declarations; `_leadingUnderscore` for private members.
- Avoid `!` (the bang/force-unwrap operator). Prefer null-aware operators (`?.`, `??`), Dart 3 pattern matching (`if (value case var v?)`), or early-return null guards. Reserve `!` only for places where a null value is a programming error and crashing is correct.

```dart
// BAD — crashes if user is null
final name = user!.name;

// GOOD
final name = user?.name ?? 'Unknown';

// GOOD — Dart 3 pattern matching (exhaustive, compiler-checked)
final name = switch (user) {
    User(:final name) => name,
    null => 'Unknown',
};
```

- Avoid `late` unless initialization before first access is guaranteed (e.g., in `initState()` before any user interaction). Prefer nullable or constructor initialization.
- Use sealed classes to model closed state hierarchies. Always switch on sealed types exhaustively — no `default` or wildcard cases. The compiler enforces completeness.
- Error handling: use specific `on ExceptionType catch (e)` clauses — never bare `catch (e)`. Never catch `Error` subtypes — they signal programming bugs, not recoverable conditions.
- Futures: always `await` them or call `unawaited()` to signal intentional fire-and-forget. Use Dart 3 record destructuring + `Future.wait` extension for concurrent operations: `final (users, orders) = await (fetchUsers(), fetchOrders()).wait`.
- Check `context.mounted` before using `BuildContext` after any `await` in a `StatefulWidget` (Flutter 3.7+). Stale context causes crashes in background-completed async callbacks.
- Use `package:` imports throughout — no relative imports (`../`) for cross-feature or cross-layer code. Order imports: `dart:` → external `package:` → internal `package:`.
- Never manually edit generated files (`.g.dart`, `.freezed.dart`, `.gr.dart`). Pick one strategy per project — either commit generated files or gitignore them — and apply it consistently.
