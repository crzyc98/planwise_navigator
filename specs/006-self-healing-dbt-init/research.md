# Research: Self-Healing dbt Initialization

**Feature Branch**: `006-self-healing-dbt-init`
**Date**: 2025-12-12

## Research Questions

### RQ-001: How to detect missing tables efficiently?

**Decision**: Use DuckDB's `information_schema.tables` query with a predefined list of required tables.

**Rationale**:
- DuckDB supports standard SQL `information_schema` views
- Single query can check all tables at once: `SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'`
- Compare against known required tables list (defined in Pydantic model)
- Existing pattern in `init_database.py:validate_database_structure()` already uses this approach

**Alternatives Considered**:
1. **Try/catch on first query**: Rejected - inconsistent error messages across DuckDB versions
2. **dbt manifest parsing**: Rejected - requires `dbt compile` first, circular dependency
3. **File system checks**: Rejected - DuckDB database is single file, can't inspect tables

### RQ-002: What tables are required for simulation to start?

**Decision**: Two-tier required table list:
- **Tier 1 (Seeds)**: `config_age_bands`, `config_tenure_bands`, `config_job_levels`, `comp_levers`, `irs_contribution_limits`
- **Tier 2 (Foundation)**: `int_baseline_workforce`, `int_employee_compensation_by_year`, `int_employee_benefits`

**Rationale**:
- Per clarification in spec.md: "Seed tables + foundation models"
- Seeds must load first (dbt seed), then foundation models build on them
- These are the minimum tables needed for `fct_yearly_events` generation

**Source**:
- `dbt/seeds/` directory listing
- `init_database.py:validate_database_structure()` required_tables list
- `pipeline/workflow.py` stage dependencies

### RQ-003: How to integrate with existing pipeline without breaking changes?

**Decision**: Add pre-simulation hook in `HookManager` that runs `AutoInitializer.ensure_initialized()`.

**Rationale**:
- `HookManager` already exists in `pipeline/hooks.py` (E072 modular architecture)
- Hooks are the extension point designed for cross-cutting concerns
- No changes to `PipelineOrchestrator.execute_multi_year_simulation()` signature
- Backward compatible: existing code paths unchanged

**Integration Point**:
```python
# In factory.py or PipelineOrchestrator.__init__
hook_manager.register_pre_simulation_hook(auto_initializer.ensure_initialized)
```

### RQ-004: How to handle concurrent initialization attempts?

**Decision**: Use file-based mutex lock (`.planalign_init.lock`) with timeout.

**Rationale**:
- Existing pattern: `ExecutionMutex` in `utils.py` provides file-based locking
- DuckDB supports single writer, so concurrent initializations would fail anyway
- Lock file location: same directory as database file for visibility
- 60-second timeout matches SC-003 performance target

**Implementation**:
```python
from planalign_orchestrator.utils import ExecutionMutex

class AutoInitializer:
    def ensure_initialized(self, db_path: Path) -> None:
        with ExecutionMutex(db_path.parent / ".planalign_init.lock", timeout=60):
            # Check and initialize
```

### RQ-005: How to provide progress feedback during initialization?

**Decision**: Use Rich console output with step progress, compatible with existing CLI patterns.

**Rationale**:
- `planalign_cli` already uses Rich for progress display
- Console output for CLI, structured logging for programmatic use
- Step timing logged per NFR-001/NFR-002

**Progress Steps**:
1. "Checking database tables..." (0-2s)
2. "Loading seed data..." (2-15s)
3. "Building foundation models..." (15-50s)
4. "Verifying initialization..." (50-55s)
5. "Initialization complete" (55-60s)

### RQ-006: How to handle corrupted database files?

**Decision**: Offer to recreate database after user confirmation (CLI) or fail with actionable error (API).

**Rationale**:
- Corruption detection: DuckDB raises `duckdb.IOException` on corrupt files
- User confirmation prevents accidental data loss
- API mode must fail fast with clear error for automation scenarios

**Detection**:
```python
try:
    conn = duckdb.connect(str(db_path))
    conn.execute("SELECT 1")  # Basic connectivity check
except duckdb.IOException as e:
    if "corrupt" in str(e).lower():
        raise DatabaseCorruptionError(db_path, original_error=e)
```

### RQ-007: Best practices for idempotent dbt initialization?

**Decision**: Use `dbt seed --full-refresh` + `dbt run --select tag:foundation` with `--threads 1`.

**Rationale**:
- `--full-refresh` ensures seeds are completely replaced (idempotent)
- Tag-based selection (`tag:foundation`) allows targeted model building
- Single-threaded execution per constitution principle VI

**dbt Commands**:
```bash
# Step 1: Load all seed data
dbt seed --full-refresh --threads 1

# Step 2: Build foundation models only
dbt run --select tag:foundation --threads 1
```

## Research Summary

| Question | Decision | Confidence |
|----------|----------|------------|
| RQ-001: Table detection | `information_schema.tables` query | High |
| RQ-002: Required tables | Two-tier: Seeds + Foundation models | High |
| RQ-003: Pipeline integration | Pre-simulation hook in HookManager | High |
| RQ-004: Concurrency control | File-based mutex with ExecutionMutex | High |
| RQ-005: Progress feedback | Rich console + structured logging | High |
| RQ-006: Corruption handling | User confirmation (CLI) / fail fast (API) | Medium |
| RQ-007: Idempotent init | `dbt seed --full-refresh` + tagged models | High |

## Outstanding Questions

None - all critical questions resolved.
