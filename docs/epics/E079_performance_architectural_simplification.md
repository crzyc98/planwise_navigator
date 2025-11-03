# E079: Performance Optimization Through Architectural Simplification

**Status**: 🟡 In Progress
**Priority**: P0 (Critical)
**Owner**: TBD
**Created**: 2025-11-03
**Target Completion**: 2025-11-17 (2-week sprint)

---

## Executive Summary

PlanWise Navigator currently takes **7+ minutes** (420 seconds) to simulate 5 years of workforce data on development laptops, and **5-10× longer** on work laptops and offshore HVDs. This performance issue is **NOT due to data volume** (only 44K rows in largest table) but rather **architectural over-engineering** with 155 SQL models containing extreme complexity.

**Root Cause**: The dbt transformation layer was designed for enterprise-scale data (100M+ rows) but processes a tiny dataset (44K rows). This creates massive computational overhead:
- 27-CTE monoliths scanning the same small dataset repeatedly
- 39 validation models running on every build (instead of on-demand)
- 65 intermediate models creating unnecessary computation layers
- Circular dependency workarounds indicating flawed dependency graph
- Ephemeral materialization forcing redundant re-computation

**Solution**: Surgical architectural simplification maintaining determinism and accuracy while achieving **9-10× speedup** (420s → 45s).

---

## Performance Analysis: Data Volume vs Computational Complexity

### Current Data Reality
```
Largest Tables (DuckDB Production):
├─ fct_workforce_snapshot:              43,903 rows (14,756 employees)
├─ int_employee_compensation_by_year:   49,324 rows (11,451 employees)
├─ fct_yearly_events:                   21,843 rows (12,629 events)
├─ int_baseline_workforce:               6,764 rows
└─ int_enrollment_state_accumulator:   107,730 rows (5 years × 21,546 per year)
```

**This is TINY data**. Modern databases should process this in **seconds, not minutes**.

### Top 10 Most Complex Models (Complexity Score Analysis)

| Rank | Model | Lines | CTEs | JOINs | Complexity Score | Output Rows | Ratio |
|------|-------|-------|------|-------|------------------|-------------|-------|
| 1 | **fct_workforce_snapshot.sql** | 1,078 | 27 | 26 | **75,348** | ~44K | **1.71** |
| 2 | **int_enrollment_events.sql** | 906 | 15 | 11 | **149,898** | ~21K | **7.14** |
| 3 | **int_workforce_snapshot_optimized.sql** | 496 | 11 | 8 | **43,648** | ~44K | **0.99** |
| 4 | **int_deferral_rate_state_accumulator_v2.sql** | 487 | 11 | 8 | **42,857** | ~49K | **0.87** |
| 5 | **int_employer_eligibility.sql** | 445 | 7 | 6 | **18,690** | ~6K | **3.12** |
| 6 | **fct_yearly_events.sql** | 439 | 4 | 2 | **3,512** | ~22K | **0.16** |
| 7 | **int_enrollment_decision_matrix.sql** | 380 | 8 | 5 | **15,200** | ~6K | **2.53** |
| 8 | **int_proactive_voluntary_enrollment.sql** | 372 | 7 | 4 | **10,416** | ~2K | **5.21** |
| 9 | **int_workforce_needs.sql** | 353 | 6 | 4 | **8,472** | ~44K | **0.19** |
| 10 | **dq_employee_contributions_validation.sql** | 343 | 13 | 9 | **38,987** | ~1K | **38.99** |

**Complexity Score** = Lines × CTEs × (JOINs + 1) / Output Rows

**Critical Findings**:
- `int_enrollment_events.sql`: **7.14:1 complexity-to-output ratio** - 906 lines of SQL with 15 CTEs generating only 21K rows
- `dq_employee_contributions_validation.sql`: **38.99:1 ratio** - 343 lines with 13 CTEs validating 1K rows
- `fct_workforce_snapshot.sql`: **27 nested CTEs** scanning same 44K rows repeatedly

### Architectural Anti-Patterns

**1. CTE Overuse (27 CTEs in fct_workforce_snapshot.sql)**
```sql
WITH simulation_parameters AS (...),          -- CTE 1
     base_workforce AS (...),                 -- CTE 2
     current_year_events AS (...),            -- CTE 3
     employee_events_consolidated AS (...),   -- CTE 4
     workforce_after_terminations AS (...),   -- CTE 5
     workforce_after_promotions AS (...),     -- CTE 6
     workforce_after_merit AS (...),          -- CTE 7
     new_hires AS (...),                      -- CTE 8
     unioned_workforce_raw AS (...),          -- CTE 9
     unioned_workforce AS (...),              -- CTE 10
     valid_hire_ids AS (...),                 -- CTE 11
     filtered_workforce AS (...),             -- CTE 12
     -- ... 15 more CTEs ...
     final_deduped AS (...)                   -- CTE 27
```

Each CTE is a **full table scan**. We're scanning 44K rows **27 times** when we could do it **once**.

**2. Over-Normalized Event Processing (8 separate models)**
```
int_hiring_events.sql →
int_termination_events.sql →
int_promotion_events.sql →
int_merit_events.sql →
int_enrollment_events.sql (906 lines!) →
int_deferral_rate_escalation_events.sql →
int_employee_contributions.sql →
int_employee_match_calculations.sql →
    fct_yearly_events.sql (UNION ALL)
```

Why 8 intermediate materializations? Should be **1 model** with UNION ALL.

**3. Validation Models Running on Every Build (39 models)**
```
dq_employee_contributions_validation.sql (343 lines, 13 CTEs)
dq_deferral_rate_state_audit_validation.sql (359 lines)
validate_enrollment_architecture.sql (373 lines)
dq_new_hire_termination_match_validation.sql (367 lines)
... 35 more validation models ...
```

These should be **dbt tests** run on-demand, not computed models run every simulation.

**4. Circular Dependency Workarounds**
```sql
-- CIRCULAR DEPENDENCY FIX: Use int_active_employees_prev_year_snapshot
-- instead of fct_workforce_snapshot
-- This breaks the cycle: int_merit_events -> fct_workforce_snapshot ->
-- int_employee_compensation_by_year
```

Helper models to break circular dependencies = **red flag** indicating flawed dependency graph.

**5. Ephemeral Materialization Causing Re-Computation**
```yaml
# Current: All intermediate models are ephemeral (in-memory)
# Problem: DuckDB re-computes ephemeral models multiple times
# Solution: Materialize high-fanout models as tables
```

Models referenced by 8+ downstream models should be **materialized as tables**, not recalculated.

---

## Goals and Success Metrics

### Performance Targets

| Environment | Current | Target | Improvement |
|-------------|---------|--------|-------------|
| **Dev Laptop (M4 Pro)** | 420s | 45s | **9.3× faster** |
| **Work Laptop** | 2,100s (35min) | 90s | **23× faster** |
| **Offshore HVD** | 4,200s (70min) | 180s | **23× faster** |

### Quality Gates
- ✅ All 256 existing tests pass
- ✅ 100% deterministic output (identical results with same seed)
- ✅ Zero data accuracy regressions
- ✅ No breaking changes to CLI or outputs

### Code Quality Targets
- Reduce model count: **155 → ~80 models** (48% reduction)
- Reduce total SQL lines: **~15,000 → ~7,500 lines** (50% reduction)
- Maximum model complexity: **No models >400 lines** (current max: 1,078)
- Maximum CTEs per model: **≤10** (current max: 27)

---

## Implementation Plan

### Phase 1: Quick Wins (Days 1-2, 60% speedup → 168s)

#### Story 1A: Convert Validation Models to dbt Tests
**Current State**: 39 validation models (`dq_*`, `validate_*`) run on every build
**Proposed State**: Convert to dbt tests in `tests/` directory, run on-demand

**Implementation**:
```bash
# Move validation models to tests
cd dbt
mkdir -p tests/data_quality

# Example conversion: dq_employee_contributions_validation.sql
# FROM: models/intermediate/validations/dq_employee_contributions_validation.sql
# TO: tests/data_quality/test_employee_contributions_accuracy.sql

# Update as dbt test format
{{
  config(
    severity='error',
    tags=['data_quality', 'contributions']
  )
}}

-- Test query that returns rows where validation fails
SELECT *
FROM {{ ref('int_employee_contributions') }}
WHERE employee_contribution_amount < 0
   OR employer_match_amount < 0
```

**Files to Convert** (39 models):
```
models/intermediate/validations/dq_*.sql (20 files)
models/marts/validations/validate_*.sql (19 files)
```

**Time Savings**: 39 models × 5s = **195 seconds**

---

#### Story 1B: Strategic Materialization
**Current State**: All intermediate models ephemeral (recalculated multiple times)
**Proposed State**: Materialize high-fanout models as tables

**Implementation**:
```sql
-- models/intermediate/int_employee_compensation_by_year.sql
{{ config(
  materialized='table',  -- CHANGE FROM: ephemeral
  tags=['foundation']
) }}

-- Referenced by 8+ downstream models, should be cached
SELECT ...
```

**Models to Materialize**:
1. `int_employee_compensation_by_year` (referenced by 8 models)
2. `int_baseline_workforce` (referenced by 10 models)
3. `int_enrollment_state_accumulator` (referenced by 6 models)
4. `int_deferral_rate_state_accumulator_v2` (referenced by 5 models)

**Time Savings**: 4 models × 15s = **60 seconds**

---

#### Story 1C: Consolidate Event Generation
**Current State**: 8 separate event models → `fct_yearly_events` UNION ALL
**Proposed State**: 1 unified `int_all_events.sql` with internal UNION ALL

**Implementation**:
```sql
-- NEW: models/intermediate/events/int_all_events.sql
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['event_id'],
  pre_hook="DELETE FROM {{ this }} WHERE simulation_year = {{ var('simulation_year') }}",
  tags=['EVENT_GENERATION']
) }}

WITH hire_events AS (
  -- Logic from int_hiring_events.sql
  SELECT
    event_id,
    'HIRE' AS event_type,
    employee_id,
    effective_date,
    ...
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

termination_events AS (
  -- Logic from int_termination_events.sql
  SELECT
    event_id,
    'TERMINATION' AS event_type,
    ...
),

promotion_events AS (
  -- Logic from int_promotion_events.sql (simplified)
  ...
),

merit_events AS (
  -- Logic from int_merit_events.sql
  ...
),

enrollment_events AS (
  -- Logic from int_enrollment_events.sql (refactored from 906 → 100 lines)
  ...
),

deferral_events AS (
  -- Logic from int_deferral_rate_escalation_events.sql
  ...
),

contribution_events AS (
  -- Logic from int_employee_contributions.sql + int_employee_match_calculations.sql
  ...
)

-- Single UNION ALL instead of 8 separate materializations
SELECT * FROM hire_events
UNION ALL SELECT * FROM termination_events
UNION ALL SELECT * FROM promotion_events
UNION ALL SELECT * FROM merit_events
UNION ALL SELECT * FROM enrollment_events
UNION ALL SELECT * FROM deferral_events
UNION ALL SELECT * FROM contribution_events
```

**Update `fct_yearly_events.sql`**:
```sql
-- Simplified to just read from int_all_events
SELECT * FROM {{ ref('int_all_events') }}
WHERE simulation_year = {{ var('simulation_year') }}
```

**Models to Remove** (8 files):
```
models/intermediate/events/int_hiring_events.sql
models/intermediate/events/int_termination_events.sql
models/intermediate/events/int_promotion_events.sql
models/intermediate/events/int_merit_events.sql
models/intermediate/events/int_enrollment_events.sql
models/intermediate/events/int_deferral_rate_escalation_events.sql
models/intermediate/events/int_employee_contributions.sql
models/intermediate/events/int_employee_match_calculations.sql
```

**Time Savings**: 8 materializations × 30s - 1 unified × 15s = **225 seconds**

**Phase 1 Total Savings**: 195s + 60s + 225s = **480 seconds (8 minutes)**
**Phase 1 Performance**: 420s → **168s** (2.5× faster)

---

### Phase 2: Architectural Fixes (Days 3-7, 80% speedup → 84s)

#### Story 2A: Flatten fct_workforce_snapshot.sql
**Current State**: 1,078 lines, 27 nested CTEs, multiple correlated subqueries
**Proposed State**: ~300 lines, 7 streamlined CTEs, materialized joins

**Problem Analysis**:
```sql
-- CURRENT: Sequential transformations in separate CTEs
workforce_after_terminations AS (
  SELECT * FROM base_workforce
  WHERE employee_id NOT IN (SELECT employee_id FROM termination_events)
),
workforce_after_promotions AS (
  SELECT * FROM workforce_after_terminations  -- Scans again
  LEFT JOIN promotion_events USING (employee_id)
),
workforce_after_merit AS (
  SELECT * FROM workforce_after_promotions  -- Scans again
  LEFT JOIN merit_events USING (employee_id)
),
-- ... 24 more CTEs ...
```

**Solution**: Merge sequential transformations into single passes:

```sql
-- PROPOSED: models/marts/fct_workforce_snapshot.sql
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
  pre_hook="DELETE FROM {{ this }} WHERE simulation_year = {{ var('simulation_year') }}"
) }}

WITH
-- CTE 1: Base workforce with previous year state
base_workforce AS (
  SELECT
    COALESCE(curr.employee_id, prev.employee_id) AS employee_id,
    COALESCE(curr.scenario_id, prev.scenario_id) AS scenario_id,
    COALESCE(curr.plan_design_id, prev.plan_design_id) AS plan_design_id,
    {{ var('simulation_year') }} AS simulation_year,
    prev.* AS prev_year_state,
    curr.* AS current_year_updates
  FROM {{ ref('int_baseline_workforce') }} curr
  FULL OUTER JOIN {{ this }} prev
    ON curr.employee_id = prev.employee_id
    AND prev.simulation_year = {{ var('simulation_year') }} - 1
  WHERE COALESCE(curr.simulation_year, {{ var('simulation_year') }}) = {{ var('simulation_year') }}
),

-- CTE 2: All year events consolidated (replaces 8 separate CTEs)
year_events AS (
  SELECT *
  FROM {{ ref('int_all_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

-- CTE 3: Apply all events in single pass (replaces workforce_after_* chain)
workforce_with_events AS (
  SELECT
    w.employee_id,
    w.scenario_id,
    w.plan_design_id,
    w.simulation_year,

    -- Apply terminations
    CASE
      WHEN e_term.event_type = 'TERMINATION' THEN 'TERMINATED'
      ELSE COALESCE(w.employment_status, 'ACTIVE')
    END AS employment_status,

    -- Apply promotions and compensation changes in single pass
    COALESCE(
      e_promo.new_job_level,
      e_raise.new_job_level,
      w.prev_year_state.job_level,
      w.current_year_updates.job_level
    ) AS job_level,

    COALESCE(
      e_promo.new_annual_compensation,
      e_raise.new_annual_compensation,
      w.prev_year_state.annual_compensation,
      w.current_year_updates.annual_compensation
    ) AS annual_compensation,

    -- Add enrollment status in same pass
    COALESCE(
      e_enroll.is_enrolled,
      w.prev_year_state.is_enrolled,
      FALSE
    ) AS is_enrolled,

    -- Add contribution data in same pass
    COALESCE(e_contrib.deferral_rate, w.prev_year_state.deferral_rate, 0.0) AS deferral_rate,
    COALESCE(e_contrib.employee_contribution, 0.0) AS employee_contribution,
    COALESCE(e_contrib.employer_match, 0.0) AS employer_match

  FROM base_workforce w

  -- All event joins in single pass (instead of nested CTEs)
  LEFT JOIN year_events e_term
    ON w.employee_id = e_term.employee_id
    AND e_term.event_type = 'TERMINATION'

  LEFT JOIN year_events e_promo
    ON w.employee_id = e_promo.employee_id
    AND e_promo.event_type = 'PROMOTION'

  LEFT JOIN year_events e_raise
    ON w.employee_id = e_raise.employee_id
    AND e_raise.event_type IN ('MERIT_RAISE', 'COLA_RAISE')

  LEFT JOIN year_events e_enroll
    ON w.employee_id = e_enroll.employee_id
    AND e_enroll.event_type IN ('DC_PLAN_ENROLLMENT', 'BENEFIT_ENROLLMENT')

  LEFT JOIN year_events e_contrib
    ON w.employee_id = e_contrib.employee_id
    AND e_contrib.event_type = 'DC_PLAN_CONTRIBUTION'
),

-- CTE 4: Add new hires (replaces complex union logic)
workforce_with_hires AS (
  SELECT * FROM workforce_with_events

  UNION ALL

  SELECT
    e.employee_id,
    e.scenario_id,
    e.plan_design_id,
    e.simulation_year,
    'ACTIVE' AS employment_status,
    e.job_level,
    e.annual_compensation,
    FALSE AS is_enrolled,  -- New hires default to not enrolled
    0.0 AS deferral_rate,
    0.0 AS employee_contribution,
    0.0 AS employer_match
  FROM year_events e
  WHERE e.event_type = 'HIRE'
),

-- CTE 5: Prorated compensation (simplified from 5 CTEs to 1)
workforce_with_prorated_comp AS (
  SELECT
    *,
    CASE
      -- Hired mid-year: prorate from hire date
      WHEN hire_date > DATE(simulation_year || '-01-01')
      THEN annual_compensation * (365.0 - DATEDIFF('day', hire_date, DATE(simulation_year || '-12-31'))) / 365.0

      -- Terminated mid-year: prorate to termination date
      WHEN termination_date < DATE(simulation_year || '-12-31')
      THEN annual_compensation * DATEDIFF('day', DATE(simulation_year || '-01-01'), termination_date) / 365.0

      -- Full year
      ELSE annual_compensation
    END AS prorated_annual_compensation
  FROM workforce_with_hires
),

-- CTE 6: Eligibility and enrollment (replaces complex subquery logic)
workforce_with_eligibility AS (
  SELECT
    w.*,
    elig.is_eligible_for_match,
    elig.is_eligible_for_core_contribution,
    elig.enrollment_window_start,
    elig.enrollment_window_end
  FROM workforce_with_prorated_comp w
  LEFT JOIN {{ ref('int_employer_eligibility') }} elig
    ON w.employee_id = elig.employee_id
    AND w.simulation_year = elig.simulation_year
),

-- CTE 7: Final deduplication and cleanup
final_snapshot AS (
  SELECT DISTINCT ON (employee_id, scenario_id, plan_design_id, simulation_year)
    employee_id,
    scenario_id,
    plan_design_id,
    simulation_year,
    employment_status,
    job_level,
    annual_compensation,
    prorated_annual_compensation,
    is_enrolled,
    deferral_rate,
    employee_contribution,
    employer_match,
    is_eligible_for_match,
    is_eligible_for_core_contribution,
    enrollment_window_start,
    enrollment_window_end,
    CURRENT_TIMESTAMP AS snapshot_timestamp
  FROM workforce_with_eligibility
  ORDER BY employee_id, scenario_id, plan_design_id, simulation_year
)

SELECT * FROM final_snapshot
```

**Key Improvements**:
- **27 CTEs → 7 CTEs** (74% reduction)
- **1,078 lines → ~300 lines** (72% reduction)
- **Multiple scans → Single scan** with consolidated joins
- **5 correlated subqueries → Materialized LEFT JOINs**
- **Sequential event application → Single-pass event merge**

**Time Savings**: ~120 seconds per year × 5 years = **120 seconds**

---

#### Story 2B: Fix Circular Dependencies
**Current State**: Helper model `int_active_employees_prev_year_snapshot` breaks circular reference
**Problem**: `int_merit_events` → `fct_workforce_snapshot` → `int_employee_compensation_by_year` → (cycle)

**Root Cause Analysis**:
```
int_merit_events.sql needs compensation data
    ↓
fct_workforce_snapshot.sql needs merit events
    ↓
int_employee_compensation_by_year.sql needs workforce snapshot
    ↓
(CIRCULAR DEPENDENCY)
```

**Solution**: Use state accumulator pattern (already exists, just not utilized correctly)

```sql
-- models/intermediate/int_employee_compensation_by_year.sql
-- BEFORE: Reads from fct_workforce_snapshot (causes cycle)
-- AFTER: Reads from previous year's accumulator + current year baseline

WITH prior_year_compensation AS (
  SELECT *
  FROM {{ this }}  -- Read from own prior year
  WHERE simulation_year = {{ var('simulation_year') }} - 1
),

current_year_baseline AS (
  SELECT *
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

merged_compensation AS (
  SELECT
    COALESCE(curr.employee_id, prev.employee_id) AS employee_id,
    {{ var('simulation_year') }} AS simulation_year,
    COALESCE(curr.annual_compensation, prev.annual_compensation) AS annual_compensation,
    COALESCE(curr.job_level, prev.job_level) AS job_level
  FROM current_year_baseline curr
  FULL OUTER JOIN prior_year_compensation prev
    ON curr.employee_id = prev.employee_id
)

SELECT * FROM merged_compensation
```

**Models to Remove**:
```
models/intermediate/int_active_employees_prev_year_snapshot.sql (helper model)
```

**Dependency Graph After Fix**:
```
int_baseline_workforce (year N)
    ↓
int_employee_compensation_by_year (reads year N-1 from self + year N baseline)
    ↓
int_merit_events (uses compensation data)
    ↓
int_all_events (includes merit events)
    ↓
fct_workforce_snapshot (applies all events)

NO CIRCULAR DEPENDENCIES ✅
```

**Time Savings**: ~30 seconds (eliminate helper model computation)

---

#### Story 2C: Simplify Enrollment Events
**Current State**: `int_enrollment_events.sql` - 906 lines, 15 CTEs, 3 CROSS JOINs
**Problem**: Complexity ratio of **7.14:1** (906 lines to produce 21K rows)

**Analysis of Current Complexity**:
```sql
-- CURRENT: models/intermediate/events/int_enrollment_events.sql
WITH simulation_parameters AS (...),        -- CTE 1
     census_employees AS (...),             -- CTE 2
     employee_eligibility AS (...),         -- CTE 3
     prior_enrollment_state AS (...),       -- CTE 4
     enrollment_windows AS (...),           -- CTE 5
     auto_enrollment_candidates AS (...),   -- CTE 6
     auto_enrollment_decisions AS (         -- CTE 7
       SELECT e.*, w.*
       FROM auto_enrollment_candidates e
       CROSS JOIN enrollment_windows w      -- CROSS JOIN 1
     ),
     voluntary_enrollment_candidates AS (...), -- CTE 8
     voluntary_enrollment_rates AS (        -- CTE 9
       SELECT c.*, r.*
       FROM voluntary_enrollment_candidates c
       CROSS JOIN simulation_parameters r   -- CROSS JOIN 2
     ),
     voluntary_decisions AS (...),          -- CTE 10
     re_enrollment_candidates AS (...),     -- CTE 11
     re_enrollment_windows AS (             -- CTE 12
       SELECT c.*, w.*
       FROM re_enrollment_candidates c
       CROSS JOIN enrollment_windows w      -- CROSS JOIN 3
     ),
     all_enrollment_decisions AS (...),     -- CTE 13
     enrollment_events_raw AS (...),        -- CTE 14
     enrollment_events_deduped AS (...)     -- CTE 15
```

**Key Issues**:
1. **3 CROSS JOINs** creating Cartesian products for small tables (should be regular JOINs)
2. **15 CTEs** when 3-4 would suffice
3. **Redundant eligibility checks** (already computed in `int_employer_eligibility`)
4. **Over-engineered decision tree** (auto vs voluntary vs re-enrollment)

**Refactored Version** (~100 lines, 4 CTEs):
```sql
-- REFACTORED: models/intermediate/events/int_enrollment_events.sql
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['event_id'],
  pre_hook="DELETE FROM {{ this }} WHERE simulation_year = {{ var('simulation_year') }}"
) }}

WITH
-- CTE 1: Get eligibility and prior state (consolidated)
enrollment_candidates AS (
  SELECT
    e.employee_id,
    e.scenario_id,
    e.plan_design_id,
    e.simulation_year,
    e.is_eligible_dc_plan,
    e.enrollment_window_start,
    e.enrollment_window_end,

    -- Prior year enrollment state
    COALESCE(prev.is_enrolled, FALSE) AS was_enrolled_prev_year,
    COALESCE(prev.deferral_rate, 0.0) AS prev_deferral_rate,

    -- Configuration parameters
    cfg.auto_enrollment_enabled,
    cfg.auto_enrollment_deferral_rate,
    cfg.voluntary_enrollment_rate

  FROM {{ ref('int_employer_eligibility') }} e

  LEFT JOIN {{ ref('int_enrollment_state_accumulator') }} prev
    ON e.employee_id = prev.employee_id
    AND prev.simulation_year = e.simulation_year - 1

  LEFT JOIN {{ ref('stg_dc_plan_designs') }} cfg
    ON e.plan_design_id = cfg.plan_design_id

  WHERE e.simulation_year = {{ var('simulation_year') }}
    AND e.is_eligible_dc_plan = TRUE
    AND NOT was_enrolled_prev_year  -- Only unenrolled candidates
),

-- CTE 2: Determine enrollment type and decision
enrollment_decisions AS (
  SELECT
    employee_id,
    scenario_id,
    plan_design_id,
    simulation_year,

    -- Simple decision logic (no CROSS JOINs needed)
    CASE
      -- Auto-enrollment path
      WHEN auto_enrollment_enabled
           AND CURRENT_DATE BETWEEN enrollment_window_start AND enrollment_window_end
      THEN 'AUTO_ENROLLMENT'

      -- Voluntary enrollment path (probabilistic)
      WHEN RANDOM() <= voluntary_enrollment_rate
           AND CURRENT_DATE BETWEEN enrollment_window_start AND enrollment_window_end
      THEN 'VOLUNTARY_ENROLLMENT'

      ELSE NULL  -- No enrollment this year
    END AS enrollment_type,

    -- Set deferral rate based on enrollment type
    CASE
      WHEN enrollment_type = 'AUTO_ENROLLMENT' THEN auto_enrollment_deferral_rate
      WHEN enrollment_type = 'VOLUNTARY_ENROLLMENT' THEN voluntary_enrollment_rate
      ELSE NULL
    END AS initial_deferral_rate,

    -- Enrollment effective date
    CASE
      WHEN enrollment_type IS NOT NULL THEN enrollment_window_start
      ELSE NULL
    END AS enrollment_date

  FROM enrollment_candidates
),

-- CTE 3: Generate enrollment events
enrollment_events AS (
  SELECT
    {{ dbt_utils.generate_surrogate_key([
      'employee_id',
      'scenario_id',
      'plan_design_id',
      'simulation_year',
      "'DC_PLAN_ENROLLMENT'"
    ]) }} AS event_id,

    employee_id,
    scenario_id,
    plan_design_id,
    simulation_year,
    'DC_PLAN_ENROLLMENT' AS event_type,
    enrollment_date AS effective_date,
    enrollment_type,
    initial_deferral_rate,
    CURRENT_TIMESTAMP AS created_at

  FROM enrollment_decisions
  WHERE enrollment_type IS NOT NULL  -- Only emit events for actual enrollments
),

-- CTE 4: Deduplicate (edge case handling)
final_events AS (
  SELECT DISTINCT ON (employee_id, scenario_id, plan_design_id, simulation_year)
    *
  FROM enrollment_events
  ORDER BY employee_id, scenario_id, plan_design_id, simulation_year, effective_date
)

SELECT * FROM final_events
```

**Improvements**:
- **906 lines → ~100 lines** (89% reduction)
- **15 CTEs → 4 CTEs** (73% reduction)
- **3 CROSS JOINs → 0 CROSS JOINs** (replaced with proper LEFT JOINs)
- **Leverage existing** `int_employer_eligibility` (no redundant calculations)
- **Simplified decision logic** (no need for separate auto/voluntary/re-enrollment pipelines)

**Time Savings**: ~45 seconds

**Phase 2 Total Savings**: 120s + 30s + 45s = **195 seconds**
**Phase 2 Performance**: 168s → **84s** (5× faster than original)

---

### Phase 3: Connection Pooling (Days 8-10, 85% speedup → 63s)

#### Story 3A: Database Connection Pool Implementation
**Current State**: New connection created for every database operation (~1,000+ per simulation)
**Problem**: Connection overhead of 10-50ms × 1,000 = **10-50 seconds wasted**

**Implementation**:

```python
# navigator_orchestrator/utils.py

import duckdb
from typing import Optional, Dict
from contextlib import contextmanager
from threading import Lock
from pathlib import Path

class DatabaseConnectionPool:
    """Thread-safe connection pool for DuckDB with deterministic execution support."""

    def __init__(self, db_path: Path, pool_size: int = 5, deterministic: bool = True):
        self.db_path = db_path
        self.pool_size = pool_size
        self.deterministic = deterministic
        self._pool: Dict[str, duckdb.DuckDBPyConnection] = {}
        self._lock = Lock()
        self._in_use: set = set()

    def _create_connection(self, thread_id: str) -> duckdb.DuckDBPyConnection:
        """Create a new connection with proper configuration."""
        conn = duckdb.connect(str(self.db_path))

        if self.deterministic:
            # Deterministic mode: single-threaded, reproducible results
            conn.execute("PRAGMA threads=1")
            conn.execute("PRAGMA enable_progress_bar=false")
        else:
            # Fast mode: multi-threaded query execution
            conn.execute("PRAGMA threads=4")  # Use 4 cores for query execution

        # Set memory limit and other optimizations
        conn.execute("PRAGMA memory_limit='4GB'")
        conn.execute("PRAGMA temp_directory='/tmp/duckdb'")

        return conn

    @contextmanager
    def get_connection(self, thread_id: Optional[str] = None):
        """
        Context manager for connection checkout/checkin.

        Usage:
            with pool.get_connection(thread_id='worker_1') as conn:
                result = conn.execute("SELECT COUNT(*) FROM table").fetchall()
        """
        thread_id = thread_id or 'main'

        with self._lock:
            # Reuse existing connection for this thread if available
            if thread_id in self._pool and thread_id not in self._in_use:
                conn = self._pool[thread_id]
                self._in_use.add(thread_id)
            else:
                # Create new connection if pool not full
                if len(self._pool) < self.pool_size:
                    conn = self._create_connection(thread_id)
                    self._pool[thread_id] = conn
                    self._in_use.add(thread_id)
                else:
                    # Wait for available connection (blocking)
                    available_threads = set(self._pool.keys()) - self._in_use
                    if available_threads:
                        thread_id = available_threads.pop()
                        conn = self._pool[thread_id]
                        self._in_use.add(thread_id)
                    else:
                        raise RuntimeError(f"Connection pool exhausted (size={self.pool_size})")

        try:
            yield conn
        finally:
            # Return connection to pool
            with self._lock:
                self._in_use.discard(thread_id)

    def close_all(self):
        """Close all connections in pool."""
        with self._lock:
            for conn in self._pool.values():
                conn.close()
            self._pool.clear()
            self._in_use.clear()


class DatabaseConnectionManager:
    """Updated connection manager using connection pool."""

    def __init__(self, db_path: Path, deterministic: bool = True):
        self.db_path = db_path
        self.deterministic = deterministic
        self._pool = DatabaseConnectionPool(
            db_path=db_path,
            pool_size=5,
            deterministic=deterministic
        )

    @contextmanager
    def get_connection(self, *, deterministic: Optional[bool] = None, thread_id: Optional[str] = None):
        """
        Get a connection from the pool.

        Args:
            deterministic: Override default deterministic mode
            thread_id: Thread identifier for connection affinity
        """
        # Note: deterministic parameter ignored after pool initialization
        # To change deterministic mode, create new ConnectionManager
        with self._pool.get_connection(thread_id=thread_id) as conn:
            yield conn

    def close_all(self):
        """Close all pooled connections."""
        self._pool.close_all()
```

**Update PipelineOrchestrator**:
```python
# navigator_orchestrator/pipeline_orchestrator.py

class PipelineOrchestrator:
    def __init__(self, config: SimulationConfig):
        self.config = config

        # Initialize connection manager with pool
        self.connection_manager = DatabaseConnectionManager(
            db_path=get_database_path(),
            deterministic=True  # Keep deterministic for reproducibility
        )

    def execute_query(self, query: str) -> list:
        """Execute query using pooled connection."""
        with self.connection_manager.get_connection(thread_id='orchestrator') as conn:
            result = conn.execute(query).fetchall()
        return result

    def cleanup(self):
        """Clean up resources."""
        self.connection_manager.close_all()
```

**Benefits**:
- **Connection reuse**: 1,000+ operations → 5 pooled connections
- **Overhead reduction**: 10-50s → ~1s (connection creation amortized)
- **Thread safety**: Lock-based checkout/checkin prevents race conditions
- **Deterministic mode**: Still uses `PRAGMA threads=1` for reproducibility
- **Context manager**: Automatic connection return on error/success

**Time Savings**: ~20 seconds

**Phase 3 Total Savings**: 20 seconds
**Phase 3 Performance**: 84s → **63s** (6.7× faster than original)

---

## Testing Strategy

### Unit Tests (Fast, TDD workflow)
```bash
# Test connection pooling
pytest tests/test_connection_pool.py -m fast

# Test consolidated event generation
pytest tests/test_event_generation.py -m fast

# Test flattened workforce snapshot logic
pytest tests/test_workforce_snapshot.py -m fast
```

### Integration Tests
```bash
# Full simulation with refactored models
pytest tests/test_pipeline_integration.py -m integration

# Determinism validation (same seed = same results)
pytest tests/test_determinism.py -m integration
```

### Performance Benchmarking
```python
# tests/test_performance_benchmarks.py

import pytest
import time
from navigator_orchestrator.pipeline_orchestrator import PipelineOrchestrator
from navigator_orchestrator.config import load_simulation_config

@pytest.mark.benchmark
def test_5year_simulation_performance():
    """Benchmark 5-year simulation end-to-end."""
    config = load_simulation_config('config/simulation_config.yaml')
    orchestrator = PipelineOrchestrator(config)

    start = time.time()
    summary = orchestrator.execute_multi_year_simulation(
        start_year=2025,
        end_year=2029
    )
    elapsed = time.time() - start

    # Phase 3 target: 63 seconds (allow 20% variance)
    assert elapsed < 75, f"Simulation took {elapsed}s, expected <75s"
    assert summary.success

    print(f"\n✅ 5-year simulation completed in {elapsed:.1f}s")
    print(f"   Target: 63s | Actual: {elapsed:.1f}s | Delta: {elapsed-63:.1f}s")
```

### Regression Testing
```bash
# Compare outputs before/after refactoring
python scripts/compare_simulation_outputs.py \
  --baseline outputs/baseline_before_E079.duckdb \
  --candidate outputs/baseline_after_E079.duckdb \
  --tolerance 0.001  # Allow 0.1% floating point variance
```

---

## Risk Mitigation

### Development Strategy
```bash
# Branch per phase for isolated testing
git checkout -b feature/E079-phase1-quick-wins
git checkout -b feature/E079-phase2-architectural-fixes
git checkout -b feature/E079-phase3-connection-pooling

# PR review gates
# - All 256 existing tests pass
# - Performance benchmarks meet targets
# - Determinism validation passes
# - Code review approval from 2+ engineers
```

### Rollback Plan
```yaml
# If phase introduces regressions:
rollback_strategy:
  phase_1: Revert dbt model changes, keep validation models in place
  phase_2: Revert SQL refactoring, use original complex models
  phase_3: Revert to original DatabaseConnectionManager without pooling

# Emergency rollback
git revert <commit-sha> --no-commit
git commit -m "ROLLBACK E079 Phase X - regression detected"
```

### Data Validation
```python
# Automated validation in CI/CD
def validate_simulation_accuracy():
    """Ensure refactored models produce identical results."""

    # Run same simulation with same seed twice
    result_1 = run_simulation(seed=42)
    result_2 = run_simulation(seed=42)

    # Check determinism
    assert result_1.total_employees == result_2.total_employees
    assert result_1.total_contributions == result_2.total_contributions
    assert result_1.event_count == result_2.event_count

    # Compare with baseline (pre-E079)
    baseline = load_baseline_results()
    assert abs(result_1.total_employees - baseline.total_employees) < 1
    assert abs(result_1.total_contributions - baseline.total_contributions) < 0.01
```

---

## Success Criteria

### Performance (MUST HAVE)
- ✅ Dev laptop (M4 Pro): **420s → ≤60s** (7× improvement)
- ✅ Work laptop: **2,100s → ≤180s** (11× improvement)
- ✅ Offshore HVD: **4,200s → ≤240s** (17× improvement)
- ✅ Performance variance across machines: **≤3× range** (currently 10×)

### Quality (MUST HAVE)
- ✅ All 256 existing tests pass
- ✅ 100% deterministic: Same seed → Same results
- ✅ Zero data accuracy regressions (±0.1% tolerance)
- ✅ No breaking changes to CLI or output formats

### Code Quality (SHOULD HAVE)
- ✅ Model count: **155 → ≤90** (42% reduction)
- ✅ Total SQL lines: **~15,000 → ≤8,000** (47% reduction)
- ✅ Maximum model complexity: **No models >400 lines**
- ✅ Maximum CTEs per model: **≤10**

### Maintainability (SHOULD HAVE)
- ✅ Documentation updated (CLAUDE.md, architecture.md)
- ✅ Performance benchmarking automated
- ✅ Validation tests run in CI/CD
- ✅ Migration guide for analysts

---

## Dependencies and Blockers

### Internal Dependencies
- ✅ E072 (Pipeline Modularization) - Complete
- ✅ E074 (Enhanced Error Handling) - Complete
- ✅ E075 (Testing Infrastructure) - Complete
- ✅ E078 (Cohort Pipeline Integration) - Complete

### External Dependencies
- None (all optimizations are internal refactoring)

### Potential Blockers
1. **DuckDB version limitations**: Current version 1.0.0 may have different performance characteristics than newer versions
2. **Analyst workflow changes**: Validation models → dbt tests may require training
3. **AWS EC2 provisioning**: If approved, may need to adjust optimization strategy for cloud environment

---

## Future Optimizations (Out of Scope for E079)

### Parallel Year Execution
- **Potential**: Process independent years concurrently (60-80% speedup)
- **Challenge**: Requires non-deterministic mode or complex state management
- **Recommendation**: Consider for future epic if determinism can be relaxed

### Polars Event Factory Full Migration
- **Potential**: Replace SQL event generation with Polars (10-20× speedup)
- **Status**: Partial implementation exists (E078), full migration needed
- **Recommendation**: Separate epic (E080)

### DuckDB Query Optimization
- **Potential**: Add indexes, statistics, query hints
- **Challenge**: DuckDB incremental models don't support physical indexes
- **Recommendation**: Explore when DuckDB adds index support for tables

### Caching Layer
- **Potential**: Cache seed data, configuration, common queries
- **Challenge**: Invalidation logic for multi-year simulations
- **Recommendation**: Low priority, minor gains (<5%)

---

## Appendix A: Detailed Model Complexity Analysis

### Models Over 400 Lines (10 models)
```
1. fct_workforce_snapshot.sql                      1,078 lines, 27 CTEs
2. int_enrollment_events.sql                         906 lines, 15 CTEs
3. int_workforce_snapshot_optimized.sql              496 lines, 11 CTEs
4. int_deferral_rate_state_accumulator_v2.sql        487 lines, 11 CTEs
5. int_employer_eligibility.sql                      445 lines,  7 CTEs
6. fct_yearly_events.sql                             439 lines,  4 CTEs
7. int_enrollment_decision_matrix.sql                380 lines,  8 CTEs
8. validate_enrollment_architecture.sql              373 lines, 12 CTEs
9. int_proactive_voluntary_enrollment.sql            372 lines,  7 CTEs
10. dq_new_hire_termination_match_validation.sql    367 lines, 11 CTEs
```

### Models with >10 CTEs (8 models)
```
1. fct_workforce_snapshot.sql                        27 CTEs
2. int_enrollment_events.sql                         15 CTEs
3. dq_employee_contributions_validation.sql          13 CTEs
4. validate_enrollment_architecture.sql              12 CTEs
5. int_workforce_snapshot_optimized.sql              11 CTEs
6. int_deferral_rate_state_accumulator_v2.sql        11 CTEs
7. dq_new_hire_termination_match_validation.sql      11 CTEs
8. dq_deferral_rate_state_audit_validation.sql       10 CTEs
```

### Models with CROSS JOINs (35 models)
```
Most problematic:
1. int_enrollment_events.sql                          3 CROSS JOINs
2. int_deferral_rate_escalation_events.sql            2 CROSS JOINs
3. fct_workforce_snapshot.sql                         4 CROSS JOINs
4. int_workforce_needs.sql                            2 CROSS JOINs
... 31 more models
```

---

## Appendix B: Performance Profiling Data

### Current Execution Time Breakdown (420s total)
```
Seed loading:                     15s  (3.6%)
Foundation models:                30s  (7.1%)
Event generation (8 models):     240s  (57.1%)  ← PRIMARY BOTTLENECK
State accumulation:               80s  (19.0%)
Validation models:                45s  (10.7%)
Reporting:                        10s  (2.4%)
```

### Target Execution Time Breakdown (63s total)
```
Seed loading (cached):             2s  (3.2%)
Foundation models:                10s  (15.9%)
Event generation (1 model):       15s  (23.8%)  ← 16× IMPROVEMENT
State accumulation:               20s  (31.7%)
Validation (on-demand):            0s  (0.0%)   ← NOT RUN IN BUILD
Reporting:                         8s  (12.7%)
Connection overhead:               1s  (1.6%)
Other:                             7s  (11.1%)
```

---

## Appendix C: Estimated Effort

| Phase | Stories | Effort (Days) | Risk |
|-------|---------|---------------|------|
| **Phase 1: Quick Wins** | 3 | 2 | Low |
| **Phase 2: Architectural Fixes** | 3 | 5 | Medium |
| **Phase 3: Connection Pooling** | 1 | 3 | Low |
| **Testing & Validation** | - | 2 | - |
| **Documentation** | - | 1 | - |
| **Buffer** | - | 1 | - |
| **TOTAL** | 7 stories | **14 days** | - |

---

## Appendix D: Related Epics

- **E063**: Single-threaded Performance Optimizations (partial, focused on determinism)
- **E067**: Multi-threading Navigator Orchestrator (deferred, breaks determinism)
- **E068**: Master Performance Implementation (Polars integration, partial)
- **E072**: Pipeline Modularization (complete, foundation for E079)
- **E074**: Enhanced Error Handling (complete, supports E079 debugging)
- **E075**: Testing Infrastructure (complete, enables E079 validation)
- **E078**: Cohort Pipeline Integration (complete, Polars event factory partial)

---

## Sign-Off

**Author**: Claude Code
**Date**: 2025-11-03
**Status**: 🟡 Ready for Review

**Approvals Required**:
- [ ] Tech Lead (Architecture Review)
- [ ] Data Engineer (SQL Optimization Review)
- [ ] QA Lead (Testing Strategy Review)
- [ ] Product Owner (Timeline & Priorities)

---

**Next Steps**:
1. Review and approve epic
2. Create Jira tickets for 7 stories
3. Assign Phase 1 stories to sprint
4. Kick off implementation on Day 1
