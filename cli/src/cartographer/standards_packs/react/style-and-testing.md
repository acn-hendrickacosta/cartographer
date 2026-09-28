# React: Style and testing

- Use TypeScript for all new components. Avoid `any`; define explicit types for props and state.
- Name components in PascalCase; name hooks with `use` prefix; name utilities in camelCase.
- One component per file. The file name matches the component name.
- Keep components focused on one responsibility. When a component's render method exceeds ~80 lines, consider extracting a child component or a custom hook.
- Co-locate tests with their components: `Button.test.tsx` next to `Button.tsx`. Use Vitest or Jest with React Testing Library. Test behavior, not implementation: test what the user sees and interacts with, not which internal state variables change.
- Prefer `userEvent` over `fireEvent` in tests. It simulates real user input more accurately.
- Avoid snapshots tests for behavior. Use them only for stable, reviewable output like generated HTML emails or PDF templates.
- Accessibility is not optional: every interactive element must have an accessible name. Run axe in tests with `@axe-core/react` and fix all critical violations.
