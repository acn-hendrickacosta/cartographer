# NestJS Patterns

## Project Structure

- Organize code by feature module under `src/modules/`. Put cross-cutting concerns (filters, guards, interceptors, pipes, decorators) in `src/common/`. Keep DTOs close to the module that owns them.

```
src/
├── app.module.ts
├── main.ts
├── common/
│   ├── filters/
│   ├── guards/
│   ├── interceptors/
│   └── pipes/
└── modules/
    └── users/
        ├── dto/
        ├── entities/
        ├── users.controller.ts
        ├── users.module.ts
        └── users.service.ts
```

## Bootstrap with Global Validation

- Enable `ValidationPipe` globally with `whitelist: true` and `forbidNonWhitelisted: true` so unrecognized fields are rejected on all public endpoints. Configure it once in `main.ts`, not per-route.
- Add `ClassSerializerInterceptor` globally to ensure response DTOs are serialized consistently via `@Exclude`/`@Expose` decorators.

```typescript
app.useGlobalPipes(
  new ValidationPipe({
    whitelist: true,
    forbidNonWhitelisted: true,
    transform: true,
    transformOptions: { enableImplicitConversion: true },
  }),
)
app.useGlobalInterceptors(new ClassSerializerInterceptor(app.get(Reflector)))
app.useGlobalFilters(new HttpExceptionFilter())
```

## Modules, Controllers, Providers

- Keep controllers thin — parse HTTP input, call a service method, return a response DTO. No business logic in controllers.
- Put business logic in injectable services. Services receive their dependencies via the constructor.
- Export only providers that other modules genuinely need; do not re-export everything.

```typescript
@Controller('users')
export class UsersController {
  constructor(private readonly usersService: UsersService) {}

  @Get(':id')
  getById(@Param('id', ParseUUIDPipe) id: string) {
    return this.usersService.getById(id)
  }

  @Post()
  create(@Body() dto: CreateUserDto) {
    return this.usersService.create(dto)
  }
}
```

## DTOs and Validation

- Validate every request body with `class-validator` decorators on DTO classes. Define separate response DTOs — never return raw ORM entities, which may expose passwords, internal fields, or audit columns.
- Mark sensitive fields with `@Exclude()` and use `@Expose()` on what should be returned.

```typescript
export class CreateUserDto {
  @IsEmail()
  email!: string

  @IsString()
  @Length(2, 80)
  name!: string

  @IsOptional()
  @IsEnum(UserRole)
  role?: UserRole
}
```

## Guards and Authorization

- Use guards for coarse access rules (is the user authenticated? do they have this role?). Perform resource-specific authorization — does this user own this record? — inside the service.
- Keep auth strategies module-local unless they are explicitly shared via `exports`.

```typescript
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('admin')
@Get('admin/report')
getReport(@Req() req: AuthenticatedRequest) {
  return this.reportService.getForUser(req.user.id)
}
```

## Exception Filters and Error Shape

- Use a global exception filter to maintain one consistent error envelope. Translate `HttpException` to the appropriate HTTP status. Catch unexpected errors, log them, and return a 500 without leaking internals.
- Throw NestJS `HttpException` subclasses (`NotFoundException`, `ForbiddenException`, etc.) for expected client errors. For unexpected failures, let the global filter catch and wrap them.

## Config and Environment Validation

- Validate environment variables at boot using `ConfigModule` with a `validate` function. A missing variable should crash startup, not fail silently at first use.
- Access config through typed helpers or the `ConfigService`, not by calling `process.env` directly throughout feature code.

```typescript
ConfigModule.forRoot({
  isGlobal: true,
  load: [configuration],
  validate: validateEnv,
})
```

## Persistence and Transactions

- Isolate ORM or repository code behind service methods that speak the domain language. Controllers should not coordinate multi-step database writes directly.
- In Prisma or TypeORM, keep transactional workflows inside a single service method that owns the unit of work.

## Testing

- Unit test providers with mocked dependencies. Add HTTP-level tests for guards, validation pipes, and exception filters — they need the NestJS runtime to fire correctly.
- Reuse the same global pipes and filters in tests that run in production to avoid behavior differences.

```typescript
const moduleRef = await Test.createTestingModule({
  imports: [UsersModule],
}).compile()

const app = moduleRef.createNestApplication()
app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }))
await app.init()
```

## Production Defaults

- Enable structured logging and per-request correlation IDs from day one.
- Validate and fail fast on invalid config at startup rather than booting partially.
- Keep background jobs, queues, and event consumers in their own modules, not inside HTTP controllers.
- Make rate limiting, authentication, and audit logging explicit for all public endpoints — do not rely on implicit defaults.
