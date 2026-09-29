# Architecture Patterns

## Hexagonal Architecture (Ports and Adapters)

- Separate the core domain model from all infrastructure and framework dependencies.
  The domain model should import nothing from ORMs, HTTP frameworks, or SDK clients.
- Define use cases in an application layer that orchestrates domain behavior. A use
  case receives its dependencies through constructor injection (ports), not by
  importing concrete implementations.
- Express every external dependency as a port (interface): `UserRepositoryPort`,
  `BillingGatewayPort`, `ClockPort`. Ports model capabilities, not technologies. The
  application layer depends on port interfaces, never on database libraries or HTTP
  clients directly.
- Adapters implement ports at the edges. Inbound adapters convert protocol input
  (HTTP request, CLI args, queue message) into use-case input. Outbound adapters
  translate port contracts into real infrastructure calls.
- Dependency direction flows inward: adapters depend on the application layer, the
  application layer depends on port interfaces, the domain depends on nothing external.
  This constraint is what makes the architecture testable.
- Wire everything in a single composition root. Instantiate adapters, inject them into
  use cases, and bind use cases to inbound adapters in one place. Hidden global
  singletons and scattered `new` calls undermine this.
- Organize by feature, not by layer. A feature slice groups its domain model,
  application use cases, port definitions, and adapters together. Flat layer
  directories (`controllers/`, `services/`, `repositories/`) couple unrelated features.

## Testing Across Boundaries

- Unit test use cases with in-memory fakes for all outbound ports. These tests prove
  business logic independently of any real infrastructure.
- Integration test adapters against real infrastructure (database, external API). These
  tests prove serialization, query behavior, retries, and error mapping.
- Write contract tests at port boundaries so every adapter implementation is verified
  against the same interface contract.
- E2E tests cover critical user journeys through the inbound adapter → use case →
  outbound adapter chain.

## Anti-Patterns

- Domain entities importing ORM models, web framework types, or SDK clients.
- Use cases reading `req`, `res`, or raw queue message wrappers — these are transport
  details and belong in the inbound adapter.
- Returning database rows directly from use cases without mapping through a domain or
  application type.
- Adapters calling each other directly instead of flowing through the use-case port
  boundary.

## Repository Pattern

- Abstract data access behind a consistent interface: `findAll`, `findById`, `create`,
  `update`, `delete`. Business logic depends on the abstract interface, not on the
  storage mechanism.
- The repository interface belongs in the application or domain layer; the
  implementation belongs in the infrastructure layer.
- Caching can be added as a decorator that implements the same repository interface,
  wrapping the base implementation without modifying it.

## Service Layer

- Business logic lives in services or use cases, not in controllers or route handlers.
  Controllers translate protocol input and output; they do not make business decisions.
- Services should be stateless. State lives in the domain model or the persistence
  layer, not in service instances.

## Migration Playbook

- Migrate toward hexagonal architecture one vertical slice at a time, not all at once.
  Pick one endpoint or job, extract its use-case boundary, and verify behavior is
  preserved before moving to the next.
- Use the strangler-fig pattern: keep old adapters and route one use case at a time
  through new ports and adapters. Avoid big-bang rewrites.
- Write characterization tests before extracting a boundary. These tests document
  current behavior and fail if the refactor breaks something.
