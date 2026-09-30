# Testing

- Every codebase should maintain 80% coverage across unit, integration, and E2E tests
  combined. This is a floor, not a target; critical paths should be higher.
- Write tests before implementing code (TDD). A failing test defines the contract;
  the implementation satisfies it. This order catches design problems earlier and makes
  the coverage genuine rather than retrofitted.
- Three test types are all required: unit tests for individual functions, utilities,
  and components; integration tests for API endpoints, database operations, and service
  interactions; and E2E tests for critical user flows through the full stack.
- Structure tests with Arrange-Act-Assert. Each test sets up its own state (no shared
  mutable state between tests), executes one action, and asserts on the outcome.
- Name tests to describe the behavior under test, not the implementation. "Returns an
  empty list when no records match the query" is better than "test search". A failing
  test name should tell the reader what broke.
- Test user-visible behavior, not internal implementation details. Tests that reach into
  private state or assert on intermediate variables break when the implementation
  changes for legitimate reasons.
- Each test must be independent. Tests that depend on execution order or shared database
  rows are fragile and produce false failures. Set up and tear down state within the
  test or use isolated fixtures.
- Mock only external dependencies (network calls, databases, third-party APIs), not
  internal modules that can be tested directly. Over-mocking hides integration bugs.
- Test error paths, not just the happy path. Null inputs, empty collections, missing
  configuration, and upstream failures all deserve tests.
- Keep unit tests fast — under 50ms each. Tests that take seconds per case will be
  skipped. Slow tests belong in a separate integration suite run on CI but not locally
  on every save.
- Flaky tests must be fixed or quarantined, not ignored. A test that sometimes passes
  and sometimes fails provides no signal and erodes confidence in the entire suite.
- Use `data-testid` attributes or semantic ARIA roles as selectors in E2E and UI tests.
  CSS class names and DOM structure change; semantic identifiers stay stable.
