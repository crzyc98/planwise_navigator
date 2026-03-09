# Data Model: Async Streaming for Simulation Progress Display

**Date**: 2026-03-09
**Branch**: `065-async-progress-streaming`

## Entities

### ProgressUpdate (value object)

Represents a single progress signal emitted during simulation execution.

| Field | Type | Description |
|-------|------|-------------|
| update_type | enum: YEAR_START, STAGE_START, STAGE_COMPLETE, YEAR_COMPLETE, EVENT_COUNT, DBT_LINE | Type of progress signal |
| year | int (optional) | Simulation year (e.g., 2025) |
| stage | str (optional) | Pipeline stage name (e.g., "EVENT_GENERATION") |
| duration | float (optional) | Stage/year completion time in seconds |
| event_count | int (optional) | Number of events generated |
| message | str (optional) | Raw dbt output line (for DBT_LINE type) |

### ProgressCallback (protocol)

Interface that progress consumers must implement.

| Method | Parameters | Description |
|--------|-----------|-------------|
| update_year | year: int | Called when a new simulation year begins |
| update_stage | stage: str | Called when a pipeline stage begins |
| stage_completed | stage: str, duration: float | Called when a pipeline stage finishes |
| update_events | event_count: int | Called when events are generated |
| year_validation | year: int | Called when a year's validation completes |
| on_dbt_line | line: str | Called for each dbt output line (verbose mode) |

### LiveProgressTracker (existing entity, extended)

Current state of the progress display.

| Field | Type | Description |
|-------|------|-------------|
| total_years | int | Total simulation years to execute |
| current_year | int | Currently executing year |
| current_stage | str | Currently executing stage name |
| years_completed | int | Count of completed years |
| stage_durations | dict[str, float] | Duration of each completed stage |
| year_durations | list[float] | Duration of each completed year |
| events_per_year | dict[int, int] | Event counts by year |
| is_tty | bool | NEW: Whether running in an interactive terminal |
| estimated_remaining | float (optional) | NEW: Estimated seconds remaining |

## State Transitions

```
IDLE → YEAR_START → STAGE_START → STAGE_COMPLETE → ... → YEAR_COMPLETE → YEAR_START → ... → COMPLETE
                    ↑____________↓ (repeats for each of 6 stages)
```

Each year cycles through 6 stages:
1. INITIALIZATION
2. FOUNDATION
3. EVENT_GENERATION
4. STATE_ACCUMULATION
5. VALIDATION
6. REPORTING

## Relationships

- **LiveProgressTracker** consumes **ProgressUpdate** signals
- **YearExecutor** emits **ProgressUpdate** for stage lifecycle events
- **DbtRunner** emits **ProgressUpdate** (DBT_LINE type) for subprocess output lines
- **PipelineOrchestrator** emits **ProgressUpdate** for year lifecycle events
- **ProgressAwareOrchestrator** bridges the callback from CLI to orchestrator layers
