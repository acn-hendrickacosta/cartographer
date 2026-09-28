# React: Component design

- Prefer controlled components over uncontrolled ones for form inputs that need validation or conditional behavior. Use uncontrolled inputs (refs) only for integration with non-React libraries or file inputs.
- Compose behavior via hooks, not inheritance. Extract shared logic into custom hooks. Do not create "base components" that other components extend.
- Keep render logic in JSX, not in separate template functions within the component. `renderHeader()` methods are a pattern from class components; extract a `Header` component instead.
- Do not put business logic in components. Components should call hooks and render; hooks should own the logic.
- Keep prop interfaces small. A component that accepts 12 props is too complex. Split it or use composition.
- Avoid optional props whose absence silently changes behavior. Make required things required. Use discriminated unions for components that have meaningfully different modes.
- Export components as named exports, not default exports. Named exports are easier to refactor and import-trace.
