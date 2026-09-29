# Java Code Review Criteria

## Critical — Block Approval

- **SQL injection**: any query built by concatenating user input — in Spring (`@Query` with string concat) or Quarkus (Panache `find("name = " + input)`). Must use parameterized bindings.
- **Command injection**: `ProcessBuilder` or `Runtime.exec` with user-supplied arguments. Sanitize and validate, or use a whitelist of allowed commands.
- **Code injection**: `ScriptEngine.eval()` with user content. Never execute user-supplied code.
- **Path traversal**: file path operations accepting user input without `Path.normalize()` and a prefix check against an allowed root.
- **Hardcoded secrets**: API keys, passwords, JWT signing keys in source code or committed property files. Must be externalized to environment variables or a secrets manager.
- **PII or token logging**: logging user passwords, tokens, credit card numbers, or PII at any log level.
- **Missing `@Valid`**: controller methods accepting `@RequestBody` or `@RequestParam` without input validation — leaves the service layer exposed to malformed input.
- **CSRF disabled without documentation**: `csrf.disable()` is acceptable for stateless JWT APIs but must have a comment explaining the rationale; never silently disabled in a session-based app.
- **Swallowed exceptions**: empty `catch` blocks, or `catch` blocks that only log without rethrowing or handling properly.
- **`Optional.get()` without `isPresent()`**: will throw `NoSuchElementException` at runtime. Use `orElseThrow()` with a meaningful exception.
- **Missing `@RestControllerAdvice` or Quarkus `ExceptionMapper`**: unhandled exceptions leak stack traces to clients.
- **Wrong HTTP status codes**: returning 200 for an error, 500 for a client mistake, or 200 with an error body instead of an appropriate 4xx/5xx code.

## High — Strong Recommendation to Fix

- **Field injection** (`@Autowired` on a field): prevents immutability, makes unit testing difficult. Use constructor injection.
- **Business logic in controllers**: controllers must delegate to services. Domain rules, calculations, and decisions in a controller are an architectural violation.
- **`@Transactional` on the wrong layer**: transactions belong on service methods, not on controllers or repository implementations.
- **Entity exposed in HTTP response**: JPA entities in response bodies leak internal structure, can trigger lazy-loading exceptions, and break clients when the schema changes. Map to a DTO.
- **N+1 queries**: `FetchType.EAGER` on `@OneToMany` or `@ManyToMany`, or calling a method inside a loop that issues individual queries. Use JOIN FETCH or `@EntityGraph`.
- **Unbounded list queries**: returning `List<Entity>` from a query without pagination. Will OOM under load.
- **Missing `@Modifying`** on `@Query` UPDATE/DELETE methods.
- **`CascadeType.ALL` without justification**: usually too broad. Specify only the cascade operations that make semantic sense.
- **Mutable singleton fields**: `@ApplicationScoped` or `@Component` beans with non-final, non-thread-safe mutable fields. All singleton state must be thread-safe.
- **Blocking code on reactive/Quarkus I/O thread**: calling `Thread.sleep`, blocking I/O, or synchronous JDBC on the Vert.x event loop.
- **Quarkus `@Singleton` instead of `@ApplicationScoped`**: skips CDI proxying and breaks interceptors (`@Transactional`, `@Cacheable`).

## Medium — Worth Discussing

- Unbounded `@Async` / `@Scheduled` operations without thread pool configuration — can exhaust executor threads under load.
- MongoDB `listAll()` without pagination or criteria — will load the entire collection.
- Missing index on Panache MongoDB query fields — unindexed queries become table scans.
- Regex or expensive computation in a hot request path without caching.

## Approval Criteria

Any CRITICAL or HIGH finding blocks approval. The author must address the issue (fix, documented exception, or accepted risk with written justification) before the PR is merged.
