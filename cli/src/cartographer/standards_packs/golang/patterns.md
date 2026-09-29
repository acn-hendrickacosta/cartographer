# Go Patterns

## Functional Options

Use functional options for constructors with many optional parameters. This keeps the API clean and backward-compatible as options evolve.

```go
type Option func(*Server)

func WithTimeout(d time.Duration) Option {
    return func(s *Server) { s.timeout = d }
}

func WithLogger(l *log.Logger) Option {
    return func(s *Server) { s.logger = l }
}

func NewServer(addr string, opts ...Option) *Server {
    s := &Server{addr: addr, timeout: 30 * time.Second, logger: log.Default()}
    for _, opt := range opts {
        opt(s)
    }
    return s
}
```

## Dependency Injection

Inject dependencies via constructor functions — never via `init()` or package-level variables. This makes dependencies explicit and enables testing.

```go
func NewUserService(repo UserRepository, logger Logger) *UserService {
    return &UserService{repo: repo, logger: logger}
}
```

## Interface Design

- Define interfaces where they are consumed (in the consumer package), not where they are implemented. This keeps the interface minimal and avoids circular imports.
- Use single-method interfaces (`io.Reader`, `io.Writer`) and compose them when multiple methods are needed (`io.ReadWriteCloser`).
- Use type assertions to check for optional behavior rather than adding methods to interfaces:

```go
func WriteAndFlush(w io.Writer, data []byte) error {
    if _, err := w.Write(data); err != nil {
        return err
    }
    if f, ok := w.(interface{ Flush() error }); ok {
        return f.Flush()
    }
    return nil
}
```

## Concurrency

- Use `context.Context` for cancellation and timeout propagation. Always `defer cancel()` immediately after creating a context with a deadline.
- Use `sync.WaitGroup` to wait for goroutines to finish. Use `errgroup` (from `golang.org/x/sync/errgroup`) when goroutines return errors.
- Buffer channels to avoid goroutine leaks. A goroutine writing to an unbuffered channel blocks forever if the receiver is gone.
- Use `select` with `ctx.Done()` in goroutines that produce or relay values:

```go
func safeProduce(ctx context.Context) <-chan Result {
    ch := make(chan Result, 1)
    go func() {
        result := compute()
        select {
        case ch <- result:
        case <-ctx.Done():
        }
    }()
    return ch
}
```

- Build worker pools with a bounded number of goroutines reading from a job channel. Close the results channel after `wg.Wait()`.
- Use `defer mu.Unlock()` immediately after `mu.Lock()` — never defer in a loop or unlock manually unless required for performance.
- Prefer `sync.RWMutex` for read-heavy shared state.

## Struct Embedding

Embed types to compose behavior. The embedded type's methods promote to the outer type.

```go
type Server struct {
    *Logger
    addr string
}
```

Use embedding for composition, not inheritance. Avoid embedding when the outer type should not expose all methods of the embedded type.

## Package Layout

Organize packages by domain, not by type. Keep business logic in `internal/` to prevent external use.

```text
myproject/
├── cmd/myapp/main.go       # Entry point only — wires up dependencies
├── internal/
│   ├── handler/            # HTTP handlers
│   ├── service/            # Business logic
│   └── repository/         # Data access
├── pkg/                    # Code safe to import by external projects
├── go.mod
└── go.sum
```

## Memory and Performance

- Preallocate slices when the size is known: `make([]T, 0, len(input))`. Avoids repeated allocations as the slice grows.
- Use `strings.Builder` (or `strings.Join`) to concatenate strings in loops — string `+` inside a loop is O(n²).
- Use `sync.Pool` to reuse frequently allocated objects (e.g., buffers) in hot paths. Always `Reset()` before returning to the pool.

## Error Types

Define sentinel errors for common domain cases:

```go
var ErrNotFound = errors.New("resource not found")
```

Define structured error types when callers need to inspect fields:

```go
type ValidationError struct {
    Field   string
    Message string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation failed on %s: %s", e.Field, e.Message)
}
```
