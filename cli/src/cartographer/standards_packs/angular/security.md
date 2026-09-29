# Angular Security

- Never call `bypassSecurityTrustHtml()`, `bypassSecurityTrustScript()`, `bypassSecurityTrustUrl()`, or any `bypassSecurityTrust*` method without a security review comment explaining why it's safe. These functions disable Angular's XSS protection. Prefer `sanitize(SecurityContext.HTML, value)` for HTML content that must be rendered.
- Only use `HttpClient` for HTTP requests — never raw `fetch()`. `HttpClient` participates in Angular's interceptor chain, enabling centralized auth token injection, error handling, and retry logic.
- Inject auth tokens in an `HttpInterceptorFn`, not in individual service calls. Store tokens in memory (a signal or BehaviorSubject), not in `localStorage` or `sessionStorage`, to prevent XSS token theft.
- Never log HTTP responses that may contain authentication tokens, personal data, or session identifiers.
- Environment files (`environment.ts`) are for configuration shape, not real secrets. Anything in `environment.ts` ships to the browser. Real API keys, signing secrets, and credentials belong server-side or in a secrets manager.
- Every authenticated or role-restricted route must have a `canMatch` guard. Relying on UI hiding alone (an `@if` in a template) is not access control.
- For SSR: never expose server-side environment variables through `TransferState`. Gate browser-only APIs with `isPlatformBrowser()`. Use server-side CSP nonces for inline scripts rather than `'unsafe-inline'`.
- Validate and sanitize URL bindings: `:href` with `javascript:` executes as JavaScript. Use Angular's `SafeUrl` type or validate the scheme before binding. Same for `:src` bindings to user-supplied URLs.
- Configure Content Security Policy server-side. Use nonces for any inline scripts. Do not rely on Angular's template sanitization alone — CSP is a defense-in-depth layer.
