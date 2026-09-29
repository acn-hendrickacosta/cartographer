# Java Coding Style

- Use google-java-format for all Java source files. Enforce in CI with `mvn fmt:check` or a Spotless plugin step so formatting is never a review concern.
- Prefer immutability: use `record` for value objects and DTOs, `final` fields for all class members, and defensive copies when accepting mutable types (`List.copyOf`, `new ArrayList<>(input)`).
- Naming: `PascalCase` for classes/interfaces/enums, `camelCase` for methods and fields, `SCREAMING_SNAKE_CASE` for constants, plural names for collections (`userIds`, not `userId`). Interface names describe capability (`Readable`, `UserRepository`), not "IUserRepository".
- Embrace modern Java: use `record` instead of data classes with boilerplate getters, sealed classes to model closed hierarchies, pattern-matching switch expressions, and text blocks for multi-line SQL, JSON, or HTML. Never build SQL or JSON by string concatenation.
- Use `Optional` as a return type when a method may legitimately return nothing. Never use `Optional` as a field type, parameter type, or inside collections — it signals "this might not exist" at API boundaries only.
- Error handling: use checked exceptions for expected, recoverable failures the caller must handle. Use unchecked (runtime) exceptions for programming errors. Never swallow exceptions with an empty `catch` block. Always log or rethrow.
- Streams: prefer streams for transforming collections; keep pipelines short and readable. Avoid side effects in intermediate operations (`map`, `filter`). Assign `Collector` results to clearly-named variables rather than chaining collectors inline.
- Limit method length to ~30 lines. Methods doing more than one thing should be extracted. Avoid deeply nested conditionals — guard clauses and early returns flatten the control flow.
- Constructor injection is the only acceptable DI style. Field injection with `@Autowired` is banned. Setter injection is acceptable only for optional dependencies with defaults.
- Log with SLF4J (`LoggerFactory.getLogger(MyClass.class)`). Use structured key=value format in messages: `log.info("create_user userId={}", id)`. Never log secrets, tokens, or PII.
