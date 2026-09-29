# Java Architecture Patterns

- Follow a three-layer architecture: `@RestController` (HTTP boundary) → `@Service` (business logic, transactions) → `@Repository` (data access). Business logic belongs in services, not controllers. Controllers validate input and delegate; services are where rules live.
- Use constructor injection everywhere. Declare service dependencies as `private final` fields, initialize them in the constructor. Lombok's `@RequiredArgsConstructor` is acceptable shorthand.
- DTOs are `record` types. Use a static factory method `from(Entity entity)` or `from(DomainModel model)` to map to the DTO — keep mapping logic in the DTO itself, not in services.

```java
public record MarketResponse(Long id, String name, MarketStatus status) {
    static MarketResponse from(Market market) {
        return new MarketResponse(market.id(), market.name(), market.status());
    }
}
```

- Validate all incoming request bodies with Bean Validation on the DTO and `@Valid` on the controller parameter. Apply `@NotBlank`, `@Email`, `@Size`, `@NotNull`, `@Min`/`@Max` directly on `record` components.
- Handle exceptions centrally with `@RestControllerAdvice` (Spring) or `ExceptionMapper` (Quarkus/Jakarta). Never let raw `Exception` propagate to the response. Map domain exceptions to appropriate HTTP status codes: `NotFoundException` → 404, validation failures → 400, access denied → 403.
- Use sealed classes to model closed domain state hierarchies (e.g., `sealed interface OrderStatus permits Draft, Submitted, Fulfilled, Cancelled`). Pattern-matching switch on sealed types is exhaustive and compiler-checked.
- Paginate all list endpoints. Accept `page` and `size` query parameters, return `Page<T>` or a custom envelope containing total count and items. Never return an unbounded list from an API.
- Apply `@Transactional(readOnly = true)` to all read-only service methods. This enables database optimizations and prevents accidental writes in query paths.
- Never expose JPA/Hibernate `@Entity` classes directly in HTTP responses. Entities contain lazy-loaded associations, version fields, and internal state that should not leak to clients. Always map to a record DTO before returning.
