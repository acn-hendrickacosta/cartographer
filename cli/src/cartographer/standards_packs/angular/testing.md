# Angular Testing

- Configure `TestBed` for standalone components by passing the component directly in `imports: [MyComponent]`, along with any dependencies it needs. Do not declare standalone components — they are imported, not declared.
- Set signal inputs in tests using `fixture.componentRef.setInput('inputName', value)`. Direct property assignment bypasses Angular's change detection for signal-based inputs.
- Use Angular CDK testing harnesses for component interaction in tests. `HarnessLoader` + `MatButtonHarness`, `MatInputHarness`, etc. provide stable, semantic access to UI elements that survives DOM restructuring.

```typescript
const loader = TestbedHarnessEnvironment.loader(fixture);
const button = await loader.getHarness(MatButtonHarness.with({ text: 'Submit' }));
await button.click();
```

- Use `RouterTestingHarness` to test routed components, including guard behavior and query parameter handling. It navigates in a test environment without requiring a real browser.
- Use `fakeAsync` + `tick()` for tests involving timers, debounce, or delayed Observables. This runs the event loop synchronously and makes timing deterministic.
- Test `HttpClient` calls with `provideHttpClientTesting()` + `HttpTestingController`. Assert that the correct requests are made and flush mock responses.

```typescript
httpMock.expectOne('/api/users').flush(mockUsers);
httpMock.verify();
```

- Inject services directly in tests using `inject(MyService)` or `TestBed.inject(MyService)` — no need to test through a component if you're testing service behavior.
- What to test: service methods and their side effects; component inputs/outputs and rendered output changes; pipe transformations; guard return values; resolver data. Don't test implementation details — test observable behavior.
- For E2E tests, use Cypress or Playwright. Use `data-cy` or `data-testid` attributes as selectors. Do not rely on CSS classes or DOM structure as selectors — they change frequently and make tests brittle.
- Run unit tests with `ng test --watch=false` in CI. Set coverage thresholds in the Jest or Karma configuration. Fail the build when coverage drops below the agreed minimum.
