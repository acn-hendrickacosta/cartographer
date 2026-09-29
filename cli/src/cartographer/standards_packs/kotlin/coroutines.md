# Kotlin Coroutines and Flow

- Never use `GlobalScope`. Coroutines must be launched from a structured scope (`viewModelScope`, `lifecycleScope`, `coroutineScope { }`) so cancellation and error propagation are handled correctly.
- Use `coroutineScope { }` with `async { }` for parallel decomposition of independent work. Use `supervisorScope { }` when child coroutine failures should not cancel sibling coroutines.

```kotlin
suspend fun loadDashboard(): Dashboard = coroutineScope {
    val users = async { userRepo.getAll() }
    val orders = async { orderRepo.getRecent() }
    Dashboard(users.await(), orders.await())
}
```

- Use `Flow` for streams of values. For UI state, expose `StateFlow` (always has a current value) rather than a mutable backing property. Use `SharedFlow` for one-time events (navigation, toasts) — configure `replay = 0` so events are not replayed to new subscribers.
- Scope `StateFlow` collection in ViewModels with `WhileSubscribed(5_000)` to stop upstream collection five seconds after the last subscriber disappears, reducing resource use while surviving configuration changes.

```kotlin
val uiState: StateFlow<UiState> = repository.observeItems()
    .map { UiState.Success(it) }
    .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), UiState.Loading)
```

- Apply standard Flow operators to tame noisy streams: `debounce(300)` for search queries, `distinctUntilChanged()` to suppress redundant emissions, `flatMapLatest` to cancel in-flight work when a new value arrives.
- Implement exponential backoff with `retryWhen { cause, attempt -> ... delay(2.0.pow(attempt).toLong() * 100) ... }` on network Flows. Do not retry infinitely — set a maximum attempt count.
- In long-running loops inside coroutines, call `ensureActive()` or `yield()` regularly to respect cancellation. Cancellation is cooperative — code that never checks cancellation will block cancellation.
- Use `withContext(Dispatchers.IO)` for blocking I/O and `withContext(Dispatchers.Default)` for CPU-intensive computation. Do not perform blocking calls on `Dispatchers.Main` or `Dispatchers.Unconfined`.
- Always catch `CancellationException` and rethrow it — swallowing it breaks structured concurrency. Only catch `Exception` in `try/catch` if you immediately check `is CancellationException` and rethrow.
- Use `finally { }` blocks to clean up resources (close connections, cancel jobs) when a coroutine is cancelled. Resources opened inside a coroutine must be closed whether the coroutine completed normally or was cancelled.
- Test `StateFlow` with Turbine (`flow.test { ... }`). Test coroutine timing with `StandardTestDispatcher` and `advanceTimeBy()`. Use `FakeRepository` implementations that emit from `MutableSharedFlow` for deterministic Flow tests.
