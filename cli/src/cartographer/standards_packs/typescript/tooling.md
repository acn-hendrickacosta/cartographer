# Frontend Tooling

## Vite: Key Facts

- `vite build` transpiles TypeScript but does NOT type-check. Type errors silently ship to production. Add `vite-plugin-checker` or run `tsc --noEmit` in CI to close the gap.
- `vite preview` is not a production server — it is a smoke-test for the built bundle. Deploy `dist/` to a real static host (NGINX, Cloudflare Pages, Vercel).
- Vite binds the dev server to `localhost` by default, which is unreachable from inside a container. Set `server.host: true` to bind `0.0.0.0`.

## Vite: Essential Plugins

| Plugin | Purpose |
|---|---|
| `@vitejs/plugin-react-swc` | React HMR + Fast Refresh via SWC (faster than Babel variant) |
| `@vitejs/plugin-react` | React HMR via Babel — only when Babel plugins are required |
| `vite-plugin-checker` | Runs `tsc` + ESLint in a worker thread with HMR overlay |
| `vite-tsconfig-paths` | Honors `tsconfig.json` `paths` aliases — use instead of hand-rolled `resolve.alias` |
| `vite-plugin-dts` | Emits `.d.ts` files in library mode |
| `rollup-plugin-visualizer` | Bundle treemap for periodic size audits |

## Vite: Environment Variables

- Only `VITE_`-prefixed variables are exposed to client code. They are statically inlined into the bundle at build time. Minification and disabled source maps do NOT hide them.
- Never put secrets, private keys, or database URLs in `VITE_` variables. They are public.
- Use `.env.local` for local secret overrides. It is gitignored by default.
- When using `loadEnv` in config, always pass an explicit prefix list — `loadEnv(mode, root, ['VITE_'])`. Passing `''` as the prefix loads all env vars including server secrets into config scope.

## Vite: Performance Pitfalls

- Barrel files (`index.ts` re-exporting a directory) are the leading cause of slow dev servers. Each barrel forces Vite to load every re-exported file even when a single symbol is used. Import directly from the source file.

```typescript
// Wrong: forces loading the entire module graph behind the barrel
import { formatDate } from '@/utils'

// Correct: only the one file is loaded
import { formatDate } from '@/utils/formatDate'
```

- Stale `node_modules/.vite` cache after switching branches or patching dependencies causes phantom errors. Delete the directory when something unexplained breaks.

## Vite: Security Checklist

- `envPrefix: ''` in `vite.config.ts` exposes ALL environment variables (including server secrets) as client constants. Never use it.
- Production `build.sourcemap: true` ships your source code publicly. Set to `false` unless you upload source maps to an error tracker and delete them locally.
- `.gitignore` must include: `.env.local`, `.env.*.local`, `dist/`, `node_modules/.vite`.

## Vite: Library Mode

- When publishing an npm package, set `build.lib` and externalize all peer dependencies. Unexternalized peers get bundled into your library and cause duplicate-runtime errors in consumers.
- Types are not emitted automatically in library mode. Add `vite-plugin-dts` or run `tsc --emitDeclarationOnly` separately.

```typescript
build: {
  lib: {
    entry: 'src/index.ts',
    formats: ['es', 'cjs'],
    fileName: (format) => `my-lib.${format}.js`,
  },
  rolldownOptions: {
    external: ['react', 'react-dom', 'react/jsx-runtime'],
  },
}
```

## TypeScript Build Pipeline

- Run `tsc --noEmit` in CI to catch type errors independently of the bundler. Do not rely on the bundler's transpile step to surface type issues.
- In project-reference monorepos, prefer the non-emitting solution check command rather than invoking `tsc -b` in build mode blindly — build mode emits output files and may be slow.
- Configure type coverage via `tsconfig.json` strict mode: `"strict": true` enables `strictNullChecks`, `noImplicitAny`, `strictFunctionTypes`, and several others. Do not relax these settings without explicit justification.
