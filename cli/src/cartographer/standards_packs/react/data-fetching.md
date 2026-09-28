# React: Data fetching

- Fetch data in hooks, not in component bodies. A `useQuery` hook or a custom `useSomething` hook is the correct location for fetch logic. Components declare their data dependencies; they do not issue fetch calls directly.
- Handle loading, error, and empty states explicitly. A component that renders nothing while loading is a worse experience than a skeleton or spinner, and a component that crashes on a missing field is worse than an error boundary.
- Use `AbortController` to cancel in-flight fetches when a component unmounts or a query changes. React Query and SWR do this automatically; manual fetch calls must do it explicitly.
- Do not fetch inside `useEffect` without a cleanup. The cleanup cancels the in-flight request and prevents state updates on unmounted components.
- Paginate or virtualize long lists. Do not fetch all records and render them in one pass; large DOM trees degrade performance.
- Co-locate the API layer: each domain area should have its own API module (`src/api/users.ts`, `src/api/artifacts.ts`). Do not scatter `fetch` calls throughout components.
- Type API responses. Define TypeScript interfaces for every response shape and validate them at the boundary (with zod or a similar schema validator) rather than trusting untyped JSON.
