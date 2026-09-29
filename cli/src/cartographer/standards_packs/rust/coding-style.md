# Rust Coding Style

## Formatting and Linting

- Run `cargo fmt` before every commit. Use `cargo fmt --check` in CI to enforce it. There is no style debate — rustfmt decides.
- Run `cargo clippy -- -D warnings` in CI. Clippy warnings are treated as errors; address them rather than suppressing with `#[allow(...)]` without justification.
- 4-space indent and a max line width of 100 characters are rustfmt defaults — commit a `rustfmt.toml` only if the project has a principled reason to deviate.

## Immutability

- Variables are immutable by default; use `let mut` only when mutation is required.
- Prefer returning a new value over mutating in place. This reduces aliasing and makes data flow explicit.
- Use `Cow<'_, T>` when a function may or may not need to allocate — it avoids unconditional cloning:

```rust
use std::borrow::Cow;

fn normalize(input: &str) -> Cow<'_, str> {
    if input.contains(' ') {
        Cow::Owned(input.replace(' ', "_"))
    } else {
        Cow::Borrowed(input)
    }
}
```

## Naming Conventions

- `snake_case` for functions, methods, variables, modules, and crate names.
- `PascalCase` for types, traits, enums, and type parameters.
- `SCREAMING_SNAKE_CASE` for constants and statics.
- Lifetimes: short lowercase names (`'a`, `'b`) for simple cases; descriptive names (`'input`, `'arena`) when multiple lifetimes interact.

## Ownership and Borrowing

- Borrow (`&T`) by default; take ownership only when the function needs to store or consume the value.
- Do not clone to satisfy the borrow checker without understanding why the borrow conflict exists. The root cause is usually a data model issue.
- Accept `&str` over `String` and `&[T]` over `Vec<T>` in function parameters. Use `impl Into<String>` in constructors that need to own a `String`.

```rust
// GOOD — borrows when ownership isn't needed
fn word_count(text: &str) -> usize {
    text.split_whitespace().count()
}

// GOOD — Into<String> lets callers pass &str or String
fn new(name: impl Into<String>) -> Self {
    Self { name: name.into() }
}
```

## Error Handling

- Use `Result<T, E>` and `?` for propagation. Never use `unwrap()` in production code paths — it panics on `Err`.
- **Libraries**: define typed errors with `thiserror` so callers can match on variants.
- **Applications**: use `anyhow` for flexible error context.
- Add call-site context with `.with_context(|| format!("failed to ..."))?`.
- Reserve `unwrap()` and `expect()` for tests and provably unreachable states. `expect("message")` is preferred over bare `unwrap()` because the message aids debugging.

```rust
// Library: typed, matchable errors
#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    #[error("failed to read config: {0}")]
    Io(#[from] std::io::Error),
    #[error("invalid config format: {0}")]
    Parse(String),
}

// Application: anyhow for flexible propagation
fn load_config(path: &str) -> anyhow::Result<Config> {
    let content = std::fs::read_to_string(path)
        .with_context(|| format!("failed to read {path}"))?;
    toml::from_str(&content)
        .with_context(|| format!("failed to parse {path}"))
}
```

## Iterators Over Loops

Prefer iterator chains for transformations; use explicit loops only when complex control flow (multiple early returns, mutable state) makes a chain unreadable.

```rust
// GOOD — declarative and composable
let active_emails: Vec<&str> = users.iter()
    .filter(|u| u.is_active)
    .map(|u| u.email.as_str())
    .collect();
```

## Module Organization

Organize by domain, not by type. Do not create `models/`, `services/`, `handlers/` top-level modules — instead, group by feature (`auth/`, `orders/`, `billing/`).

```text
src/
├── main.rs
├── lib.rs
├── auth/
│   ├── mod.rs
│   ├── token.rs
│   └── middleware.rs
└── orders/
    ├── mod.rs
    ├── model.rs
    └── service.rs
```

## Visibility

- Default to private. Use `pub(crate)` for sharing within the crate without exposing to external consumers.
- Only mark `pub` what belongs to the crate's public API.
- Re-export the public API from `lib.rs` so consumers have a stable import path.
