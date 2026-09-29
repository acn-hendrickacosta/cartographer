# Angular Coding Style

- Keep your Angular CLI and framework version current. Run `ng version` to confirm the version in CI. New projects start with the latest stable release.
- All new components are standalone (no `NgModule`). Use `@Component({ standalone: true, imports: [...] })`. NgModule-based components are only acceptable when incrementally migrating a large legacy codebase.
- Default to `ChangeDetectionStrategy.OnPush` on every component. This forces explicit state management and eliminates most unnecessary re-renders. Only omit OnPush when you have a documented reason.
- Use `inject()` instead of constructor injection for all dependencies. It works in functional contexts (interceptors, guards, resolvers) and reduces boilerplate.

```typescript
@Component({ ... })
export class UserListComponent {
    private userService = inject(UserService);
    private router = inject(Router);
}
```

- For non-class tokens (config objects, environment values), define an `InjectionToken<T>` and provide it in the root module or a feature provider.
- Use Signals for reactive state: `signal()` for mutable state, `computed()` for derived values, `linkedSignal()` for writable derived state, `resource()` for async data fetching. Use `effect()` only for side effects (analytics, third-party integrations) — not for state synchronization.
- Use block template syntax in all new templates: `@for (item of items; track item.id) { }`, `@if (condition) { } @else { }`, `@switch (value) { @case (x) { } }`. Always provide a `track` expression in `@for` — use a stable ID, never the loop index.
- Scope styles with `:host` selectors and the default `ViewEncapsulation.Emulated`. Avoid `ViewEncapsulation.None` except for global stylesheet overrides.
- Follow Angular CLI file naming conventions: `user-list.component.ts`, `user.service.ts`, `auth.guard.ts`, `user.pipe.ts`. One class per file.
