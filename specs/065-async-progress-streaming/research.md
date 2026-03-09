# Research: Async Streaming for Simulation Progress Display

**Date**: 2026-03-09
**Branch**: `065-async-progress-streaming`

## R1: Why sys.stdout Redirection Fails with Rich Live

**Decision**: Replace sys.stdout redirection with callback-based progress signaling.

**Rationale**: The current `EnhancedProgressMonitor` redirects `sys.stdout` to intercept print statements and extract progress markers via regex. This approach has two fundamental flaws:

1. **Subprocess output bypasses sys.stdout**: dbt runs in a subprocess with `subprocess.Popen(..., stdout=subprocess.PIPE)`. The subprocess writes to its own file descriptor, not Python's `sys.stdout`. Redirecting `sys.stdout` only captures Python-level `print()` calls from the orchestrator, not dbt's actual output.

2. **Rich Live refresh conflicts with raw stdout**: Rich's `Live` display redraws the terminal every 0.5 seconds (refresh_per_second=2). When anything else writes to the same terminal via `sys.stdout.write()`, the output interleaves with Rich's ANSI escape sequences, causing visual corruption and apparent "freezing."

**Alternatives considered**:
- **pty-based capture**: Using `os.openpty()` to create a pseudo-terminal and capture all subprocess output. Rejected: too complex, platform-dependent (no Windows pty support), and overkill for this use case.
- **Thread-based stdout queue**: Queue all stdout writes and flush them during Rich's refresh cycle. Rejected: adds latency to output and complexity to threading model.
- **Rich Console.print() integration**: Use Rich's own `Console.print()` inside the `Live` context to safely inject log lines into the display. This is Rich's officially supported pattern for output during Live rendering.

## R2: Best Practice for Rich Live + Subprocess Output

**Decision**: Use Rich's `Live.console.print()` for verbose dbt output; use callback-based progress signaling for stage/year tracking.

**Rationale**: Rich's `Live` display provides `Live.console.print()` which safely renders text above the live display area without corruption. This is the documented pattern for showing log output alongside a live progress display.

For progress tracking, instead of intercepting stdout, inject a progress callback directly into the execution pipeline:
- `DbtRunner` already has an `on_line` callback parameter
- `YearExecutor` already has access to stage lifecycle events
- `PipelineOrchestrator` already has a year-level loop

Wire these existing callback points directly to `LiveProgressTracker` methods.

**Alternatives considered**:
- **Keep sys.stdout redirection but fix regex patterns**: Would fix pattern matching but not the fundamental subprocess PIPE issue or Rich Live conflict.
- **Use Rich's `Console(file=...)` with captured output**: Would require buffering all output and losing real-time display.

## R3: Non-Interactive Terminal Detection

**Decision**: Use `sys.stdout.isatty()` to detect interactive terminals; fall back to plain-text `print()` progress for non-interactive sessions.

**Rationale**: When stdout is piped (e.g., `planalign simulate 2025 > log.txt`), Rich's ANSI escape codes produce unreadable output. Python's `sys.stdout.isatty()` reliably detects this on all platforms. Rich also provides `Console(force_terminal=...)` for explicit override.

**Alternatives considered**:
- **Environment variable override** (`PLANALIGN_PROGRESS=plain`): Adds configuration surface; not needed when isatty() works.
- **Rich's auto-detection**: Rich's `Console()` already detects TTY, but we need to also skip the `Live` context manager entirely for non-TTY scenarios.

## R4: Regex Pattern Mismatch in EnhancedProgressMonitor

**Decision**: Fix the regex patterns to match actual print statements, but also add direct callback wiring as the primary mechanism.

**Rationale**: The `EnhancedProgressMonitor` expects patterns like `📋 Executing stage:` but the actual code in `year_executor.py` prints `📋 Starting {stage.name.value}`. Even fixing the patterns is fragile — print message format changes would silently break progress tracking.

The robust solution: wire progress callbacks directly through the execution stack so progress signals are explicit method calls, not regex-parsed stdout text.

**Mapping of actual print statements to expected patterns**:
| Expected Pattern | Actual Print Statement | Match? |
|-----------------|----------------------|--------|
| `🔄 Starting simulation year (\d+)` | `🔄 Starting simulation year {year}` | Yes |
| `📋 Executing stage: (\w+)` | `📋 Starting {stage.name.value} with {threads} threads` | No |
| `✅ Completed (\w+) in (\d+\.\d+)s` | `✅ Completed {stage.name.value} in {time:.1f}s` | Yes |
| `📊 Generated (\d+) events` | Not printed | No |

## R5: Cross-Platform Terminal Compatibility

**Decision**: Rely on Rich's built-in platform detection; add Windows ProactorEventLoop guard only if async is introduced.

**Rationale**: Rich handles cross-platform terminal rendering (ANSI on Linux/macOS, Windows Console API on Windows) automatically. Since this feature does NOT introduce asyncio (despite the issue title mentioning "async"), no ProactorEventLoop handling is needed. The "async" in the issue title refers to non-blocking progress updates, not Python's `asyncio`.

**Alternatives considered**:
- **asyncio-based progress updates**: Would require restructuring the synchronous pipeline execution model. Rejected: unnecessary complexity for a display-only feature.
- **Threading for progress refresh**: Rich's `Live` already runs its refresh in a background thread. No additional threading needed.

## R6: Estimated Time Remaining Calculation

**Decision**: Use simple arithmetic based on first-year completion time.

**Rationale**: After year 1 completes, calculate `estimated_remaining = year_1_duration * remaining_years`. This is accurate enough (within 30% per SC-003) because each simulation year performs roughly the same work. No sophisticated statistical estimation is needed.

The `LiveProgressTracker` already tracks `year_durations` in its state, so ETA calculation requires only a simple method addition.

**Alternatives considered**:
- **Exponential moving average across stages**: More accurate but unnecessary complexity for 2-5 year simulations.
- **Stage-weighted estimation**: Weight EVENT_GENERATION higher since it takes ~60% of year time. Deferred to future enhancement if the simple approach proves inaccurate.
