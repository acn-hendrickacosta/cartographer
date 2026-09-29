# API Design

## Resource Naming

- Resource URLs use nouns (not verbs), are plural, lowercase, and kebab-case:
  `GET /api/v1/team-members`, not `/api/v1/getTeamMember`.
- Nest sub-resources to express ownership: `GET /api/v1/users/:id/orders`.
- Use verbs only for actions that don't map to CRUD:
  `POST /api/v1/orders/:id/cancel`.
- Filter, sort, and paginate via query parameters, not URL path segments:
  `GET /api/v1/products?status=active&sort=-created_at&page=2`.

## HTTP Methods and Status Codes

- Use methods semantically: GET reads (idempotent, safe), POST creates or triggers
  actions, PUT replaces a resource (idempotent), PATCH partially updates, DELETE
  removes (idempotent).
- Return correct status codes. Key ones to get right: `201 Created` with a `Location`
  header for POST creates; `204 No Content` for DELETE or PUT with no body; `400 Bad
  Request` for malformed input; `401 Unauthorized` for missing/invalid auth; `403
  Forbidden` for authenticated but not authorized; `404 Not Found`; `409 Conflict` for
  duplicate or state conflict; `422 Unprocessable Entity` for semantically invalid input;
  `429 Too Many Requests` with a `Retry-After` header.
- Never return `200` for everything. Using HTTP status semantically allows clients to
  handle errors without parsing the body.

## Response Format

- Wrap responses consistently. For public APIs, use a `data` envelope on success and an
  `error` envelope on failure:
  ```json
  { "data": { ... } }
  { "error": { "code": "not_found", "message": "User not found" } }
  ```
- List responses should include pagination metadata (`total`, `page`, `per_page`) and
  `links` for `self`, `next`, and `last` where applicable.
- Error responses must include a machine-readable `code` string in addition to a human-
  readable `message`. Field-level validation errors should name the field and the reason.
- Responses must never contain stack traces, SQL error messages, or internal server
  details.

## Pagination

- Prefer cursor-based pagination for large or append-only datasets (feeds, activity
  logs). Cursor pagination is `O(1)` regardless of position; offset pagination degrades
  at high offsets.
- Use offset/page pagination for small datasets and admin views where users need to jump
  to an arbitrary page.
- Expose a `has_next` flag and an opaque `next_cursor` in cursor responses. Never leak
  internal IDs in cursors — encode them.

## Filtering and Sorting

- Use bracket notation for comparison operators:
  `?price[gte]=10&price[lte]=100`, `?created_at[after]=2025-01-01`.
- Sort with a prefix: `?sort=-created_at` (descending), `?sort=name` (ascending).
  Allow comma-separated multi-field sort.
- Support sparse fieldsets (`?fields=id,name,email`) to reduce payload size on
  bandwidth-sensitive clients.

## Authentication and Authorization

- Use Bearer tokens in the `Authorization` header for user-facing APIs. Use `X-API-Key`
  for server-to-server keys.
- Check authorization (not just authentication) per resource. Authenticated does not
  mean authorized: verify that the caller can access the specific resource they are
  requesting.
- Always check ownership before returning a resource, not just the presence of a valid
  token.

## Rate Limiting

- Apply rate limits to all public endpoints. Expose the limit, remaining count, and
  reset time in response headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`,
  `X-RateLimit-Reset`).
- Use tiered limits: stricter for anonymous requests, looser for authenticated users,
  and higher still for internal service calls.
- Rate limiting state must live in a shared store; never use per-process in-memory
  counters on multi-instance services.

## Versioning

- Version via URL path: `/api/v1/`, `/api/v2/`. This is explicit, cacheable, and easy
  to test.
- Maintain at most two active versions at a time (current and the previous). Announce
  deprecation at least six months before sunset for public APIs. Use the `Sunset`
  response header on deprecated endpoints.
- Additive changes (new optional fields, new endpoints) do not require a new version.
  Removing or renaming fields, changing types, and altering authentication do.

## Input Validation

- Validate all inputs with a schema library at the API boundary. Return field-level
  error details in the `422` response body so clients can show precise messages.
- Never construct SQL, shell commands, or HTML from raw input strings. Use parameterized
  queries and framework-level escaping.
