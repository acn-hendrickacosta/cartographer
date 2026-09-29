# Swift Testing

- Use Swift Testing (`import Testing`) for all new tests. Use `@Test` for test functions and `#expect` for assertions. `#expect` captures the full expression on failure, giving richer output than XCTestAssert variants.

```swift
@Test("User creation validates email format")
func userCreationValidatesEmail() throws {
    #expect(throws: ValidationError.invalidEmail) {
        try User(email: "not-an-email")
    }
}
```

- Each test gets a fresh state — set up in `init`, tear down in `deinit`. Avoid class-level shared mutable state between test cases. Swift Testing's struct-based tests guarantee isolation automatically.
- Use parameterized tests to cover multiple input variants without duplicating test bodies:

```swift
@Test("Validates supported formats", arguments: ["json", "xml", "csv"])
func validatesFormat(format: String) throws {
    let parser = try Parser(format: format)
    #expect(parser.isValid)
}
```

- Mock external dependencies using the protocol-injection pattern. Define a protocol for each external concern (`FileSystemProviding`, `NetworkProviding`), create a production implementation and a mock implementation. Inject the mock in tests.

```swift
final class MockFileAccessor: FileAccessorProviding, @unchecked Sendable {
    var files: [URL: Data] = [:]
    var readError: Error?

    func read(from url: URL) throws -> Data {
        if let error = readError { throw error }
        guard let data = files[url] else { throw CocoaError(.fileReadNoSuchFile) }
        return data
    }
}
```

- Only mock external boundaries (file system, network, databases, third-party SDKs). Do not mock internal types — test them directly. Over-mocking creates tests that verify mock behavior rather than real behavior.
- For actor-based types, test the full `async` interface using `await`. Test cancellation by checking that resources are released in the `finally` or `defer` block when a `Task` is cancelled.
- Measure coverage with `swift test --enable-code-coverage`. Generate an HTML report with `xcrun llvm-cov show`. Target 80%+ for business logic. Coverage misses on error handling paths are usually the most important ones — test them explicitly.
- For SwiftUI views, use `#Preview` macros with mock data injected via constructor DI. This keeps previews honest — they use the same injection path as production and tests.
