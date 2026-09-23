# React standards

- Prefer function components and hooks. Do not introduce a class component into a
  hooks-based codebase.
- Keep state as local as possible. Lift it only when two or more components
  genuinely need to share it, and reach for a global store only when prop drilling
  has become the actual problem, not preemptively.
- Derive values during render instead of syncing them into state with an effect.
  An effect that exists only to copy one piece of state into another is almost
  always removable.
- Name components and files identically, one component per file, colocated with its
  test and styles.
- Test behavior a user can observe (rendered text, interactions) rather than
  implementation details (internal state, private methods). Prefer a testing
  library that queries by role and text over one that reaches into component
  internals.
- Treat prop and state shapes as part of the component's contract. Type them
  explicitly rather than relying on inference from a single call site.
