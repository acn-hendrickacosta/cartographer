# Spring Boot Patterns

- Controllers are thin HTTP adapters. Annotate with `@RestController` + `@RequestMapping`, declare the service dependency via constructor, validate inputs with `@Valid`, delegate to service, and map the result to a response DTO. No business logic in controllers.

```java
@RestController
@RequestMapping("/api/markets")
@Validated
class MarketController {
    private final MarketService marketService;

    MarketController(MarketService marketService) {
        this.marketService = marketService;
    }

    @PostMapping
    ResponseEntity<MarketResponse> create(@Valid @RequestBody CreateMarketRequest req) {
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(MarketResponse.from(marketService.create(req)));
    }
}
```

- Services own `@Transactional` boundaries. Mark write methods with `@Transactional` and read methods with `@Transactional(readOnly = true)`. Do not put `@Transactional` on controllers or repositories.
- Use Spring Data JPA repositories. Prefer derived query methods for simple lookups and `@Query` with JPQL/named parameters for complex queries. Never write native SQL with string concatenation.
- Handle all exceptions centrally with `@RestControllerAdvice`. Map `MethodArgumentNotValidException` → 400, domain not-found exceptions → 404, `AccessDeniedException` → 403, and unexpected exceptions → 500 with a generic message logged server-side.
- Enable `spring.mvc.problemdetails.enabled=true` (Spring Boot 3+) to emit RFC 7807 `application/problem+json` error responses automatically.
- Cache with `@Cacheable(value = "...", key = "#id")` on service methods. Require `@EnableCaching` on a configuration class. Use `@CacheEvict` on mutation methods. Configure a real cache backend (Redis, Caffeine) — not the default in-memory map for production.
- Use `@Async` for fire-and-forget background work. Require `@EnableAsync` on a configuration class. Configure a `ThreadPoolTaskExecutor` bean to control pool sizes and queue depth rather than relying on the default unbounded executor.
- Log with SLF4J: `private static final Logger log = LoggerFactory.getLogger(MyClass.class)`. Log key=value pairs for machine-parseable logs. Use Logback with a JSON encoder in production.
- Implement middleware as `OncePerRequestFilter` subclasses. This is the correct extension point for request logging, rate limiting, authentication, and correlation ID injection.
- Configure HikariCP connection pool explicitly: set `maximumPoolSize`, `connectionTimeout`, `idleTimeout`, `maxLifetime`, and `leak-detection-threshold`. Do not rely on defaults for production workloads.
- Wire Micrometer metrics and OpenTelemetry tracing from day one. Expose `/actuator/health`, `/actuator/metrics`, and `/actuator/prometheus`. Add `@Observed` or `Observation` instrumentation to service methods for distributed traces.
