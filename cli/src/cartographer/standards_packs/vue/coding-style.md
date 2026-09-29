# Vue 3 Coding Style

- Always use `<script setup lang="ts">` — no Options API in new code. `<script setup>` eliminates most boilerplate and is the recommended Vue 3 form for all components.
- Block order within SFCs: `<script setup>` → `<template>` → `<style scoped>`. Within `<script setup>`: imports → props/emits → composables → local state → computed → methods → watchers → lifecycle hooks.
- File naming: `PascalCase.vue` for all component files (enforced by `vue/multi-word-component-names`). Composable files use camelCase with a `use` prefix: `useUserFilters.ts`. Route-level pages may use kebab-case for readability.
- Enforce code quality with Prettier + `eslint-plugin-vue` using the `vue3-recommended` ruleset. Run `vue-tsc --noEmit` in CI for type checking.
- `ref` is the primary state API. Use it for all primitive and most object state. Use `reactive` only for grouped configuration objects where you need to destructure reactively without losing reactivity — and never reassign the whole `reactive` object.
- `computed` must be pure — no side effects, no async, no mutations inside a computed getter. If you need an async operation triggered by state, use `watch` or `watchEffect`.
- When watching a `reactive` object property, pass a getter function: `watch(() => form.email, handler)`. Passing the reactive object itself or a destructured property watches the wrong thing.
- Call lifecycle hooks synchronously inside `setup` — never inside a `setTimeout`, `Promise.then`, or conditional. Clean up event listeners, timers, and subscriptions in `onUnmounted`.
- Use stable, unique keys in `v-for` — use database IDs, never array indices. Index keys cause state reuse bugs during reordering. Never put `v-if` and `v-for` on the same element — filter with a computed array instead.
- Use `readonly()` or `Object.freeze()` on data that should not be mutated by child components. Treat props as read-only — always emit events to communicate changes upward.
