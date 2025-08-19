# Census Deferral Rate Integration Plan

**Status**: Ready for Implementation
**Date**: 2025-01-20
**Owner**: Data/Modeling Team
**Related Epics**: E023 (Enrollment), E035 (Escalation), E036 (Deferral State), S042-02 (Temporal Accumulator)

## Executive Summary

Transform the unrealistic 6% deferral rate clustering into a natural distribution by using actual census deferral rates (including fractional percentages like 1.3%, 2.3%) for pre-enrolled employees. This plan maintains full event-sourcing while reflecting real-world participant behavior.

## Current State Analysis

### Problems Identified
1. **Artificial 6% Mass**: ~96% of pre-enrolled employees defaulted to hard-coded 6% rate
2. **Ignored Census Data**: System doesn't use actual census deferral rates (avg 7.2%, range 0-15%)
3. **Configuration Mismatch**: Auto-enrollment default still at 6% instead of realistic 2%
4. **Escalation Gaps**: Many employees stuck at baseline with no escalations applied
5. **No Event Trail**: Pre-enrolled rates not event-sourced, breaking auditability

### Census Data Reality
- **Total Employees**: 5,000 with deferral rates
- **Distribution**: Min 0%, P25 3.8%, Median 7.5%, P75 11.3%, Max 15%
- **Average**: 7.2% (realistic for mature 401(k) plans)
- **Fractional Rates**: Many at 1.3%, 2.3%, 3.9%, etc. (real participant choices)

## Solution Architecture

### Core Principle: Event-Sourced Census Baseline
Generate synthetic enrollment events from census data to maintain full event-sourcing while using real deferral rates.

### Component Design

#### 1. Census Rate Propagation
**File**: `dbt/models/intermediate/int_baseline_workforce.sql`
```sql
-- Add after line 53 (preserves census deferral rates)
stg.employee_deferral_rate,  -- Actual census rate (0.013, 0.023, 0.075, etc.)
stg.is_enrolled_at_census,   -- Flag for pre-enrolled participants
```

#### 2. Synthetic Baseline Events
**New File**: `dbt/models/intermediate/events/int_synthetic_baseline_enrollment_events.sql`
```sql
{{ config(
    materialized='table',
    tags=['enrollment_pipeline', 'event_sourcing']
) }}

/*
  Synthetic Baseline Enrollment Events from Census

  Creates enrollment events for pre-enrolled census participants to maintain
  event-sourcing while preserving actual deferral rates (including fractional
  percentages like 1.3%, 2.3%, etc.)
*/

WITH census_enrolled AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_deferral_rate,
        employee_enrollment_date,
        employee_hire_date,
        current_age,
        current_tenure,
        level_id,
        current_compensation
    FROM {{ ref('int_baseline_workforce') }}
    WHERE simulation_year = {{ var('start_year', 2025) }}
      AND employee_enrollment_date IS NOT NULL
      AND employee_enrollment_date < '{{ var("start_year", 2025) }}-01-01'::DATE
      AND employee_deferral_rate IS NOT NULL
      AND employee_deferral_rate > 0
)

SELECT
    employee_id,
    employee_ssn,
    'enrollment' as event_type,
    {{ var('start_year', 2025) }} as simulation_year,
    employee_enrollment_date as effective_date,

    -- Preserve exact census deferral rate with proper formatting
    CONCAT(
        'Census baseline enrollment - ',
        CAST(ROUND(employee_deferral_rate * 100, 1) AS VARCHAR),
        '% deferral rate'
    ) as event_details,

    current_compensation as compensation_amount,
    NULL as previous_compensation,

    -- Exact census deferral rate (normalized to [0,1])
    LEAST(
        GREATEST(0.0, employee_deferral_rate),
        {{ var('plan_deferral_cap', 0.75) }}
    ) as employee_deferral_rate,

    0.00 as prev_employee_deferral_rate,
    current_age as employee_age,
    current_tenure as employee_tenure,
    level_id,

    -- Age and tenure bands
    CASE
        WHEN current_age < 25 THEN '< 25'
        WHEN current_age < 35 THEN '25-34'
        WHEN current_age < 45 THEN '35-44'
        WHEN current_age < 55 THEN '45-54'
        WHEN current_age < 65 THEN '55-64'
        ELSE '65+'
    END as age_band,
    CASE
        WHEN current_tenure < 2 THEN '< 2'
        WHEN current_tenure < 5 THEN '2-4'
        WHEN current_tenure < 10 THEN '5-9'
        WHEN current_tenure < 20 THEN '10-19'
        ELSE '20+'
    END as tenure_band,

    1.0 as event_probability,  -- Certain event (already enrolled)
    'census_baseline' as event_category,

    -- Event sourcing metadata
    0 as event_sequence,  -- Pre-simulation baseline
    CURRENT_TIMESTAMP as created_at,
    'synthetic_baseline_generator' as event_source,
    '{{ var("scenario_id", "default") }}' as parameter_scenario_id,
    'census_import' as parameter_source,
    'VALID' as data_quality_flag
FROM census_enrolled
WHERE employee_deferral_rate > 0  -- Only enrolled participants
ORDER BY employee_id
```

#### 3. Updated Deferral Rate State Accumulator
**File**: `dbt/models/intermediate/int_deferral_rate_state_accumulator_v2.sql`

Replace lines 180-200 with:
```sql
-- Get ALL enrollment events (real + synthetic baseline)
all_enrollment_events AS (
    -- Real enrollment events from int_enrollment_events
    SELECT
        employee_id,
        effective_date as enrollment_date,
        employee_deferral_rate as initial_deferral_rate,
        simulation_year as enrollment_year,
        'int_enrollment_events' as source
    FROM {{ ref('int_enrollment_events') }}
    WHERE LOWER(event_type) = 'enrollment'
      AND employee_id IS NOT NULL
      AND employee_deferral_rate IS NOT NULL

    UNION ALL

    -- Synthetic baseline events for census pre-enrolled
    SELECT
        employee_id,
        effective_date as enrollment_date,
        employee_deferral_rate as initial_deferral_rate,
        EXTRACT(YEAR FROM effective_date) as enrollment_year,
        'synthetic_baseline' as source
    FROM {{ ref('int_synthetic_baseline_enrollment_events') }}
    WHERE employee_id IS NOT NULL
      AND employee_deferral_rate IS NOT NULL
),

-- No more hard-coded fallback - purely event-driven
baseline_pre_enrolled AS (
    SELECT
        employee_id,
        enrollment_date,
        initial_deferral_rate,  -- Uses actual census rate
        enrollment_year,
        source,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY enrollment_date, source
        ) as rn
    FROM all_enrollment_events
    WHERE enrollment_year < {{ simulation_year }}
)
```

#### 4. Configuration Updates
**File**: `config/simulation_config.yaml`

```yaml
# Deferral rate configuration
deferral_rates:
  # Census integration
  use_census_rates: true           # Use actual census deferral rates when available
  census_rate_field: "employee_deferral_rate"  # Field name in census data

  # Fallback rates (only when census data missing)
  pre_enrolled_fallback: 0.03      # 3% fallback for pre-enrolled without census data

  # Plan limits
  plan_deferral_cap: 0.75           # 75% IRS maximum (was incorrectly using 10%)
  plan_deferral_floor: 0.00         # 0% minimum

  # Rate normalization
  normalize_percentages: true       # Auto-detect if rates are percentages (>1) vs decimals

# Auto-enrollment configuration (already updated)
enrollment:
  auto_enrollment:
    default_deferral_rate: 0.02    # 2% for new auto-enrollments (changed from 0.06)

# Escalation configuration
deferral_auto_escalation:
  enabled: true
  effective_day: "01-01"
  increment_amount: 0.01            # 1% annual increase
  maximum_rate: 0.10                # 10% cap for escalations
  enrollment_maturity_years: 0      # Allow immediate escalation (new)
  apply_to_synthetic_baseline: true # Allow census pre-enrolled to escalate
```

#### 5. Macros for Consistency
**New File**: `dbt/macros/deferral_rate_macros.sql`
```sql
-- Default deferral rate for auto-enrollment
{% macro default_deferral_rate() %}
    {{ var('auto_enrollment_default_deferral_rate', 0.02) }}
{% endmacro %}

-- Plan deferral cap (IRS limit)
{% macro plan_deferral_cap() %}
    {{ var('plan_deferral_cap', 0.75) }}
{% endmacro %}

-- Pre-enrolled fallback rate
{% macro pre_enrolled_fallback_rate() %}
    {{ var('pre_enrolled_fallback', 0.03) }}
{% endmacro %}

-- Normalize and clamp deferral rate
{% macro normalize_deferral_rate(rate_field) %}
    LEAST(
        {{ plan_deferral_cap() }},
        GREATEST(
            0.0,
            CASE
                -- Auto-detect percentage vs decimal
                WHEN {{ rate_field }} > 1.0 THEN {{ rate_field }} / 100.0
                ELSE {{ rate_field }}
            END
        )
    )
{% endmacro %}
```

## Implementation Phases

### Phase 1: Foundation (Day 1)
1. ✅ Update config with new deferral rate settings
2. Add deferral rate macros
3. Update `int_baseline_workforce` to include census deferral rates

### Phase 2: Event Generation (Day 2)
1. Create `int_synthetic_baseline_enrollment_events` model
2. Update `int_enrollment_events` to union synthetic events
3. Test synthetic event generation

### Phase 3: State Accumulator (Day 3)
1. Update `int_deferral_rate_state_accumulator_v2` to be purely event-driven
2. Remove hard-coded 6% fallback
3. Add lineage tracking fields

### Phase 4: Escalation Fix (Day 4)
1. Update escalation eligibility to use configurable maturity
2. Allow synthetic baseline employees to escalate
3. Fix escalation targeting logic

### Phase 5: Testing & Validation (Day 5)
1. Add parity tests between accumulator and contributions
2. Add distribution tests to detect clustering
3. Run multi-year simulation and validate results

## Validation Criteria

### Year 2025 (Baseline)
- [ ] Average deferral rate: 7.0-7.5% (matches census)
- [ ] Median deferral rate: 7.3-7.7% (matches census)
- [ ] No artificial clustering at 6%
- [ ] Fractional rates preserved (1.3%, 2.3%, etc.)
- [ ] New hires at 2% (auto-enrollment default)

### Year 2026+ (Escalation)
- [ ] ~70% of eligible employees receive 1% escalation
- [ ] Distribution shifts right by ~1% per year
- [ ] High deferrers plateau at 10% cap
- [ ] No duplicate escalations

### Data Quality
- [ ] 100% parity between accumulator and contributions
- [ ] All pre-enrolled have synthetic baseline events
- [ ] Event trail complete for audit
- [ ] No NULL deferral rates for enrolled employees

## Testing SQL Queries

```sql
-- Verify census rates are used
SELECT
    simulation_year,
    COUNT(*) as total,
    AVG(current_deferral_rate) as avg_rate,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY current_deferral_rate) as median_rate,
    COUNT(CASE WHEN current_deferral_rate = 0.06 THEN 1 END) as at_6_percent,
    COUNT(CASE WHEN current_deferral_rate = 0.02 THEN 1 END) as at_2_percent
FROM int_deferral_rate_state_accumulator_v2
GROUP BY simulation_year
ORDER BY simulation_year;

-- Check synthetic baseline events
SELECT
    COUNT(*) as synthetic_events,
    AVG(employee_deferral_rate) as avg_rate,
    MIN(employee_deferral_rate) as min_rate,
    MAX(employee_deferral_rate) as max_rate
FROM int_synthetic_baseline_enrollment_events;

-- Verify parity
SELECT
    a.simulation_year,
    COUNT(*) as mismatches
FROM int_deferral_rate_state_accumulator_v2 a
JOIN int_employee_contributions c
    ON a.employee_id = c.employee_id
    AND a.simulation_year = c.simulation_year
WHERE ABS(a.current_deferral_rate - c.final_deferral_rate) > 0.0001
GROUP BY a.simulation_year;
```

## Risk Mitigation

1. **Data Loss**: Backup database before implementation
2. **Performance**: Materialize synthetic events as table, not view
3. **Compatibility**: Maintain same output schema for downstream models
4. **Validation**: Run parallel comparison with current system

## Success Metrics

- **Distribution**: Natural bell curve instead of 6% spike
- **Accuracy**: ±0.5% of census average/median
- **Escalation Coverage**: >65% of eligible employees
- **Performance**: <10% increase in runtime
- **Audit Trail**: 100% event coverage

## Next Steps

1. Review and approve this plan
2. Create feature branch `feature/census-deferral-rates`
3. Implement Phase 1-2 (foundation and events)
4. Validate synthetic events match census
5. Complete Phase 3-5 (accumulator, escalation, testing)
6. Run full multi-year validation
7. Merge to main after approval

## Appendix: Sample Output

### Before (Current State)
```
Year 2025: 96% at 6.0%, avg 5.6%
Year 2026: 73% at 6.0%, avg 5.8%
Year 2027: 69% at 6.0%, avg 6.1%
```

### After (With Census Rates)
```
Year 2025: Natural distribution, avg 7.2% (matches census)
Year 2026: Distribution + 1% escalation, avg 7.8%
Year 2027: Distribution + 2% cumulative, avg 8.3%
```

This preserves the real-world complexity of participant behavior while maintaining full event-sourcing and auditability.
