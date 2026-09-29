# Ktor Patterns

- Define the application as a module function (`fun Application.module()`) and wire plugins there. This keeps the application testable with `testApplication { }` without starting a real server.
- Group routes with `route("/api/v1") { }` blocks and protect authenticated routes with `authenticate("jwt") { }` blocks. Keep each route handler short — delegate to a service class for anything beyond request parsing and response mapping.

```kotlin
fun Application.configureRouting(userService: UserService) {
    routing {
        route("/api/users") {
            authenticate("jwt") {
                get { call.respond(userService.getAll()) }
                post {
                    val body = call.receive<CreateUserRequest>()
                    require(body.name.isNotBlank()) { "name is required" }
                    call.respond(HttpStatusCode.Created, userService.create(body))
                }
            }
        }
    }
}
```

- Install `ContentNegotiation` with `json()` (kotlinx.serialization). Mark all request/response classes `@Serializable`. For types that kotlinx.serialization cannot handle automatically (e.g., `Instant`), write a custom `KSerializer`.
- Install `StatusPages` to convert domain exceptions into HTTP responses. Map `ContentTransformationException` → 400, `IllegalArgumentException` → 400, `AuthenticationException` → 401, and `Throwable` → 500 with a generic message logged server-side. Never let raw exceptions reach the client.
- Configure CORS with `install(CORS) { allowHost("app.example.com", schemes = listOf("https")); allowHeader(HttpHeaders.Authorization) }`. Never allow all hosts (`allowHost("*")`) in production.
- Wire dependency injection with Koin. Define a `module { }` with `single { }` for singletons and `factory { }` for per-call instances. In route handlers, inject with `val service: UserService by inject()`.
- Authenticate with JWT: configure a JWT plugin with the JWKS endpoint or secret key. Extract claims from `call.principal<JWTPrincipal>()`. Validate expiry, issuer, and audience in the JWT verifier.
- Validate request bodies with `require(condition) { "message" }` at the top of each handler. Return 400 for missing/invalid fields. The `StatusPages` handler will catch `IllegalArgumentException` thrown by `require`.
- Test routes with `testApplication { }`. Override the module function to inject fakes or mocks. Use `client.get("/api/users")` and assert on `response.status` and `response.body<T>()`.
- Use Ktor's WebSocket support for real-time endpoints. Maintain a thread-safe connection registry (`val connections = Collections.synchronizedSet(LinkedHashSet<DefaultWebSocketSession>())`). Send to all connections and remove stale sessions on close.
