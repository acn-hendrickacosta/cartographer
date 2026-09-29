# Vue 3 Patterns

- Split components into container (smart) and presentational (dumb). Container components own data fetching, store access, and side effects. Presentational components receive props and emit events — no store access, no API calls.
- All composables must start with `use` and return reactive values (`ref`, `computed`, `reactive`). Accept reactive inputs via `MaybeRefOrGetter` + `toValue()` so composables work with both plain values and refs. Clean up side effects in `onUnmounted` or watcher `onCleanup`. Never create module-scope side effects — everything that sets up subscriptions or timers must do so inside the composable setup, not at module top-level.

```typescript
export function useDebounce<T>(value: MaybeRefOrGetter<T>, delay: number) {
    const debounced = ref(toValue(value)) as Ref<T>;
    let timer: ReturnType<typeof setTimeout>;
    watch(() => toValue(value), (v) => {
        clearTimeout(timer);
        timer = setTimeout(() => { debounced.value = v; }, delay);
    });
    onUnmounted(() => clearTimeout(timer));
    return readonly(debounced);
}
```

- Use Pinia setup stores (not options stores). Define state as `ref`, derived values as `computed`, and mutations as plain functions. For state and getters, destructure with `storeToRefs()` to preserve reactivity. Destructure actions directly — they are plain functions.
- TanStack Query (vue-query) owns server cache state. Pinia owns client-only UI state. Do not duplicate server responses into a Pinia store — that creates stale data and cache invalidation complexity.
- For `provide`/`inject`, define `InjectionKey<T>` symbols in the module that defines the interface. The providing component is the sole owner of mutations — inject a `readonly` ref plus explicit updater functions, never the raw mutable ref.
- Lazy-load routes: `component: () => import('@/pages/UserDetail.vue')`. Pass `props: true` to receive route params as component props. Centralize auth guards in `router.beforeEach`.

```typescript
router.beforeEach((to) => {
    if (to.meta.requiresAuth && !useAuthStore().isLoggedIn) {
        return { name: 'login', query: { redirect: to.fullPath } };
    }
});
```

- Watch reactive route params with a getter: `watch(() => route.params.id, fetchItem)`. Destructured route params are not reactive — always access them through `route.params`.
- Vue 3.5+: destructured `defineProps()` variables are reactive. Use a getter wrapper when watching them: `watch(() => count, handler)`. Use `useTemplateRef('refName')` instead of name-matched plain refs. Use `onWatcherCleanup()` inside watcher callbacks to abort pending requests.
- Performance: use `v-memo` on list items that rarely change, `shallowRef` for large data structures replaced wholesale, `<KeepAlive :max="10">` for toggled views, and `v-show` over `v-if` for frequent visibility toggles.
