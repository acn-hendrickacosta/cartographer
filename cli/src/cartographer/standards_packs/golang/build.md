# Go Build and Dependencies

## Build Verification

Run these checks in order when diagnosing build failures:

```bash
go build ./...         # Compilation
go vet ./...           # Static analysis
staticcheck ./...      # Extended checks (if installed)
golangci-lint run      # Full linter suite (if installed)
go mod verify          # Checksum integrity
go mod tidy -v         # Dependency hygiene
```

## Common Build Errors

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| `undefined: X` | Missing import or typo | Add import or correct casing (exported vs. unexported) |
| `cannot use X as type Y` | Type mismatch, pointer vs. value | Add type conversion or fix pointer indirection |
| `X does not implement Y` | Missing method on receiver | Implement the missing method with the correct receiver type |
| `import cycle not allowed` | Circular dependency between packages | Extract shared types to a new package that neither imports |
| `cannot find package` | Missing dependency or wrong path | `go get module@version` or `go mod tidy` |
| `missing return` | Incomplete control flow | Add a return statement or ensure all branches return |
| `declared and not used` | Unused variable or import | Remove it or assign to `_` |
| `multiple-value in single-value context` | Ignoring multi-return | `result, err := f()` |
| `cannot assign to struct field in map` | Map value mutation | Use a pointer map (`map[K]*V`) or copy-modify-reassign |

## Module Troubleshooting

```bash
go mod why -m github.com/some/module   # Why is this version selected?
go get github.com/some/module@v1.2.3   # Pin a specific version
go clean -modcache && go mod download  # Fix corrupt module cache / checksum mismatches
grep "replace" go.mod                  # Check for local path replaces (common CI issue)
```

## Key Principles

- Apply minimal, surgical fixes — do not refactor while fixing build errors.
- Never add `//nolint` directives without a specific justification comment.
- Never change function signatures unless the error requires it.
- Always run `go mod tidy` after adding or removing imports.
- Fix root causes, not symptoms — suppressing an error with `_` or a nolint is not a fix.
