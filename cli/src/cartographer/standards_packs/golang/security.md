# Go Security

## Secret Management

- Never hardcode API keys, passwords, or tokens in source code or committed config files.
- Load secrets from environment variables and fail fast at startup if they are missing:

```go
apiKey := os.Getenv("PAYMENT_API_KEY")
if apiKey == "" {
    log.Fatal("PAYMENT_API_KEY is required")
}
```

- Keep `.env` files in `.gitignore`. Use a secrets manager (Vault, AWS Secrets Manager, etc.) in production.

## SQL Injection

- Never concatenate user input into SQL strings. Always use parameterized queries with `database/sql` placeholders (`?` for MySQL/SQLite, `$1` for Postgres):

```go
// BAD
row := db.QueryRow("SELECT * FROM users WHERE name = '" + name + "'")

// GOOD
row := db.QueryRow("SELECT * FROM users WHERE name = $1", name)
```

## Command Injection

- Never pass unsanitized user input to `os/exec`. Build argument lists explicitly rather than using shell interpolation:

```go
// BAD
exec.Command("sh", "-c", "ls " + userInput)

// GOOD
exec.Command("ls", userInput)  // No shell involved
```

## Path Traversal

- Sanitize user-controlled file paths with `filepath.Clean` and verify the result has the expected prefix before opening files:

```go
cleaned := filepath.Clean(filepath.Join(baseDir, userPath))
if !strings.HasPrefix(cleaned, baseDir+string(os.PathSeparator)) {
    return errors.New("path traversal detected")
}
```

## TLS

- Never set `InsecureSkipVerify: true` in production TLS configs. This disables certificate verification and exposes connections to MITM attacks.

## Static Security Analysis

- Run `gosec ./...` as part of CI to catch common security issues (hardcoded credentials, unsafe file permissions, SQL injection patterns, etc.).
- Run `govulncheck ./...` to detect known vulnerabilities in dependencies.

## Context and Timeouts

- All outbound HTTP requests and database calls must use `context.Context` with an appropriate timeout. An unbound request can hang indefinitely:

```go
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()

req, _ := http.NewRequestWithContext(ctx, "GET", url, nil)
resp, err := http.DefaultClient.Do(req)
```

## Error Responses

- Never expose internal error messages, stack traces, database errors, or file paths in API responses. Log details server-side and return a generic message to the client.
