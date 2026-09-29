# Dart / Flutter Patterns

- Follow Clean Architecture layer boundaries: `domain/` (pure Dart — no Flutter, no external packages), `data/` (implements domain interfaces, maps DTOs to domain models), `presentation/` (widgets + state management). Domain must not import `package:flutter` or any data-layer package.
- Define repository interfaces in `domain/`. The interface uses domain model types — not DTOs or database models. Implement repositories in `data/`, coordinating remote and local data sources with explicit cache-or-fetch logic.

```dart
abstract interface class UserRepository {
    Future<User?> getById(String id);
    Stream<List<User>> watchAll();
    Future<void> save(User user);
}
```

- Use case classes have a single public `call()` method. Inject the repository via constructor. Presentation calls use cases, not repositories directly. This keeps business rules out of both widgets and data access code.
- Use sealed classes for async state and domain states. Switch on them exhaustively — the compiler enforces completeness when you add a new case. Boolean flag combinations (`isLoading && hasError`) allow impossible states; sealed types don't.

```dart
sealed class AsyncState<T> {
    const AsyncState();
}
final class Loading<T> extends AsyncState<T> { const Loading(); }
final class Success<T> extends AsyncState<T> { const Success(this.data); final T data; }
final class Failure<T> extends AsyncState<T> { const Failure(this.error); final Object error; }
```

- State management: choose BLoC/Cubit for event-driven state with explicit transitions, or Riverpod for declarative provider graphs with auto-dispose. Pick one and apply it consistently across the feature.
- Pinia (BLoC): `Cubit` for simple state, `Bloc` for event-driven. State classes must be `@immutable`. Use `copyWith()` for state updates. Use `blocTest` for testing all state transitions.
- Riverpod: `@riverpod` code generation for providers. Use `Notifier`/`AsyncNotifier` for mutable state with business logic. Derived state uses `ref.watch` — do not store derived values redundantly. Use `ProviderContainer` with `overrides` for unit tests.
- Extract widgets to separate `StatelessWidget` classes — never private builder methods returning `Widget`. Widget classes enable `const` constructors, element reuse, and scoped rebuilds. Builder methods rebuild the entire parent.
- Use GoRouter for navigation. Centralize auth redirects in `GoRouter.redirect` with a `GoRouterRefreshStream` tied to auth state changes. Pass type-safe route parameters via `state.pathParameters`.
- Freeze boilerplate with `freezed`: `@freezed class UserState with _$UserState { ... }`. Gives you `copyWith`, `==`, `hashCode`, `toString`, and JSON serialization with `fromJson`/`toJson` for free.
