# FastAPI

## Project structure

- Use an app factory function `create_app()` that returns a configured `FastAPI` instance. This makes the application testable and avoids import-time side effects.
- Organize as: `routers/` (HTTP routing), `schemas/` (Pydantic models), `services/` (business logic), `models/` (ORM models), `dependencies.py` (shared `Depends` functions), `config.py` (settings). Keep these layers separate.
- Keep routers thin. A route handler should call a service method, catch domain exceptions, and map them to HTTP responses. Database queries, password hashing, and conditional logic belong in the service layer.
- Configure settings with `pydantic-settings` `BaseSettings`. Settings are read from environment variables (and optionally a `.env` file) at startup. Do not pass raw `os.environ` calls throughout the codebase.

## Schemas and response models

- Separate request schemas (`UserCreate`), update schemas (`UserUpdate`), and response schemas (`UserResponse`). Never reuse the same schema for input and output.
- Always declare `response_model` on every endpoint that returns application data. Without it, FastAPI cannot validate or document the response shape, and internal fields may leak to callers.
- Never include passwords, password hashes, refresh tokens, access tokens, or internal auth state in a response schema.
- Use Pydantic field constraints (`Field(min_length=3, ge=0)`) instead of hand-written validation when Pydantic can express the rule.
- Use `model_validator(mode="after")` for cross-field validation (e.g., confirming two passwords match).

## Dependency injection

- Use `Depends()` for database sessions, authenticated users, pagination, and settings. Never create a `SessionLocal()` or long-lived client inside a route handler.
- Type-alias repeated `Annotated[...]` dependencies to reduce boilerplate and keep signatures readable:

```python
DbDep = Annotated[AsyncSession, Depends(get_db)]
ActiveUserDep = Annotated[User, Depends(get_current_active_user)]
```

- The `get_db` dependency should use an `async with` session context and roll back on exception. Session lifecycle should not leak into the handler.

## Async correctness

- Use `async def` for endpoints that perform I/O (database, HTTP, filesystem). Never call blocking I/O — `requests`, sync SQLAlchemy queries, `time.sleep`, blocking file reads — from an async route. These block the event loop and stall all concurrent requests.
- Use async database clients (e.g., SQLAlchemy `AsyncSession` with `asyncpg`) from async endpoints. The sync counterpart will deadlock under load.

## Security

- Keep CORS origins environment-specific. Never combine `allow_origins=["*"]` with `allow_credentials=True` — this is a security misconfiguration that browsers will reject and that enables cross-site credential exposure.
- Validate JWT claims defensively: check expiry, algorithm, issuer, and audience. Parse `sub` with a type assertion; do not trust that it is an integer without validating.
- Rate-limit auth endpoints (login, registration, password reset) and write-heavy endpoints. Do not expose brute-force targets.
- Redact authorization headers, cookies, tokens, and request/response bodies that may contain credentials from application logs.

## Testing

- Test with `httpx.AsyncClient` and `ASGITransport(app=app)` rather than a real server. This gives full async test support without network overhead.
- Override the exact dependency used by `Depends` in `app.dependency_overrides`. Target the dependency that the router imports, not a copy of it.
- Clear `app.dependency_overrides` in teardown (or use a fixture that yields and cleans up) to avoid state leaking between tests.
- Use an in-memory SQLite or a test-specific database with tables created and dropped per test session.

## Operational practices

- Enforce deterministic ordering on all paginated endpoints (e.g., `.order_by(Model.id)`). Without explicit ordering, offset pagination silently skips or repeats rows when the underlying set changes.
- Use `@asynccontextmanager` lifespan (not deprecated `on_event`) for startup and shutdown tasks such as connection pool initialization and cleanup.
- Use `IntegrityError` from the database driver to handle uniqueness violations atomically rather than a pre-check `SELECT` followed by an `INSERT`. Application-level prechecks are race-prone.
