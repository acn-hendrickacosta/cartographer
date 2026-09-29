# Android Clean Architecture (Kotlin)

- Structure the project into modules with strict dependency rules: `domain` (pure Kotlin, no Android framework imports), `data` (implements domain interfaces, uses Room/network/DB), `presentation` (ViewModels + Jetpack Compose), `app` (wires everything together), plus optional `design-system` and `feature:*` modules.
- The domain module must be pure Kotlin — zero imports of `android.*`, `androidx.*`, Room, Ktor, or any framework package. This keeps business logic testable on the JVM without an Android runtime.
- UseCase classes implement a single public `operator fun invoke(...)` (or `suspend operator fun invoke(...)`). They receive domain-layer inputs, apply business rules, and return domain outputs or `Flow<T>`. One class, one operation.

```kotlin
class GetUserUseCase(private val repository: UserRepository) {
    suspend operator fun invoke(id: UserId): User = repository.getById(id)
        ?: throw UserNotFoundException(id)
}
```

- Repository interfaces live in the `domain` module. Their implementations live in the `data` module. The domain never imports the implementation. Dependency inversion is enforced at the module boundary, not just at the class level.
- Domain models are plain Kotlin `data class` or `value class`. They do not extend Room `@Entity`, implement `Parcelable`, or carry JSON annotations. Mapping to/from persistence and network representations happens in the `data` layer via `toDomain()` / `toEntity()` extension functions.
- Room `@Dao` methods should return `Flow<T>` for observable queries and suspend functions for one-shot operations. Use `@Upsert` for insert-or-update. Prefer named queries over `rawQuery`.
- Wire dependencies with Koin or Hilt. Koin: `factory { GetUserUseCase(get()) }` for use cases (new instance per injection), `single { UserRepositoryImpl(get(), get()) }` for repositories. Hilt: `@HiltViewModel` + `@Binds` in a `@Module`. Never instantiate dependencies manually in ViewModels or Fragments.
- ViewModels expose UI state as `StateFlow<UiState>`. Use `WhileSubscribed(5_000)` when converting upstream `Flow` to `StateFlow`. Never expose `MutableStateFlow` publicly — only expose the read-only `StateFlow` interface.
- Sealed classes or `sealed interface` model the complete set of possible UI states: `Loading`, `Success(data)`, `Error(message)`. Never use nullable data or boolean flags as a proxy for loading/error state.
- Jetpack Compose: avoid passing `NavController` into composables below the screen level. Instead, pass lambdas (`onNavigate: (Destination) -> Unit`). This keeps composables independent of the navigation framework and testable in isolation.
