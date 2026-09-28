# React: Performance

- Measure before optimizing. Use React DevTools Profiler to identify the actual slow components before applying memoization. Premature optimization adds complexity without benefit.
- Use `React.memo` to skip re-renders of pure components whose props have not changed. Do not wrap everything in `memo` — only components that re-render frequently with stable props.
- Use `useMemo` for expensive computations whose inputs change rarely. Do not use `useMemo` for simple arithmetic or string operations — the overhead of the memo check is comparable.
- Use `useCallback` for callbacks passed to `memo`-wrapped children or included in dependency arrays. Not for every callback.
- Virtualize long lists with `react-window` or `react-virtual`. The performance cliff at ~500 rows is real and not fixable with memoization.
- Code-split at route boundaries with `React.lazy` and `Suspense`. Do not load the entire app bundle on first paint.
- Avoid inline object and array creation in JSX props: `<Comp style={{ color: 'red' }}>` creates a new object every render. Move constants outside the component.
