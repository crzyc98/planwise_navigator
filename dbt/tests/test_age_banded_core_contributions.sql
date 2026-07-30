/* The amount and audit rate must always describe the same annual decision. */
SELECT *
FROM {{ ref('int_employer_core_contributions') }}
WHERE simulation_year = {{ var('simulation_year', 2025) }}
  AND employer_core_amount > 0
  AND ABS(employer_core_amount - ROUND(
    LEAST(eligible_compensation, irs_401a17_limit) * core_contribution_rate, 2
  )) > 0.01
