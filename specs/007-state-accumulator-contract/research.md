# Research: Temporal State Accumulator Contract

**Feature**: 007-state-accumulator-contract
**Date**: 2025-12-14

## Research Summary

All technical context is resolved; no "NEEDS CLARIFICATION" items remain.

---

## R1: Existing Registry Pattern Analysis

### Question
How does the existing `EventRegistry` pattern work, and should `StateAccumulatorRegistry` follow the same approach?

### Findings

The `EventRegistry` in `planalign_orchestrator/generators/registry.py` implements:

1. **Singleton Pattern**: Class-level dictionaries (`_generators`, `_instances`, `_disabled`)
2. **Decorator Registration**: `@EventRegistry.register("event_type")` for generator classes
3. **Lazy Instantiation**: Instances cached on first `get()` call
4. **Scenario-Specific Disabling**: `disable(event_type, scenario_id)` method
5. **Execution Ordering**: `list_ordered(scenario_id)` returns generators sorted by `execution_order`
6. **Mode Filtering**: `list_by_mode("sql"/"polars", scenario_id)` for execution mode support

### Decision
**Follow the EventRegistry pattern** for `StateAccumulatorRegistry` with these adaptations:
- Use class methods and class-level storage (singleton)
- No decorator (SQL models can't use Python decorators) - use explicit `register()` calls
- No scenario-specific disabling (all accumulators always active)
- Add `get_registered_tables()` for validation queries

### Rationale
Consistency with existing codebase patterns reduces cognitive load for developers familiar with the system.

---

## R2: State Accumulator Table Analysis

### Question
Which tables implement the temporal state accumulator pattern and what are their specific dependencies?

### Findings

**`int_enrollment_state_accumulator`** (`dbt/models/intermediate/int_enrollment_state_accumulator.sql`):
- Table: `int_enrollment_state_accumulator`
- Prior Year Source: `{{ this }}` WHERE `simulation_year = {{ simulation_year - 1 }}`
- Start Year Source: `int_baseline_workforce` (baseline_enrollment_state CTE)
- Key Columns: `employee_id`, `simulation_year`, `enrollment_status`, `enrollment_date`
- Self-Reference Pattern: Lines 175-189 read from `{{ this }}` for prior year state

**`int_deferral_rate_state_accumulator`** (`dbt/models/intermediate/int_deferral_rate_state_accumulator.sql`):
- Table: `int_deferral_rate_state_accumulator`
- Prior Year Source: Multiple upstream models (not direct self-reference)
- Start Year Source: `int_employee_compensation_by_year`, `int_enrollment_state_accumulator`
- Key Columns: `employee_id`, `simulation_year`, `current_deferral_rate`
- Note: Does NOT use `{{ this }}` self-reference; reads from upstream int_* models

**Additional Accumulator: `int_deferral_escalation_state_accumulator`**:
- Table: `int_deferral_escalation_state_accumulator`
- Uses similar temporal pattern with escalation tracking

### Decision
**Register both enrollment and deferral rate accumulators** initially. The deferral rate accumulator's dependencies are indirect (via `int_enrollment_state_accumulator`), so validating the enrollment accumulator's prior year data is sufficient for dependency chain validation.

### Rationale
Start with the most critical accumulators; the registry is extensible for future additions.

---

## R3: Validation Insertion Point

### Question
Where in the pipeline execution flow should year dependency validation occur?

### Findings

Pipeline execution flow (from `pipeline_orchestrator.py` and `year_executor.py`):

1. `PipelineOrchestrator.execute_multi_year_simulation()` - Iterates years
2. `PipelineOrchestrator._execute_year_workflow(year)` - Orchestrates single year
3. `YearExecutor.execute_workflow_stage(stage, year)` - Executes individual stages
4. Within `execute_workflow_stage()`:
   - Line 163-166: Special handling for `WorkflowStage.EVENT_GENERATION`
   - Line 166-177: Special handling for `WorkflowStage.STATE_ACCUMULATION`

The `STATE_ACCUMULATION` stage is where temporal dependencies matter most.

### Decision
**Insert validation in `YearExecutor.execute_workflow_stage()`** at the beginning of STATE_ACCUMULATION handling (before line 166). This is:
- Stage-specific (only validates when stage requires it)
- Year-aware (has access to `year` parameter)
- Early (fails before any model execution)

### Rationale
Validation at the YearExecutor level is the right abstraction - it's per-year, per-stage, and fails fast before wasting compute.

---

## R4: Database Connection Pattern

### Question
How should the validator access the database to check for prior year data?

### Findings

Existing patterns in `planalign_orchestrator`:

1. **`DatabaseConnectionManager`** (from `utils.py`): Provides `execute_with_retry()` for resilient queries
2. **`YearExecutor`** has `self.db_manager` attribute
3. **Query pattern** used in `StateManager.verify_year_population()`:
   ```python
   def _counts(conn):
       snap = conn.execute(
           "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
           [year],
       ).fetchone()[0]
       return int(snap)
   result = self.db_manager.execute_with_retry(_counts)
   ```

### Decision
**Use `DatabaseConnectionManager.execute_with_retry()`** with simple COUNT queries:
```python
def _check_year(conn):
    result = conn.execute(
        f"SELECT COUNT(*) FROM {table_name} WHERE simulation_year = ?",
        [year - 1]
    ).fetchone()[0]
    return int(result) > 0
```

### Rationale
Consistent with existing patterns; retry logic handles transient DuckDB lock issues.

---

## R5: Error Message Format

### Question
What information should the `YearDependencyError` include for actionable debugging?

### Findings

Existing error patterns from `exceptions.py` and `error_catalog.py`:
- `NavigatorError` base class with `message`, `error_code`, `context`, `resolution_hint`
- Error messages include: what failed, why it failed, how to fix it

### Decision
**YearDependencyError format**:
```
Year 2027 depends on year 2026 data which has not been executed.

Missing data for accumulators:
  - int_enrollment_state_accumulator (0 rows for year 2026)
  - int_deferral_rate_state_accumulator (0 rows for year 2026)

Resolution: Run years in sequence: 2025 → 2026 → 2027
            Or use --start-year 2026 to begin from the last valid checkpoint.
```

### Rationale
Actionable error messages reduce debugging time (Constitution Principle IV - Enterprise Transparency).

---

## R6: Checkpoint Recovery Integration

### Question
How should checkpoint recovery validate the dependency chain?

### Findings

Existing checkpoint flow (from `state_manager.py`):
1. `find_last_checkpoint()` returns `WorkflowCheckpoint` with year, stage, timestamp, state_hash
2. `PipelineOrchestrator.execute_multi_year_simulation()` uses checkpoint to set `start` year
3. No existing validation of database state against checkpoint

### Decision
**Add `validate_checkpoint_dependencies(checkpoint_year)` method** to `YearDependencyValidator`:
- Called before resuming from checkpoint
- Validates all years from `config.start_year` to `checkpoint_year - 1` have data
- Raises `YearDependencyError` if chain is broken

### Rationale
Prevents silent corruption when checkpoint exists but underlying data was deleted.

---

## Technology Choices Confirmed

| Choice | Technology | Version | Rationale |
|--------|------------|---------|-----------|
| Contract Model | Pydantic v2 | 2.7.4 | Type-safe validation, consistent with existing config patterns |
| Registry Pattern | Singleton (class methods) | N/A | Follows EventRegistry pattern |
| Database Access | DatabaseConnectionManager | N/A | Existing pattern with retry logic |
| Error Handling | NavigatorError subclass | N/A | Consistent with existing error catalog |
| Testing | pytest + fixtures | N/A | Consistent with tests/fixtures/ infrastructure |
