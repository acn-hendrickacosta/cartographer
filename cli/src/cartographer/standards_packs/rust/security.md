# Rust Security

## Secrets Management

- Never hardcode API keys, tokens, or credentials in source code.
- Load secrets from environment variables using `std::env::var`. Validate at startup and fail fast if required secrets are missing:

```rust
fn load_api_key() -> anyhow::Result<String> {
    std::env::var("PAYMENT_API_KEY")
        .context("PAYMENT_API_KEY must be set")
}
```

- Keep `.env` files in `.gitignore`. Use a secrets manager in production.

## SQL Injection

- Never format user input into SQL strings. Use parameterized queries with your database library. Placeholder syntax varies by backend: `$1` for Postgres (sqlx/diesel), `?` for MySQL and SQLite.

```rust
// BAD — SQL injection via format string
let query = format!("SELECT * FROM users WHERE name = '{name}'");
sqlx::query(&query).fetch_one(&pool).await?;

// GOOD — parameterized with sqlx (Postgres)
sqlx::query("SELECT * FROM users WHERE name = $1")
    .bind(&name)
    .fetch_one(&pool)
    .await?;
```

## Input Validation

- Validate all user input at system boundaries before processing.
- Use the type system to enforce invariants — the "parse, don't validate" principle. Convert unstructured data into typed structs at the entry point so the rest of the code works with valid values:

```rust
pub struct Email(String);

impl Email {
    pub fn parse(input: &str) -> Result<Self, ValidationError> {
        let trimmed = input.trim();
        if !trimmed.contains('@') || trimmed.len() > 254 {
            return Err(ValidationError::InvalidEmail(input.to_string()));
        }
        Ok(Self(trimmed.to_string()))
    }
}
```

For production use, prefer a validated crate like `email_address` rather than hand-rolled parsing.

## Unsafe Code

- Every `unsafe` block must have a `// SAFETY:` comment documenting all invariants that must hold for the block to be sound.
- Never use `unsafe` to bypass the borrow checker. A borrow checker error is a signal to rethink ownership.
- Minimize the scope of `unsafe` — the block should be as small as possible.
- Audit all `unsafe` code during code review. Absence of a `// SAFETY:` comment is grounds for blocking a PR.

```rust
// GOOD — safety comment documents ALL required invariants
let widget: &Widget = {
    // SAFETY: `ptr` is non-null, aligned, points to an initialized Widget,
    // and no mutable references or mutations exist for its lifetime.
    unsafe { &*ptr }
};
```

## Dependency Security

- Run `cargo audit` regularly to check for known CVEs in dependencies.
- Run `cargo deny check` to enforce license compliance and advisory policies. Commit a `deny.toml` to the repository.
- Use `cargo tree` to review the transitive dependency graph before adding a new crate.
- Keep dependencies updated — use Dependabot or Renovate to automate pull requests.
- Minimize the number of dependencies; evaluate every new crate for maintenance health and supply-chain risk.

```bash
cargo audit                  # CVE scan
cargo deny check             # License and advisory compliance
cargo tree                   # Full dependency tree
cargo tree -d                # Show duplicate crate versions
```

## Error Messages

- Never expose internal error messages, stack traces, database errors, or file paths in API responses.
- Log detailed errors server-side with `tracing::error!` or `log::error!`; return a generic message to clients.

```rust
// Map errors to appropriate HTTP status and safe message
match order_service.find_by_id(id) {
    Ok(order) => Ok(Json(order)),
    Err(ServiceError::NotFound(_)) => {
        tracing::info!(order_id = id, "order not found");
        Err((StatusCode::NOT_FOUND, "Resource not found"))
    }
    Err(e) => {
        tracing::error!(order_id = id, error = %e, "unexpected error");
        Err((StatusCode::INTERNAL_SERVER_ERROR, "Internal server error"))
    }
}
```
