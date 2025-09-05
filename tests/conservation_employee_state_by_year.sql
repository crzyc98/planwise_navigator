-- Epic E068B: Conservation Test for Employee State Accumulation
-- Validates that employee count changes match hiring and termination events

{% set simulation_year = var('simulation_year', 2025) | int %}

SELECT
  simulation_year,
  -- Calculate net change from previous year
  COUNT(*) - COALESCE(
    LAG(COUNT(*)) OVER (ORDER BY simulation_year),
    COUNT(*)
  ) AS net_change,

  -- Count events that should affect workforce size
  SUM(CASE
    WHEN is_active AND hire_date >= DATE('{{ simulation_year }}-01-01')
    THEN 1 ELSE 0
  END) AS new_hires,

  SUM(CASE
    WHEN NOT is_active AND termination_date >= DATE('{{ simulation_year }}-01-01')
    THEN 1 ELSE 0
  END) AS terminations,

  -- Calculate conservation error (should be close to zero)
  ABS((COUNT(*) - COALESCE(LAG(COUNT(*)) OVER (ORDER BY simulation_year), COUNT(*))) -
      (SUM(CASE WHEN is_active AND hire_date >= DATE('{{ simulation_year }}-01-01') THEN 1 ELSE 0 END) -
       SUM(CASE WHEN NOT is_active AND termination_date >= DATE('{{ simulation_year }}-01-01') THEN 1 ELSE 0 END))) AS conservation_error

FROM {{ ref('int_employee_state_by_year') }}
WHERE simulation_year IN ({{ simulation_year }} - 1, {{ simulation_year }})
GROUP BY simulation_year
HAVING conservation_error > 10  -- Allow small tolerance for rounding/timing
