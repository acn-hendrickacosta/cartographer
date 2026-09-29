# TypeScript Security

## Secret Management

- Never hardcode API keys, tokens, or passwords in source. Always read them from environment variables and fail at startup if they are missing.

```typescript
// Wrong
const apiKey = "sk-proj-xxxxx"

// Correct
const apiKey = process.env.API_KEY
if (!apiKey) throw new Error('API_KEY not configured')
```

## Dynamic Code Execution

- Never pass user-controlled input to `eval`, `new Function`, or `setTimeout`/`setInterval` with a string argument. These execute arbitrary code. Use data structures or function references instead.

## Injection via String Concatenation

- Build database queries with parameterized placeholders, not string concatenation. This applies to SQL, NoSQL query operators, and any query language.
- Do not build shell commands from user input. If `child_process.exec` or `spawn` must receive external data, validate and allowlist every argument before passing it.

## Path Traversal

- Never join user-supplied values into file paths directly. Resolve the path, then verify it starts with the intended root before opening the file.

```typescript
import path from 'path'

function safeReadFile(userInput: string, baseDir: string): string {
  const resolved = path.resolve(baseDir, userInput)
  if (!resolved.startsWith(baseDir)) {
    throw new Error('Path traversal attempt detected')
  }
  return fs.readFileSync(resolved, 'utf-8')
}
```

## Prototype Pollution

- Do not spread or merge untrusted objects directly onto application state. An attacker-controlled `__proto__` key can corrupt every object in the process.
- Parse external data with a schema validator (Zod, joi, yup) before merging. The validator rejects unknown keys and does not transfer prototype references.

```typescript
// Wrong: attacker controls __proto__
const update = await req.json()
Object.assign(config, update)

// Correct: validate first
const Allowed = z.object({ theme: z.string(), locale: z.string() })
const parsed = Allowed.parse(await req.json())
Object.assign(config, parsed)
```

## XSS via innerHTML

- Do not assign user-controlled strings to `innerHTML`, `outerHTML`, or `document.write`. Assign to `textContent` or use a sanitization library with an allowlist when raw HTML is genuinely required.

## Input Validation at Boundaries

- Validate all external input at the boundary — HTTP request bodies, query parameters, URL segments, environment variables, and imported data files.
- Do not trust data that passes through a client. Clients can be modified; the server must be the source of truth for authorization and business rules.

## Environment Variables at Startup

- Validate required environment variables when the process starts, not lazily at first use. A missing variable that crashes a request handler is harder to debug than a crash at boot.

```typescript
const env = z.object({
  DATABASE_URL: z.string().url(),
  JWT_SECRET: z.string().min(32),
  PORT: z.coerce.number().default(3000),
}).parse(process.env)
```
