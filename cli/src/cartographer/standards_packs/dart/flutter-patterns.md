# Flutter Patterns

- Extract widgets to separate `StatelessWidget` (or `ConsumerWidget`) classes — never private builder methods returning `Widget`. Widget classes enable `const` constructors, preserve element identity during rebuilds, stop rebuild propagation, and allow the framework to cache elements. Builder methods rebuild with the parent on every state change.
- Use `const` constructors everywhere possible. `const` widgets are never rebuilt and can be shared across the widget tree. A missing `const` in a widget that qualifies is a missed optimization.
- Scope rebuilds as narrowly as possible. In Riverpod: extract the widget that reads a provider into a small `ConsumerWidget`. In BLoC: use `BlocSelector` or `buildWhen` to limit rebuilds to relevant state changes. In `setState`: localize it to the smallest subtree.

```dart
// BAD — entire page rebuilds on every counter change
class CounterPage extends ConsumerWidget {
    @override
    Widget build(BuildContext context, WidgetRef ref) {
        final count = ref.watch(counterProvider); // rebuilds everything
        return Scaffold(body: Column(children: [const ExpensiveHeader(), Text('$count')]));
    }
}

// GOOD — only the count display rebuilds
class _CounterDisplay extends ConsumerWidget {
    const _CounterDisplay();
    @override
    Widget build(BuildContext context, WidgetRef ref) {
        return Text('${ref.watch(counterProvider)}');
    }
}
```

- Check `context.mounted` before using `BuildContext` after any `await`. Stale context causes crashes and "Using context after async gap" analyzer warnings.
- Use `ListView.builder` and `GridView.builder` for long or dynamic lists — they create items lazily. Use concrete `ListView(children: [...])` only for small, static lists.
- Wire global error handling in `main()`: set `FlutterError.onError` for framework errors (build, layout) and `PlatformDispatcher.instance.onError` for async errors outside Flutter. Customize `ErrorWidget.builder` in release builds to show a friendly error UI instead of a red screen.
- Dio is the standard HTTP client. Configure `connectTimeout` and `receiveTimeout`. Add an auth interceptor that reads tokens from secure storage and injects the `Authorization` header. Handle 401 responses with a single retry after token refresh — use an `_isRetry` flag in `requestOptions.extra` to prevent infinite retry loops.
- Navigate with GoRouter. Define an `enum Destination: Hashable` for type-safe destinations. Wire a `GoRouterRefreshStream(authStream)` to `refreshListenable` so navigation re-evaluates the auth redirect whenever auth state changes.
- Colors and text styles come from `Theme.of(context).colorScheme` and `Theme.of(context).textTheme`. Never hardcode colors or font sizes inline. Spacing uses consistent tokens or constants, not magic numbers.
- Declare `Semantics` labels on interactive elements that lack clear text. Set `semanticLabel` on images. Use `ExcludeSemantics` for decorative-only elements. Ensure touch targets are at least 48×48 points.
