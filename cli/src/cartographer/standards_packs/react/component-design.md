# React: Component design

- Prefer controlled components over uncontrolled ones for form inputs that need validation or conditional behavior. Use uncontrolled inputs (refs) only for integration with non-React libraries or file inputs.
- Compose behavior via hooks, not inheritance. Extract shared logic into custom hooks. Do not create "base components" that other components extend.
- Keep render logic in JSX, not in separate template functions within the component. `renderHeader()` methods are a pattern from class components; extract a `Header` component instead.
- Do not put business logic in components. Components should call hooks and render; hooks should own the logic.
- Keep prop interfaces small. A component that accepts 12 props is too complex. Split it or use composition.
- Avoid optional props whose absence silently changes behavior. Make required things required. Use discriminated unions for components that have meaningfully different modes.
- Export components as named exports, not default exports. Named exports are easier to refactor and import-trace.

## File and Naming Conventions

- Use `.tsx` for any file containing JSX, even a one-liner. Use `.ts` for pure logic, custom hooks without JSX, and type definitions.
- Components: `PascalCase` for both the symbol and the file (`UserCard.tsx`, default export `UserCard`). Custom hooks: `useCamelCase` for the symbol.
- Boolean props: `isLoading`, `hasError`, `canSubmit` — never `loading` or `error` alone for booleans.
- Context: name the context type `<Domain>Context`, the provider `<Domain>Provider`, and the consumer hook `use<Domain>`.
- Class components are forbidden in new code. Convert legacy class components to function components when making non-trivial changes.

## File Layout

- Group related files in a component directory when the component has tests and styles:

```
components/UserCard/
  UserCard.tsx
  UserCard.module.css
  UserCard.test.tsx
  index.ts   # re-export only
```

- Inline single-file components are fine for simple presentational pieces.

## JSX Style

- Self-close elements with no children: `<UserCard user={u} />`, `<img />`.
- Use fragments `<>...</>` over wrapper `<div>` when no DOM element is needed.
- Do not put multi-line logic inline in JSX — extract to a `const` above the return.

```tsx
// Prefer
const greeting = user.isAdmin ? 'Welcome, admin' : `Hello ${user.name}`
return <h1>{greeting}</h1>

// Over
return <h1>{user.isAdmin ? 'Welcome, admin' : `Hello ${user.name}`}</h1>
```

## Container / Presentational Split

- Container components own data fetching, state, and side effects. Presentational components receive props and render — no service calls, no hooks beyond local UI state.

```tsx
// Container — owns data
export function UserPage({ userId }: { userId: string }) {
  const { data: user, isLoading } = useUser(userId)
  if (isLoading) return <Spinner />
  if (!user) return <NotFound />
  return <UserCard user={user} onSelect={handleSelect} />
}

// Presentational — pure
export function UserCard({ user, onSelect }: { user: User; onSelect: (id: string) => void }) {
  return <button onClick={() => onSelect(user.id)}>{user.name}</button>
}
```

## Suspense and Error Boundaries

- Every `<Suspense>` boundary needs an `<ErrorBoundary>` above it. The pair handles both loading and error states.
- Place boundaries close to where data is consumed, not at the route root. Multiple narrow boundaries reveal loaded sections progressively.

```tsx
<ErrorBoundary fallback={<ErrorView />}>
  <Suspense fallback={<Skeleton />}>
    <UserDetails id={id} />
  </Suspense>
</ErrorBoundary>
```

## Lists and Keys

- `key` must be stable across renders — never use array index for lists that can reorder, insert, or delete. Use database IDs.
- `key` must be unique among siblings, not globally.

## Composition Patterns

- Use `children` for slot-style composition. Use named props (`header`, `sidebar`) for multiple slots.
- Use compound components (sharing state via Context) for tightly related controls like Tabs, Accordion, or Menu.
- Use `createPortal` for modals, tooltips, and toast containers that must escape `overflow: hidden` or `z-index` stacking.

## React Hooks Discipline

- Call all hooks at the top of the component, before any conditional logic. Never call hooks inside loops, conditionals, or nested functions.
- `useEffect` is for synchronizing with external systems — subscriptions, browser APIs, third-party libraries. It is NOT for computing derived state (compute during render), resetting state on prop change (use a `key`), or notifying parents (call the callback in the event handler).
- Always clean up subscriptions, intervals, listeners, and in-flight requests in the `useEffect` return function.
- Include all reactive values in effect dependency arrays. Enable `react-hooks/exhaustive-deps` and treat it as an error in CI.
- Add `useMemo` or `useCallback` only when a value is a dependency of another hook, is passed to a `React.memo`-wrapped child, or is measurably expensive. Profile before assuming.
- Extract a custom hook when the same hook sequence appears in two or more components, or when the logic has a clear, testable purpose.

## React 19 Hooks

- `useActionState` and `useFormStatus` manage form submission state without prop drilling.
- `useOptimistic` applies an optimistic update while a server action is pending.
- `use()` unwraps promises and contexts inline and can be called conditionally.
- `useTransition` marks non-urgent state updates so urgent interactions stay responsive.
