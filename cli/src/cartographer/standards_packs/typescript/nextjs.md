# Next.js Patterns

## Turbopack (Next.js 16+)

- From Next.js 16, `next dev` uses Turbopack by default. It is an incremental, Rust-based bundler that caches build output to disk, making dev restarts significantly faster on large projects.
- Fall back to the legacy webpack bundler (`--webpack` or `--no-turbopack` flag) only when a specific webpack plugin has no Turbopack equivalent. Document the reason.
- The production build (`next build`) behavior depends on the Next.js version — check the official docs for your release. Do not assume production uses Turbopack.
- If dev startup is slow, verify you are running Turbopack (the default) and that `.next/` cache is not being cleared on every restart.

## Middleware Filename (Next.js 16+)

- Next.js 16 renamed the middleware file from `middleware.ts` to `proxy.ts`. Place it at the project root.
- `proxy.ts` and `middleware.ts` are version-specific conventions, not bundler-specific. Do not rename `proxy.ts` to `middleware.ts` on a Next.js 16 project — it will break middleware execution.

## Server vs Client Components

- Default new files to Server Components. Only add `"use client"` when the component uses `useState`, `useEffect`, refs, browser APIs, or event handlers.
- Place `"use client"` on the first line of the file, before all imports.
- Never import a Server Component from inside a Client Component file. Compose them via `children` or named props instead.
- Mark modules that must stay server-only with `import "server-only"` so the bundler errors loudly if a Client Component imports them.

## Server Actions

- Treat Server Actions (`"use server"`) as public API endpoints. Validate every input with a schema validator. Authenticate and authorize inside the action — do not rely on client-side route guards.
- Rate limit sensitive Server Actions. Apply the same scrutiny as an HTTP route handler.

## Data Fetching

- In the App Router, `await fetch()` inside a Server Component is the preferred pattern for per-request data. It is cached, deduped, and composable with `Suspense`.
- For client-side data that needs caching, mutations, or background refetching, use TanStack Query or SWR — not `useEffect` + `fetch`.

## Environment Variables

- Variables prefixed `NEXT_PUBLIC_` are bundled into the client and visible to anyone. Treat them as public.
- Server-side secrets must have no `NEXT_PUBLIC_` prefix and must never be imported in a Client Component or accessed via a route that ships the value to the browser.

## Bundle Analysis

- Use the Next.js Bundle Analyzer (experimental flag in Next.js 16.1+) to inspect output and identify large dependencies before they affect production load times. Run it before shipping a new dependency that looks large.
