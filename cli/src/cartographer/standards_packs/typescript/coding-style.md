# TypeScript Coding Style

## Types and Interfaces

- Add parameter and return types to exported functions, shared utilities, and public class methods. Let TypeScript infer obvious local variable types — annotate at the boundary, not everywhere.
- Extract repeated inline object shapes into named types or interfaces rather than repeating the shape.
- Use `interface` for object shapes that may be extended or implemented. Use `type` for unions, intersections, tuples, mapped types, and utility types.
- Prefer string literal unions over `enum` for simple sets of values. Use `enum` only when numeric values or declaration merging are required.

```typescript
interface User {
  id: string
  email: string
}

type UserRole = 'admin' | 'member'
type UserWithRole = User & { role: UserRole }

// Exported functions need explicit types
export function formatUser(user: User): string {
  return `${user.firstName} ${user.lastName}`
}
```

## Avoid `any`

- Do not use `any` in application code. It disables the type checker for the value and anything that touches it.
- Use `unknown` for external or untrusted input, then narrow it safely before use.
- Use generics when a value's type depends on the caller.

```typescript
// Wrong: any removes type safety
function getErrorMessage(error: any) {
  return error.message
}

// Correct: unknown forces safe narrowing
function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return 'Unexpected error'
}
```

## Component and Function Props

- Define component props with a named `interface` or `type`. Type callback props explicitly with their parameter and return types.
- Do not use `React.FC` — it adds implicit `children` and does not improve inference.
- Always destructure props in the parameter list; avoid `props.foo` access inside the body.

## Immutability

- Treat objects and arrays as immutable. Use spread to produce updates rather than mutating in place.
- Mark parameters with `Readonly<T>` when a function should not modify its input.

```typescript
function updateUser(user: Readonly<User>, name: string): User {
  return { ...user, name }
}
```

## Error Handling

- Use `async/await` with `try/catch`. Catch clauses always receive `unknown` — narrow before accessing properties.
- Never swallow errors with an empty catch. At minimum log the error and rethrow or return a typed error value.
- Always `throw new Error(message)` rather than throwing strings or plain objects.

```typescript
async function loadUser(userId: string): Promise<User> {
  try {
    return await riskyOperation(userId)
  } catch (error: unknown) {
    logger.error('Operation failed', error)
    throw new Error(getErrorMessage(error))
  }
}
```

## Input Validation

- Use Zod (or an equivalent schema library) to validate external input at the boundary — API responses, form data, environment variables.
- Infer TypeScript types from the schema so the type and the validator stay in sync.

```typescript
import { z } from 'zod'

const userSchema = z.object({
  email: z.string().email(),
  age: z.number().int().min(0).max(150),
})

type UserInput = z.infer<typeof userSchema>

const validated: UserInput = userSchema.parse(rawInput)
```

## JavaScript Files

- In `.js` and `.jsx` files, add JSDoc type annotations when types improve clarity and a TypeScript migration is not practical. Keep JSDoc aligned with runtime behavior.

## Console and Logging

- Remove `console.log` from production code. Use a structured logging library (pino, winston, or the platform equivalent) that emits machine-readable output.
- Console statements left in production make logs noisy and may leak sensitive data.
