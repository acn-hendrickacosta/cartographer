# Python: Async and concurrency

- Choose async when I/O is the bottleneck and the framework already uses async (FastAPI, MCP SDK, etc.). Do not add async to CPU-bound or synchronous library code — the overhead of context switching is real.
- Do not mix sync and async code in the same call stack without an explicit bridge (`asyncio.run`, `loop.run_in_executor`). Calling a sync blocking function directly from an async function blocks the event loop.
- Use `asyncio.gather` for concurrent I/O. Avoid creating tasks that are never awaited.
- Keep the async surface at the edge of the application (API handlers, server main loops). Internal business logic that does not need async should not be async.
- If a function is async solely to satisfy an interface (e.g., an MCP handler signature), mark that explicitly with a comment and keep the body synchronous.
- Do not use `asyncio.sleep(0)` as a yield point in a tight loop. Use a proper queue or event instead.
- For subprocess calls inside an async context, use `asyncio.create_subprocess_exec` rather than `subprocess.run` to avoid blocking the event loop.
