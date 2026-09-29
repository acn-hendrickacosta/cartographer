# Vue 3 Testing

- Use Vitest + `@vue/test-utils` + happy-dom (or jsdom) as the standard test stack for components and composables.
- Mount components with `mount()` for full rendering and `shallowMount()` when child components should be stubbed. Prefer `mount()` — shallow mounting hides integration issues between components.
- Trigger user interactions and then await the Vue update cycle before asserting:

```typescript
await wrapper.find('button').trigger('click');
await wrapper.setValue('input', 'hello');
await flushPromises(); // for async operations
await nextTick();      // for synchronous reactivity
```

- Test the public interface of components — props in, emitted events out, rendered text and DOM structure. Do not assert on internal reactive state (`wrapper.vm.someInternalRef`). Tests that depend on internals break on refactors.
- Composables that use `provide`/`inject` or lifecycle hooks must be tested through a host component, not called directly. Create a minimal `TestHost` component that uses the composable and assert through the component.
- For Pinia stores in tests: use `createTestingPinia({ createSpy: vi.fn })` to isolate stores and stub actions. Call `setActivePinia(createPinia())` in `beforeEach` for tests that need a real Pinia instance with real action behavior.

```typescript
beforeEach(() => setActivePinia(createPinia()));

it('loads users on mount', async () => {
    const wrapper = mount(UserList, { global: { plugins: [createTestingPinia({ createSpy: vi.fn })] } });
    await flushPromises();
    expect(wrapper.text()).toContain('Alice');
});
```

- Stub `RouterLink` with `RouterLinkStub` from `@vue/test-utils` when testing components that use `<RouterLink>` without a full router instance.
- For E2E tests, use Playwright or Cypress with `data-testid` attributes as selectors. `data-testid` attributes are stable across refactors and do not couple tests to CSS class names or DOM structure.
- Run tests with `vitest run --coverage` in CI. Configure coverage thresholds for business-critical composables and stores.
