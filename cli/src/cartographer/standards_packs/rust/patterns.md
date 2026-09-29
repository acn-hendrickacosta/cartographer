# Rust Patterns

## Repository Pattern

Encapsulate data access behind a trait. Concrete implementations (Postgres, SQLite, in-memory) are swappable without touching business logic, and tests use in-memory fakes.

```rust
pub trait OrderRepository: Send + Sync {
    fn find_by_id(&self, id: u64) -> Result<Option<Order>, StorageError>;
    fn save(&self, order: &Order) -> Result<Order, StorageError>;
    fn delete(&self, id: u64) -> Result<(), StorageError>;
}
```

## Service Layer

Business logic lives in service structs. Inject dependencies as boxed trait objects via the constructor:

```rust
pub struct OrderService {
    repo: Box<dyn OrderRepository>,
    payment: Box<dyn PaymentGateway>,
}

impl OrderService {
    pub fn new(repo: Box<dyn OrderRepository>, payment: Box<dyn PaymentGateway>) -> Self {
        Self { repo, payment }
    }

    pub fn place_order(&self, req: CreateOrderRequest) -> anyhow::Result<OrderSummary> {
        let order = Order::from(req);
        self.payment.charge(order.total())?;
        let saved = self.repo.save(&order)?;
        Ok(OrderSummary::from(saved))
    }
}
```

## Newtype Pattern

Wrap primitives to create distinct types. This prevents mixing up arguments at call sites and lets you add domain-specific methods.

```rust
struct UserId(u64);
struct OrderId(u64);

fn get_order(user: UserId, order: OrderId) -> anyhow::Result<Order> {
    // Compiler prevents accidentally swapping user and order IDs
    todo!()
}
```

## Enum State Machines

Model states as enums to make illegal states unrepresentable. Always match exhaustively — avoid wildcard `_` for business-critical enums so that adding a new variant causes a compile error at every match site.

```rust
enum ConnectionState {
    Disconnected,
    Connecting { attempt: u32 },
    Connected { session_id: String },
    Failed { reason: String, retries: u32 },
}

fn handle(state: &ConnectionState) {
    match state {
        ConnectionState::Disconnected => connect(),
        ConnectionState::Connecting { attempt } if *attempt > 3 => abort(),
        ConnectionState::Connecting { .. } => wait(),
        ConnectionState::Connected { session_id } => use_session(session_id),
        ConnectionState::Failed { retries, .. } if *retries < 5 => retry(),
        ConnectionState::Failed { reason, .. } => log_failure(reason),
    }
}
```

## Builder Pattern

Use for structs with many optional parameters. Required parameters go in the `builder()` constructor; optional ones are setter methods returning `Self`.

```rust
impl ServerConfig {
    pub fn builder(host: impl Into<String>, port: u16) -> ServerConfigBuilder {
        ServerConfigBuilder { host: host.into(), port, max_connections: 100 }
    }
}

impl ServerConfigBuilder {
    pub fn max_connections(mut self, n: usize) -> Self {
        self.max_connections = n;
        self
    }
    pub fn build(self) -> ServerConfig { /* ... */ }
}
```

## Traits and Generics

- Use generics (`impl Trait` or `<T: Trait>`) when you need static dispatch and performance (monomorphization).
- Use `dyn Trait` for heterogeneous collections or plugin systems where the concrete type is unknown at compile time.
- Prefer `impl Trait` in function parameters for simplicity:

```rust
fn read_all(reader: &mut impl Read) -> std::io::Result<Vec<u8>> {
    let mut buf = Vec::new();
    reader.read_to_end(&mut buf)?;
    Ok(buf)
}
```

## Sealed Traits

Use a private module to prevent external crates from implementing a trait, while keeping it public for use:

```rust
mod private {
    pub trait Sealed {}
}

pub trait Format: private::Sealed {
    fn encode(&self, data: &[u8]) -> Vec<u8>;
}
```

## Concurrency

**Shared mutable state**: Use `Arc<Mutex<T>>` for shared ownership with interior mutability. Handle `PoisonError` from `.lock()` — do not silently ignore it.

```rust
let counter = Arc::new(Mutex::new(0u64));
let handles: Vec<_> = (0..10).map(|_| {
    let counter = Arc::clone(&counter);
    std::thread::spawn(move || {
        *counter.lock().expect("mutex poisoned") += 1;
    })
}).collect();
for h in handles { h.join().expect("thread panicked"); }
```

**Message passing**: Use bounded channels (`mpsc::sync_channel(n)` or `tokio::sync::mpsc::channel(n)`) with explicit backpressure. Unbounded channels can grow without limit under load.

**Async**: Use `tokio` as the async runtime. Never call blocking operations (`std::thread::sleep`, synchronous `std::fs`) inside async functions — use `tokio::time::sleep` and `tokio::fs` instead.

```rust
async fn fetch_with_timeout(url: &str) -> anyhow::Result<String> {
    let response = tokio::time::timeout(
        Duration::from_secs(5),
        reqwest::get(url),
    )
    .await
    .context("request timed out")?
    .context("request failed")?;
    response.text().await.context("failed to read body")
}
```

## Unsafe Code

- Minimize `unsafe` blocks. Every `unsafe` block must have a `// SAFETY:` comment explaining every invariant the caller is upholding.
- Never use `unsafe` to bypass the borrow checker for convenience. A borrow checker error is a signal to rethink the data model.
- Audit all `unsafe` blocks during code review as a hard requirement.

```rust
// GOOD — every invariant is documented
let widget: &Widget = {
    // SAFETY: `ptr` is non-null, aligned, points to an initialized Widget,
    // and no mutable references or mutations exist for the returned lifetime.
    unsafe { &*ptr }
};
```

## Option Combinators

Prefer combinator chains over nested `match` for `Option` manipulation:

```rust
fn find_user_email(users: &[User], id: u64) -> Option<&str> {
    users.iter()
        .find(|u| u.id == id)
        .map(|u| u.email.as_str())
}
```

## API Response Envelope

Consistent REST API responses using a tagged enum and `serde`:

```rust
#[derive(Debug, serde::Serialize)]
#[serde(tag = "status")]
pub enum ApiResponse<T: serde::Serialize> {
    #[serde(rename = "ok")]
    Ok { data: T },
    #[serde(rename = "error")]
    Error { message: String },
}
```
