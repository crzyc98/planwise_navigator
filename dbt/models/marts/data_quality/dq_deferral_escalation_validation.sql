{{ config(
    materialized='table'
) }}

/*
  Data Quality Validation Summary for Deferral Rate Escalation (Epic E035)

  Queries fct_yearly_events for deferral_escalation events and validates:
  1. No rates above cap (default 10%)
  2. No duplicate employee+year escalation events
  3. Effective dates on January 1st
  4. new_deferral_rate > previous_deferral_rate (meaningful increase)

  Computes a real health_score (0-100) based on violation counts.
  Handles the case where zero escalation events exist (returns health_score=100).
*/

{% set simulation_year = var('simulation_year', 2025) %}
{% set esc_cap = var('deferral_escalation_cap', 0.10) %}

WITH escalation_events AS (
  SELECT
    employee_id,
    simulation_year,
    effective_date,
    employee_deferral_rate,
    prev_employee_deferral_rate,
    event_details
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'deferral_escalation'
    AND simulation_year = {{ simulation_year }}
),

total_count AS (
  SELECT COUNT(*) AS cnt FROM escalation_events
),

-- Check 1: Rates above cap
invalid_rates AS (
  SELECT COUNT(*) AS cnt
  FROM escalation_events
  WHERE employee_deferral_rate > {{ esc_cap }} + 0.0001
),

-- Check 2: Duplicate employee+year
duplicates AS (
  SELECT COUNT(*) AS cnt
  FROM (
    SELECT employee_id, simulation_year, COUNT(*) AS n
    FROM escalation_events
    GROUP BY employee_id, simulation_year
    HAVING COUNT(*) > 1
  ) dups
),

-- Check 3: Effective dates not on January 1st
bad_dates AS (
  SELECT COUNT(*) AS cnt
  FROM escalation_events
  WHERE EXTRACT(MONTH FROM effective_date) != 1
     OR EXTRACT(DAY FROM effective_date) != 1
),

-- Check 4: Rate did not increase (new <= previous)
rate_mismatches AS (
  SELECT COUNT(*) AS cnt
  FROM escalation_events
  WHERE prev_employee_deferral_rate IS NOT NULL
    AND employee_deferral_rate <= prev_employee_deferral_rate
),

-- Escalation count decreases: not applicable in single-year context, default 0
esc_count_decreases AS (
  SELECT 0::INTEGER AS cnt
),

violations AS (
  SELECT
    (SELECT cnt FROM invalid_rates) AS invalid_deferral_rates,
    (SELECT cnt FROM duplicates) AS duplicate_escalations,
    (SELECT cnt FROM bad_dates) AS incorrect_effective_dates,
    (SELECT cnt FROM rate_mismatches) AS deferral_rate_mismatches,
    (SELECT cnt FROM esc_count_decreases) AS escalation_count_decreases,
    (SELECT cnt FROM total_count) AS total_records
),

summary AS (
  SELECT
    {{ simulation_year }}::INTEGER AS simulation_year,
    v.total_records,
    (v.invalid_deferral_rates + v.duplicate_escalations + v.incorrect_effective_dates
     + v.deferral_rate_mismatches + v.escalation_count_decreases)::INTEGER AS total_violations,
    v.invalid_deferral_rates::INTEGER AS invalid_deferral_rates,
    v.duplicate_escalations::INTEGER AS duplicate_escalations,
    v.incorrect_effective_dates::INTEGER AS incorrect_effective_dates,
    v.deferral_rate_mismatches::INTEGER AS deferral_rate_mismatches,
    v.escalation_count_decreases::INTEGER AS escalation_count_decreases,
    -- Health score: 100 when no violations, reduced proportionally
    CASE
      WHEN v.total_records = 0 THEN 100
      ELSE GREATEST(0, 100 - CAST(
        (v.invalid_deferral_rates + v.duplicate_escalations + v.incorrect_effective_dates
         + v.deferral_rate_mismatches + v.escalation_count_decreases) * 100.0
        / GREATEST(v.total_records, 1) AS INTEGER
      ))
    END::INTEGER AS health_score,
    -- Violation rate percentage
    CASE
      WHEN v.total_records = 0 THEN 0.0
      ELSE ROUND(
        (v.invalid_deferral_rates + v.duplicate_escalations + v.incorrect_effective_dates
         + v.deferral_rate_mismatches + v.escalation_count_decreases) * 100.0
        / GREATEST(v.total_records, 1), 2
      )
    END::DOUBLE AS violation_rate_pct
  FROM violations v
)

SELECT
  simulation_year,
  health_score,
  CASE
    WHEN health_score = 100 THEN 'PERFECT'
    WHEN health_score >= 95 THEN 'EXCELLENT'
    WHEN health_score >= 85 THEN 'GOOD'
    WHEN health_score >= 70 THEN 'FAIR'
    WHEN health_score >= 50 THEN 'POOR'
    ELSE 'CRITICAL'
  END::VARCHAR AS health_status,
  total_violations,
  total_records,
  violation_rate_pct,
  invalid_deferral_rates,
  duplicate_escalations,
  incorrect_effective_dates,
  deferral_rate_mismatches,
  escalation_count_decreases,
  CASE
    WHEN total_violations = 0 THEN 'System healthy; no issues detected'
    ELSE 'Violations detected: '
      || CASE WHEN invalid_deferral_rates > 0 THEN invalid_deferral_rates || ' invalid rates; ' ELSE '' END
      || CASE WHEN duplicate_escalations > 0 THEN duplicate_escalations || ' duplicates; ' ELSE '' END
      || CASE WHEN incorrect_effective_dates > 0 THEN incorrect_effective_dates || ' bad dates; ' ELSE '' END
      || CASE WHEN deferral_rate_mismatches > 0 THEN deferral_rate_mismatches || ' rate mismatches; ' ELSE '' END
      || CASE WHEN escalation_count_decreases > 0 THEN escalation_count_decreases || ' count decreases' ELSE '' END
  END::VARCHAR AS recommendations,
  CURRENT_TIMESTAMP AS validation_timestamp
FROM summary
