# Epic E027: Multi-Year Simulation Reliability & Performance

## Epic Overview

### Summary
Fix critical cold start failures and performance bottlenecks in multi-year workforce simulations to ensure reliable, efficient execution on fresh environments. This epic addresses the fundamental issues preventing successful multi-year simulations on clean database states and optimizes long-running SCD operations.

### Business Value
- Eliminates production failures from cold start scenarios, ensuring reliable deployment
- Reduces SCD processing time from 19+ minutes to <2 minutes, enabling faster iterations
- Provides robust workforce state initialization for consistent simulation results
- Enables reliable multi-year workforce planning for enterprise clients

### Success Criteria
- ✅ Multi-year simulations execute successfully on fresh database instances
- ✅ `scd_workforce_state` processing completes in <2 minutes on 16 vCPU/64GB machines
- ✅ Workforce state properly initializes with active employees in all simulation years
- ✅ Cold start detection and fallback mechanisms prevent dependency failures
- ✅ Performance monitoring alerts on SLA breaches during long-running operations
- ✅ Comprehensive test coverage for cold start and performance scenarios

---

## Problem Statement

### Current Issues
1. **Cold Start Workforce Failure**: Multi-year simulations start with empty workforce on fresh runs, causing subsequent years to have no active employees
2. **SCD Performance Bottleneck**: `scd_workforce_state` takes 19+ minutes on powerful hardware (16 vCPU/64GB), blocking simulation completion
3. **Missing Bootstrap Logic**: No proper initialization sequence for "year 0" scenarios in workforce baseline preparation
4. **Inefficient SCD Implementation**: Slowly changing dimension logic lacks optimization for incremental processing

### Root Causes
- `int_previous_year_workforce` model expects prior year data that doesn't exist on cold starts
- SCD implementation uses inefficient queries causing full table rebuilds
- Missing conditional logic to handle fresh vs continuing simulations
- Lack of proper workforce state handoff between simulation years

---

## User Stories

### Story S083-01: Cold Start Workforce Initialization (5 points)
**As a** simulation analyst
**I want** multi-year simulations to work on fresh database instances
**So that** I can deploy reliably without pre-existing workforce state

**Acceptance Criteria:**
- Multi-year simulations execute successfully on empty databases
- Workforce baseline properly seeds from census data on first run
- Proper workforce state handoff between simulation years
- `int_previous_year_workforce` handles missing prior year data gracefully
- Workforce continuity maintained across all simulation years

**File:** `/docs/stories/S083-01-cold-start-workforce-initialization.md`

### Story S083-02: SCD Performance Optimization (8 points)
**As a** simulation developer
**I want** SCD processing to complete in under 2 minutes
**So that** multi-year simulations run efficiently without blocking

**Acceptance Criteria:**
- `scd_workforce_state` execution time reduced from 19+ minutes to <2 minutes
- Implement proper indexing and partitioning strategies
- Add incremental processing to avoid full table rebuilds
- Optimize joins and window functions in SCD logic
- Performance monitoring with SLA alerts for long-running operations

**File:** `/docs/stories/S083-02-scd-performance-optimization.md`

### Story S083-03: Cold Start Detection & Fallback (3 points)
**As a** system administrator
**I want** intelligent detection of simulation state
**So that** the system handles fresh vs continuing simulations appropriately

**Acceptance Criteria:**
- Detect fresh vs continuing simulations automatically
- Implement fallback mechanisms for missing dependencies
- Create proper initialization sequence validation
- Graceful handling of missing prior year data
- Clear error messages for unrecoverable dependency failures

**File:** `/docs/stories/S083-03-cold-start-detection-fallback.md`

### Story S083-04: Multi-Year Performance Monitoring (2 points)
**As a** operations engineer
**I want** comprehensive performance tracking for multi-year runs
**So that** I can detect and resolve performance regressions quickly

**Acceptance Criteria:**
- Extend performance framework for multi-year scenarios
- Add SLA monitoring for long-running SCD operations
- Create performance regression detection
- Track execution time trends across simulation runs
- Alert on performance degradation patterns

**File:** `/docs/stories/S083-04-multi-year-performance-monitoring.md`

### Story S083-05: Integration Testing & Validation (3 points)
**As a** quality assurance engineer
**I want** comprehensive testing for cold start and performance scenarios
**So that** I can ensure reliable multi-year simulation behavior

**Acceptance Criteria:**
- Create comprehensive cold start test scenarios
- Validate workforce continuity across multiple years
- Add automated performance benchmarking
- Test simulation recovery from various failure states
- Validate data consistency between fresh and continuing runs

**File:** `/docs/stories/S083-05-integration-testing-validation.md`

---

## Technical Specifications

### Cold Start Bootstrap Pattern
```python
def initialize_workforce_baseline(duckdb_conn, simulation_year: int):
    """Initialize workforce baseline with proper cold start handling"""

    # Check if this is a cold start (no prior year data)
    prior_year_exists = duckdb_conn.execute(f"""
        SELECT COUNT(*) as count
        FROM information_schema.tables
        WHERE table_name = 'int_previous_year_workforce'
    """).fetchone()[0] > 0

    if not prior_year_exists or simulation_year == 1:
        # Cold start: Initialize from census data
        duckdb_conn.execute("""
            CREATE OR REPLACE TABLE int_previous_year_workforce AS
            SELECT
                employee_id,
                hire_date,
                termination_date,
                annual_salary,
                'ACTIVE' as employee_status,
                0 as simulation_year
            FROM stg_census_data
            WHERE termination_date IS NULL
        """)
    else:
        # Continuing simulation: Use previous year's end state
        duckdb_conn.execute(f"""
            CREATE OR REPLACE TABLE int_previous_year_workforce AS
            SELECT *
            FROM fct_workforce_snapshot
            WHERE simulation_year = {simulation_year - 1}
        """)
```

### SCD Performance Optimization
```sql
-- Optimized SCD implementation with incremental processing
CREATE OR REPLACE TABLE scd_workforce_state AS
WITH changed_employees AS (
    -- Only process employees with changes
    SELECT DISTINCT employee_id
    FROM fct_yearly_events
    WHERE simulation_year = ?
),
workforce_changes AS (
    SELECT
        w.employee_id,
        w.simulation_year,
        w.annual_salary,
        w.employee_status,
        w.effective_date,
        LAG(w.annual_salary) OVER (
            PARTITION BY w.employee_id
            ORDER BY w.simulation_year
        ) as prev_salary,
        CASE
            WHEN w.annual_salary != LAG(w.annual_salary) OVER (
                PARTITION BY w.employee_id
                ORDER BY w.simulation_year
            ) THEN 'CHANGED'
            ELSE 'UNCHANGED'
        END as scd_flag
    FROM fct_workforce_snapshot w
    INNER JOIN changed_employees c ON w.employee_id = c.employee_id
)
SELECT *
FROM workforce_changes
WHERE scd_flag = 'CHANGED'

-- Union with unchanged employees from previous processing
UNION ALL

SELECT *
FROM scd_workforce_state_previous
WHERE employee_id NOT IN (SELECT employee_id FROM changed_employees);
```

### Performance Monitoring Integration
```python
from orchestrator.performance_monitor import PerformanceMonitor

def monitor_scd_performance(asset_context, start_time, end_time, row_count):
    """Monitor SCD performance with SLA alerting"""

    execution_time = (end_time - start_time).total_seconds()

    # SLA: SCD processing should complete in <2 minutes
    sla_threshold = 120  # seconds

    if execution_time > sla_threshold:
        asset_context.log.warning(
            f"SCD processing exceeded SLA: {execution_time:.2f}s > {sla_threshold}s"
        )

        # Send alert through performance monitoring
        PerformanceMonitor.record_sla_breach(
            asset_name="scd_workforce_state",
            execution_time=execution_time,
            sla_threshold=sla_threshold,
            row_count=row_count
        )

    # Record performance metrics
    PerformanceMonitor.record_execution_time(
        asset_name="scd_workforce_state",
        execution_time=execution_time,
        row_count=row_count
    )
```

---

## Performance Requirements

| Metric | Current | Target | Implementation Strategy |
|--------|---------|--------|------------------------|
| Multi-Year Cold Start | Fails | 100% success | Bootstrap logic with proper initialization |
| SCD Processing Time | 19+ minutes | <2 minutes | Incremental processing with optimized queries |
| Workforce Continuity | Broken on fresh runs | 100% consistent | Proper baseline initialization and state handoff |
| Performance Monitoring | Basic | Comprehensive | SLA monitoring with automated alerting |
| Test Coverage | Limited | 90%+ scenarios | Comprehensive cold start and performance testing |

## Dependencies
- Performance framework (S072-06) - must be complete for monitoring
- DuckDB optimization capabilities
- Workforce baseline preparation models
- Event sourcing infrastructure
- Multi-year orchestration pipeline

## Risks
- **Risk**: Complex SCD optimization may introduce data consistency issues
- **Mitigation**: Comprehensive testing with data validation checks
- **Risk**: Cold start logic may not handle all edge cases
- **Mitigation**: Extensive testing with various initial data states
- **Risk**: Performance improvements may not scale to larger datasets
- **Mitigation**: Benchmark with realistic data volumes (100K+ employees)

## Estimated Effort
**Total Story Points**: 21 points
**Estimated Duration**: 2-3 sprints

---

## Definition of Done
- [ ] Multi-year simulations execute successfully on fresh database instances
- [ ] SCD processing completes in <2 minutes on target hardware
- [ ] Workforce state properly initializes with active employees in all years
- [ ] Cold start detection and fallback mechanisms implemented
- [ ] Performance monitoring with SLA alerting operational
- [ ] Comprehensive test coverage for cold start and performance scenarios
- [ ] Documentation updated with troubleshooting guides
- [ ] Performance benchmarks established and validated
