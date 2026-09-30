# Feature Development

A structured workflow for implementing features that emphasizes understanding before
building and verification before shipping.

## Phases

- **Discovery**: Read the feature request carefully. Identify requirements, constraints,
  and acceptance criteria. Resolve ambiguities before writing code — questions answered
  during planning are cheaper than bugs found during review.
- **Research and reuse**: Search for existing implementations before writing new code.
  Check the codebase for similar patterns, package registries for established libraries,
  and documentation for API behavior. Prefer adopting or wrapping a proven approach
  over building net-new when the requirement is met.
- **Codebase exploration**: Trace the execution path and architecture layers that the
  feature will touch. Understand the integration points, existing conventions, and data
  models before proposing a design.
- **Architecture design**: Design the feature structure and major decisions before
  implementing. Present the plan and get alignment on it. The plan should cover: what
  new code is added, what existing code changes, what the data model looks like, and
  what edge cases exist.
- **Implementation**: Implement following the approved design. Prefer TDD: write a
  failing test for each behavior, implement the minimum to make it pass, then refactor.
  Keep commits small and focused.
- **Quality review**: Review the implementation against the acceptance criteria and
  coding standards. Address critical and high-severity issues before marking complete.
  Verify test coverage meets the 80% floor.
- **Summary**: Document what was built, any deviations from the original plan and why,
  known limitations, and follow-up work items. This makes the feature auditable after
  the fact.

## Principles

- Understand before building. Code written without understanding the existing system
  produces collisions, inconsistencies, and duplicate logic.
- One feature per branch. A branch that contains unrelated changes is harder to review,
  harder to revert, and harder to understand six months later.
- Ship incrementally. A feature that is "almost done" in a long-lived branch provides
  no value and accumulates merge conflicts. Break large features into deliverable slices.
