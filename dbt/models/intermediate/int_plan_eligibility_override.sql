{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['employee_id', 'simulation_year'],
  pre_hook=[
    "{% if is_incremental() %}DELETE FROM {{ this }} WHERE simulation_year = {{ var('simulation_year') }}{% endif %}"
  ],
  tags=['EVENT_GENERATION']
) }}

/*
  Plan Eligibility Override (Feature 103)

  Single resolution point for the per-employee DC-plan ineligibility override:
  "resolve once, gate everywhere." Downstream enrollment/eligibility models join
  this model on (employee_id, simulation_year) and fold
  `NOT is_plan_ineligible_override` into their existing eligibility gate, so all
  current age/service/timing logic still applies on top.

  Two populations (disjoint by ID prefix, so no precedence conflict — FR-006):
    - Census employees (EMP_*): static attribute read DIRECTLY from
      stg_census_data.eligibility_override (NOT via int_employee_compensation_by_year,
      whose Year-2+ path is rebuilt from the prior-year snapshot and would lose the
      flag — same multi-year-correct approach as the #316 opt-out). Ineligible iff
      eligibility_override IS explicitly FALSE; NULL/TRUE → eligible.
    - New hires (NH_*): deterministic, reproducible hash of employee_id + sim year
      against the effective ineligible rate.

  Effective new-hire ineligible rate:
    - new_hire_eligibility_match_census = false → new_hire_ineligible_pct (the dial).
    - true → census-observed ineligible share = COUNT(eligibility_override = FALSE)
      / COUNT(*) over ALL stg_census_data rows (blanks counted eligible — clarify
      2026-06-29). All-NULL census → 0%.

  Multi-year consistency (FR-010): this is an incremental temporal accumulator.
  Census rows are re-resolved every year (stable). New-hire classification is
  carried forward from the prior year for continuing new hires so an employee
  marked ineligible in their hire year stays ineligible across the horizon.

  Default no-op: dial 0.0 + match_census false + no census values → every employee
  resolves is_plan_ineligible_override = FALSE, leaving the existing gate unchanged.
*/

{% set simulation_year = var('simulation_year') | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set new_hire_ineligible_pct = var('new_hire_ineligible_pct', 0.0) %}
{% set match_census = var('new_hire_eligibility_match_census', false) %}

WITH census_source AS (
  SELECT
    employee_id,
    eligibility_override
  FROM {{ ref('stg_census_data') }}
  WHERE employee_id IS NOT NULL
),

-- Census-observed ineligible rate over TOTAL headcount (blanks = eligible)
census_rate AS (
  SELECT
    CASE
      WHEN COUNT(*) = 0 THEN 0.0
      ELSE CAST(SUM(CASE WHEN eligibility_override = FALSE THEN 1 ELSE 0 END) AS DOUBLE) / COUNT(*)
    END AS observed_ineligible_rate
  FROM census_source
),

-- Census employees: static flag straight from the census
census_resolved AS (
  SELECT
    employee_id,
    {{ simulation_year }} AS simulation_year,
    COALESCE(eligibility_override = FALSE, FALSE) AS is_plan_ineligible_override,
    CASE WHEN COALESCE(eligibility_override = FALSE, FALSE) THEN 'census' END AS override_source
  FROM census_source
),

-- Current-year new hires
new_hires AS (
  SELECT DISTINCT employee_id
  FROM {{ ref('int_hiring_events') }}
  WHERE simulation_year = {{ simulation_year }}
    AND employee_id IS NOT NULL
),

new_hires_resolved AS (
  SELECT
    nh.employee_id,
    {{ simulation_year }} AS simulation_year,
    (
      ABS(MOD(HASH(nh.employee_id || '_eligibility_' || CAST({{ simulation_year }} AS VARCHAR)), 1000000)) / 1000000.0
    ) < {% if match_census %}(SELECT observed_ineligible_rate FROM census_rate){% else %}{{ new_hire_ineligible_pct }}{% endif %} AS is_plan_ineligible_override,
    '{% if match_census %}census_match{% else %}new_hire_dial{% endif %}' AS override_source
  FROM new_hires nh
),

{% if simulation_year > start_year %}
-- Carry forward prior-year classification for continuing employees (chiefly new
-- hires from earlier years who are no longer in census or current-year hires)
prior_year_overrides AS (
  SELECT
    employee_id,
    {{ simulation_year }} AS simulation_year,
    is_plan_ineligible_override,
    override_source
  FROM {{ this }}
  WHERE simulation_year = {{ simulation_year - 1 }}
),
{% endif %}

all_resolved AS (
  SELECT employee_id, simulation_year, is_plan_ineligible_override, override_source, 1 AS resolution_priority
  FROM census_resolved
  UNION ALL
  SELECT employee_id, simulation_year, is_plan_ineligible_override, override_source, 2 AS resolution_priority
  FROM new_hires_resolved
  {% if simulation_year > start_year %}
  UNION ALL
  SELECT employee_id, simulation_year, is_plan_ineligible_override, override_source, 3 AS resolution_priority
  FROM prior_year_overrides
  {% endif %}
),

deduplicated AS (
  SELECT
    employee_id,
    simulation_year,
    is_plan_ineligible_override,
    override_source,
    ROW_NUMBER() OVER (
      PARTITION BY employee_id, simulation_year
      ORDER BY resolution_priority
    ) AS rn
  FROM all_resolved
)

SELECT
  employee_id,
  simulation_year,
  is_plan_ineligible_override,
  CASE
    WHEN is_plan_ineligible_override THEN override_source
    ELSE 'eligible'
  END AS override_source
FROM deduplicated
WHERE rn = 1
