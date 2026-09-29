# Test-Driven Development

- Write the test before writing the implementation. This is not optional: tests written
  after the fact tend to be shaped by the implementation they describe rather than by
  the requirements they should verify.
- A valid RED state means the test compiles and executes, and fails for the intended
  reason (missing behavior, wrong output). A test that fails due to a syntax error or
  broken setup is not a RED gate — fix the test infrastructure first.
- Write the minimum implementation to make the failing test pass. Resist the urge to
  generalize while the test is red. Generalization belongs in the refactor step, not
  the implementation step.
- Refactor only when the tests are green. Changing behavior and cleaning up code in the
  same step produces untestable intermediate states. Keep those concerns separate.
- The RED → GREEN → REFACTOR cycle is a discipline, not a suggestion. Skipping RED
  (implementing before confirming the test fails) produces tests that never verified
  anything.
- Start from user journeys, not from implementation details. A good test answers "what
  does the user experience?" rather than "how does the function work internally?" This
  makes tests resilient to refactoring.
- Each test covers one behavior. Tests that assert multiple unrelated things become hard
  to diagnose on failure. One assertion per test is a useful heuristic; one focused
  behavior per test is the underlying goal.
- Tests are first-class code. Name them descriptively, keep them readable, and
  refactor them when they become hard to maintain. Tests that are incomprehensible are
  not maintained and not trusted.
- Maintain 80% coverage as a floor. Track coverage trends. Coverage that drops is a
  signal that tests are being skipped. Coverage that stays high despite additions means
  tests are actually being written.
- Mock external dependencies (network, database, third-party APIs) to keep unit tests
  fast and deterministic. Test real integrations in a separate integration suite.
- Bug fixes start with a test that reproduces the bug. The test must fail before the
  fix and pass after. This prevents the same bug from reappearing silently.
