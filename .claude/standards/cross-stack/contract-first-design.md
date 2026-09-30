# Contract-First Design

- When frontend and backend work proceeds in parallel, or when two services exchange
  payloads, define a machine-checkable contract before writing code. The contract is
  the single authoritative description of the boundary — not the wiki, not the mock
  file, not the provider's internal types.
- Choose one canonical artifact per boundary: OpenAPI for HTTP APIs, AsyncAPI for
  event-driven APIs, Protocol Buffers for RPC or message schemas, JSON Schema for
  standalone payloads. Do not maintain the same shape in multiple places independently.
- Design the contract from the consumer's perspective, not the provider's storage
  model. Ask: which fields are actually required? What do missing, empty, and null
  mean? Can one task-oriented response replace several coupled calls? A database row
  is not a contract.
- Make the observable behavior explicit in the contract: field names, required vs
  optional, nullability, enum values, error shapes, and semantic constraints (e.g.,
  `cancellationReason` is null except when status is `cancelled`). Syntax alone is not
  enough.
- Generate consumer types from the contract where the ecosystem supports it. Handwritten
  type copies drift. Generated types that fail to compile when the contract changes are
  the goal.
- Verify provider responses against the contract, not just against internal types. A
  cast or type annotation can hide runtime data that does not match the declared shape.
  Validate real serialized output, including alternate code paths and error cases.
- Never change the implementation first and update the contract afterward. That records
  what happened; it does not coordinate parallel work. Change the contract first, get
  affected-owner review, then update implementations on both sides.
- Additive changes (new optional fields) are non-breaking; verify old consumers still
  work. Removing or renaming fields, changing types, and repurposing fields are breaking
  changes and require versioning or a migration plan.
- Delete handwritten mock files and type copies once generated or derived versions exist.
  Duplicate sources of truth always diverge.
- Treat a contract diff as a cross-team change. It is not a unilateral implementation
  decision; it affects every consumer of that boundary.

## Anti-Patterns

- Exposing a storage model directly: `SELECT * FROM orders` returned as the API
  response. Storage columns, internal field names, and accidental renames all become
  public interface.
- Parallel wiki, frontend interface, backend serializer, and mock JSON that each drift
  independently.
- Using casts (`as unknown as MyType`) to satisfy the type checker without validating
  the actual data.
- Changing a field name in one implementation without updating and reviewing the
  contract — even if that implementation's tests pass.
