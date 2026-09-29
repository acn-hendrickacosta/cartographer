# Vue 3 Code Review Criteria

## Critical — Block Approval

- **`v-html` without DOMPurify sanitization**: direct XSS vector. Any user-controlled content in `v-html` is an immediate security issue. Sanitize with a restrictive DOMPurify allowlist or replace with structured template rendering.
- **`:href` or `:src` binding without scheme validation**: `javascript:` URL bound to `:href` executes on click. Validate that the scheme is `https:` or `http:` before binding.
- **Nuxt `runtimeConfig.public` containing server secrets**: values in `runtimeConfig.public` ship to the browser. Secrets, API keys, and credentials must be server-only config.
- **API route without input schema validation**: server routes that use raw `getRouterParams()` or `readBody()` without zod/yup validation accept arbitrary malicious input.
- **`localStorage` used for session tokens**: tokens in `localStorage` are accessible to any JavaScript running on the page, including XSS payloads. Use `httpOnly` cookies.
- **Prop destructuring in Vue < 3.5**: `const { count } = defineProps<{count: number}>()` destroys reactivity. Access via `props.count` or use `toRefs(props)`.
- **`ref` used without `.value` in script**: `ref` is a wrapper — accessing `myRef` instead of `myRef.value` in script context returns the ref object, not the value.
- **`reactive()` used for primitive values**: `reactive(0)` does not work — `reactive` only tracks object properties. Use `ref` for primitives.

## High — Strong Recommendation to Fix

- **Module-scope side effects in a composable**: `setInterval`, `addEventListener`, or `$fetch` at the top level of a composable module run once globally and are never cleaned up. Move setup into the composable body.
- **Composable missing cleanup**: subscriptions, timers, event listeners registered in a composable must be torn down in `onUnmounted` or watcher `onCleanup`. Missing cleanup causes memory leaks and stale callbacks.
- **`v-for` with index as key**: `key="index"` causes incorrect state reuse when the list is reordered or filtered. Use stable entity IDs.
- **`v-if` and `v-for` on the same element**: evaluation order is undefined. Filter with a computed array and use only `v-for` on the element.
- **Props mutation**: components must never mutate prop values directly. Emit an event and let the parent update its state.
- **`useRoute()` params destructured and used reactively**: destructured params are not reactive. Access them via `route.params.id` or wrap in a computed.
- **Pinia mutations scattered across components**: Pinia state must be mutated only through store actions. Direct mutations from components bypass business logic in actions.
- **Nuxt `useAsyncData` without a stable key**: two `useAsyncData` calls with the same auto-generated key collide and return incorrect data.
- **SSR browser-only API at top level**: `window`, `document`, or `navigator` accessed outside `onMounted` or `import.meta.client` causes a server-side crash.
- **`<ClientOnly>` wrapping SEO-critical content**: content inside `<ClientOnly>` is invisible to crawlers. Use SSR data fetching for content that must be indexed.

## Medium

- Component files exceeding ~300 lines — split into smaller focused components.
- Missing prop type validation on components accepting complex objects.
- Watcher without cleanup for `AbortController` — in-flight requests are not cancelled when the watcher re-triggers.
- `defineEmits` missing TypeScript types — untyped emits allow any event name and payload.

## Approval Criteria

CRITICAL and HIGH findings block approval. Fix before merge or document an accepted exception with written justification.
