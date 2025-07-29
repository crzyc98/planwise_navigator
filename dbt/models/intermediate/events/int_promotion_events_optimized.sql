{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id'], 'type': 'btree'},
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['effective_date'], 'type': 'btree'},
        {'columns': ['from_level', 'to_level'], 'type': 'btree'}
    ],
    tags=['optimization', 'events', 'promotion_compensation_fix']
) }}

{% set simulation_year = var('simulation_year') %}
{% set previous_year = simulation_year - 1 %}

-- **OPTIMIZED PROMOTION EVENTS WITH CURRENT COMPENSATION**
-- 
-- **PERFORMANCE IMPROVEMENT**: Uses fct_workforce_snapshot from previous year-end
-- instead of stale int_active_employees_prev_year_snapshot to get accurate
-- post-merit compensation for promotion calculations.
--
-- **BUSINESS LOGIC**: 
-- - Promotions occur February 1st using compensation updated from July 15th merit/COLA
-- - Merit increases occur July 15th (previous year)
-- - This ensures promotions use current salary, not 4-year-old baseline data
--
-- **DuckDB OPTIMIZATION**:
-- - Direct columnar storage access for efficient temporal joins
-- - Indexed lookups on employee_id and simulation_year
-- - Pre-filtered eligible workforce to minimize join overhead
-- - Optimized age/tenure band calculations using CASE expressions

WITH simulation_params AS (
    SELECT 
        {{ simulation_year }} AS current_year,
        {{ previous_year }} AS previous_year
),

-- **OPTIMIZATION 1**: Use fct_workforce_snapshot for accurate current compensation
-- This replaces the stale int_active_employees_prev_year_snapshot approach
current_workforce AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_hire_date,
        -- **KEY FIX**: Use current_compensation (includes merit increases from July 15)
        current_compensation AS employee_gross_compensation,
        current_age + 1 AS current_age, -- Age for the new simulation year
        current_tenure + 1 AS current_tenure, -- Tenure for the new simulation year
        level_id
    FROM {{ ref('fct_workforce_snapshot') }} 
    WHERE simulation_year = (SELECT previous_year FROM simulation_params)
      AND employment_status = 'active'
      -- **PERFORMANCE FILTER**: Pre-filter promotion-eligible employees
      AND level_id < 5  -- Can't promote beyond max level
      AND current_tenure >= 0  -- Will be >= 1 after increment
      AND current_age < 64  -- Will be < 65 after increment
),

-- **OPTIMIZATION 2**: Efficient band calculation with single-pass logic
eligible_workforce AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        -- **DuckDB OPTIMIZATION**: Vectorized CASE expressions for band calculation
        CASE
            WHEN current_age < 25 THEN '< 25'
            WHEN current_age < 35 THEN '25-34'
            WHEN current_age < 45 THEN '35-44'
            WHEN current_age < 55 THEN '45-54'
            WHEN current_age < 65 THEN '55-64'
            ELSE '65+'
        END AS age_band,
        CASE
            WHEN current_tenure < 2 THEN '< 2'
            WHEN current_tenure < 5 THEN '2-4'
            WHEN current_tenure < 10 THEN '5-9'
            WHEN current_tenure < 20 THEN '10-19'
            ELSE '20+'
        END AS tenure_band,
        -- **DETERMINISTIC RANDOM**: Consistent hash-based probability
        (ABS(HASH(employee_id || '{{ simulation_year }}' || 'promotion')) % 1000) / 1000.0 AS random_value
    FROM current_workforce
    WHERE current_tenure >= 1  -- Final eligibility check
      AND current_age < 65
),

-- **OPTIMIZATION 3**: Efficient hazard rate lookup with indexed join
promotion_candidates AS (
    SELECT
        ew.*,
        h.promotion_rate
    FROM eligible_workforce ew
    INNER JOIN {{ ref('int_hazard_promotion') }} h
        ON ew.level_id = h.level_id
        AND ew.age_band = h.age_band
        AND ew.tenure_band = h.tenure_band
        AND h.year = {{ simulation_year }}
    WHERE ew.random_value < h.promotion_rate  -- Apply probability threshold
),

-- **OPTIMIZATION 4**: Vectorized salary calculation with business rules
promoted_employees AS (
    SELECT
        employee_id,
        employee_ssn,
        'promotion' AS event_type,
        {{ simulation_year }} AS simulation_year,
        -- **CALENDAR-DRIVEN**: Promotions occur February 1st
        CAST('{{ simulation_year }}-02-01' AS DATE) AS effective_date,
        level_id AS from_level,
        level_id + 1 AS to_level,
        employee_gross_compensation AS previous_salary,
        -- **OPTIMIZED SALARY CALCULATION**: Vectorized with caps
        ROUND(
            LEAST(
                -- 30% increase cap
                employee_gross_compensation * 1.30,
                -- $500K absolute increase cap  
                employee_gross_compensation + 500000,
                -- Base 15-25% increase (deterministic)
                employee_gross_compensation * (1.15 + ((ABS(HASH(employee_id || 'promo_pct')) % 100) / 1000.0))
            ), 2
        ) AS new_salary,
        current_age,
        current_tenure,
        age_band,
        tenure_band,
        promotion_rate,
        random_value
    FROM promotion_candidates
)

-- **FINAL OUTPUT**: Comprehensive promotion events with metadata
SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    from_level,
    to_level,
    previous_salary,
    new_salary,
    current_age,
    current_tenure,
    age_band,
    tenure_band,
    promotion_rate,
    random_value,
    -- **QUALITY METRICS**: Salary increase analysis
    ROUND((new_salary - previous_salary) / previous_salary * 100, 2) AS salary_increase_pct,
    new_salary - previous_salary AS salary_increase_amount
FROM promoted_employees
ORDER BY employee_id