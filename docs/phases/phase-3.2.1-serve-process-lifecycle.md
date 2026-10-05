# Phase 3.2.1: Serve Process Lifecycle — PID File, Signal Handling, and Supervision

**Status:** Code complete as of 2026-10-05. All 9 exit criteria verified — the first 7 manually against a live running instance (clean SIGTERM shutdown, startup collision refusal, stale-PID-file self-heal, `serve stop`/`status`, independent child-restart detection, and a crash loop that fired for real against leftover multi-day-old orphaned ports from this project's own earlier debugging session), plus 14 new unit tests in `cli/tests/test_serve_lifecycle.py` (171 total passing, no regressions).

## Goal

Make `cartographer serve` safe to run as a long-lived background process, not just an interactive foreground command. After this phase, stopping, restarting, and checking the health of `serve` are first-class operations with no manual `ps`/`kill` archaeology, and a crashed child process is detected and reported instead of silently leaving the index half-served.

**Entry condition:** Phase 3.1.1 complete (the subprocess-based `serve` architecture — main process spawning `cartographer-vdb-server` and `cartographer-kg-server --watch` as children — already exists and is in production use). No central backend required; this phase is local/process-management only. Numbered 3.2.1 rather than 3.1.3 because Phase 3.2 (tombstone protocol) is already complete as of this writing — this phase has no dependency on it, but slots after it chronologically rather than appearing to block it.

**Why now:** In enterprise deployments where `allowManagedHooksOnly` blocks Claude Code project hooks (see [[project_hooks_blocked_accenture]]-class policies), `cartographer serve --watch` is not an optional convenience — it is the *only* mechanism that keeps the local index fresh. Its process-lifecycle fragility has a direct, outsized impact on exactly the users who have no fallback.

---

## References

| Document | What to read |
|---|---|
| `cli/src/cartographer/commands/serve.py` | Current implementation — `KeyboardInterrupt`-only shutdown, no PID file, no supervision |
| `cli/src/cartographer/commands/doctor.py` | Existing check pattern (`OK`/`FAIL`/`INFO` console output) this phase extends |
| [phase-3.1.1-management-server.md](phase-3.1.1-management-server.md) | The subprocess architecture this phase hardens — do not re-architect it |

---

## Problem

Observed directly during Phase 3.2 development (2026-10-01), reproduced multiple times:

1. **SIGTERM is not handled.** `serve.py`'s shutdown logic lives entirely in `except KeyboardInterrupt:`, which only fires on SIGINT (Ctrl+C in an attached foreground terminal). A plain `kill <pid>` — the only option once the process is backgrounded with `nohup ... &`, which is how any non-interactive deployment (a background service, a login item, a supervisor-managed unit) necessarily runs it — delivers SIGTERM, skips the cleanup block entirely, and the main process exits immediately while its two subprocess children survive as orphans.
2. **No PID file.** There is no record of which PIDs belong to a running `serve` instance. Stopping it correctly requires manually finding the parent *and both children* via `ps`, which is exactly what this project's own debugging sessions had to do repeatedly.
3. **No startup collision check.** Starting a second `serve` while orphaned children from a prior instance still hold the ports fails with a raw `[Errno 48] address already in use` traceback from inside the child subprocess — not a clear message from the parent telling the user what's already running and how to stop it.
4. **No child supervision.** `for p in procs: p.wait()` blocks on the *first* subprocess (`vdb-server`) in sequence. If the *second* (`kg-server --watch` — the one actually holding the watcher thread) crashes or exits, the parent does not notice until the first one also exits. A dead watcher can sit silently for an arbitrary length of time with the index going stale and nothing surfacing that fact.
5. **No stop/status command.** There is no `cartographer serve stop` or `cartographer serve status`. The only supported lifecycle is "run in a foreground terminal and press Ctrl+C."
6. **`cartographer doctor` has no awareness of `serve` at all.** In an environment where `serve --watch` is the sole freshness mechanism, `doctor` passing all checks while `serve` is silently dead is a false sense of health.

---

## Scope

### In scope

| Component | Change |
|---|---|
| `commands/serve.py` | PID file write/cleanup; SIGTERM handler alongside existing SIGINT handling; startup collision check against an existing live PID file; replace sequential `p.wait()` with a supervision loop that notices either child exiting |
| `commands/serve.py` | New `cartographer serve stop` subcommand |
| `commands/serve.py` | New `cartographer serve status` subcommand |
| `commands/doctor.py` | New check: is `serve` running (PID file + liveness + `/health` on both ports)? `INFO` if not running (serve is optional unless hooks are blocked — doctor cannot know the org policy), clear status if running |
| New: `runtime/serve_state.py` | Shared PID-file read/write/validate helpers, used by `serve.py`'s own commands and by `doctor.py` — avoid duplicating liveness-check logic in two places |

### Explicitly out of scope

- Any change to what the watcher does once running (Phase 3.1's `on_deleted`/`on_moved` filtering bug is already fixed, separately, outside this phase)
- Unbounded auto-restart / crash-loop daemonization (e.g. systemd-style exponential backoff forever) — this phase bounds a single restart attempt per child and then fails loudly; running `serve` under an OS-level supervisor (launchd, systemd, a container restart policy) is the user's responsibility and explicitly out of scope
- Multi-machine or multi-user coordination (e.g. detecting another *user's* `serve` instance on a shared host) — PID files are per-user under `~/.cartographer/`, consistent with the existing registry location
- Changing the vdb-server/kg-server subprocess split or moving the watcher thread (Phase 3.1.1's architecture is correct and untouched)

---

## Component breakdown

### PID file

Location: `~/.cartographer/serve.pid` (same directory as `registry.json` — one `serve` instance is shared across all registered projects on a machine, so this is correctly machine-scoped, not project-scoped).

```json
{
  "pid": 12345,
  "vdb_pid": 12346,
  "kg_pid": 12347,
  "vdb_port": 4010,
  "kg_port": 4011,
  "started_at": "2026-10-01T20:17:23+00:00"
}
```

Written immediately after both subprocesses spawn successfully. Removed on any clean shutdown path (SIGTERM, SIGINT, or `serve stop`).

### Startup collision check

Before spawning, `serve.py` reads any existing PID file:

```python
existing = serve_state.read_pid_file()
if existing and serve_state.is_alive(existing.pid) and serve_state.is_healthy(existing):
    console.print(f"[red]cartographer serve is already running (pid {existing.pid}, started {existing.started_at})[/red]")
    console.print("Run 'cartographer serve stop' first, or 'cartographer serve status' to inspect it.")
    raise typer.Exit(code=1)
```

If the PID file exists but the process is dead (stale file — e.g. the machine was rebooted, or a prior run was `kill -9`'d), delete it silently and proceed.

### Signal handling

Register handlers for both `SIGTERM` and `SIGINT` that run the identical shutdown sequence (terminate children, wait with a timeout, `kill -9` any child still alive after the timeout, remove the PID file). This replaces the current `except KeyboardInterrupt` block, which only covers one of the two signals a backgrounded process will actually receive.

### Child supervision loop

Replace:

```python
for p in procs:
    p.wait()
```

with a loop that polls both children (e.g. `psutil`-free: `p.poll()` on each at a short interval, or `os.waitpid(-1, 0)` to block on *either* child exiting first) so that either child dying is noticed immediately, not only when both have exited.

On an unexpected child exit (return code != 0, and not during an intentional shutdown already in progress):
1. Log clearly which child died and its exit code.
2. Attempt exactly one restart of that child with a short delay (e.g. 2s).
3. If it exits again within a short window (e.g. 10s) after the restart, treat it as a crash loop: terminate the remaining healthy child, remove the PID file, exit non-zero. Do not retry indefinitely.

### `cartographer serve stop`

```
cartographer serve stop
```

Reads the PID file. If absent, reports "not running" and exits 0 (idempotent — matches the project's stated idempotency principle). If present, sends SIGTERM to the main PID, waits up to a few seconds for the PID file to be removed (i.e. for the shutdown sequence to complete cleanly), and force-kills any PID still alive after the timeout. Reports a final clear status.

### `cartographer serve status`

```
cartographer serve status
```

Reads the PID file; if present and the process is alive, hits `/health` on both the VDB and KG ports and reports uptime, PIDs, ports, and whether the watcher is enabled (`kg-server`'s `/health` already returns `"watch": true/false` — Phase 3.1.1 already exposes this, this command just surfaces it instead of requiring a manual `curl`).

### `cartographer doctor` addition

New check, placed after the existing local VDB/KG checks:

```
[green]OK[/green]   cartographer serve is running (pid 12345, watching)
```
or
```
[yellow]INFO[/yellow] cartographer serve is not running — local index will not auto-update on file changes
```

`INFO`, not `FAIL` — `doctor` has no way to know whether the user's org blocks hooks (in which case this is load-bearing) or not (in which case it's optional). The message itself should still be actionable.

---

## Exit criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | `kill <pid>` (plain SIGTERM, not SIGINT) against the main `serve` process cleanly stops both children and removes the PID file | Start serve; `kill` the main PID; confirm `ps` shows no cartographer-vdb-server/kg-server processes within a few seconds; confirm PID file is gone |
| 2 | Starting `serve` while a healthy instance is already running refuses to start a second instance and tells the user how to stop it | Start serve twice in a row without stopping; confirm the second invocation exits non-zero with a clear message, and the first instance's ports are untouched |
| 3 | Starting `serve` after a stale PID file (process no longer exists) succeeds without manual cleanup | Start serve; `kill -9` it directly (bypassing clean shutdown, leaving a stale PID file); start serve again; confirm it starts successfully |
| 4 | `cartographer serve stop` stops a running instance and is idempotent when run again | Start serve; `cartographer serve stop`; confirm clean shutdown; run `cartographer serve stop` again; confirm it reports "not running" and exits 0 |
| 5 | `cartographer serve status` reports accurate PIDs, ports, uptime, and watch state while running, and reports "not running" when stopped | Start serve; run status; confirm fields match; stop serve; run status again; confirm "not running" |
| 6 | If the kg-server child is killed independently (parent and vdb-server still alive), the parent notices, logs it, and attempts one restart | Start serve; `kill -9` only the kg-server child PID; confirm the parent's log shows detection and a restart attempt within a few seconds |
| 7 | A crash loop (child keeps dying immediately after restart) is detected, both children are shut down, and the process exits non-zero rather than looping forever | Simulate a child that exits immediately on start (e.g. a broken `--kg-port` pointing at a port the OS refuses); confirm serve detects the loop and exits non-zero instead of retrying indefinitely |
| 8 | `cartographer doctor` reports `serve` status accurately in both states | Run doctor with serve running (expect `OK`, watching); stop serve; run doctor again (expect `INFO`, not running) |
| 9 | All existing Phase 3.1/3.1.1/3.1.2 exit criteria still pass | Re-run `cli/tests/test_watcher.py`, `cli/tests/test_management_server.py`, `cli/tests/test_ui_delegation.py` |

---

## Test approach

### Unit tests (new: `cli/tests/test_serve_lifecycle.py`)

- PID file write/read round-trip; malformed/missing PID file handled gracefully
- `is_alive(pid)` correctly distinguishes a live PID from a stale one (spawn a real short-lived subprocess for the "stale" case rather than guessing at an unused PID number)
- Startup collision check: live PID file blocks a second start; stale PID file does not
- `serve stop` against a running instance (spawn real lightweight subprocesses standing in for vdb/kg-server, not the real heavyweight servers, to keep the test fast) and against no instance (idempotent no-op)
- Child supervision: simulate one child exiting unexpectedly; confirm restart-once-then-give-up behavior with a short timeout so the test doesn't hang

### Manual / integration verification

- The SIGTERM reproduction (exit criterion 1) cannot be meaningfully faked with a mock subprocess — it depends on real OS signal delivery to a real process tree. Verify manually against the actual `cartographer serve` command, not just the unit-tested helpers.

---

*Previous pass: [Phase 3.2 — Tombstone Protocol](phase-3.2-tombstone.md)*
*Next pass: [Phase 3.3 — Rename Tracking](phase-3.3-rename-tracking.md)*
