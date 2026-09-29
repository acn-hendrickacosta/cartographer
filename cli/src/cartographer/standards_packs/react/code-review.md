# React Code Review Criteria

What to look for when reviewing React component code. Generic TypeScript issues (type safety, async correctness, Node.js security) belong in a separate TypeScript review pass — this list covers React-specific concerns.

## Critical — React Security

- `dangerouslySetInnerHTML` with user-controlled HTML and no sanitization at the same call site.
- `href` or `src` accepting user-supplied URLs without validating the scheme. `javascript:` and `data:` URLs execute code.
- Server Action (`"use server"`) that accepts `FormData` or arguments without schema validation. Treat as a public API.
- `NEXT_PUBLIC_*`, `VITE_*`, or `REACT_APP_*` env var holding a private key or secret bundled into the client.
- Session tokens stored in `localStorage` or `sessionStorage`. Require httpOnly cookies.

## Critical — Hook Rules

- Hook called inside an `if`, `for`, `&&`, ternary, or after an early return. Order must be stable across renders.
- `useState`, `useEffect`, etc. called outside a function component or custom hook.
- State mutated directly (`state.push(x)`, `obj.field = value` then `setState(obj)`). Mutation does not trigger re-render and breaks memoization equality checks.

## High — Hook Correctness

- Missing reactive value in a `useEffect`, `useMemo`, or `useCallback` dependency array. Every `eslint-disable-next-line react-hooks/exhaustive-deps` without an explanatory comment should be flagged.
- `useEffect` used to compute derived state. Compute the value during render instead.
- Effect with no cleanup for a subscription, interval, listener, or `fetch` call. Missing cleanup causes memory leaks and race conditions.
- Async handler capturing a value that changes between when the handler was created and when it runs (stale closure). Fix with functional updater form or a ref.
- Custom hook not prefixed `use`. Breaks lint detection.

## High — Server/Client Boundary (Next.js App Router)

- `"use client"` file importing a module marked `"server-only"` or a known DB client (Prisma root, AWS SDK with secrets).
- Sensitive data (full user record with hashed password, tokens) passed as props from a Server Component to a Client Component.
- Server Action accessible without an auth check inside the action body.

## High — Accessibility

- `<div onClick>` or `<span onClick>` without `role`, `tabIndex={0}`, and `onKeyDown`. Mouse-only — excludes keyboard and assistive tech users.
- `<input>` without an associated `<label htmlFor>`, `aria-label`, or `aria-labelledby`.
- `<img>` without `alt`. Decorative images need `alt=""`, content images need a description.
- `target="_blank"` without `rel="noopener noreferrer"`.
- ARIA misuse: `aria-label` on a non-interactive element without a `role`, `role` overriding native semantics unnecessarily, missing `aria-controls`/`aria-expanded` on disclosure widgets.
- Heading levels skipped (`<h1>` directly to `<h3>`).

## High — Rendering and State Correctness

- `key={index}` on a list that can reorder, insert, or delete items. Attach state to the wrong row.
- Same data stored in two separate `useState` calls (duplicated state).
- Effect chain: an effect sets state that triggers another effect that sets more state. Refactor to derive during render or consolidate.
- Component initialized from a prop with no `key` to reset it when the prop changes.

## Medium — Performance

- `useMemo` or `useCallback` applied without a measured reason. The wrapping adds overhead; if props change on most renders or the value is not used by a memoized child, it is pure cost.
- Inline object or function literal as a prop to a `React.memo`-wrapped child. Creates a new reference every render, defeating the memo.
- Synchronous expensive work (sorting, regex compile, parsing) in render without `useMemo`.
- `<Suspense>` only at the route root. Push boundaries closer to where data is consumed for progressive loading.
- 50+ visible list items without virtualization.
- High-frequency value served via `useContext`. Every consumer re-renders on every change.

## Medium — Forms

- Form without a semantic `<form>` element. Loses native submit-on-Enter and browser integration.
- `onSubmit` handler without `preventDefault()` (except when using React 19 form actions).
- Hand-rolled validation in a multi-field or multi-step form. Recommend React Hook Form or TanStack Form.
- Input inside a `<form>` without a `name` attribute. Cannot be read via `FormData`.

## Medium — Composition

- Prop drilling beyond three levels. Consider Context or composition via `children`.
- Component exceeding ~200 lines. Extract subcomponents or a custom hook.
- Class component in new code. Convert to function component when modifying.

## Approval Criteria

- **Approve**: no Critical or High issues.
- **Caution**: Medium issues only — note them and merge with awareness.
- **Block**: any Critical or High issue must be resolved before merge.
