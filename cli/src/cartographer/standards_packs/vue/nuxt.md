# Nuxt 4 Patterns

- Never use `Date.now()`, `Math.random()`, or any non-deterministic value directly in SSR-rendered state. These produce different values on server and client, causing hydration mismatches. Generate such values in `onMounted` or inside `import.meta.client` guards.
- Browser-only code (DOM APIs, `window`, `navigator`, third-party SDKs that require a browser) goes in `onMounted`, inside `if (import.meta.client)`, or inside a `<ClientOnly>` component. Never call browser APIs at the top level of a `<script setup>` in a Nuxt page.
- Use Nuxt's `useRoute()`, not Vue Router's `useRoute()` directly, for SSR compatibility.
- Choose the right data fetching primitive: `useFetch` for SSR-safe reads tied to the component's lifecycle; `useAsyncData` when the fetcher is not a simple `$fetch` call and you need more control; `$fetch` for user-triggered mutations (form submissions, button actions).
- Always provide a stable, unique key to `useAsyncData`. Without it, multiple calls on the same page can collide.

```typescript
const { data: user } = await useAsyncData(
    `user-${route.params.id}`,
    () => $fetch(`/api/users/${route.params.id}`)
);
```

- Trim payload size with the `pick` option: `useFetch('/api/posts', { pick: ['id', 'title', 'slug'] })`. Only send to the client what the component actually renders.
- Use `lazy: true` for non-critical data that can load after the page is interactive. The component renders immediately with `null` data and updates when the fetch completes.
- Configure rendering strategy per-route with `routeRules` in `nuxt.config.ts`: `prerender` for static content, `swr` for stale-while-revalidate, `isr` for incremental static regeneration, `ssr: false` for purely client-side pages.
- Lazy-load heavy components with the `Lazy` prefix: `<LazyHeavyChart v-if="showChart" />`. Nuxt code-splits lazy components automatically. Use `<NuxtLink>` instead of `<RouterLink>` for automatic prefetching.
- Server-only config belongs in `runtimeConfig` (not `runtimeConfig.public`). Anything under `runtimeConfig.public` is sent to the client — never put API secrets, tokens, or private keys there.
- Validate all server route inputs: `const { id } = await getValidatedRouterParams(event, z.object({ id: z.string().uuid() }).parse)`. Never use `getRouterParams()` without validation on public-facing routes.
