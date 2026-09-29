# Vue 3 Security

- `v-html` is a direct XSS vector. Never bind `v-html` to user-supplied content without sanitizing with DOMPurify using a restrictive allowlist first. The same risk applies to `h()` with `innerHTML` in render functions.
- Validate URL schemes before binding to `:href` or `:src`. The `javascript:` scheme executes as script when the user clicks the link. Check that the scheme is `https:` or `http:` before binding.
- `:style` with user-controlled values enables CSS injection attacks, including content exfiltration via `url()`. Sanitize or reject style values that contain `url(`, `expression(`, or other dangerous constructs.
- Templates must come from trusted sources. Never compile templates at runtime from user input (`Vue.compile(userInput)` or the `template` option with user data). This turns any XSS into arbitrary code execution.
- `VITE_*` environment variables are bundled into the client build. Never put API secrets, service account keys, or tokens in `VITE_*` variables. Use server-side environment variables for anything that must stay secret.
- Session tokens and auth tokens belong in `httpOnly` cookies managed by the server, not in `localStorage` or `sessionStorage`. Tokens in web storage are accessible to any JavaScript on the page, including injected scripts.
- Never persist raw auth tokens to `localStorage`. If client-side token storage is required, use `sessionStorage` at minimum and combine with anti-CSRF measures.
- For Nuxt: server-only config goes in `runtimeConfig` (not `runtimeConfig.public`). Values under `runtimeConfig.public` are sent to the client. API secrets, database credentials, and signing keys must be server-only.
