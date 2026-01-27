{{
  config(
    severity='error',
    tags=['data_quality', 'compliance', 'irs', '401a17']
  )
}}

/*
  Data Quality Test: IRS Section 401(a)(17) Compensation Limit Compliance

  Validates that employer contributions (match and core) do not exceed
  the amounts that would result from applying the 401(a)(17) compensation cap.

  For high earners (compensation > 401(a)(17) limit), employer contributions
  should be calculated using the capped compensation, not full compensation.

  2026 Example:
  - 401(a)(17) limit: $360,000
  - Employee earning $1,675,000
  - Max employer match at 4% cap: 4% × $360,000 = $14,400
  - Max employer core at 2%: 2% × $360,000 = $7,200

  Returns rows where contributions exceed the 401(a)(17)-based maximum.
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set match_cap_percent = var('match_cap_percent', 0.04) %}
{% set employer_core_contribution_rate = var('employer_core_contribution_rate', 0.02) %}

WITH irs_limits AS (
    -- Get the 401(a)(17) compensation limit for the simulation year
    SELECT
        limit_year,
        compensation_limit AS irs_401a17_limit
    FROM {{ ref('config_irs_limits') }}
    WHERE limit_year = {{ simulation_year }}
),

match_violations AS (
    -- Check employer match amounts against the 401(a)(17) cap
    SELECT
        mc.employee_id,
        mc.simulation_year,
        mc.eligible_compensation,
        mc.employer_match_amount,
        lim.irs_401a17_limit,
        -- Maximum allowable match based on capped compensation
        ROUND(LEAST(mc.eligible_compensation, lim.irs_401a17_limit) * {{ match_cap_percent }}, 2) AS max_allowable_match,
        'match' AS violation_type,
        mc.employer_match_amount - ROUND(LEAST(mc.eligible_compensation, lim.irs_401a17_limit) * {{ match_cap_percent }}, 2) AS excess_amount
    FROM {{ ref('int_employee_match_calculations') }} mc
    CROSS JOIN irs_limits lim
    WHERE mc.simulation_year = {{ simulation_year }}
      -- Only check high earners (above 401(a)(17) limit)
      AND mc.eligible_compensation > lim.irs_401a17_limit
      -- Violation: match exceeds what would be allowed with capped compensation
      AND mc.employer_match_amount > ROUND(LEAST(mc.eligible_compensation, lim.irs_401a17_limit) * {{ match_cap_percent }}, 2)
      -- Only check employees with actual match amounts
      AND mc.employer_match_amount > 0
),

core_violations AS (
    -- Check employer core contribution amounts against the 401(a)(17) cap
    SELECT
        cc.employee_id,
        cc.simulation_year,
        cc.eligible_compensation,
        cc.employer_core_amount AS employer_contribution_amount,
        lim.irs_401a17_limit,
        -- Maximum allowable core based on capped compensation
        ROUND(LEAST(cc.eligible_compensation, lim.irs_401a17_limit) * {{ employer_core_contribution_rate }}, 2) AS max_allowable_amount,
        'core' AS violation_type,
        cc.employer_core_amount - ROUND(LEAST(cc.eligible_compensation, lim.irs_401a17_limit) * {{ employer_core_contribution_rate }}, 2) AS excess_amount
    FROM {{ ref('int_employer_core_contributions') }} cc
    CROSS JOIN irs_limits lim
    WHERE cc.simulation_year = {{ simulation_year }}
      -- Only check high earners (above 401(a)(17) limit)
      AND cc.eligible_compensation > lim.irs_401a17_limit
      -- Violation: core exceeds what would be allowed with capped compensation
      AND cc.employer_core_amount > ROUND(LEAST(cc.eligible_compensation, lim.irs_401a17_limit) * {{ employer_core_contribution_rate }}, 2)
      -- Only check employees with actual core amounts
      AND cc.employer_core_amount > 0
)

-- Return all violations
SELECT
    employee_id,
    simulation_year,
    eligible_compensation,
    employer_match_amount AS employer_contribution_amount,
    irs_401a17_limit,
    max_allowable_match AS max_allowable_amount,
    violation_type,
    excess_amount,
    CONCAT(
        'Match exceeds 401(a)(17) cap: $', ROUND(employer_match_amount, 2),
        ' > max allowable $', max_allowable_match,
        ' (compensation $', ROUND(eligible_compensation, 0),
        ' exceeds $', irs_401a17_limit, ' limit)'
    ) AS violation_description
FROM match_violations

UNION ALL

SELECT
    employee_id,
    simulation_year,
    eligible_compensation,
    employer_contribution_amount,
    irs_401a17_limit,
    max_allowable_amount,
    violation_type,
    excess_amount,
    CONCAT(
        'Core contribution exceeds 401(a)(17) cap: $', ROUND(employer_contribution_amount, 2),
        ' > max allowable $', max_allowable_amount,
        ' (compensation $', ROUND(eligible_compensation, 0),
        ' exceeds $', irs_401a17_limit, ' limit)'
    ) AS violation_description
FROM core_violations

ORDER BY excess_amount DESC
