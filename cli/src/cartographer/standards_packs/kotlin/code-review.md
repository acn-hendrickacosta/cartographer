# Kotlin Code Review Criteria

## Critical — Block Approval

- **Domain module importing Android/Ktor/Room/framework packages**: the domain module must be pure Kotlin. Any framework import in `domain/` breaks testability and violates the architecture contract.
- **Data layer accessed directly from UI/presentation**: presentation must call use cases, not repositories or data sources. Direct access bypasses business rules and couples UI to infrastructure.
- **Business logic in a ViewModel**: ViewModels coordinate UI state and delegate to use cases. Domain rules, calculations, and data transformations belong in use cases or the domain layer.
- **Circular module dependencies**: creates an unmaintainable build graph. Restructure with interfaces or shared abstractions.
- **`GlobalScope` usage**: tears coroutines free from structured concurrency — leaked coroutines outlive their intended scope and cannot be cancelled by the parent.
- **Swallowing `CancellationException`**: catching `Exception` and not rethrowing `CancellationException` breaks coroutine cancellation. Always rethrow `CancellationException`.
- **Blocking call on Main dispatcher**: `Thread.sleep`, JDBC, `HttpURLConnection.connect`, or any blocking I/O on `Dispatchers.Main` freezes the UI thread. Wrap in `withContext(Dispatchers.IO)`.
- **Hardcoded secrets or API keys** in source code.
- **Exported Android component without justification**: `android:exported="true"` on an Activity, Service, or BroadcastReceiver that isn't an entry point exposes it to other apps.
- **`WebView` with JavaScript enabled and no URL validation**: opens the app to JavaScript injection. Validate URLs and disable JavaScript unless required.

## High — Strong Recommendation to Fix

- **`!!` (non-null assertion) in production code**: force-unwraps crash at runtime. Use `?.let`, `?: throw`, or pattern matching instead.
- **`var` where `val` works**: mutable state should be explicit and justified.
- **Mutable `StateFlow` or `MutableLiveData` exposed publicly**: external code can emit arbitrary values, bypassing ViewModel logic. Expose as read-only `StateFlow`/`LiveData`.
- **`Flow` collected in `init { }` or `viewModelScope.launch { }` without `WhileSubscribed`**: collection starts immediately and never stops, even when the UI is in the background.
- **Unstable Compose parameters**: non-stable types passed to `@Composable` functions prevent Compose from skipping recomposition. Use `@Stable`, `@Immutable`, or stable data classes.
- **Side effects outside `LaunchedEffect`/`SideEffect`**: direct state mutations or coroutine launches in composable function bodies run on every recomposition.
- **NavController passed deep into the composable tree**: composables below the screen level should receive navigation callbacks as lambdas, not a `NavController` reference.
- **Missing `key()` in `LazyColumn`/`LazyRow`**: reordering items without stable keys causes incorrect animations and state reuse bugs.
- **Non-exhaustive `when` on a sealed type**: adding a new subtype later will silently fall through without a compile error.
- **`Context` stored in a ViewModel**: causes a memory leak. Use `Application` context via `AndroidViewModel` if needed, or avoid storing context entirely.

## Medium

- Java-style patterns in Kotlin: null-returning methods instead of `null`-safe returns or `Result`, utility classes instead of extension functions, getter/setter methods instead of properties.
- String concatenation for building multi-part strings — use string templates or `StringBuilder`.
- Unused dependencies in `build.gradle.kts` adding binary size and compile time.
- Missing `@ProGuard` / R8 rules for serialized or reflected classes in release builds.

## Approval Criteria

CRITICAL and HIGH findings block approval. Fix, add a documented exception, or record accepted risk with written justification before merging.
