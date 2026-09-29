# JPA and Persistence

- Define indexes on `@Entity` classes explicitly: `@Table(name = "users", indexes = {@Index(name = "idx_users_email", columnList = "email")})`. Do not rely on the database to discover which columns need indexes.
- Use `@EntityListeners(AuditingEntityListener.class)` with `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, `@LastModifiedBy` to track audit fields automatically. Enable Spring Data auditing with `@EnableJpaAuditing`.
- Fetch strategy default is `LAZY` for all associations. `FetchType.EAGER` causes N+1 problems and is almost never correct. Only use EAGER for associations that are always required with the parent.
- Prevent N+1 queries by using JOIN FETCH in JPQL or `@EntityGraph` on repository methods when related entities are needed. Explicitly selecting required associations is the right pattern; Hibernate's lazy batching is a mitigation, not a substitute.

```java
@Query("select u from User u left join fetch u.orders where u.id = :id")
Optional<User> findByIdWithOrders(@Param("id") Long id);
```

- Use interface-based projections for read-only queries that return a subset of columns. This avoids loading the full entity when only a few fields are needed.

```java
public interface UserSummary {
    Long getId();
    String getName();
}
@Query("select u.id as id, u.name as name from User u where u.active = true")
List<UserSummary> findActiveSummaries();
```

- Annotate `@OneToMany` relationships with `orphanRemoval = true` when child entities have no independent lifecycle. Use `CascadeType.PERSIST` and `CascadeType.MERGE` explicitly — avoid `CascadeType.ALL` unless you have thought through each cascade operation.
- Mark `@Modifying` on all `@Query` methods that perform UPDATE or DELETE. Forgetting this annotation causes silent failures.
- Paginate all list queries with `Pageable`. Returning `List<Entity>` from unbounded queries will OOM under load. Accept `Pageable` as a repository parameter and return `Page<T>` or `Slice<T>`.
- Never use `spring.jpa.hibernate.ddl-auto=create` or `update` in production. Use Flyway or Liquibase for schema migrations. Migrations must be sequential, versioned, and committed alongside the code changes that require them.
- Configure HikariCP for your workload: `maximumPoolSize`, `connectionTimeout` (30s), `idleTimeout` (600s), `maxLifetime` (1800s). Set `leak-detection-threshold` to catch connection leaks in dev/staging.
- Test repository and persistence logic with `@DataJpaTest` + `@AutoConfigureTestDatabase(replace = NONE)` + Testcontainers. This tests real SQL against the same database engine as production, catching schema and query issues that H2 emulation hides.
