# Angular Patterns

- Split components into smart (container) and dumb (presentational). Container components own data fetching, state, and side effects; they render presentational components. Presentational components receive inputs, emit outputs, and contain no service calls or store access.
- Services own all data access. Components and templates never inject `HttpClient` directly — that belongs in a service. Services are `@Injectable({ providedIn: 'root' })` unless they have non-singleton lifecycle requirements.
- Use `resource()` for reactive async data fetching tied to a signal. Use `toSignal()` to bridge an existing Observable into a signal, passing `initialValue` to avoid the nullable `undefined` type.
- Unsubscribe from Observables in long-lived components using `takeUntilDestroyed()`. Call it inside the component (in the inject context) or pass `destroyRef` to composables that subscribe.

```typescript
this.searchQuery$.pipe(
    debounceTime(300),
    switchMap(q => this.searchService.search(q)),
    takeUntilDestroyed(),
).subscribe(results => this.results.set(results));
```

- Use `canMatch` guards instead of `canActivate` for route-level access control. `canMatch` prevents the module from loading entirely, while `canActivate` only blocks navigation after the module is loaded.
- Lazy-load feature modules with `loadChildren: () => import('./feature/feature.routes')`. Route-level code splitting is the primary performance lever for large Angular apps.
- Write guards, resolvers, and interceptors as functions, not classes. Functional guards are simpler, composable, and tree-shakable.

```typescript
export const authGuard: CanMatchFn = (route, segments) => {
    const auth = inject(AuthService);
    return auth.isLoggedIn() ? true : inject(Router).createUrlTree(['/login']);
};
```

- Use `ResolveFn` resolvers to prefetch data before navigation. The component receives resolved data via `ActivatedRoute.snapshot.data`. This eliminates loading spinners for navigation-driven data.
- Prefer Angular CDK primitives (overlay, focus trap, live announcer) over rolling accessibility patterns from scratch. CDK handles the edge cases.
- For SSR (Angular Universal / application builder): gate browser-only APIs with `isPlatformBrowser(platformId)` or the `DOCUMENT` injection token. Never expose server environment variables through `TransferState`.
- Apply `withViewTransitions()` in the router configuration for smooth page transitions. This is a single-line addition with significant UX impact.
