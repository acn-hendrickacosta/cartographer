# Frontend Patterns

## Component Design

- Favor composition over inheritance. Build complex UI by composing small, focused
  components rather than extending a base component class.
- Compound components share state through context rather than prop drilling. A `Tabs`
  component that exposes `TabList` and `Tab` children is more ergonomic than a single
  component receiving a configuration array.
- Extract data fetching logic into custom hooks. Components should receive data and
  dispatch events; hooks manage loading, error, and stale states.
- A component is responsible for one thing. A component that fetches data, transforms
  it, and renders UI is three responsibilities. Split it.

## State Management

- Start with local state (`useState`, `useReducer`) and lift only when multiple
  components genuinely need the same state.
- Use context for state that many components need (theme, current user, locale). Do not
  use context for high-frequency updates — it re-renders every consumer on every change.
- Prefer functional state updates (`setState(prev => ...)`) over reading state directly
  in async callbacks. Direct reads produce stale closures.
- Large UI state machines (multi-step forms, wizard flows) benefit from `useReducer`
  over multiple `useState` calls. The reducer makes state transitions explicit and
  auditable.

## Performance

- Memoize expensive computations with `useMemo` and stable callbacks with `useCallback`.
  Apply them only when profiling shows a real problem — premature memoization adds
  complexity without benefit.
- Virtualize long lists (hundreds to thousands of items). Rendering all items at once
  is a common cause of scroll jank.
- Code-split at route boundaries and for large, conditionally rendered components (rich
  text editors, charts, 3D scenes). Lazy loading reduces initial bundle size.
- Array `.sort()` mutates in place. Copy the array before sorting in render code:
  `[...items].sort(...)`.

## Data Fetching

- Keep fetcher functions referentially stable (via `useRef`) when they are dependencies
  in `useEffect`. Inline arrow functions in deps create infinite fetch loops.
- Debounce search inputs before triggering fetches. Firing a request on every
  keystroke wastes network and server resources.
- Display loading, empty, error, and success states explicitly for every async
  operation. Blank screens on loading and silent failures are not acceptable in
  production UIs.

## Forms

- Validate inputs on blur (not just on submit) to give users early feedback.
- Validate with a schema library at the form boundary. Do not duplicate validation
  logic between the form and the server — the server must always validate independently.
- Disable the submit button while submission is in progress to prevent double submits.

## Accessibility

- Every interactive element must be keyboard-accessible. Avoid click handlers on
  non-interactive elements (`div`, `span`) without adding `role`, `tabIndex`, and key
  handlers.
- Modals must trap focus while open and return focus to the trigger element on close.
- Icon-only buttons must have a visible label accessible to screen readers.

## Error Handling

- Wrap component trees in error boundaries to catch render exceptions. A crashed
  component should show a fallback, not crash the entire page.
- Surface error state to users with a message they can act on. "Something went wrong"
  with no next step is not a useful error message.
