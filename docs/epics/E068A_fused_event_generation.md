# Epic E068A: Fused Event Generation

## Goal
Reduce Event Generation wall-time by ~2× by replacing many small per-event models with a single per-year compiled query that scans the cohort once, computes RNG once, branches to event CTEs, then UNION ALLs to the canonical events table/partition.

## Rationale
Event Gen ≈ 41% of total runtime; current pattern re-scans the same cohort and repeats hazard lookups and RNG in multiple models.

## Scope
- **In**: fct_yearly_events (or events_for_year) fused model; mark thin int_* helpers as materialized: ephemeral; compute RNG once; single writer per year.
- **Out**: State accumulation (covered in E068B), orchestrator changes (E068C).

## Deliverables
- `models/events/fct_yearly_events.sql` (single compiled query per year).
- All `int_*_events.sql` converted to macros (branch SQL lives in macros/events/*.sql) and/or ephemeral helpers.

## Implementation Notes
- **CTEs**: cohort_t (state at t-1) → rng (u_hire/u_term/u_promo/u_merit) → branch CTEs (promo/term/merit/eligibility/deferral/escalation) → UNION ALL.
- **Final writer**: explicitly ORDER BY employee_id, sim_year, event_type for stable diffs.
- **Use tags**: ['EVENT_GENERATION'].

## Tasks / Stories

### 1. Create RNG macro and cohort_t + rng pattern
- Implement hash-based RNG macro (see E068F)
- Create cohort_t CTE pattern for single employee scan
- Add rng CTE with all random values computed once per employee

### 2. Macro-ize each event branch
- Convert existing event logic to macros:
  - `events_promotion_sql`
  - `events_termination_sql`
  - `events_merit_sql`
  - `events_hire_sql`
  - `events_enrollment_sql`
  - `events_deferral_sql`
  - `events_escalation_sql`

### 3. Convert thin int_* to materialized: ephemeral
- Mark existing `int_*_events` models as ephemeral
- Or delete/inline if fully moved into macros
- Ensure no intermediate disk writes

### 4. Write final union writer table/partition
- Create `fct_yearly_events` as single writer
- Implement incremental strategy with year partitioning
- Include scenario_id and plan_design_id in all keys

### 5. Add dbt tests
- Uniqueness on (employee_id, sim_year, event_type[, event_seq])
- Row count validation vs baseline
- Contract enforcement with explicit column types

## Acceptance Criteria
- Per-year Event Gen ≤ 8–10s on 16 vCPU box (5k×5).
- Outputs byte-identical vs baseline (fixed seed).
- No model writes collide; only the final writer persists.

## Runbook

```bash
dbt run --select tag:EVENT_GENERATION --vars '{"simulation_year": 2027}' --threads 6
```

## Risks & Mitigations
- **Debuggability ↓** → see E068F (debug wrappers + flags).
- **Memory spikes** → shard by hash (see E068C) or push heavy joins late.

## Example Implementation

### Fused Event Model Structure
```sql
-- models/events/fct_yearly_events.sql
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year', 'event_type'],
  pre_hook="DELETE FROM {{ this }} WHERE simulation_year = {{ var('simulation_year') }}",
  tags=['EVENT_GENERATION']
) }}

WITH cohort_t AS (
  -- Single cohort scan with state at t-1
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    level, tenure_months, department, performance_tier,
    -- Employee state for hazard calculations
    hire_date, current_salary, enrollment_status
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

rng AS (
  -- Compute all RNG values once per employee
  SELECT
    *,
    {{ hash_rng('employee_id', var('simulation_year'), 'hire') }} AS u_hire,
    {{ hash_rng('employee_id', var('simulation_year'), 'termination') }} AS u_term,
    {{ hash_rng('employee_id', var('simulation_year'), 'promotion') }} AS u_promo,
    {{ hash_rng('employee_id', var('simulation_year'), 'merit') }} AS u_merit,
    {{ hash_rng('employee_id', var('simulation_year'), 'enrollment') }} AS u_enroll,
    {{ hash_rng('employee_id', var('simulation_year'), 'deferral') }} AS u_defer,
    {{ hash_rng('employee_id', var('simulation_year'), 'escalation') }} AS u_escal
  FROM cohort_t
),

-- Event branch CTEs using shared RNG
hire_events AS (
  {{ events_hire_sql('rng') }}
),

termination_events AS (
  {{ events_termination_sql('rng') }}
),

promotion_events AS (
  {{ events_promotion_sql('rng') }}
),

merit_events AS (
  {{ events_merit_sql('rng') }}
),

enrollment_events AS (
  {{ events_enrollment_sql('rng') }}
),

deferral_events AS (
  {{ events_deferral_sql('rng') }}
),

escalation_events AS (
  {{ events_escalation_sql('rng') }}
),

final_events AS (
  SELECT scenario_id, plan_design_id, employee_id, event_type, event_date, event_payload FROM hire_events
  UNION ALL
  SELECT scenario_id, plan_design_id, employee_id, event_type, event_date, event_payload FROM termination_events
  UNION ALL
  SELECT scenario_id, plan_design_id, employee_id, event_type, event_date, event_payload FROM promotion_events
  UNION ALL
  SELECT scenario_id, plan_design_id, employee_id, event_type, event_date, event_payload FROM merit_events
  UNION ALL
  SELECT scenario_id, plan_design_id, employee_id, event_type, event_date, event_payload FROM enrollment_events
  UNION ALL
  SELECT scenario_id, plan_design_id, employee_id, event_type, event_date, event_payload FROM deferral_events
  UNION ALL
  SELECT scenario_id, plan_design_id, employee_id, event_type, event_date, event_payload FROM escalation_events
)

SELECT
  {{ generate_event_uuid() }} AS event_id,
  scenario_id,
  plan_design_id,
  employee_id,
  event_type,
  event_date,
  event_payload,
  {{ var('simulation_year') }} AS simulation_year,
  CURRENT_TIMESTAMP AS created_at
FROM final_events
ORDER BY employee_id, event_type, event_date  -- Deterministic ordering
```

### Macro Example
```sql
-- macros/events/events_hire_sql.sql
{% macro events_hire_sql(cohort_table) %}
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    'hire' AS event_type,
    {{ realistic_event_date() }} AS event_date,
    JSON_OBJECT(
      'level', level,
      'department', department,
      'salary', {{ sample_starting_salary('level', 'department') }}
    ) AS event_payload
  FROM {{ cohort_table }}
  WHERE u_hire < {{ var('hire_rate', 0.15) }}
    AND hire_date IS NULL  -- Only hire if not already employed
{% endmacro %}
```

## Success Metrics
- Event Generation time per year: Current 23.2s → Target 8-10s (55-65% improvement)
- Total models materialized per year: Current 7+ → Target 1 (fct_yearly_events only)
- Memory usage: Maintain <1GB peak during event generation
- Result determinism: 100% identical outputs with same random seed

## Dependencies
- E068F (RNG macro) - Required for hash_rng implementation
- E068D (Hazard caches) - Optional for performance boost
- Baseline workforce model - Must support scenario_id/plan_design_id context

---

**Epic**: E068A
**Parent Epic**: E068 - Database Query Optimization
**Status**: 🔴 NOT STARTED
**Priority**: Critical
**Estimated Effort**: 5 story points
**Target Performance**: 55-65% improvement in Event Generation stage
