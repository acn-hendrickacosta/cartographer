# Java Security

- Never hardcode secrets (API keys, DB credentials, JWT signing keys, tokens) in source code or `application.yml`. Use environment variable placeholders (`${DB_PASSWORD}`) and load real values from a secrets manager (HashiCorp Vault, AWS Secrets Manager) at startup. Fail fast if a required secret is missing.
- Prevent SQL injection: use Spring Data derived queries, JPQL with named parameters, or native queries with `:param` bindings. Never concatenate user input into query strings.

```java
// BAD
@Query(value = "SELECT * FROM users WHERE name = '" + name + "'", nativeQuery = true)

// GOOD
@Query(value = "SELECT * FROM users WHERE name = :name", nativeQuery = true)
List<User> findByName(@Param("name") String name);
```

- Validate all controller input with Bean Validation (`@Valid` on the parameter, constraints on the DTO). Apply `@NotBlank`, `@Email`, `@Size`, `@Min`/`@Max`. Sanitize HTML fields with a DOMPurify-equivalent allowlist before persisting.
- Hash passwords with `BCryptPasswordEncoder(12)` or Argon2. Never store plaintext passwords or use MD5/SHA1. Use Spring Security's `PasswordEncoder` bean, not ad-hoc hashing.
- Implement JWT authentication with `OncePerRequestFilter`. Enable method-level authorization with `@EnableMethodSecurity` and `@PreAuthorize("hasRole('ADMIN')")` or expression-based rules (`@PreAuthorize("@authz.isOwner(#id, authentication)")`). Deny by default — every sensitive path needs an explicit guard.
- Configure CSRF: disable it for pure REST APIs using stateless JWT (`csrf.disable()` + `SessionCreationPolicy.STATELESS`). For session-based apps (browser forms), keep CSRF enabled and include the token in forms/headers.
- Configure CORS at the security filter level, not per-controller. Restrict `allowedOrigins` to your actual domains — never use `*` in production. Set `allowCredentials(true)` only when needed.
- Set security response headers: Content-Security-Policy (`default-src 'self'`), X-Frame-Options (SAMEORIGIN), HSTS, and Referrer-Policy. Configure them in the Spring Security `headers()` customizer.
- Rate-limit expensive or authentication endpoints with Bucket4j. Use `request.getRemoteAddr()` for client IP — only trust `X-Forwarded-For` when `ForwardedHeaderFilter` is registered and your proxy overwrites (not appends) the header.
- Run OWASP Dependency-Check or Snyk in CI. Fail builds on known CVEs. Keep Spring Boot and Spring Security on supported releases.
- Never log secrets, tokens, passwords, credit card numbers, or PII. Use structured JSON logging. Redact sensitive fields before they reach the log appender.
- Error responses must never expose stack traces, internal class names, or SQL errors to clients. Return generic messages (e.g., "Internal server error") and log the full detail server-side.
