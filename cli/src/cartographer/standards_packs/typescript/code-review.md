# TypeScript Code Review Criteria

A checklist of what to look for when reviewing TypeScript and JavaScript code. Issues are grouped by severity.

## Critical — Security

- `eval` or `new Function` called with user-controlled input. Dynamic code execution with untrusted data.
- User input assigned to `innerHTML`, `document.write`, or similar. XSS risk.
- Database or file system queries built by string concatenation. SQL/NoSQL injection or path traversal.
- API keys, tokens, or passwords hardcoded in source. Move to environment variables.
- Untrusted objects merged without schema validation. Prototype pollution risk via `__proto__`.
- User input passed to `child_process.exec` or `spawn` without allowlisting. Command injection.

## High — Type Safety

- `any` used without a comment explaining why. Disables the type checker for anything downstream.
- Non-null assertion (`value!`) without a preceding guard. A missing runtime check means a crash.
- `as` cast to an unrelated type to silence a compiler error. Fix the type instead.
- `tsconfig.json` changes that weaken strictness settings (`strict: false`, `noImplicitAny: false`).

## High — Async Correctness

- `async` function called without `await` or `.catch()`. Unhandled promise rejection.
- `await` statements in a loop for independent operations. Use `Promise.all` instead.
- `array.forEach(async fn)`. Does not await the promises — use `for...of` or `Promise.all(array.map(...))`.
- Fire-and-forget promises in constructors or event handlers with no error handler.

## High — Error Handling

- Empty `catch` block. The error is silently swallowed.
- `JSON.parse` without `try/catch`. Throws on malformed input.
- `throw "string"` instead of `throw new Error("string")`. Loses the stack trace.
- Missing input validation (no Zod, joi, or similar) on external data entering the system.
- `process.env.SOME_VAR` accessed without a fallback or startup check.

## High — Node.js Specifics

- `fs.readFileSync` or other synchronous operations inside a request handler. Blocks the event loop.
- Mixing `require()` and `import` without clear intent. Choose one module system per project.

## High — React Patterns (when applicable)

- `useEffect` or `useMemo` with an incomplete dependency array. Stale closures and missed updates.
- State mutated directly (`state.push(x)`, `obj.field = y` then `setState(obj)`). React does not detect mutation.
- `key={index}` on a list that can reorder, insert, or delete items.
- `useEffect` used to compute derived state. Compute during render instead.
- Server-only imports in Client Components (Next.js).

## Medium — Performance

- Inline object or array literals as props to memoized children. Creates a new reference every render.
- Database queries inside loops. Batch with `Promise.all` or `IN` clause.
- `import _ from 'lodash'`. Import named functions or use tree-shakeable alternatives.

## Medium — Code Quality

- `console.log` left in production code. Use a structured logger.
- Magic numbers or strings without named constants.
- `==` instead of `===`. Use strict equality.
- Implicit `any` from public functions missing a return type annotation.
- `var` instead of `const`/`let`.

## Approval Criteria

- **Approve**: no Critical or High issues.
- **Caution**: Medium issues only — document them and merge with awareness.
- **Block**: any Critical or High issue must be resolved before merge.
