{{ config(
    materialized='table',
    tags=['eligibility', 'enrollment', 'E023']
) }}

-- Plan eligibility determination model - determines who can participate in the 401(k) plan
-- This is separate from employer contribution eligibility
-- Uses rule-based calculation to avoid circular dependencies

WITH simulation_config AS (
    SELECT {{ var('simulation_year') }} AS simulation_year
),

-- Get plan eligibility configuration
plan_eligibility_config AS (
    SELECT
        {{ var('plan_eligibility_waiting_period_days', 0) }} AS waiting_period_days,
        {{ var('plan_eligibility_minimum_age', 21) }} AS minimum_age
),

-- Get all active employees from workforce pre-enrollment
active_employees AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_hire_date,
        current_age,
        current_tenure,
        level_id,
        current_compensation,
        age_band,
        tenure_band,
        simulation_year
    FROM {{ ref('int_workforce_pre_enrollment') }}
    WHERE simulation_year = {{ var('simulation_year') }}
),

-- Calculate plan eligibility for each employee
eligibility_calculation AS (
    SELECT
        ae.employee_id,
        ae.employee_ssn,
        ae.employee_hire_date,
        ae.current_age,
        ae.current_tenure,
        ae.level_id,
        ae.current_compensation,
        ae.age_band,
        ae.tenure_band,
        ae.simulation_year,
        
        -- Plan eligibility configuration
        pec.waiting_period_days,
        pec.minimum_age,
        
        -- Calculate plan eligibility date
        ae.employee_hire_date + INTERVAL (pec.waiting_period_days) DAY AS plan_eligibility_date,
        
        -- Check age requirement
        ae.current_age >= pec.minimum_age AS meets_age_requirement,
        
        -- Check tenure requirement (based on waiting period)
        -- If waiting_period_days = 0, they're immediately eligible after hire
        CASE
            WHEN pec.waiting_period_days = 0 THEN TRUE
            ELSE DATE_DIFF('day', ae.employee_hire_date, MAKE_DATE(ae.simulation_year, 12, 31)) >= pec.waiting_period_days
        END AS meets_tenure_requirement,
        
        -- Calculate days until eligible (if not yet eligible)
        CASE
            WHEN ae.current_age < pec.minimum_age THEN 
                -- Need to wait until minimum age
                (pec.minimum_age - ae.current_age) * 365
            WHEN DATE_DIFF('day', ae.employee_hire_date, MAKE_DATE(ae.simulation_year, 12, 31)) < pec.waiting_period_days THEN
                -- Need to wait for waiting period
                pec.waiting_period_days - DATE_DIFF('day', ae.employee_hire_date, MAKE_DATE(ae.simulation_year, 12, 31))
            ELSE 0
        END AS days_until_eligible
        
    FROM active_employees ae
    CROSS JOIN plan_eligibility_config pec
)

-- Final eligibility determination
SELECT
    employee_id,
    employee_ssn,
    simulation_year,
    employee_hire_date,
    current_age,
    current_tenure,
    level_id,
    current_compensation,
    age_band,
    tenure_band,
    
    -- Eligibility fields
    waiting_period_days,
    minimum_age,
    plan_eligibility_date,
    meets_age_requirement,
    meets_tenure_requirement,
    
    -- Overall plan eligibility
    (meets_age_requirement AND meets_tenure_requirement) AS is_plan_eligible,
    
    -- Eligibility timing
    CASE
        WHEN meets_age_requirement AND meets_tenure_requirement THEN 'eligible'
        WHEN NOT meets_age_requirement THEN 'not_eligible_age'
        WHEN NOT meets_tenure_requirement THEN 'not_eligible_tenure'
        ELSE 'not_eligible_other'
    END AS eligibility_status,
    
    days_until_eligible,
    
    -- Eligibility effective date (when they became/will become eligible)
    CASE
        WHEN meets_age_requirement AND meets_tenure_requirement THEN
            GREATEST(
                employee_hire_date + INTERVAL (waiting_period_days) DAY,
                -- Approximate date when they turned minimum_age
                MAKE_DATE(simulation_year - current_age + minimum_age, 1, 1)
            )
        ELSE NULL
    END AS eligibility_effective_date,
    
    -- Metadata
    CURRENT_TIMESTAMP AS determination_timestamp,
    'plan_eligibility' AS eligibility_type,
    'rule_based' AS determination_method
    
FROM eligibility_calculation
ORDER BY employee_id