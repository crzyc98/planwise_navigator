# Implementation Plan: Async Streaming for Simulation Progress Display

**Branch**: `065-async-progress-streaming` | **Date**: 2026-03-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/065-async-progress-streaming/spec.md`

## Summary

Enable real-time Rich progress display during multi-year simulations by resolving the stdout conflict between Rich Live rendering and dbt subprocess output. The core approach: replace the broken sys.stdout redirection strategy with a callback-based architecture where the DbtRunner's existing `on_line` callback feeds progress updates to the LiveProgressTracker, and Rich's `Console.print()` is used for verbose dbt output instead of raw stdout writes.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Rich (Live, Progress, Layout, Console), Typer, subprocess (stdlib)
**Storage**: N/A (no data persistence changes)
**Testing**: pytest with `tests/fixtures/` library; mock subprocess for display tests
**Target Platform**: Linux (primary), macOS, Windows (ProactorEventLoop)
**Project Type**: CLI application (planalign_cli)
**Performance Goals**: <2% overhead on simulation total time; Rich Live refresh at 2 Hz
**Constraints**: No additional dependencies; must work with single-threaded dbt execution
**Scale/Scope**: 3 files modified, 1 new module (~150 lines), ~100 lines changed in existing files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | No event store changes |
| II. Modular Architecture | PASS | New output capture module has single responsibility; no module exceeds 600 lines |
| III. Test-First Development | PASS | Tests planned for progress callback wiring and output capture |
| IV. Enterprise Transparency | PASS | Progress display improves operational transparency |
| V. Type-Safe Configuration | N/A | No configuration schema changes |
| VI. Performance & Scalability | PASS | <2% overhead constraint; Rich refresh at 2 Hz is lightweight |

**Gate Result**: PASS — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/065-async-progress-streaming/
├── plan.md              # This file
├── research.md          # Phase 0: Architecture research
├── data-model.md        # Phase 1: Progress state model
├── quickstart.md        # Phase 1: Developer quickstart
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
planalign_cli/
├── commands/
│   └── simulate.py              # MODIFY: Wire progress_callback, add TTY detection
├── integration/
│   └── orchestrator_wrapper.py  # MODIFY: Fix regex patterns, use Console.print for verbose output
└── ui/
    └── output_capture.py        # NEW: Thread-safe output capture for Rich Live coexistence

planalign_orchestrator/
├── dbt_runner.py                # MODIFY: Add progress hook to on_line callback chain
└── pipeline/
    └── year_executor.py         # MODIFY: Emit structured progress signals via callback (not print)

tests/
├── test_progress_display.py     # NEW: Progress callback wiring and display tests
└── test_output_capture.py       # NEW: Output capture mechanism tests
```

**Structure Decision**: Modifications to existing CLI and orchestrator modules with one new UI module (`output_capture.py`) for the thread-safe capture mechanism. No new packages or architectural layers.
