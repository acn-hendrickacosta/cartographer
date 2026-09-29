# Rust Testing

## Test Organization

- Unit tests go inside `#[cfg(test)]` modules in the same source file as the code they test. This gives them access to private items.
- Integration tests go in the `tests/` directory. Each file is compiled as a separate binary. Shared utilities go in `tests/common/mod.rs`.
- Benchmarks go in `benches/` using Criterion.

```text
my_crate/
├── src/
│   ├── lib.rs              # #[cfg(test)] mod tests { ... }
│   └── orders/service.rs   # #[cfg(test)] mod tests { ... }
├── tests/
│   ├── api_test.rs
│   └── common/mod.rs       # Shared test helpers
└── benches/benchmark.rs
```

## Test Framework

- `#[test]` with `#[cfg(test)]` modules for unit tests.
- `rstest` for parameterized tests and fixtures.
- `proptest` for property-based testing of invariants.
- `mockall` for generating mocks from traits.
- `#[tokio::test]` for async tests.

## Unit Tests

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn creates_user_with_valid_email() {
        let user = User::new("Alice", "alice@example.com").unwrap();
        assert_eq!(user.name, "Alice");
    }

    #[test]
    fn rejects_invalid_email() {
        let result = User::new("Bob", "not-an-email");
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("invalid email"));
    }
}
```

Use `assert_eq!` over `assert!` where possible — it prints both values on failure. Prefer `?` in tests returning `Result` for cleaner output.

## Parameterized Tests (rstest)

```rust
use rstest::rstest;

#[rstest]
#[case("hello", 5)]
#[case("", 0)]
#[case("rust", 4)]
fn test_string_length(#[case] input: &str, #[case] expected: usize) {
    assert_eq!(input.len(), expected);
}
```

## Async Tests

```rust
#[tokio::test]
async fn fetches_data_successfully() {
    let client = TestClient::new().await;
    let result = client.get("/data").await;
    assert!(result.is_ok());
}
```

Never use `std::thread::sleep` in async tests. Use `tokio::time::sleep` or `tokio::time::pause` for timer-controlled scenarios.

## Testing Result and Panic

```rust
#[test]
fn returns_error_for_invalid_input() -> Result<(), Box<dyn std::error::Error>> {
    let result = parse_config("}{invalid");
    assert!(matches!(result, Err(ConfigError::ParseError(_))));
    Ok(())
}

#[test]
#[should_panic(expected = "index out of bounds")]
fn panics_on_empty_slice() {
    let v: Vec<i32> = vec![];
    let _ = v[0];
}
```

Prefer testing `Result::is_err()` over `#[should_panic]` when the function returns `Result`.

## Mocking (mockall)

Define traits in production code; generate mocks in test modules with `#[automock]` or `mockall::mock!`:

```rust
use mockall::{automock, predicate::eq};

#[automock]
pub trait UserRepository {
    fn find_by_id(&self, id: u64) -> Option<User>;
}

#[test]
fn service_returns_user_when_found() {
    let mut mock = MockUserRepository::new();
    mock.expect_find_by_id()
        .with(eq(42))
        .times(1)
        .returning(|_| Some(User { id: 42, name: "Alice".into() }));

    let service = UserService::new(Box::new(mock));
    assert_eq!(service.get_user(42).unwrap().name, "Alice");
}
```

## Property-Based Testing (proptest)

Use `proptest` for invariant testing — the framework generates random inputs to try to falsify the property:

```rust
use proptest::prelude::*;

proptest! {
    #[test]
    fn encode_decode_roundtrip(input in ".*") {
        let encoded = encode(&input);
        let decoded = decode(&encoded).unwrap();
        prop_assert_eq!(input, decoded);
    }
}
```

## Test Helpers

Write helper functions for repeated setup. There is no `t.Helper()` equivalent in Rust, but clear function names serve the same purpose:

```rust
#[cfg(test)]
mod tests {
    fn make_user(name: &str) -> User {
        User::new(name, &format!("{name}@test.com")).unwrap()
    }
}
```

## Doc Tests

Write runnable examples in `///` documentation. They serve as both documentation and tests:

```rust
/// Adds two numbers.
///
/// ```
/// assert_eq!(my_crate::add(2, 3), 5);
/// ```
pub fn add(a: i32, b: i32) -> i32 { a + b }
```

## Benchmarking (Criterion)

```toml
[dev-dependencies]
criterion = { version = "0.5", features = ["html_reports"] }

[[bench]]
name = "benchmark"
harness = false
```

```rust
use criterion::{black_box, criterion_group, criterion_main, Criterion};

fn bench_process(c: &mut Criterion) {
    c.bench_function("process 1k", |b| b.iter(|| process(black_box(&data))));
}

criterion_group!(benches, bench_process);
criterion_main!(benches);
```

## Coverage (cargo-llvm-cov)

```bash
cargo llvm-cov                        # Summary
cargo llvm-cov --html                 # HTML report
cargo llvm-cov --fail-under-lines 80  # CI gate
```

Target 80%+ line coverage for general code, 90%+ for public APIs, 100% for critical business logic. Exclude generated code and FFI bindings.

## Testing Commands

```bash
cargo test                        # Run all tests
cargo test -- --nocapture         # Show println output
cargo test test_name              # Run tests matching pattern
cargo test --lib                  # Unit tests only
cargo test --test api_test        # Specific integration test
cargo test --doc                  # Doc tests only
cargo test -- --ignored           # Run tests marked #[ignore]
```

## Best Practices

- Write tests before implementation (TDD).
- Test behavior through the public API — do not test private functions directly.
- Keep tests independent — no shared mutable state between tests.
- Use descriptive names that explain the scenario: `creates_user_with_valid_email`, `rejects_order_when_insufficient_stock`.
- Fix flaky tests immediately. A flaky test that is quarantined with `#[ignore]` is acceptable only as a short-term measure while the fix is in progress.
