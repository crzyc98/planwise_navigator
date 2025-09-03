# Epic E068: Database Query Optimization for 2× Performance Improvement

## Epic Overview

### Summary
Implement comprehensive database query optimizations to achieve a 2× performance improvement in multi-year workforce simulation execution. Based on detailed performance analysis showing Event Generation (41%) and State Accumulation (35%) as the primary bottlenecks, this epic focuses on SQL query optimization, model fusion, incremental processing, and DuckDB-specific performance tuning — while preserving our event-sourced architecture, unified SimulationEvent model, and full auditability.

**Status**: 🔴 **NOT STARTED** (0 of 28 story points planned)

### Business Value
- 🎯 **2× Performance Improvement**: Reduce 4.7-4.8 minute multi-year simulations to 2.5-3.0 minutes
- 📊 **Data-Driven Optimizations**: Target proven bottlenecks with measurable impact
- 💰 **Maintain Financial Precision**: Preserve all workforce modeling and audit trail capabilities
- 🔧 **DuckDB-Optimized**: Leverage columnar storage and query optimization capabilities
- 🏗️ **Foundation for Scale**: Enable larger dataset processing and enterprise deployment

### Success Criteria
- Multi-year simulations (2025-2029) complete in 150-180 seconds vs current 285 seconds
- Event Generation stage reduces from 23.2s average to 10-12s per year (50%+ improvement)
- State Accumulation stage reduces from 19.9s average to 8-10s per year (60%+ improvement)
- Maintains identical simulation results (deterministic with same random seed)
- Supports all existing configuration and resume capabilities
- Zero regression in data quality or audit trail functionality
 - Enforces primary-key uniqueness and contracts on all modified dbt models
 - Adheres to naming standards (tier_entity_purpose), avoids `SELECT *`, uses uppercase SQL and 2-space indents
 - Preserves `scenario_id` and `plan_design_id` context across events and state

---

## Performance Analysis

### Current Performance Baseline
Based on recent performance data from 5-year simulation (2025-2029):

| Stage | Average Duration | % of Total Runtime | Target Duration | Target Improvement |
|-------|-----------------|-------------------|-----------------|-------------------|
| **Event Generation** | 23.2s | 41% | 10-12s | 50-55% faster |
| **State Accumulation** | 19.9s | 35% | 8-10s | 55-60% faster |
| Validation | 2.0s | 4% | 2.0s | Maintain |
| Foundation | 2.3s | 4% | 2.3s | Maintain |
| Initialization | 4.3s | 8% | 4.3s | Maintain |
| Reporting | 0.5s | 1% | 0.5s | Maintain |
| **Total Per Year** | ~55s | 100% | ~25-30s | **45-55% faster** |

**Current Total Runtime**: 285.6 seconds (4m 45s)
**Target Total Runtime**: 150-180 seconds (2m 30s - 3m)
**Overall Improvement**: **2× performance gain**

### Root Cause Analysis

#### Event Generation Bottlenecks (41% of runtime)
- **Multiple dbt runs per event type**: Separate commands for hire/termination/promotion/merit events
- **Repeated cohort scanning**: Same employee cohort processed multiple times
- **Complex CTE rebuilding**: Hazard calculations rebuilt for each event type
- **Sequential event processing**: No parallelization of independent event generation

#### State Accumulation Bottlenecks (35% of runtime)
- **Recursive accumulator pattern**: O(n²) complexity for multi-year state tracking
- **Full table scans**: Reading entire workforce snapshots for incremental updates
- **Redundant calculations**: Same employee state calculations repeated across models
- **Memory pressure**: Large intermediate result sets during state transitions

#### Technical Debt Impact
- **Individual model materialization**: Each intermediate model written to disk unnecessarily
- **Suboptimal join patterns**: Cross-year joins without proper indexing
- **Missing query optimization**: No DuckDB-specific performance tuning applied
- **Inefficient filtering**: Year filters applied late in query execution

---

## Solution Architecture

### Core Optimization Strategies

#### 1. Unified Event Model (Highest Impact)
**Target**: 50%+ performance improvement in Event Generation stage

**Current State**:
```sql
-- Separate models for each event type (4 dbt runs per year)
int_hire_events.sql          → 5.8s
int_termination_events.sql   → 6.1s
int_promotion_events.sql     → 5.7s
int_merit_events.sql         → 5.6s
Total: ~23.2s per year
```

**Optimized State**:
```sql
-- Single fused model with unified cohort processing
fct_yearly_events.sql → ~10-12s per year
```

**Implementation Approach**:
- Build single `fct_yearly_events.sql` model with unified cohort CTE (final fact table)
- Compute all RNG keys once per employee/year and reuse across event branches
- Use discriminated UNION ALL to combine all event types in single query
- Mark existing `int_*_events` models as `materialized: ephemeral`
- Retain `scenario_id` and `plan_design_id` in all joins and writers

#### 2. Incremental State Architecture (High Impact)
**Target**: 55-60% performance improvement in State Accumulation stage

**Current State**: Recursive accumulators reading full history
```sql
-- Current: O(n²) complexity
SELECT * FROM all_years_up_to_current_year
WHERE simulation_year <= {{ var('simulation_year') }}
```

**Optimized State**: Incremental state tracking
```sql
-- Target: O(n) complexity
WITH previous_state AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    -- list explicit state columns...
  FROM int_employee_state_by_year
  WHERE simulation_year = {{ var('simulation_year') }} - 1
),
current_events AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    event_type,
    event_date
    -- list explicit event columns...
  FROM fct_yearly_events
  WHERE simulation_year = {{ var('simulation_year') }}
)
SELECT ... -- Compute current year state from previous + events
```

**Implementation Approach**:
- Create `int_employee_state_by_year` incremental model with `delete+insert` strategy
- Each year reads only (t-1) state + current year events → produces year t state
- Eliminate circular dependencies through temporal state accumulation pattern
- Apply to enrollment state, deferral rate state, and workforce snapshots

#### 3. Single Writer Architecture (Medium Impact)
**Target**: Eliminate intermediate model I/O overhead

**Implementation Approach**:
- Event Generation: Only final `fct_yearly_events` writes to disk, all precursors ephemeral
- State Accumulation: Only final `int_employee_state_by_year` writes to disk
- Validation: Combine multiple validation queries into single reporting model
- Use CTEs and views for intermediate calculations within each stage

#### 4. Hazard Cache Optimization (Medium Impact)
**Target**: Eliminate repeated hazard calculations

**Implementation Approach**:
- Pre-compute `dim_promotion_hazards`, `dim_termination_hazards`, `dim_merit_hazards`
- Key by `(level, tenure_band, performance_tier, department)`
- Join cached hazards instead of recalculating in each event model
- Update hazard tables only when parameters change

#### 5. Deterministic RNG and Ordering (Low Impact, High Importance)
**Target**: Maintain reproducibility while optimizing performance

**Implementation Approach**:
- Hash-based RNG: `u = hash(scenario_id, plan_design_id, employee_id, sim_year, event_type, salt)`
- Compute RNG columns once per employee/year in cohort CTE
- Add explicit `ORDER BY employee_id, sim_year, event_type` in final writers
- Maintain deterministic results across optimization changes

### DuckDB-Specific Optimizations

#### Query-Level Optimizations
```sql
-- Enable DuckDB performance features
PRAGMA enable_object_cache=true;
PRAGMA memory_limit='4GB';
PRAGMA threads={{ var('dbt_threads', 1) }};

-- Columnar storage optimization
PRAGMA enable_profiling=true;
PRAGMA profiling_output='query_profile.json';
```

#### Model Configuration Patterns
```yaml
# Optimized model configuration
models:
  planwise_navigator:
    +materialized: view           # Default to views
    events:
      fct_yearly_events:
        +materialized: incremental
        +incremental_strategy: 'delete+insert'  # Year-partition overwrite only
        +unique_key: ['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year', 'event_type']
      int_*_events:
        +materialized: ephemeral  # No disk I/O for intermediate models
    state:
      int_employee_state_by_year:
        +materialized: incremental
        +incremental_strategy: 'delete+insert'
    on-run-start:
      - "PRAGMA enable_object_cache=true;"
      - "PRAGMA memory_limit='4GB';"
      - "PRAGMA threads={{ var('dbt_threads', 1) }};"
    on-run-end:
      - "PRAGMA enable_profiling=false;"
```

#### Contracts and Tests (schema.yml)
```yaml
version: 2

models:
  - name: fct_yearly_events
    config:
      contract: true
    columns:
      - name: event_id
        tests: [unique, not_null]
      - name: scenario_id
        tests: [not_null]
      - name: plan_design_id
        tests: [not_null]
      - name: employee_id
        tests: [not_null]
      - name: simulation_year
        tests: [not_null]
      - name: event_type
        tests: [not_null]

  - name: int_employee_state_by_year
    columns:
      - name: scenario_id
        tests: [not_null]
      - name: plan_design_id
        tests: [not_null]
      - name: employee_id
        tests: [not_null]
      - name: simulation_year
        tests: [not_null]
      - name: is_current
        tests: []
```

---

## Implementation Roadmap

### Phase 1: Unified Event Model (8 points)
**Target**: Complete event generation optimization with 50%+ improvement

#### Story E068-01: Unified Event Generation Model (5 points)
- Create `models/events/fct_yearly_events.sql` with unified cohort processing
- Implement discriminated UNION ALL for all event types
- Add hash-based RNG computation in cohort CTE
- Mark existing `int_*_events` models as ephemeral
- Include `scenario_id` and `plan_design_id` in all keys and joins

#### Story E068-02: Hazard Calculation Optimization (3 points)
- Create `dim_promotion_hazards`, `dim_termination_hazards`, `dim_merit_hazards`
- Implement cached hazard joins in unified event model
- Add hazard cache refresh logic based on parameter changes

### Phase 2: Incremental State Architecture (12 points)

#### Story E068-03: Employee State Accumulator (5 points)
- Create `int_employee_state_by_year` incremental model
- Implement temporal state tracking (year N-1 → year N)
- Replace recursive accumulators with incremental pattern

#### Story E068-04: Enrollment State Optimization (3 points)
- Refactor enrollment state tracking to use new accumulator pattern
- Eliminate circular dependencies in enrollment models
- Optimize enrollment date propagation logic

#### Story E068-05: Workforce Snapshot Performance (4 points)
- Optimize `fct_workforce_snapshot` to use incremental employee state (`int_employee_state_by_year`)
- Implement efficient year-over-year delta processing
- Add performance monitoring for snapshot generation

### Phase 3: Architecture Optimization (5 points)

#### Story E068-06: Single Writer Implementation (3 points)
- Implement single writer pattern for each workflow stage
- Convert intermediate models to ephemeral materialization
- Add explicit ordering for deterministic results

#### Story E068-07: DuckDB Query Optimization (2 points)
- Add DuckDB PRAGMAs for performance tuning
- Implement query profiling and optimization monitoring
- Add memory and resource management for large datasets

### Phase 4: Validation and Testing (3 points)

#### Story E068-08: Performance Validation Framework (3 points)
- Create automated performance regression testing
- Implement result accuracy validation (same seed → same results)
- Add performance benchmarking and optimization recommendations

---

## Technical Implementation Details

### Unified Event Model Example

```sql
-- models/events/fct_yearly_events.sql
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year', 'event_type'],
  pre_hook="DELETE FROM {{ this }} WHERE simulation_year = {{ var('simulation_year') }}"
) }}

WITH cohort_t AS (
  -- Single cohort scan with all RNG keys computed once
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    -- Compute all RNG values once per employee
    {{ hash_rng('employee_id', var('simulation_year'), 'hire') }} AS hire_rng,
    {{ hash_rng('employee_id', var('simulation_year'), 'termination') }} AS term_rng,
    {{ hash_rng('employee_id', var('simulation_year'), 'promotion') }} AS promo_rng,
    {{ hash_rng('employee_id', var('simulation_year'), 'merit') }} AS merit_rng,
    -- Employee attributes for hazard lookups
    level, tenure_months, department, performance_tier
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

hazards AS (
  -- Join pre-computed hazard caches
  SELECT
    c.*,
    ph.promotion_probability,
    th.termination_probability,
    mh.merit_probability
  FROM cohort_t c
  LEFT JOIN {{ ref('dim_promotion_hazards') }} ph USING (level, tenure_months, department)
  LEFT JOIN {{ ref('dim_termination_hazards') }} th USING (level, tenure_months, performance_tier)
  LEFT JOIN {{ ref('dim_merit_hazards') }} mh USING (level, department)
),

-- Event-specific CTEs using shared hazards
hire_events AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    'hire' AS event_type,
    {{ realistic_event_date() }} AS event_date,
    -- Event-specific attributes
  FROM hazards
  WHERE hire_rng < {{ var('hire_rate') }}
),

termination_events AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    'termination' AS event_type,
    {{ realistic_event_date() }} AS event_date,
    -- Event-specific attributes
  FROM hazards
  WHERE term_rng < termination_probability
),

-- ... promotion_events, merit_events CTEs

final_events AS (
  SELECT scenario_id, plan_design_id, employee_id, event_type, event_date FROM hire_events
  UNION ALL
  SELECT scenario_id, plan_design_id, employee_id, event_type, event_date FROM termination_events
  UNION ALL
  SELECT scenario_id, plan_design_id, employee_id, event_type, event_date FROM promotion_events
  UNION ALL
  SELECT scenario_id, plan_design_id, employee_id, event_type, event_date FROM merit_events
)

SELECT
  {{ generate_event_uuid() }} AS event_id,
  scenario_id,
  plan_design_id,
  employee_id,
  event_type,
  event_date,
  {{ var('simulation_year') }} AS simulation_year,
  -- Standard audit fields
  CURRENT_TIMESTAMP AS created_at
FROM final_events
ORDER BY employee_id, event_type  -- Deterministic ordering
```

### Incremental State Accumulator Pattern

```sql
-- models/state/int_employee_state_by_year.sql
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
  pre_hook="DELETE FROM {{ this }} WHERE simulation_year = {{ var('simulation_year') }}"
) }}

WITH previous_year_state AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    hire_date,
    -- ... other state attributes
    simulation_year
  FROM {{ this }}
  WHERE simulation_year = {{ var('simulation_year') }} - 1
  {% if is_incremental() %}
    AND simulation_year = {{ var('simulation_year') }} - 1
  {% endif %}
),

current_year_events AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    event_type,
    event_date,
    simulation_year
  FROM {{ ref('fct_yearly_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

state_transitions AS (
  -- Compute new state from previous state + current events
  SELECT
    COALESCE(p.scenario_id, e.scenario_id) AS scenario_id,
    COALESCE(p.plan_design_id, e.plan_design_id) AS plan_design_id,
    COALESCE(p.employee_id, e.employee_id) AS employee_id,
    {{ var('simulation_year') }} AS simulation_year,
    -- Carry forward previous state with event-driven updates
    CASE
      WHEN e.event_type = 'hire' THEN e.event_date
      ELSE p.hire_date
    END AS hire_date,
    -- ... other state attributes
  FROM previous_year_state p
  FULL OUTER JOIN current_year_events e USING (employee_id)
)

SELECT
  scenario_id,
  plan_design_id,
  employee_id,
  simulation_year,
  hire_date
  -- ... other state attributes
FROM state_transitions
```

---

## Success Metrics

### Performance Targets

| Metric | Current | Target | Improvement |
|--------|---------|---------|-------------|
| **Total Multi-Year Runtime** | 285.6s | 150-180s | **2× faster** |
| **Event Generation per Year** | 23.2s | 10-12s | **50-55% faster** |
| **State Accumulation per Year** | 19.9s | 8-10s | **55-60% faster** |
| **Memory Usage** | <1GB | <1GB | Maintain |
| **Result Accuracy** | 100% | 100% | No regression |

### Quality Assurance

#### Automated Testing
- **Performance Regression Tests**: Validate each optimization maintains or improves performance targets
- **Result Accuracy Tests**: Same random seed produces identical simulation results pre/post optimization
- **Data Quality Tests**: All existing dbt tests continue to pass
- **Memory Usage Tests**: Optimizations don't exceed memory constraints
 - **Distribution Drift Tests**: Maintain KS test p-value expectations per CLAUDE.md
 - **Row Count Drift**: Ensure staged→int model drift ≤ 0.5%

#### Validation Framework
```python
# Performance validation example
def test_event_generation_performance():
    baseline_time = measure_stage_time('event_generation', baseline=True)
    optimized_time = measure_stage_time('event_generation', optimized=True)

    improvement_ratio = baseline_time / optimized_time
    assert improvement_ratio >= 1.5, f"Expected 50%+ improvement, got {improvement_ratio:.2f}×"

def test_result_determinism():
    baseline_results = run_simulation(seed=12345, version='baseline')
    optimized_results = run_simulation(seed=12345, version='optimized')

    assert_simulation_results_equal(baseline_results, optimized_results)

def test_dbt_contracts_and_uniqueness():
    # Ensure contracts/uniqueness are enforced for modified models
    run("dbt test --select fct_yearly_events int_employee_state_by_year")
```

---

## Risk Assessment

### Technical Risks

#### High Risk: Result Accuracy
- **Risk**: Query optimizations change simulation outcomes
- **Mitigation**: Comprehensive result validation testing with multiple random seeds
- **Detection**: Automated comparison tests in CI/CD pipeline

#### Medium Risk: Complexity Management
- **Risk**: Fused queries become difficult to maintain and debug
- **Mitigation**: Comprehensive documentation, modular CTE structure, extensive commenting
- **Detection**: Code review process and maintainability scoring

#### Medium Risk: Memory Usage
- **Risk**: Larger queries consume more memory
- **Mitigation**: Memory usage monitoring, adaptive batch sizing, DuckDB memory limits
- **Detection**: Performance monitoring with memory alerts

#### Low Risk: Compatibility
- **Risk**: DuckDB-specific optimizations reduce database portability
- **Mitigation**: Feature flags for database-specific optimizations, fallback patterns
- **Detection**: Multi-database testing in development environment

### Mitigation Strategies

#### Incremental Rollout
1. **Phase-by-phase implementation**: Deploy optimizations incrementally with rollback capability
2. **A/B testing**: Run optimized and baseline versions in parallel for validation
3. **Feature flags**: Enable/disable optimizations via configuration
4. **Comprehensive monitoring**: Track performance, accuracy, and resource usage

#### Quality Gates
- All existing dbt tests must pass
- Performance improvements must meet minimum thresholds
- Result accuracy validation required before production deployment
- Memory usage must remain within configured limits

---

## Dependencies

### Technical Dependencies
- ✅ **Epic E063 (Single-threaded optimizations)**: Completed - provides foundation
- ✅ **Navigator Orchestrator architecture**: Available for performance monitoring
- ✅ **DuckDB 1.0.0**: Installed - provides columnar storage and advanced features
- ✅ **dbt incremental models**: Supported - enables delete+insert strategy
- ✅ **Unified SimulationEvent model**: Required fields (`scenario_id`, `plan_design_id`) available

### Business Dependencies
- **Stakeholder approval**: Performance optimization timeline and testing approach
- **Data validation requirements**: Acceptable tolerance for result accuracy testing
- **Production deployment window**: Scheduled maintenance for optimization rollout

---

## Quick Start Implementation

### Phase 1 Quick Wins (Week 1-2)
```bash
# Always run dbt from /dbt directory
cd dbt

# 1. Create hazard cache tables
dbt run --select dim_promotion_hazards dim_termination_hazards dim_merit_hazards --threads 1

# 2. Implement unified event model
dbt run --select fct_yearly_events --threads 1 --vars "simulation_year: 2025"

# 3. Mark intermediate models as ephemeral
# Update dbt_project.yml materialization settings

# 4. Performance validation
python -m navigator_orchestrator run --years 2025 --optimization high --profile-performance
```

### PR Checklist Template
```markdown
## Epic E068 Performance Optimization Checklist

### Code Changes
- [ ] Tag thin int_* event models as `materialized: ephemeral`
- [ ] Add `models/events/fct_yearly_events.sql` with unified cohort processing
- [ ] Create `models/state/int_employee_state_by_year.sql` incremental model
- [ ] Update workflow to use single writer per stage
- [ ] Create `dim_*_hazards` persisted cache tables
- [ ] Add hash-seed RNG macro for deterministic randomness
- [ ] Add explicit `ORDER BY` in final writers
- [ ] Include `scenario_id` and `plan_design_id` in all keys and joins
- [ ] Update/extend `schema.yml` with contracts and uniqueness tests

### Validation
- [ ] Performance targets met (Event Gen: <12s, State Accum: <10s per year)
- [ ] Result accuracy validation (same seed → same results)
- [ ] All existing dbt tests pass
- [ ] Memory usage within limits (<1GB peak)
- [ ] Documentation updated
- [ ] No `SELECT *` in modified models; uppercase SQL keywords

### Testing
- [ ] Automated performance regression tests added
- [ ] Multi-seed result validation tests
- [ ] Memory usage monitoring tests
- [ ] Integration tests with full multi-year simulation

### Deployment
- [ ] Feature flags implemented for gradual rollout
- [ ] Performance monitoring dashboard updated
- [ ] Rollback plan documented and tested
- [ ] Production deployment checklist completed
```

---

**Epic Owner**: Database Performance Team
**Created**: 2025-09-03
**Target Completion**: 2025-10-15
**Priority**: High
**Complexity**: High
**Business Impact**: Critical - Enables 2× performance improvement for workforce simulation platform

---

## Long-term Vision

This epic establishes the foundation for advanced performance optimizations:

- **Adaptive Query Optimization**: Machine learning-based query plan optimization
- **Predictive Caching**: Intelligent pre-computation of frequently accessed data
- **Distributed Processing**: Scale to multi-node processing for enterprise datasets
- **Real-time Optimization**: Dynamic query optimization based on runtime performance data

The comprehensive approach ensures that PlanWise Navigator remains performant and scalable as workforce simulation requirements continue to grow in complexity and scale.
