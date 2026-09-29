# Go Testing

## Core Approach

- Write tests before implementation (TDD). Start with a failing test that documents the expected behavior, then implement the minimum code to pass it.
- Use table-driven tests as the default pattern for any function with multiple input/output scenarios. They make coverage gaps obvious and reduce test code duplication.
- Always run tests with the race detector in CI: `go test -race ./...`. The race detector catches data races that would be otherwise non-deterministic.
- Target 80%+ coverage for general code, 90%+ for public APIs, and 100% for critical business logic. Exclude generated code.

## Table-Driven Tests

```go
func TestAdd(t *testing.T) {
    tests := []struct {
        name     string
        a, b     int
        expected int
    }{
        {"positive numbers", 2, 3, 5},
        {"negative numbers", -1, -2, -3},
        {"zero values", 0, 0, 0},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got := Add(tt.a, tt.b)
            if got != tt.expected {
                t.Errorf("Add(%d, %d) = %d; want %d", tt.a, tt.b, got, tt.expected)
            }
        })
    }
}
```

For error cases, include a `wantErr bool` field and assert `err == nil` / `err != nil` accordingly.

## Subtests and Parallel Tests

- Organize related test scenarios as subtests with `t.Run(name, func(t *testing.T) {...})`. Shared setup (e.g., a test database) can live in the parent test.
- Mark independent subtests with `t.Parallel()` to speed up the suite. Always capture loop variables before calling `t.Parallel()`: `tt := tt`.

## Test Helpers

- Mark helper functions with `t.Helper()` so failure messages show the caller's line, not the helper's.
- Register cleanup with `t.Cleanup(func() {...})` instead of `defer` for resource teardown — it works correctly with parallel subtests.
- Use `t.TempDir()` for test files — the directory is automatically removed when the test finishes.

```go
func setupTestDB(t *testing.T) *sql.DB {
    t.Helper()
    db, err := sql.Open("sqlite3", ":memory:")
    if err != nil {
        t.Fatalf("open db: %v", err)
    }
    t.Cleanup(func() { db.Close() })
    return db
}
```

## Interface-Based Mocking

Define interfaces for dependencies in the consumer package; write struct mocks in test files. This avoids third-party mock frameworks for simple cases:

```go
type MockUserRepo struct {
    GetUserFunc func(id string) (*User, error)
}
func (m *MockUserRepo) GetUser(id string) (*User, error) { return m.GetUserFunc(id) }
```

## HTTP Handler Testing

Use `net/http/httptest` — no running server required:

```go
req := httptest.NewRequest(http.MethodGet, "/users/123", nil)
w := httptest.NewRecorder()
handler.ServeHTTP(w, req)

if w.Code != http.StatusOK {
    t.Errorf("status = %d; want %d", w.Code, http.StatusOK)
}
```

## Benchmarks

```go
func BenchmarkProcess(b *testing.B) {
    data := generateTestData(1000)
    b.ResetTimer()
    for i := 0; i < b.N; i++ {
        Process(data)
    }
}
// go test -bench=BenchmarkProcess -benchmem ./...
```

Call `b.ResetTimer()` after any expensive setup. Use `-benchmem` to see allocation counts.

## Fuzzing (Go 1.18+)

Write fuzz tests for input-parsing code. Add seed corpus entries that cover the main formats, then let the fuzzer explore mutations:

```go
func FuzzParseConfig(f *testing.F) {
    f.Add(`{"port": 8080}`)
    f.Add(`{}`)
    f.Fuzz(func(t *testing.T, input string) {
        cfg, err := ParseConfig(input)
        if err != nil {
            return
        }
        // If parsing succeeded, round-tripping should not fail
        _, err = json.Marshal(cfg)
        if err != nil {
            t.Errorf("marshal after parse: %v", err)
        }
    })
}
// go test -fuzz=FuzzParseConfig -fuzztime=60s
```

## Coverage Commands

```bash
go test -race -cover ./...
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out     # Browse line-by-line coverage
go tool cover -func=coverage.out     # Per-function summary
```

## Best Practices

- Test behavior through the public API — do not call unexported functions directly.
- Never use `time.Sleep` in tests. Use channels, `sync.WaitGroup`, or condition checks.
- Fix or remove flaky tests immediately — a flaky test is worse than no test.
- Test names should read as sentences: `TestValidateEmail_rejectsEmptyInput` is clearer than `TestValidateEmail2`.
