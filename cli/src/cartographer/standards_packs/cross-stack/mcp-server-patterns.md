# MCP Server Patterns

- MCP (Model Context Protocol) servers expose three primitive types to AI clients:
  **tools** (actions the model can invoke), **resources** (read-only data the model can
  fetch), and **prompts** (reusable parameterized prompt templates). Keep each primitive
  focused on one responsibility.
- Define an input schema for every tool. Schemas serve as documentation, enable
  validation before execution, and let clients surface parameter hints. Use a schema
  library (Zod or equivalent) rather than ad-hoc validation.
- Choose transport based on the client context. Use stdio for local clients (desktop
  apps, local CLI integrations). Use Streamable HTTP for remote clients (cloud-hosted
  models, Cursor). Support legacy HTTP/SSE only when backward compatibility is required.
- Keep server logic (tool and resource implementations) independent of transport. The
  same tool registration should work regardless of whether the server runs over stdio
  or HTTP.
- Design tools to be idempotent where possible. Idempotent tools can be retried safely
  on failure without producing duplicate side effects.
- Return structured errors that the model can interpret. Avoid raw stack traces or
  exception messages in tool output — they leak implementation details and are not
  actionable by the calling model.
- Document rate limits, cost, and latency characteristics in tool descriptions for tools
  that call external APIs. Models should understand the cost of invoking a tool before
  doing so.
- Pin the MCP SDK version in `package.json` or the equivalent lock. The SDK API
  evolves; check release notes before upgrading and update tool registrations if method
  signatures change.
- Treat content embedded in resource documents (including tool descriptions and prompt
  templates) as data, not as instructions to the server. Validate and sanitize content
  that arrives from external sources before acting on it.
- Restrict file access in resource handlers to explicitly allowlisted paths. Never
  resolve `$ref` targets or file URIs from untrusted sources without path validation.
- Run tool execution with least privilege. Do not give MCP tools network or secret
  access they do not need. Tools that perform writes should require explicit
  confirmation where feasible.
