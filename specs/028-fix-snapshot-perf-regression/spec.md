# Feature Specification: Fix Workforce Snapshot Performance Regression

**Feature Branch**: `028-fix-snapshot-perf-regression`
**Created**: 2026-01-27
**Status**: Draft
**Input**: User description: "Performance Regression Fix Plan - 5-year simulation on Windows: 8 min to 45 min (5.6x slowdown)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Multi-Year Simulation Performance (Priority: P1)

As a workforce analyst, I need to run 5-year simulations in a reasonable time so I can iterate on scenario assumptions and deliver timely results to stakeholders.

**Why this priority**: This is the core issue - simulations that previously took 8 minutes now take 45 minutes, making iterative analysis impractical and blocking analyst productivity.

**Independent Test**: Run a 5-year simulation (`planalign simulate 2025-2029`) and measure total execution time. Success is achieved when simulation completes in under 15 minutes.

**Acceptance Scenarios**:

1. **Given** a standard workforce dataset (10K-100K employees), **When** running a 5-year simulation on Windows, **Then** total execution time is under 15 minutes (vs. current 45 minutes)
2. **Given** the same simulation parameters and seed, **When** running the optimized simulation, **Then** output data (workforce counts, event totals, compensation aggregates) matches the pre-optimization baseline exactly
3. **Given** a multi-year simulation, **When** execution completes, **Then** all fct_workforce_snapshot records contain valid compensation_quality_flag values

---

### User Story 2 - Single Year Performance Consistency (Priority: P2)

As a developer running incremental builds, I need single-year dbt model execution to remain fast so I can efficiently test changes.

**Why this priority**: Developers frequently rebuild individual years during development; consistent performance ensures productive development cycles.

**Independent Test**: Run `dbt run --select fct_workforce_snapshot --vars "simulation_year: 2025"` and verify execution time is proportional to dataset size (not exponentially increasing).

**Acceptance Scenarios**:

1. **Given** Year 1 of simulation, **When** running fct_workforce_snapshot model, **Then** execution time is under 30 seconds for 10K employees
2. **Given** any simulation year, **When** running fct_workforce_snapshot, **Then** model queries only data for the target simulation_year (not all historical years)

---

### User Story 3 - Cross-Platform Performance Parity (Priority: P3)

As an analyst running simulations on different operating systems, I expect consistent performance regardless of platform.

**Why this priority**: Windows I/O overhead compounds suboptimal query patterns; fixing the root cause benefits all platforms.

**Independent Test**: Run identical simulation on Windows and Linux/macOS, verify performance ratio is within 2x (not 5.6x).

**Acceptance Scenarios**:

1. **Given** the same simulation configuration, **When** running on Windows vs. Linux/macOS, **Then** Windows execution time is within 2x of Linux/macOS (down from 5.6x)

---

### Edge Cases

- What happens when baseline_compensation is zero? System returns 'NORMAL' flag (no division by zero)
- How does the system handle employees who appear in current year but not in baseline workforce? (New hires get 'NORMAL' flag)
- What happens when running Year 1 where no prior year accumulator data exists? Baseline comparison uses Year 1 baseline_workforce data

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST calculate compensation_quality_flag using a single pass over baseline compensation data (O(n) complexity, not O(n^2))
- **FR-002**: System MUST filter all baseline_workforce references by simulation_year to avoid reading unnecessary historical data
- **FR-003**: System MUST produce identical output data (workforce counts, event totals, compensation values) before and after optimization
- **FR-004**: System MUST handle zero baseline_compensation values by returning 'NORMAL' flag (no division by zero errors)
- **FR-005**: System MUST handle new hires (employees not in baseline) by returning 'NORMAL' flag
- **FR-006**: System MUST maintain the existing compensation_quality_flag threshold logic:
  - `>100x` baseline: CRITICAL_INFLATION_100X
  - `>50x` baseline: CRITICAL_INFLATION_50X
  - `>10x` baseline: SEVERE_INFLATION_10X
  - `>5x` baseline: WARNING_INFLATION_5X
  - Otherwise: NORMAL

### Key Entities

- **fct_workforce_snapshot**: Final mart table containing point-in-time workforce state including compensation_quality_flag
- **int_baseline_workforce**: Intermediate model containing baseline compensation data for comparison
- **compensation_quality_flag**: Derived field indicating anomalous compensation changes (used for data quality auditing)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 5-year simulation completes in under 15 minutes on Windows (down from 45 minutes, minimum 3x improvement)
- **SC-002**: Single-year fct_workforce_snapshot build completes in under 30 seconds for 10K employee datasets
- **SC-003**: 100% data consistency between pre-optimization and post-optimization outputs (zero record-level differences)
- **SC-004**: All dbt tests pass after optimization (no regressions in data quality checks)
- **SC-005**: Zero division-by-zero errors in compensation_quality_flag calculation

## Assumptions

- The 5.6x slowdown is primarily caused by O(n^2) scalar subqueries in fct_workforce_snapshot.sql (lines 971-1025)
- Secondary contributors are missing simulation_year filters at lines 373, 423, and 472
- The existing threshold values (100x, 50x, 10x, 5x) are correct and should not be changed
- DuckDB query optimizer does not automatically optimize the correlated scalar subqueries
- Windows I/O overhead amplifies the performance impact of excessive table scans

## Out of Scope

- Adding new data quality flags or thresholds
- Changing the compensation_quality_flag business logic
- Performance optimization of other dbt models (focus is solely on fct_workforce_snapshot.sql)
- Database schema changes or index additions
