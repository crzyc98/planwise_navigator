# Quickstart: Async Streaming for Simulation Progress Display

**Branch**: `065-async-progress-streaming`

## What This Feature Does

Enables real-time Rich progress bars during `planalign simulate` by resolving the stdout conflict between Rich's Live display and dbt subprocess output. Operators see year/stage progress, ETA, and optionally verbose dbt output — all without display corruption.

## Key Files to Modify

| File | Change | Why |
|------|--------|-----|
| `planalign_cli/commands/simulate.py` | Wire `progress_callback=progress_tracker.update` instead of `None`; add TTY detection | Enables the currently-disabled progress display |
| `planalign_cli/integration/orchestrator_wrapper.py` | Replace sys.stdout redirection with `Console.print()` for verbose output; fix regex patterns | Eliminates the root cause of display corruption |
| `planalign_orchestrator/pipeline/year_executor.py` | Add optional `progress_callback` parameter to stage execution methods | Direct callback signaling instead of print-and-parse |
| `planalign_orchestrator/dbt_runner.py` | Thread `on_line` callback through to progress display | Enables dbt output to appear in Rich Live display |

## New File

| File | Purpose |
|------|---------|
| `planalign_cli/ui/output_capture.py` | Thread-safe output capture that routes dbt output through Rich Console.print() |

## Development Flow

```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Run existing tests to establish baseline
pytest -m fast

# 3. Write tests first (TDD)
pytest tests/test_progress_display.py -v

# 4. Implement changes
# Start with simulate.py (wire callback) → orchestrator_wrapper.py (fix capture) → output_capture.py (new module)

# 5. Manual validation
planalign simulate 2025        # Single year — verify progress display
planalign simulate 2025-2027   # Multi year — verify ETA and year tracking
planalign simulate 2025 --verbose  # Verbose — verify dbt output coexistence
planalign simulate 2025 > log.txt  # Piped — verify plain-text fallback

# 6. Run full test suite
pytest --cov=planalign_cli -v
```

## Architecture Decision

**Before** (broken): `print() → sys.stdout redirect → regex parse → LiveProgressTracker`
**After** (fixed): `YearExecutor.callback() → LiveProgressTracker` (direct) + `DbtRunner.on_line → Console.print()` (Rich-safe)

The key insight: don't intercept stdout. Use explicit callbacks for progress signaling and Rich's built-in `Console.print()` for safe text output during Live rendering.
