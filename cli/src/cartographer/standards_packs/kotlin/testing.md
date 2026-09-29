# Kotlin Testing

- Use Kotest as the primary test framework. Choose a spec style and use it consistently across the module: `StringSpec` or `FunSpec` for simple unit tests, `BehaviorSpec` for given-when-then, `DescribeSpec` for nested describe/it structure matching the file's class hierarchy.
- Write custom Kotest matchers for domain assertions to keep test code readable. A matcher like `shouldBeValid()` or `shouldHaveStatus(ACTIVE)` documents intent far better than a chain of `shouldBe` on individual fields.
- Use MockK for mocking. Use `every { mock.method() } returns value` for synchronous stubs and `coEvery { mock.suspendMethod() } returns value` for suspend functions. Verify calls with `verify { ... }` and `coVerify { ... }`. Use `slot<T>()` to capture argument values for assertion.
- Test suspend functions with `runTest { }`. This replaces real time with virtual time, making coroutine tests fast. Test `Flow` emissions with the Turbine library: `flow.test { ... }`.

```kotlin
@Test
fun `search debounces rapid input`() = runTest {
    val viewModel = SearchViewModel(fakeRepo)
    viewModel.queryFlow.test {
        viewModel.onQueryChange("h")
        viewModel.onQueryChange("he")
        viewModel.onQueryChange("hello")
        advanceTimeBy(400)
        assertThat(awaitItem()).isEqualTo("hello") // only one emission
    }
}
```

- Test `StateFlow` in ViewModels by collecting with Turbine and triggering ViewModel actions. Use a `FakeRepository` that exposes a `MutableSharedFlow` so tests can push values and verify state transitions.
- Use property-based testing with Kotest's `Arb` for inputs that have a large domain (strings, integers, dates). `withData` drives data-driven tests with multiple named inputs without duplication.
- For Android modules, use Robolectric or Paparazzi for widget/snapshot tests. Do not run Android instrumented tests for pure logic — keep domain modules as pure Kotlin so they run on the JVM.
- Set up and tear down expensive shared resources with `beforeSpec { }` and `afterSpec { }`. Use `beforeEach { }` for per-test resets so tests are isolated.
- Configure Kover for coverage. Target a minimum of 80% line coverage for domain and business-logic modules. Coverage below this threshold should fail CI.
- Follow RED-GREEN-REFACTOR: write a failing test first, write the minimum code to make it pass, then refactor. Do not write tests after the fact to chase a coverage threshold — tests written this way don't catch regressions.
