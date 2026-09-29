# Rust Tooling

## Formatting

- `cargo fmt` before every commit. Use `cargo fmt --check` in CI to fail the build if formatting is wrong. No style debates — rustfmt decides.

## Linting

- `cargo clippy -- -D warnings` in CI. Clippy warnings are treated as errors. Address each warning at the source — do not suppress with `#[allow(...)]` unless there is a justified, commented reason.
- `cargo check` for fast compilation checks during development. It runs the type checker without producing a binary, making it faster than a full build.

## Security

- `cargo audit` to scan dependencies for known CVEs. Run regularly in CI.
- `cargo deny check` to enforce license compliance and advisory policies. Commit a `deny.toml` to configure allowed licenses and restricted advisories.

## Dependency Management

- `cargo tree` to inspect the full dependency graph.
- `cargo tree -d` to find duplicate crate versions (common source of binary bloat and subtle version conflicts).
- `cargo update -p <crate>` to update a single dependency (preferred over `cargo update` which changes everything at once).
- Keep `Cargo.lock` committed for applications; do not commit it for libraries.

## Testing

```bash
cargo test                          # Run all tests
cargo test -- --nocapture           # Show println output
cargo test -p specific_crate        # Test a single workspace crate
cargo bench                         # Run Criterion benchmarks
cargo llvm-cov --fail-under-lines 80 # Coverage gate (requires cargo-llvm-cov)
```

## Build

```bash
cargo build              # Debug build
cargo build --release    # Optimized build (required for benchmarks and profiling)
cargo check              # Type-check without codegen (fast feedback loop)
```

## CI Sequence

Run these checks in order — fail fast on formatting before running the full test suite:

```bash
cargo fmt --check
cargo clippy -- -D warnings
cargo test
cargo audit
```
