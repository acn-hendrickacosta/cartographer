# React: Style and testing

- Use TypeScript for all new components. Avoid `any`; define explicit types for props and state.
- Name components in PascalCase; name hooks with `use` prefix; name utilities in camelCase.
- One component per file. The file name matches the component name.
- Keep components focused on one responsibility. When a component's render method exceeds ~80 lines, consider extracting a child component or a custom hook.
- Co-locate tests with their components: `Button.test.tsx` next to `Button.tsx`. Use Vitest or Jest with React Testing Library. Test behavior, not implementation: test what the user sees and interacts with, not which internal state variables change.
- Prefer `userEvent` over `fireEvent` in tests. It simulates real user input more accurately.
- Avoid snapshots tests for behavior. Use them only for stable, reviewable output like generated HTML emails or PDF templates.
- Accessibility is not optional: every interactive element must have an accessible name. Run axe in tests with `@axe-core/react` and fix all critical violations.

## Testing: Query Priority

- Query in this order: `getByRole` first, then `getByLabelText`, `getByText`, `getByDisplayValue`, `getByAltText` — fall back to `getByTestId` only when nothing else works.
- `getBy*` throws if no match (use for "must exist"). `queryBy*` returns null (use for "must not exist"). `findBy*` returns a Promise (use for async-rendered content).

```tsx
screen.getByRole('button', { name: /save/i })  // best
screen.getByLabelText('Email')                  // good for inputs
screen.getByTestId('save-btn')                  // last resort
```

## Testing: Async Assertions

- Use `findBy*` for elements that appear after async work. Use `waitFor` for side-effect assertions. Never use `setTimeout` + assertion — it is flaky.

```tsx
expect(await screen.findByText('Loaded')).toBeInTheDocument()
await waitFor(() => expect(saveSpy).toHaveBeenCalled())
```

## Testing: Network Mocking with MSW

- Use Mock Service Worker to mock HTTP requests in tests. MSW intercepts at the network layer, so the component, hooks, and fetch library all behave exactly as in production.
- Set `onUnhandledRequest: 'error'` so any unmatched request fails the test loudly.

```tsx
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'

const server = setupServer(
  http.get('/api/users/:id', ({ params }) =>
    HttpResponse.json({ id: params.id, name: 'Alice' }),
  ),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
```

## Testing: Provider Wrapping

- Wrap providers once in a `test-utils.tsx` file and re-export RTL from it. Every test file imports from `test-utils` instead of `@testing-library/react`.

```tsx
export function renderWithProviders(ui: React.ReactElement, options?: RenderOptions) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={lightTheme}>
        <MemoryRouter>{ui}</MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
    options,
  )
}
export * from '@testing-library/react'
```

## Testing: Custom Hooks

- Use `renderHook` from RTL. Wrap state-changing calls in `act`. Test through the hook's public API only.

```tsx
import { renderHook, act } from '@testing-library/react'

test('useCounter increments', () => {
  const { result } = renderHook(() => useCounter(0))
  act(() => result.current.increment())
  expect(result.current.count).toBe(1)
})
```

## Testing: Coverage Targets

| Layer | Target |
|---|---|
| Pure utilities | ≥90% |
| Custom hooks | ≥85% |
| Presentational components | ≥80% (behavior, not lines) |
| Container components | ≥70% (golden paths + error states) |
| Pages | E2E covered separately; smoke test minimum |

## Testing: When to Use Playwright Instead of RTL

- RTL with JSDOM cannot test real layout, scrolling, drag-and-drop, CSS transitions, browser animation, cross-frame interactions, or real network flows.
- Use Playwright Component Testing for components whose behavior depends on real browser rendering. Use Playwright or Cypress E2E for full user flows across multiple pages.
