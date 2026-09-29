# Swift Design Patterns

- Define small, focused protocols — one protocol per external concern. A `FileReading` protocol and a `FileWriting` protocol are better than one `FileAccessing` "god protocol" with ten methods. Small protocols are easier to mock, compose, and reason about.
- Add `Sendable` conformance to protocols intended for use across actor boundaries. Non-`Sendable` protocol types cannot be passed to actors without a compiler error in strict concurrency mode.
- Use protocol extensions to provide default implementations. This enables optional protocol requirements without the `@objc optional` dance and keeps conforming types lean.

```swift
public protocol Logging: Sendable {
    var logger: Logger { get }
}
extension Logging {
    var logger: Logger { Logger(subsystem: "app", category: String(describing: Self.self)) }
}
```

- Inject dependencies via constructor parameters with default values pointing to production implementations. Tests inject mocks; production callers use defaults without any explicit configuration.

```swift
public actor SyncManager {
    private let fileSystem: FileSystemProviding
    private let fileAccessor: FileAccessorProviding

    public init(
        fileSystem: FileSystemProviding = DefaultFileSystemProvider(),
        fileAccessor: FileAccessorProviding = DefaultFileAccessor()
    ) {
        self.fileSystem = fileSystem
        self.fileAccessor = fileAccessor
    }
}
```

- Use `enum` with associated values for states with distinct payload shapes: `LoadState<T>` with cases `idle`, `loading`, `loaded(T)`, `failed(Error)`. A `switch` on this enum is exhaustive and compiler-checked — no invalid state combinations are possible.
- Use `actor` to protect mutable shared state accessed from multiple concurrent contexts. Actors serialize access automatically. Do not use actors for types that are only ever accessed from `@MainActor` — annotate those with `@MainActor` instead.
- `struct` for DTOs, models, configuration, and other value types. Structs have value semantics — copying is cheap for small structs and eliminates aliasing bugs. Favor composition over inheritance by embedding types in structs.
- Use `@Observable` (Observation framework) for SwiftUI view models — it tracks property-level changes so only views reading a changed property re-render. Do not use `ObservableObject`/`@Published`/`@StateObject` in new code.
