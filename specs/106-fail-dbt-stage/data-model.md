# Data Model: Fail Dbt Stage

## Simulation Run

Represents one simulation execution attempt for a scenario and year range.

**Fields relevant to this feature**:

- `status`: Must not become successful when any required workflow stage fails.
- `current_stage`: Should identify the stage active at the time of failure when available.
- `current_year`: Should identify the simulation year active at the time of failure when available.
- `error_summary`: Human-readable failure summary used by diagnostics or logs.

**Validation rules**:

- A simulation run with any failed required stage is invalid for successful result workflows.
- Failed runs may have partial outputs, but those outputs do not represent complete simulation results.

**State transitions**:

- `running` -> `failed` when a required workflow stage reports an unsuccessful or ambiguous outcome.
- `running` -> `completed` only when all required workflow stages explicitly succeed.

## Workflow Stage

Represents a required phase of simulation execution for a simulation year.

**Fields relevant to this feature**:

- `name`: Stable stage identifier used in failure messages and diagnostics.
- `year`: Simulation year for the stage execution.
- `required`: All stages in scope for this feature are required to complete before the run can be successful.

**Validation rules**:

- Required stages must produce an explicit successful outcome before orchestration proceeds.
- Required stages that fail must prevent later required stages from running for the same run.

## Stage Outcome

Represents the reported result from executing a workflow stage.

**Fields relevant to this feature**:

- `success`: Explicit success indicator. Only `true` permits orchestration to continue.
- `stage`: Stage name reported by the executor, used for diagnostics when present.
- `year`: Simulation year reported by the executor, used for diagnostics when present.
- `error`: Failure summary reported by the executor, used when present.
- `execution_time`: Duration metadata that may remain available for diagnostics.

**Validation rules**:

- `success: true` means the stage may be treated as successful.
- `success: false` means the stage must stop the run.
- Missing `success`, non-boolean success, missing outcome, or otherwise ambiguous outcome means the stage must stop the run.

## Failure Context

Represents the minimum information needed to diagnose and audit a stopped simulation run.

**Fields relevant to this feature**:

- `stage_name`: The workflow stage that failed or produced an ambiguous outcome.
- `simulation_year`: The year associated with the failed stage.
- `error_summary`: The reported error text, or a generic message when no text is available.

**Validation rules**:

- Failure context must always include stage name and simulation year from the orchestration call.
- Failure context should include the executor-provided error summary when available.
- Generic error summaries must be clear enough to identify missing or malformed stage outcomes.
