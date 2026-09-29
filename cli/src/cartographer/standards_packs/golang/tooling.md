# Go Tooling

## Formatting

- `gofmt -w .` and `goimports -w .` must pass on every commit. Configure them as editor post-save hooks and enforce in CI. `goimports` is a superset of `gofmt` that also manages import grouping.

## Static Analysis

- Run `go vet ./...` as part of CI — it catches real bugs (misformatted printf verbs, unreachable code, suspicious composite literals).
- Run `staticcheck ./...` for extended analysis beyond `go vet` (deprecated API usage, ineffective assignments, unnecessary type assertions).
- Run `golangci-lint run` for a comprehensive linter suite. Commit a `.golangci.yml` to lock the enabled linters and configuration:

```yaml
linters:
  enable:
    - errcheck
    - gosimple
    - govet
    - ineffassign
    - staticcheck
    - unused
    - gofmt
    - goimports
    - misspell
    - unconvert
    - unparam

linters-settings:
  errcheck:
    check-type-assertions: true
  govet:
    enable:
      - shadow
```

## Security

- Run `gosec ./...` to scan for security antipatterns (SQL injection, unsafe file permissions, hardcoded credentials).
- Run `govulncheck ./...` to check for known CVEs in the dependency graph.

## Module Management

- Run `go mod tidy` before committing to keep `go.mod` and `go.sum` clean. Untidy modules indicate unused or missing dependencies.
- Run `go mod verify` to confirm the module cache matches the checksums in `go.sum`.
- Use `go mod why -m <module>` to understand why a transitive dependency is present before removing it.

## Testing

```bash
go test ./...                          # Run all tests
go test -race ./...                    # With race detector (required in CI)
go test -cover -coverprofile=c.out ./... # Coverage
go test -bench=. -benchmem ./...      # Benchmarks
go test -fuzz=FuzzParse -fuzztime=60s # Fuzzing
```

## Build

```bash
go build ./...       # Verify all packages compile
go build -race ./... # Build with race instrumentation
go run ./cmd/myapp   # Run main package
```
