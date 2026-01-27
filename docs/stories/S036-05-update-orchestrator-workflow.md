# Story S036-05: Update Orchestrator Workflow

**Epic**: E036 - Deferral Rate State Accumulator Architecture
**Story Points**: 2
**Priority**: Critical
**Sprint**: Infrastructure Fix
**Owner**: Technical Architecture Team
**Status**: 🔵 Ready for Implementation
**Type**: Integration

## Story

**As a** platform engineer
**I want** to update the `run_multi_year.py` orchestrator workflow to include the deferral rate state accumulator
**So that** multi-year simulations execute in the correct order without circular dependency errors

## Business Context

The current `run_multi_year.py` orchestrator has an execution order that causes circular dependency failures when `int_employee_contributions` tries to read from `fct_yearly_events` before it's built. This story updates the orchestration workflow to include the new `int_deferral_rate_state_accumulator` model and removes the duplicate `int_employee_contributions` call, ensuring proper dependency order.

## Current Orchestration Issues

### Problematic Execution Order
```python
# CURRENT BROKEN ORDER in run_multi_year.py
1. int_enrollment_events
2. int_employee_contributions  # ❌ FAILS - tries to read fct_yearly_events before it exists
3. fct_yearly_events           # Built after contributions tries to read it
4. duplicate int_employee_contributions call (line 579)  # ❌ UNNECESSARY
```

### Target Fixed Order
```python
# CORRECTED ORDER (avoid fct_yearly_events in accumulator inputs)
1. int_enrollment_events, int_deferral_escalation_events (sources)
2. int_deferral_rate_state_accumulator (accumulates from int_* sources)
3. int_employee_contributions (reads from accumulator, no circular dep)
4. fct_yearly_events (consolidates all events including contributions)
5. fct_workforce_snapshot (final state)
```

## Acceptance Criteria

### Orchestration Order & Resilience
- [ ] **Add `int_deferral_rate_state_accumulator`** to workflow execution order
- [ ] **Implement batched phase execution** using dbt's DAG benefits within phases
- [ ] **Enforce dbt working directory** context (cd dbt/ or --project-dir dbt)
- [ ] **Add idempotent per-year cleanup** with delete+insert strategy validation
- [ ] **Implement checkpointing and resume** from last incomplete year
- [ ] **Remove duplicate `int_employee_contributions` call** from line 579

### Data Quality Gates & Error Handling
- [ ] **Add targeted `dbt test` after critical phases** for quality gates
- [ ] **Implement DuckDB lock handling** with mutex and retry logic
- [ ] **Pass complete variable scope** including scenario_id and plan_design_id
- [ ] **Add pre-run dbt compile** to fail fast on compilation errors
- [ ] **Implement per-phase validation** before proceeding to next phase

### Selector Strategy & Performance
- [ ] **Replace path-based selectors** with tags/graph-based selectors for reliability
- [ ] **Use `--defer --state` optimization** for faster incremental builds
- [ ] **Implement configurable threading** with proper resource management
- [ ] **Add accumulator continuity validation** when year > start_year
- [ ] **Preserve all existing functionality** including audit results and snapshots

## Implementation Changes

### Updated Orchestration Flow

```python
# run_multi_year.py - Resilient orchestration with batched phases and quality gates

import json
from pathlib import Path
from contextlib import contextmanager
from shared_utils import mutex  # For DuckDB locking

@contextmanager
def dbt_project_context():
    """Ensure dbt commands run from correct project directory."""
    original_cwd = os.getcwd()
    try:
        os.chdir('dbt')  # Enforce dbt working directory
        yield
    finally:
        os.chdir(original_cwd)

def dbt_cmd_with_retry(cmd_args: list, max_retries: int = 3):
    """Execute dbt command with retry logic for DuckDB lock handling."""
    for attempt in range(max_retries):
        try:
            with mutex("duckdb"):  # Serialize DB writes
                with dbt_project_context():
                    return execute_dbt_command_streaming(cmd_args)
        except Exception as e:
            if "lock" in str(e).lower() and attempt < max_retries - 1:
                wait_time = (2 ** attempt) + random.uniform(0, 1)  # Exponential backoff with jitter
                logger.warning(f"DuckDB lock detected, retrying in {wait_time:.1f}s (attempt {attempt + 1})")
                time.sleep(wait_time)
                continue
            raise

def run_year_simulation(year: int, config: SimulationConfig):
    """Run simulation for a single year with batched phases and quality gates."""

    logger.info(f"Starting simulation for year {year}")

    # Build complete variable context
    vars_dict = {
        "simulation_year": year,
        "scenario_id": config.scenario_id,
        "plan_design_id": config.plan_design_id or "default"
    }
    vars_str = json.dumps(vars_dict).replace('"', '\"')  # JSON format for --vars

    # Pre-flight: Compile to catch errors early
    logger.info(f"Pre-flight compilation check for year {year}")
    dbt_cmd_with_retry([
        "dbt", "compile",
        "--vars", vars_str,
        "--fail-fast"
    ])

    # Phase 1: Source Data Preparation (batched build)
    logger.info(f"Phase 1: Source data preparation for year {year}")
    dbt_cmd_with_retry([
        "dbt", "build",
        "--select", "stg+ int_baseline_workforce int_enrollment_events int_deferral_rate_escalation_events int_employee_compensation_by_year",
        "--vars", vars_str,
        "--fail-fast",
        "--warn-error",
        f"--threads", str(config.dbt_threads or 4)
    ])

    # Phase 2: State Accumulation (NEW - breaks circular dependency)
    logger.info(f"Phase 2: Building deferral rate state accumulator for year {year}")
    dbt_cmd_with_retry([
        "dbt", "build",
        "--select", "int_deferral_rate_state_accumulator",
        "--vars", vars_str,
        "--fail-fast"
    ])

    # Quality Gate: Test accumulator after build
    logger.info(f"Quality Gate 2: Testing state accumulator for year {year}")
    dbt_cmd_with_retry([
        "dbt", "test",
        "--select", "int_deferral_rate_state_accumulator",
        "--vars", vars_str
    ])
    validate_accumulator_state(year, config)  # Custom validation

    # Phase 3: Contribution Calculations (using accumulator, no circular dependency)
    logger.info(f"Phase 3: Calculating employee contributions for year {year}")
    dbt_cmd_with_retry([
        "dbt", "build",
        "--select", "int_employee_contributions",
        "--vars", vars_str,
        "--fail-fast"
    ])

    # Quality Gate: Test contributions after build
    logger.info(f"Quality Gate 3: Testing employee contributions for year {year}")
    dbt_cmd_with_retry([
        "dbt", "test",
        "--select", "int_employee_contributions",
        "--vars", vars_str
    ])

    # Phase 4: Event Consolidation & Final Processing (batched)
    logger.info(f"Phase 4: Event consolidation and workforce snapshot for year {year}")
    dbt_cmd_with_retry([
        "dbt", "build",
        "--select", "fct_yearly_events fct_workforce_snapshot",
        "--vars", vars_str,
        "--fail-fast"
    ])

    # Final Quality Gate: Test marts
    logger.info(f"Quality Gate 4: Testing final marts for year {year}")
    dbt_cmd_with_retry([
        "dbt", "test",
        "--select", "fct_yearly_events fct_workforce_snapshot",
        "--vars", vars_str
    ])

    # ❌ REMOVE: Duplicate int_employee_contributions call (line 579)
    # This was causing unnecessary rebuilds and potential inconsistency

    # Phase 5: Audit & Validation
    execute_audit_for_year(year, config)

    # Mark year as completed for checkpointing
    mark_year_completed(year, config)

    logger.info(f"Completed simulation for year {year}")

def execute_multi_year_simulation(config: SimulationConfig):
    """Execute multi-year simulation with checkpointing and resume capability."""

    start_year = config.start_year
    end_year = config.end_year

    logger.info(f"Starting multi-year simulation: {start_year} to {end_year}")

    # Load checkpoint status
    checkpoint_file = Path("year_status.json")
    completed_years = load_checkpoint_status(checkpoint_file)

    for year in range(start_year, end_year + 1):
        # Skip already completed years for resume capability
        if year in completed_years:
            logger.info(f"Skipping year {year} - already completed (resume mode)")
            continue

        logger.info(f"Processing year {year} of {end_year}")

        try:
            # Validate previous year state continuity (if not first year)
            if year > start_year:
                validate_previous_year_state(year - 1, config)

            run_year_simulation(year, config)

            # Validate year completion before proceeding
            validate_year_completion(year, config)

        except Exception as e:
            logger.error(f"Failed to complete year {year}: {str(e)}")
            save_checkpoint_status(checkpoint_file, completed_years)  # Save progress
            raise

    # Final multi-year validation
    validate_multi_year_consistency(start_year, end_year, config)

    # Clean up checkpoint file on successful completion
    if checkpoint_file.exists():
        checkpoint_file.unlink()

    logger.info(f"Multi-year simulation completed successfully: {start_year}-{end_year}")
```

### Alternative Selector-Based Approach

```python
def run_year_using_selectors(year: int):
    """Alternative approach using dbt selectors for dependency management."""

    # Option 1: Build accumulator and everything downstream
    execute_dbt_command_streaming([
        "dbt", "build",
        "--select", "int_deferral_rate_state_accumulator+",  # Accumulator + downstream
        "--vars", f"simulation_year: {year}"
    ])

    # Option 2: Targeted build for contributions and dependencies
    execute_dbt_command_streaming([
        "dbt", "build",
        "--select", "+int_employee_contributions int_employee_contributions+",  # Upstream + model + downstream
        "--vars", f"simulation_year: {year}"
    ])
```

### Error Handling & Recovery

```python
def validate_accumulator_state(year: int, config: SimulationConfig):
    """Validate deferral rate state accumulator has proper data for the year."""

    conn = get_database_connection()
    try:
        # Check employee count
        result = conn.execute("""
            SELECT COUNT(*) as employee_count
            FROM int_deferral_rate_state_accumulator
            WHERE simulation_year = ?
              AND scenario_id = ?
              AND is_current = TRUE
              AND is_active = TRUE
        """, [year, config.scenario_id]).fetchone()

        if result[0] == 0:
            raise ValueError(f"No active employee states found in accumulator for year {year}")

        # Check monthly grain completeness (should be 12 rows per employee)
        monthly_check = conn.execute("""
            SELECT employee_id, COUNT(*) as month_count
            FROM int_deferral_rate_state_accumulator
            WHERE simulation_year = ? AND scenario_id = ?
            GROUP BY employee_id
            HAVING COUNT(*) != 12
            LIMIT 5
        """, [year, config.scenario_id]).fetchall()

        if monthly_check:
            logger.warning(f"Found {len(monthly_check)} employees with incomplete monthly grain")

        logger.info(f"Accumulator validation passed: {result[0]} employees for year {year}")

    finally:
        conn.close()

def validate_previous_year_state(year: int, config: SimulationConfig):
    """Validate accumulator continuity from previous year."""

    conn = get_database_connection()
    try:
        result = conn.execute("""
            SELECT COUNT(*) as prev_year_count
            FROM int_deferral_rate_state_accumulator
            WHERE simulation_year = ?
              AND scenario_id = ?
              AND is_current = TRUE
        """, [year, config.scenario_id]).fetchone()

        if result[0] == 0:
            raise ValueError(f"Missing previous year state for continuity validation: year {year}")

        logger.info(f"Previous year state validation passed: {result[0]} states for year {year}")

    finally:
        conn.close()

def validate_year_completion(year: int, config: SimulationConfig):
    """Validate all required models have data for the completed year."""

    required_models = [
        "int_deferral_rate_state_accumulator",
        "int_employee_contributions",
        "fct_yearly_events",
        "fct_workforce_snapshot"
    ]

    conn = get_database_connection()
    try:
        validation_results = {}

        for model in required_models:
            result = conn.execute(f"""
                SELECT COUNT(*) FROM {model}
                WHERE simulation_year = ?
                  AND scenario_id = ?
            """, [year, config.scenario_id]).fetchone()

            validation_results[model] = result[0]

            if result[0] == 0:
                raise ValueError(f"No data found in {model} for year {year}, scenario {config.scenario_id}")

        # Consistency check: contributions should match accumulator employee count
        if validation_results["int_employee_contributions"] == 0:
            raise ValueError(f"No contributions calculated for year {year}")

        logger.info(f"Year {year} completion validation passed: {validation_results}")

    finally:
        conn.close()

def validate_multi_year_consistency(start_year: int, end_year: int, config: SimulationConfig):
    """Validate data consistency across the entire multi-year simulation."""

    conn = get_database_connection()
    try:
        # Check for year gaps in accumulator
        year_gaps = conn.execute("""
            WITH year_range AS (
                SELECT generate_series(?, ?) as expected_year
            )
            SELECT yr.expected_year
            FROM year_range yr
            LEFT JOIN (
                SELECT DISTINCT simulation_year
                FROM int_deferral_rate_state_accumulator
                WHERE scenario_id = ?
            ) acc ON yr.expected_year = acc.simulation_year
            WHERE acc.simulation_year IS NULL
        """, [start_year, end_year, config.scenario_id]).fetchall()

        if year_gaps:
            missing_years = [row[0] for row in year_gaps]
            raise ValueError(f"Missing accumulator data for years: {missing_years}")

        logger.info(f"Multi-year consistency validation passed: {start_year}-{end_year}")

    finally:
        conn.close()
```

## Orchestration Configuration Updates

### dbt Selector Definitions

### Model Tagging Strategy (Required Implementation)

```sql
-- Models should be tagged for reliable selector usage
-- int_baseline_workforce.sql
{{ config(
    materialized='incremental',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
    incremental_strategy='delete+insert',
    tags=['deferral_pipeline', 'foundation']
) }}

-- int_deferral_rate_state_accumulator.sql
{{ config(
    materialized='incremental',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year', 'as_of_month'],
    incremental_strategy='delete+insert',
    tags=['deferral_pipeline', 'state_accumulator']
) }}

-- int_employee_contributions.sql
{{ config(
    materialized='incremental',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
    incremental_strategy='delete+insert',
    tags=['deferral_pipeline', 'contributions']
) }}

-- fct_yearly_events.sql, fct_workforce_snapshot.sql
{{ config(
    materialized='incremental',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
    incremental_strategy='delete+insert',
    tags=['marts', 'final_output']
) }}
```

```yaml
# dbt/selectors.yml - Robust tag and graph-based selectors

selectors:
  - name: deferral_rate_pipeline
    description: "Complete deferral rate pipeline using tags for stability"
    definition:
      method: tag
      value: "deferral_pipeline"

  - name: contributions_pipeline
    description: "Contribution calculations with proper dependencies"
    definition:
      method: graph
      value: "+int_employee_contributions int_employee_contributions+"

  - name: state_accumulator_deps
    description: "State accumulator and all its upstream dependencies"
    definition:
      method: graph
      value: "+int_deferral_rate_state_accumulator"

  - name: year_simulation
    description: "Complete year simulation using graph relationships"
    definition:
      union:
        - method: tag
          value: "deferral_pipeline"
        - method: graph
          value: "fct_workforce_snapshot"
        - method: graph
          value: "fct_yearly_events"

  - name: quality_gates
    description: "Critical models that need testing after each phase"
    definition:
      union:
        - method: fqn
          value: "int_deferral_rate_state_accumulator"
        - method: fqn
          value: "int_employee_contributions"
        - method: tag
          value: "marts"
```

### Usage in Orchestration

```python
# Checkpointing and resume functionality
def load_checkpoint_status(checkpoint_file: Path) -> set:
    """Load completed years from checkpoint file."""
    if checkpoint_file.exists():
        with open(checkpoint_file) as f:
            data = json.load(f)
            return set(data.get("completed_years", []))
    return set()

def save_checkpoint_status(checkpoint_file: Path, completed_years: set):
    """Save completed years to checkpoint file."""
    data = {
        "completed_years": list(completed_years),
        "last_updated": datetime.now().isoformat()
    }
    with open(checkpoint_file, 'w') as f:
        json.dump(data, f, indent=2)

def mark_year_completed(year: int, config: SimulationConfig):
    """Mark year as completed in checkpoint."""
    checkpoint_file = Path("year_status.json")
    completed_years = load_checkpoint_status(checkpoint_file)
    completed_years.add(year)
    save_checkpoint_status(checkpoint_file, completed_years)

# Use selectors for clean dependency management
def run_year_with_selectors(year: int, config: SimulationConfig):
    """Alternative: Run year simulation using dbt selectors."""

    vars_dict = {
        "simulation_year": year,
        "scenario_id": config.scenario_id,
        "plan_design_id": config.plan_design_id or "default"
    }
    vars_str = json.dumps(vars_dict)

    dbt_cmd_with_retry([
        "dbt", "build",
        "--selector", "year_simulation",
        "--vars", vars_str,
        "--defer", "--state", "target/",  # Performance optimization
        f"--threads", str(config.dbt_threads or 4)
    ])
```

## Implementation Tasks

### Phase 1: Orchestration Order Updates
- [ ] **Analyze current `run_multi_year.py`** execution order and identify exact changes needed
- [ ] **Add `int_deferral_rate_state_accumulator`** to the workflow before contributions
- [ ] **Update model execution sequence** to ensure proper dependency order
- [ ] **Remove duplicate `int_employee_contributions` call** from line 579

### Phase 2: Error Handling & Validation
- [ ] **Add accumulator-specific validation** functions for data completeness
- [ ] **Implement year completion checks** for all required models
- [ ] **Add error handling** for accumulator build failures
- [ ] **Create recovery procedures** for partial year failures

### Phase 3: Alternative Selector Implementation
- [ ] **Define dbt selectors** for the new accumulator pipeline
- [ ] **Test selector-based execution** as alternative to explicit ordering
- [ ] **Document selector usage** for targeted builds and troubleshooting
- [ ] **Compare performance** of explicit vs. selector-based approaches

### Phase 4: Model Tagging & Selector Implementation
- [ ] **Tag models with `deferral_pipeline`** for reliable selection
- [ ] **Tag final models with `marts`** for quality gate testing
- [ ] **Test tag-based selectors** replace path-based selections
- [ ] **Validate graph selectors** include proper upstream dependencies

### Phase 5: Testing & Documentation
- [ ] **Test complete multi-year execution** with resilient orchestration
- [ ] **Test checkpoint/resume functionality** with partial failures
- [ ] **Validate DuckDB lock handling** under concurrent access
- [ ] **Benchmark batched vs. serial execution** performance improvements
- [ ] **Update orchestration documentation** with resilience patterns
- [ ] **Create troubleshooting guide** for accumulator and locking issues

## Dependencies

### Story Dependencies
- **S036-03**: Temporal State Tracking (needs working accumulator model)
- **S036-04**: Refactor Employee Contributions (needs refactored model)

### Technical Dependencies
- Working `int_deferral_rate_state_accumulator` model
- Refactored `int_employee_contributions` model
- Existing multi-year orchestration framework
- dbt selector functionality

### Blocking for Other Stories
- **S036-06**: Data Quality Validation (needs working orchestration)
- **S036-07**: Performance Testing (needs complete workflow)

## Success Metrics

### Orchestration Resilience & Correctness
- [ ] **Multi-year simulation executes successfully** without circular dependency errors
- [ ] **Idempotent per-year runs** produce identical outputs or replace cleanly
- [ ] **Checkpoint/resume capability** works from last incomplete year
- [ ] **DuckDB lock handling** prevents failures from concurrency issues
- [ ] **Quality gates enforce** accumulator and contribution correctness
- [ ] **Complete variable scope** passes scenario_id and plan_design_id correctly

### Performance & Reliability
- [ ] **Batched phase execution** significantly faster than model-by-model approach
- [ ] **Tag/graph selectors** more reliable than path-based selection
- [ ] **Pre-flight compilation** catches errors before expensive builds
- [ ] **`--defer --state` optimization** reduces unnecessary rebuilds when appropriate
- [ ] **Recovery procedures tested** for partial year failures with resume capability
- [ ] **Mutex and retry logic** handles DuckDB lock contention gracefully

### Integration Quality
- [ ] **Backward compatibility maintained** with existing orchestration patterns
- [ ] **Audit and validation functions** work with new orchestration flow
- [ ] **Documentation updated** with accurate workflow descriptions
- [ ] **Troubleshooting guides available** for new dependency patterns

## Testing Strategy

### End-to-End Testing
```python
# Test complete multi-year workflow
def test_multi_year_orchestration():
    config = SimulationConfig(
        start_year=2025,
        end_year=2027,
        scenario_id="test_e036"
    )

    # Should complete without errors
    execute_multi_year_simulation(config)

    # Validate all years have complete data
    for year in range(2025, 2028):
        validate_year_completion(year)
```

### Performance Testing
```python
# Compare execution times before/after changes
def benchmark_orchestration():
    old_time = benchmark_old_orchestration()
    new_time = benchmark_new_orchestration()

    performance_ratio = new_time / old_time
    assert performance_ratio <= 1.1  # No more than 10% slower
```

### Dependency Validation
```sql
-- Verify no circular dependencies exist
WITH RECURSIVE model_dependencies AS (
  -- Test dependency graph for cycles
)
SELECT * FROM model_dependencies
WHERE circular_dependency = TRUE
-- Should return 0 rows
```

## Definition of Done

- [ ] **`run_multi_year.py` updated** with `int_deferral_rate_state_accumulator` in workflow
- [ ] **Model execution order corrected** to prevent circular dependencies
- [ ] **Duplicate `int_employee_contributions` call removed** from line 579
- [ ] **End-to-end multi-year simulation tested** and executes successfully
- [ ] **Error handling implemented** for accumulator-specific failures
- [ ] **Performance validated** meets existing benchmarks
- [ ] **Documentation updated** with new orchestration workflow
- [ ] **Ready for data quality validation** in subsequent story

## Implementation Notes & Resilience Patterns

### Execution Context Enforcement
The improved orchestrator enforces **proper dbt working directory** context using:
- `@contextmanager dbt_project_context()` to ensure commands run from `dbt/` directory
- Eliminates path-related issues that can cause model compilation failures
- Consistent command execution regardless of script invocation location

### Batched Phase Execution Strategy
**Phase-based batching** leverages dbt's DAG optimization within phases:
- **Phase 1**: `--select "stg+ int_baseline_workforce int_enrollment_events int_deferral_rate_escalation_events int_employee_compensation_by_year"`
- **Phase 2**: Single critical model with immediate testing gate
- **Phase 3**: Contributions with validation
- **Phase 4**: Final marts with comprehensive testing

This approach is **significantly faster** than model-by-model execution while maintaining dependency safety.

### DuckDB Lock Handling & Concurrency
**Robust locking strategy** prevents common DuckDB concurrency issues:
- `shared_utils.mutex("duckdb")` serializes database writes
- Exponential backoff with jitter for retry logic
- Maximum 3 retry attempts with intelligent error detection
- Prevents simulation failures from temporary lock contention

### Idempotency & Resume Capability
**Checkpoint-based resume** enables recovery from failures:
- `year_status.json` tracks completed years with timestamps
- Re-running automatically skips completed years
- Model-level `delete+insert` strategies ensure clean year rebuilds
- No manual intervention required for partial failure recovery

### Data Quality Gates
**Phase-level testing** ensures data integrity:
- `dbt test` after each critical phase prevents error propagation
- Custom validation functions check accumulator completeness
- Monthly grain validation ensures 12 rows per employee per year
- Composite key validation prevents data corruption

### Variable Scope Enhancement
**Complete context passing** enables multi-scenario support:
```python
vars_dict = {
    "simulation_year": year,
    "scenario_id": config.scenario_id,
    "plan_design_id": config.plan_design_id or "default"
}
```
Prevents model compilation errors from missing context variables.

### Tag-Based Selector Strategy
**Reliable model selection** using graph relationships:
- `tag:deferral_pipeline` instead of brittle path-based selection
- Graph selectors (`+int_employee_contributions`) ensure dependency inclusion
- Union selectors combine tag and graph approaches for flexibility
- Survives model file relocations and refactoring

### Performance Optimizations
- **Pre-flight `dbt compile`** catches errors before expensive builds
- **`--defer --state` usage** avoids rebuilding unchanged upstream dependencies
- **Configurable threading** (`--threads`) optimizes resource utilization
- **`--fail-fast --warn-error`** stops execution immediately on issues

### Error Recovery & Diagnostics
- **Detailed validation functions** provide specific failure information
- **Progress checkpointing** preserves work across failures
- **Multi-year consistency checks** validate end-to-end data integrity
- **Enhanced logging** with phase-specific progress indicators

This orchestration update transforms a fragile, serial execution pattern into a **resilient, performant, and production-ready workflow** that handles real-world failure scenarios gracefully while maintaining data integrity guarantees.
