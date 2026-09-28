# React: State management

- Start with local component state (`useState`, `useReducer`). Reach for global state only when multiple unrelated components need the same data and prop-drilling becomes unmanageable.
- Use React Context for configuration and values that change infrequently (theme, locale, auth status). Do not use Context as a general-purpose event bus.
- When global state is needed, prefer a purpose-built library (Zustand, Jotai, Redux Toolkit) over rolling a custom solution with Context + useReducer. Justify the choice in an ADR.
- Keep server state separate from UI state. Use React Query, SWR, or similar for data fetched from an API. Do not store server responses in a Redux store unless there is a specific cross-component sync requirement.
- Derive values from state rather than caching derived state. Duplicate state that can be computed leads to inconsistency bugs.
- Avoid state that stores the same data in two places. If a list and a selected item are both in state, the selected item should be an id referencing the list, not a copy of the object.
