# SwiftUI Patterns

- Use `@Observable` (Observation framework) for all new view models. It tracks property-level changes so only views reading a changed property re-render. Do not use `ObservableObject`, `@Published`, `@StateObject`, or `@EnvironmentObject` in new code.
- Own view models at the correct level. The view that creates the view model holds it in `@State`. Views receiving a view model from a parent do not need a wrapper — pass it directly. Use `@Bindable` for two-way binding to `@Observable` properties.

```swift
struct ItemListView: View {
    @State private var viewModel: ItemListViewModel  // this view owns the VM

    var body: some View {
        List(viewModel.items) { item in ItemRow(item: item) }
            .task { await viewModel.load() }
    }
}
```

- Inject dependencies via `@Environment(MyType.self)` using the Observation framework. Replace legacy `@EnvironmentObject` with `.environment(myObject)` at the root and `@Environment(MyType.self) private var myObject` at the leaf.
- Break views into small, focused structs. When state changes, only the subview reading that state re-renders. Helper methods that return views (`private func buildHeader() -> some View`) do not participate in this optimization — extract to named subview structs.
- Never perform I/O, network calls, or heavy computation inside `body`. Use `.task { }` for async work — it cancels automatically when the view disappears. Use `.task(id:) { }` to restart async work when an input changes.
- Use `NavigationStack` with a `NavigationPath` and an `enum Destination: Hashable` for type-safe programmatic navigation. Centralize routing in an `@Observable Router` injected via environment.

```swift
enum Destination: Hashable {
    case detail(Item.ID)
    case settings
}

@Observable final class Router {
    var path = NavigationPath()
    func navigate(to destination: Destination) { path.append(destination) }
}
```

- Use `LazyVStack` / `LazyHStack` in `ScrollView` for large collections — they create views only when visible. In `List` and `ForEach`, always use stable identifiers (`id: \.id`), never array indices.
- Minimize expensive modifiers in scroll views: `.shadow()`, `.blur()`, and `.mask()` trigger offscreen rendering. Measure with Instruments before applying them to list rows.
- For views with expensive `body` computations that receive the same data, conform to `Equatable` and use `EquatableView` to skip re-renders when inputs have not changed.
- Use `#Preview("Description") { }` macros with injectable mock data. Multiple previews covering loading, empty, error, and populated states catch visual regressions without running the full app.
- Avoid `AnyView` type erasure — it prevents SwiftUI from optimizing the view tree. Use `@ViewBuilder` functions or `Group { }` for conditional views instead.
