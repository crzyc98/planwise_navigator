{{ config(
  materialized='ephemeral',
  tags=['EVENT_GENERATION']
) }}

{% set simulation_year = var('simulation_year') | int %}

-- One current-year employment boundary per employee. Experienced termination
-- wins only when both sources produce the same earliest date.
WITH termination_candidates AS (
  SELECT
    employee_id,
    simulation_year,
    CAST(effective_date AS DATE) AS termination_date,
    'experienced' AS termination_cohort,
    1 AS cohort_priority
  FROM {{ ref('int_termination_events') }}
  WHERE simulation_year = {{ simulation_year }}
    AND effective_date IS NOT NULL

  UNION ALL

  SELECT
    employee_id,
    simulation_year,
    CAST(effective_date AS DATE) AS termination_date,
    'new_hire' AS termination_cohort,
    2 AS cohort_priority
  FROM {{ ref('int_new_hire_termination_events') }}
  WHERE simulation_year = {{ simulation_year }}
    AND effective_date IS NOT NULL
),

ranked_boundaries AS (
  SELECT
    employee_id,
    simulation_year,
    termination_date,
    termination_cohort,
    ROW_NUMBER() OVER (
      PARTITION BY employee_id, simulation_year
      ORDER BY termination_date, cohort_priority
    ) AS boundary_rank
  FROM termination_candidates
)

SELECT
  employee_id,
  simulation_year,
  termination_date,
  termination_cohort
FROM ranked_boundaries
WHERE boundary_rank = 1
