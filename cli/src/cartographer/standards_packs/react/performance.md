# React: Performance

- Measure before optimizing. Use React DevTools Profiler to identify the actual slow components before applying memoization. Premature optimization adds complexity without benefit.
- Use `React.memo` to skip re-renders of pure components whose props have not changed. Do not wrap everything in `memo` — only components that re-render frequently with stable props.
- Use `useMemo` for expensive computations whose inputs change rarely. Do not use `useMemo` for simple arithmetic or string operations — the overhead of the memo check is comparable.
- Use `useCallback` for callbacks passed to `memo`-wrapped children or included in dependency arrays. Not for every callback.
- Virtualize long lists with `react-window` or `react-virtual`. The performance cliff at ~500 rows is real and not fixable with memoization.
- Code-split at route boundaries with `React.lazy` and `Suspense`. Do not load the entire app bundle on first paint.
- Avoid inline object and array creation in JSX props: `<Comp style={{ color: 'red' }}>` creates a new object every render. Move constants outside the component.

## Eliminating Waterfalls (Highest Priority)

- Waterfalls — sequential `await` calls for independent data — add full network round-trip latency for each step. Use `Promise.all` for independent parallel fetches.
- Check cheap synchronous conditions (props, flags) before awaiting remote data. Move `await` into the branch that actually uses the result.
- In Server Components, split parallel data fetches into separate child components. React renders sibling components concurrently; two `await` calls in the same component run sequentially.

```typescript
// Wrong: sequential awaits for independent data
const user = await getUser(id)
const posts = await getPosts(id)

// Correct: parallel
const [user, posts] = await Promise.all([getUser(id), getPosts(id)])
```

## Bundle Size

- Avoid barrel files (`index.ts` re-exporting a directory). They force the bundler to walk the full module graph even when you need one symbol. Import directly from the source file.
- Use dynamic `import()` for heavy components — charts, editors, maps. Pair with a loading skeleton so the page is not blank while the chunk loads.
- Defer third-party scripts (analytics, support widgets) until after hydration with `strategy="afterInteractive"` (Next.js) or equivalent.

```tsx
const HeavyChart = dynamic(() => import('./HeavyChart'), {
  loading: () => <Skeleton />,
  ssr: false,
})
```

## Re-render Optimization

- Do not define components inside other components. Each render of the parent creates a new component type, which defeats reconciliation and unmounts all children.
- Do not subscribe to an external store value that is only used inside a callback. Read it imperatively at call time instead.
- Subscribe to derived booleans rather than raw values to reduce re-render frequency: `useStore(s => s.cart.length > 0)` re-renders only when the boolean flips, not on every cart change.
- Use `startTransition` to mark non-urgent state updates (filter changes, sorting) so urgent interactions (typing) stay responsive.
- Use `useDeferredValue` to defer expensive renders triggered by a rapidly changing input value.

## Rendering Correctness

- Use ternary (`condition ? <A /> : null`) rather than `&&` when the condition can be a falsy non-boolean (`0`, `''`). `{count && <Badge />}` renders `0` as a text node when `count` is 0.
- `React.cache()` deduplicates data fetches within a single request. Multiple Server Components calling `getUser(id)` with the same argument result in one database query.
- For Server Components that need static data loaded once at process start (config, lookup tables), hoist the read to module scope so it runs once rather than per-request.
