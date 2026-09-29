# React Security

## dangerouslySetInnerHTML

- Treat every `dangerouslySetInnerHTML` usage as a security-critical code review point. The prop name is intentional — it is dangerous.
- Always render user content as text (`{userBio}`) or via a markdown library that sanitizes internally.
- When raw HTML is genuinely required, sanitize with DOMPurify at the same call site using an allowlist, not a denylist.

```tsx
// Critical: unsanitized user input
<div dangerouslySetInnerHTML={{ __html: userBio }} />

// Correct options:
<div>{userBio}</div>                           // render as text
<ReactMarkdown>{userBio}</ReactMarkdown>        // sanitizing markdown lib

import DOMPurify from 'isomorphic-dompurify'
<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(userBio) }} />
```

For every `dangerouslySetInnerHTML` in a PR: document whether the input is user-derived, confirm sanitization is at the same call site, and confirm the sanitizer config uses an allowlist.

## Unsafe URL Schemes

- `javascript:` and `data:` URLs in `href`, `src`, or `xlink:href` execute arbitrary code. React warns about `javascript:` in dev but does not block it at runtime.
- Validate URL scheme before rendering any user-supplied URL.

```tsx
function safeUrl(url: string): string | undefined {
  try {
    const parsed = new URL(url)
    if (['http:', 'https:', 'mailto:'].includes(parsed.protocol)) return url
  } catch {
    return undefined
  }
  return undefined
}
<a href={safeUrl(user.website)}>Visit</a>
```

## External Links

- Always add `rel="noopener noreferrer"` to `target="_blank"` links. Without it, the target page can access `window.opener` and redirect the parent. Do not rely on browser defaults.

```tsx
<a href={externalUrl} target="_blank" rel="noopener noreferrer">External</a>
```

## Server Action Input Validation

- Server Actions (`"use server"`) are public API endpoints. Validate every input with a schema validator. Authenticate and authorize inside the action — do not trust the client-side route guard.

```tsx
'use server'
import { z } from 'zod'

const Input = z.object({
  email: z.string().email(),
  age: z.number().int().min(0).max(120),
})

export async function updateUser(_state: unknown, formData: FormData) {
  const parsed = Input.safeParse({
    email: formData.get('email'),
    age: Number(formData.get('age')),
  })
  if (!parsed.success) return { error: parsed.error.flatten() }
  // authenticate → authorize → update
}
```

## Environment Variable Exposure

- Variables bundled into the client are public. Treat them as such.

| Framework | Client prefix | Keep server-only |
|---|---|---|
| Next.js | `NEXT_PUBLIC_*` | all others |
| Vite | `VITE_*` | server-side env only |
| Create React App | `REACT_APP_*` | all others |

- Never use a `NEXT_PUBLIC_*` variable for a private key, service secret, or token. Audit every PR that touches env vars.

## Authentication and Sessions

- Never store session tokens in `localStorage` or `sessionStorage` — any XSS can read them. Use httpOnly secure cookies.
- Never trust client-set state to gate sensitive UI. JSX render-gating hides elements; it does not prevent API access. The server must enforce authorization.
- CSRF: cookie-based auth requires CSRF tokens or `SameSite=Strict/Lax` cookies.

## Content Security Policy

- Configure a CSP server-side. Avoid `unsafe-inline` and `unsafe-eval` in `script-src`. For Next.js or Remix SSR with inline scripts, use per-request nonces — both frameworks support nonce injection.

```
default-src 'self';
script-src 'self' 'nonce-{REQUEST_NONCE}';
style-src 'self' 'unsafe-inline';
img-src 'self' data: https:;
connect-src 'self' https://api.example.com;
frame-ancestors 'none';
```

## Prototype Pollution

- Do not spread untrusted JSON directly into state or shared objects. An attacker-controlled `__proto__` key corrupts the object prototype for the entire process.

```tsx
// Wrong: attacker controls __proto__
const update = await req.json()
setState({ ...state, ...update })

// Correct: validate first
const Allowed = z.object({ name: z.string(), email: z.string().email() })
const parsed = Allowed.parse(await req.json())
setState({ ...state, ...parsed })
```

## Source Maps in Production

- Do not ship source maps publicly in production. Upload them to an error tracker (Sentry, Datadog) and strip them from the public bundle. Public source maps expose internal code structure and logic.

## Third-Party Components

- Run `npm audit` before adding any UI library. Check that the library does not internally use `dangerouslySetInnerHTML` on its input (common in rich text editors). Pin versions and review changelogs before major upgrades.
