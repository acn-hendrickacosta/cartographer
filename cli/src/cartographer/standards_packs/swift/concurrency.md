# Swift Concurrency

- Write single-threaded code first. In Swift 6.2 with Approachable Concurrency, async functions stay on the calling actor by default — no implicit background offloading. Add concurrency only where profiling shows a bottleneck.
- Annotate app-layer types with `@MainActor` to protect shared mutable state. `@MainActor` types can conform to non-isolated protocols using isolated conformances (`extension MyType: @MainActor SomeProtocol { ... }`), which the Swift 6.2 compiler enforces at use sites.

```swift
@MainActor
final class AppModel {
    static let shared = AppModel()  // safe in Swift 6.2 @MainActor context
    var currentUser: User?
}
```

- Use `@concurrent` only for CPU-intensive work that genuinely benefits from a background thread (image processing, compression, cryptography, complex computation). Applying `@concurrent` to every async function adds thread-switching overhead without benefit.

```swift
nonisolated final class ImageProcessor {
    // Offload expensive work explicitly
    @concurrent
    static func extractSubject(from data: Data) async -> UIImage { /* ... */ }
}
```

- Use `async let` for parallel independent work. Use `TaskGroup` when the number of parallel operations is dynamic.

```swift
async let profile = userService.fetchProfile(id)
async let orders = orderService.fetchRecent(userId: id)
let (p, o) = await (profile, orders)
```

- Use `actor` to protect mutable state accessed from multiple concurrent contexts. Actors serialize access automatically — no locks, no data races.

```swift
actor Cache<Key: Hashable, Value> {
    private var storage: [Key: Value] = [:]
    func value(for key: Key) -> Value? { storage[key] }
    func store(_ value: Value, for key: Key) { storage[key] = value }
}
```

- Do not call blocking APIs (`Thread.sleep`, `URLSession.dataTask` with completion handlers, `DispatchQueue.sync`) from async contexts. Use their async equivalents (`try await Task.sleep(for:)`, `URLSession.data(for:)`).
- Enable Approachable Concurrency build settings in Xcode (Swift 6.2): `DefaultIsolation = MainActor` for app targets, `NonisolatedNonsendingByDefault` for library code. Enable incrementally — start with `MainActor` default inference and add `@concurrent` where profiling shows the need.
- Migrate away from `DispatchQueue`, `OperationQueue`, and completion handlers. They do not participate in Swift's structured concurrency and cannot be cancelled cooperatively.
- Test concurrent code with `swift test --enable-thread-sanitizer` in CI. Thread Sanitizer catches data races that Swift's static analysis misses. Data-race errors caught by the compiler in Swift 6 are not the complete picture — TSan finds runtime races in non-strict code.
