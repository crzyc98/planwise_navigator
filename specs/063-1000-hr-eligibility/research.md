# Research: ERISA 1,000-Hour Eligibility Rules

**Feature**: `063-1000-hr-eligibility` | **Date**: 2026-03-03

## R1: Boundary-Aware IECP Implementation Within Annual Pipeline

**Decision**: Use the existing annual pipeline steps. For mid-year hires, compute IECP hours by prorating across the two plan years the IECP spans, using the hire date as the boundary.

**Rationale**: The simulation runs year-by-year. Adding sub-annual stages would require major pipeline refactoring. Instead, we compute the IECP boundary within SQL using date arithmetic already proven in `int_employer_eligibility.sql`.

**Implementation approach**: `int_eligibility_computation_period` will:
1. For each employee's first simulation year: compute days from hire_date to year-end → prorate 2,080 hours
2. For the second simulation year: compute days from year-start to IECP end (hire_date anniversary) → prorate hours
3. Sum the two partial-year hours to get the total IECP hours
4. After the IECP, switch to plan-year-aligned computation periods

**Key formula** (consistent with existing `int_employer_eligibility.sql` pattern):
```sql
-- IECP Year 1 portion (hire_date to year_end)
DATEDIFF('day', hire_date, MAKE_DATE(simulation_year, 12, 31)) / 365.0 * 2080.0

-- IECP Year 2 portion (year_start to hire_date anniversary)
DATEDIFF('day', MAKE_DATE(simulation_year, 1, 1), hire_date_anniversary) / 365.0 * 2080.0
```

**Alternatives considered**:
- Sub-annual pipeline stages: Rejected — disproportionate architectural cost
- Plan-year-only (no IECP): Rejected — non-compliant with ERISA

## R2: Temporal State Accumulator Pattern for Service Credit

**Decision**: Use the `{{ this }}` self-referencing temporal accumulator pattern (proven in `int_enrollment_state_accumulator.sql` and `int_deferral_rate_state_accumulator_v2.sql`).

**Rationale**: Service credit must accumulate across years. The temporal accumulator pattern is the established approach in this codebase — it avoids circular dependencies, supports idempotent re-runs, and integrates with existing pipeline stages.

**Implementation**:
- `int_service_credit_accumulator.sql`: Incremental model with `delete+insert` strategy
  - First year: Read from `int_baseline_workforce` + `int_eligibility_computation_period`
  - Subsequent years: Read from `{{ this }}` (prior year) + `int_eligibility_computation_period`
  - Output: per-employee eligibility_years_credited, vesting_years_credited, plan_entry_date

**Alternatives considered**:
- Non-incremental table with full recompute: Rejected — scales poorly for multi-year simulations
- Python-based accumulation: Rejected — codebase uses SQL-only mode (E024)

## R3: Parallel Model Architecture

**Decision**: Create 2 new dbt intermediate models alongside existing models. Do not modify `int_employer_eligibility.sql`, `int_eligibility_determination.sql`, or `int_plan_eligibility_determination.sql`.

**Rationale**: Existing models serve distinct purposes (match/core allocation, waiting period, age/tenure gates). New models implement ERISA-compliant computation periods — a different domain. Parallel architecture avoids breaking existing functionality.

**New models**:
1. `int_eligibility_computation_period.sql` — IECP/plan-year computation periods with 1,000-hour threshold (FR-001 through FR-005)
2. `int_service_credit_accumulator.sql` — Temporal accumulator for eligibility + vesting service years (FR-006)

**Alternatives considered**:
- Replace `int_employer_eligibility.sql`: Rejected — would break match/core eligibility
- Extend as upstream models: Rejected — creates coupling between independent domains

## R4: Hours Threshold Macro

**Decision**: Implement the 1,000-hour threshold as a reusable SQL macro.

**Rationale**: The threshold is applied in both the computation period model and the accumulator. A macro ensures consistency.

**Implementation**:
```sql
{% macro classify_service_hours(hours_column) %}
CASE
    WHEN {{ hours_column }} >= 1000 THEN 'year_of_service'
    ELSE 'no_credit'
END
{% endmacro %}
```

**Alternatives considered**:
- Inline CASE in each model: Rejected — duplicates logic
- Seed-based lookup: Rejected — over-engineering for a binary threshold

## R5: Configuration Extension

**Decision**: Add a new `erisa_eligibility` section to `simulation_config.yaml`.

**Rationale**: ERISA plan participation eligibility is conceptually separate from contribution allocation eligibility. A dedicated config section keeps concerns separated.

**New configuration**:
```yaml
erisa_eligibility:
  enabled: true
  hour_counting_method: "prorated"        # Only "prorated" supported in this iteration
  plan_year_start_month: 1
  plan_year_start_day: 1
  eligibility_threshold_hours: 1000
  vesting_computation_period: "plan_year"  # "plan_year" | "anniversary_year"
```

**Alternatives considered**:
- Extend `plan_eligibility`: Rejected — conflates simplified gate with full ERISA rules
- Extend `employer_match.eligibility`: Rejected — match eligibility is allocation-specific

## R6: Testing Strategy

**Decision**: dbt schema tests (column-level) + custom SQL tests (business logic).

**Test categories**:
1. **Schema tests** (in `schema.yml`): `not_null`, `accepted_range`, `accepted_values` on new model columns
2. **Custom SQL tests** (in `tests/data_quality/`):
   - `test_iecp_computation.sql` — IECP spans correct 12-month window from hire date
   - `test_hours_threshold.sql` — boundary value testing (0, 999, 1000, 2080)
   - `test_eligibility_vs_vesting_independence.sql` — eligibility and vesting credits can differ
3. **Expression tests** (in `schema.yml`): `dbt_utils.expression_is_true` for invariants

**Alternatives considered**:
- Python unit tests only: Rejected — logic lives in SQL/dbt
- Integration tests only: Rejected — boundary values need targeted dbt tests
