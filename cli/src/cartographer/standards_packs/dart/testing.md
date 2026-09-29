# Dart / Flutter Testing

- Test types and locations: unit tests in `test/unit/` (`dart:test`), widget tests in `test/widget/` (`flutter_test`), golden tests in `test/golden/`, integration tests in `integration_test/` (device/emulator, for critical user flows only).
- Test BLoC/Cubit with `bloc_test`. Use `blocTest<MyCubit, MyState>` to assert the sequence of emitted states for a given action. Always `tearDown(() => cubit.close())` to prevent stream leaks.

```dart
blocTest<CartBloc, CartState>(
    'emits updated items when CartItemAdded',
    build: () => CartBloc(MockCartRepository()),
    act: (b) => b.add(CartItemAdded(testItem)),
    expect: () => [CartState(items: [testItem])],
);
```

- Test Riverpod providers with `ProviderContainer(overrides: [...])`. Override with fakes or mocks at the container level — do not use `ref.read` directly in tests. Call `addTearDown(container.dispose)` to clean up.
- Widget tests: mount with `ProviderScope` overrides (Riverpod) or `BlocProvider` overrides (BLoC). Use `tester.pump()` for a single frame, `tester.pumpAndSettle()` when animations complete, and `flushPromises()` for async operations. Never use raw `Future.delayed` in widget tests — it makes tests flaky and slow.
- Prefer hand-written fakes over generated mocks for complex dependencies. Fakes implement the full interface with configurable state (`fetchError`, stored `_users` map). They are more maintainable than mock expectations and catch interface evolution automatically.

```dart
class FakeUserRepository implements UserRepository {
    final _users = <String, User>{};
    Object? fetchError;

    @override
    Future<User?> getById(String id) async {
        if (fetchError != null) throw fetchError!;
        return _users[id];
    }
    // ...
}
```

- Test time-dependent code with `fake_async`. Wrap the test body in `fakeAsync((async) { ... })` and call `async.elapse(Duration(...))` to advance virtual time. This tests timers and debounce logic without sleeping.
- Test names describe behavior: `'returns null when user does not exist'`, `'throws NotFoundException when id is empty string'`. Not: `'test 1'`, `'getUserById works'`.
- Target 80%+ line coverage for business logic (domain layer and state managers). All state transitions must have tests: loading → success, loading → error, and retry paths. Run `flutter test --coverage` in CI and fail below threshold.
- Golden tests: use `matchesGoldenFile('goldens/my_widget.png')` for design-critical components. Run `flutter test --update-goldens` when intentional visual changes are made and commit updated golden files.
