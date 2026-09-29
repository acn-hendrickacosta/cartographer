# Java Testing

- Use JUnit 5 + AssertJ + Mockito as the standard test stack. Prefer AssertJ's `assertThat(...)` over JUnit's built-in assertions for readable failure messages. Use `assertThatThrownBy(() -> ...)` to test exceptions.
- Organize tests by layer: unit tests with `@ExtendWith(MockitoExtension.class)` for services and domain logic; web layer tests with `@WebMvcTest`; full integration tests with `@SpringBootTest`; persistence tests with `@DataJpaTest`.

```java
@ExtendWith(MockitoExtension.class)
class MarketServiceTest {
    @Mock MarketRepository repo;
    @InjectMocks MarketService service;

    @Test
    void createsMarket() {
        when(repo.save(any())).thenAnswer(inv -> inv.getArgument(0));
        Market result = service.create(new CreateMarketRequest("name", "desc", ...));
        assertThat(result.name()).isEqualTo("name");
        verify(repo).save(any());
    }
}
```

- Web layer tests use `@WebMvcTest(MyController.class)` + `@MockBean` for service dependencies. Test HTTP contract (status codes, response shape, validation rejections), not business logic.
- Persistence tests use `@DataJpaTest` with `@AutoConfigureTestDatabase(replace = NONE)` and Testcontainers to run against the real database engine. This catches schema/query problems that H2 emulation hides.
- Follow Arrange-Act-Assert structure in every test. Each test asserts one logical outcome. Use `@ParameterizedTest` with `@MethodSource` or `@CsvSource` for covering multiple input variants without duplicating test bodies.
- Name tests descriptively: either given/when/then or plain English describing the scenario (`returns_empty_page_when_no_active_markets`). Use `@DisplayName` for human-readable output in CI reports.
- Build test data with builder classes or factory methods, not inline `new Entity()` calls scattered across tests. A `MarketBuilder` class with sensible defaults keeps tests readable and resilient to constructor changes.
- Enforce 80%+ line coverage with JaCoCo. Configure the Maven Surefire/JaCoCo plugin to generate reports and fail the build below the threshold. Run `mvn verify` in CI, not just `mvn test`.
- For Quarkus projects: use `@QuarkusTest` for integration tests with REST Assured for HTTP assertions. Use `@TestProfile` to supply test-only config overrides. Test Camel routes with `AdviceWith` and `MockEndpoint` to intercept route steps.
- Keep tests fast and isolated. Avoid `Thread.sleep` — use `CompletableFuture` result waits or Awaitility. Avoid shared mutable state between test cases; reinitialize state in `@BeforeEach`.
