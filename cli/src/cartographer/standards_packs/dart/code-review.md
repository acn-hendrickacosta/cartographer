# Flutter / Dart Code Review Criteria

## Critical — Block Approval

- **Business logic in widgets**: widgets are purely presentational. Domain rules, data transformations, and API calls in widget `build()` methods or event handlers violate the architecture and make testing impossible.
- **`!` (bang operator) without justification**: crashes at runtime when the value is null. Use `?.`, `??`, `if-case`, or `guard` patterns. Document unavoidable `!` uses with a `// SAFETY:` comment.
- **Bare `catch (e)` without `on` clause**: catches Dart `Error` subtypes (programming bugs) alongside `Exception` (expected failures). Always specify the exception type.
- **Hardcoded secrets or API keys in source**: any credential in Dart source or committed config files is a security breach.
- **Sensitive data in `SharedPreferences`**: tokens, passwords, and PII belong in `flutter_secure_storage`. `SharedPreferences` is unencrypted.
- **`localStorage` / unencrypted persistence for tokens**: same as above — use platform-secure storage.
- **SQL injection via string interpolation**: `rawQuery("... = '$input'")`. Use parameterized queries with `whereArgs`.
- **WebView with unvalidated URL or JavaScript enabled by default**: validates navigation requests and disables JS unless the feature requires it.
- **Ignoring `Future` return values without `unawaited()`**: fire-and-forget without explicit intent hides errors and makes async flow unpredictable.

## High — Strong Recommendation to Fix

- **Private builder methods returning `Widget`**: extract to named `StatelessWidget` classes. Builder methods rebuild with the parent — widget classes enable `const` and scoped rebuild optimization.
- **Missing `const` constructor where all fields are final**: missed performance optimization. Add `const` to the constructor and call sites.
- **`context.mounted` not checked after `await`**: causes crashes when the widget is disposed between the async operation starting and completing.
- **`late` overuse**: `late String id` that is not initialized in the constructor or `initState` defers the null error to the first access. Use nullable or required constructor parameters.
- **State mutation in `build()`**: calling `setState`, `emit`, or Riverpod mutations inside `build()` causes infinite rebuild loops.
- **`ListView(children: [...])` with large or dynamic lists**: creates all items at once, causing jank. Use `ListView.builder` for 20+ items.
- **Missing cleanup for subscriptions**: `Stream.listen()` results stored without cancellation in `dispose()`. Prevents garbage collection and causes callbacks on disposed widgets.
- **Bloc/Cubit not closed**: `cubit.close()` not called in `dispose()` or `tearDown()`. Leaks the stream subscription and timer resources.
- **`UniqueKey` in `build()`**: forces the widget to be recreated on every rebuild. Only use `UniqueKey` when forced recreation is the explicit intent.
- **Missing error handling in async actions**: async operations without try/catch leave the UI stuck in a loading state and swallow errors silently.

## Medium

- `analysis_options.yaml` missing strict mode (`strict-casts: true`, `strict-inference: true`, `strict-raw-types: true`).
- `print()` in production code — use `dart:developer` `log()` or a logging package with log levels.
- Hardcoded colors or font sizes — use `Theme.of(context).colorScheme` and `Theme.of(context).textTheme`.
- Routes defined as magic strings — centralize route paths as constants or an enum.
- Missing `semanticLabel` on images and icons used as interactive elements.
- `pubspec.yaml` with version constraints that are too broad or pinned to exact versions without justification.

## Approval Criteria

CRITICAL and HIGH findings block approval. Fix or document an accepted exception with written justification before merging.
