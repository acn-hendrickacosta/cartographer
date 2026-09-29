# E2E Testing

- E2E tests cover critical user flows through the full stack. Reserve them for journeys
  where a unit or integration test cannot catch the failure: navigation, form
  submission, multi-step workflows, and cross-service interactions.
- Organize E2E tests by feature area, not by page. Group tests for a feature together
  so the coverage map mirrors product structure.
- Use the Page Object Model to encapsulate element locators and actions. A page object
  exposes methods like `search(query)` and `getResultCount()` rather than raw
  selectors. When the UI changes, only the page object needs updating.
- Prefer `data-testid` attributes or semantic ARIA roles as locators. CSS class names
  and DOM structure change; test-specific identifiers and ARIA roles stay stable.
- Never use arbitrary waits (`waitForTimeout`). Wait for a specific condition: a network
  response, an element becoming visible, or a page state change. Arbitrary sleeps make
  tests slow and still flaky.
- Use auto-waiting locators that retry until the element is ready, rather than clicking
  immediately and hoping the element is interactive.
- Configure retries in CI (typically 2 retries on failure) but zero locally. Retries
  mask real flakiness during development. A test that needs retries to pass is a flaky
  test.
- Quarantine flaky tests with a clear label and a linked issue rather than ignoring
  them. A quarantined test is visible and trackable; an ignored failure is noise. Fix
  quarantined tests before they accumulate.
- Common causes of flakiness: race conditions (use auto-waiting locators instead of
  manual clicks), network timing (wait for the API response, not for a timeout),
  animation timing (wait for element stability before interacting).
- Capture screenshots and video on failure automatically. Attach test artifacts to CI
  runs so failures can be diagnosed without re-running locally.
- Run E2E tests against a consistent environment. Tests that pass locally but fail in
  CI due to different base URLs, missing seed data, or environment differences are
  integration problems, not E2E test problems — fix the environment.
- Skip tests on production against real money or real users explicitly in the test code.
  Safeguards that exist only in documentation get bypassed.
