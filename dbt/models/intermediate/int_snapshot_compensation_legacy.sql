{{ config(
    materialized='table',
    tags=['compensation', 'snapshot', 'legacy', 'backup', 'disabled'],
    enabled=false
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}

{#
    LEGACY BACKUP MODEL - DO NOT MODIFY

    This is a safety backup of the original int_snapshot_compensation.sql logic
    during the transition to the new payroll ledger system. This model is disabled
    by default and serves as a rollback option if issues are discovered.

    Planned deletion date: 4 weeks after payroll ledger deployment
    Original model replaced: [DATE]

    To enable this model for emergency rollback:
    1. Set enabled=true in config above
    2. Update fct_workforce_snapshot to use this model instead of fct_payroll_ledger
    3. Run dbt build to restore legacy logic
#}

-- int_snapshot_compensation.sql
-- This model calculates prorated compensation for employees, accounting for mid-year salary changes
-- from raises and promotions. It implements time-weighted averaging of compensation based on
-- the effective dates of compensation events.

WITH workforce_base AS (
    -- Get the base workforce data with starting and final compensation amounts
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        termination_date,
        employment_status,
        termination_reason,
        simulation_year,
        -- Starting compensation (at beginning of year or hire date)
        employee_gross_compensation AS starting_compensation,
        -- Final compensation after all events
        CASE
            WHEN merit_new_salary IS NOT NULL THEN merit_new_salary
            WHEN promo_new_salary IS NOT NULL THEN promo_new_salary
            ELSE employee_gross_compensation
        END AS final_compensation,
        -- Extract days since start of year for hire date
        CASE
            WHEN EXTRACT(YEAR FROM employee_hire_date) = simulation_year
            THEN DAYOFYEAR(employee_hire_date)
            ELSE 1
        END AS hire_day_of_year
    FROM {{ ref('int_snapshot_hiring') }}
    WHERE simulation_year = {{ simulation_year }}
),

compensation_events AS (
    -- Get all compensation-changing events (raises and promotions) with their effective dates
    -- Handle multiple raises per employee by selecting the latest one
    SELECT
        employee_id,
        event_type,
        simulation_year,
        effective_date,
        -- Use compensation_amount for the new salary after the event
        compensation_amount AS event_new_salary,
        previous_compensation,
        -- Calculate the day of year for the effective date
        -- Validate that event_day_of_year is within valid range (1-366)
        CASE
            WHEN DAYOFYEAR(effective_date) < 1 THEN 1
            WHEN DAYOFYEAR(effective_date) > EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE)) THEN EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE))
            ELSE DAYOFYEAR(effective_date)
        END AS event_day_of_year,
        -- Rank events by effective date to handle multiple raises
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date DESC
        ) AS event_rank
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
        AND event_type IN ('raise', 'promotion')  -- Note: event types are lowercase in fct_yearly_events
        AND effective_date IS NOT NULL
        AND compensation_amount IS NOT NULL
),

latest_compensation_events AS (
    -- Filter to only the most recent compensation event per employee
    SELECT * FROM compensation_events
    WHERE event_rank = 1
),

workforce_with_events AS (
    -- Join workforce with their compensation events
    SELECT
        w.*,
        ce.event_type,
        ce.effective_date,
        ce.event_day_of_year,
        ce.event_new_salary
    FROM workforce_base w
    LEFT JOIN latest_compensation_events ce
        ON w.employee_id = ce.employee_id
),

final_compensation AS (
    -- Calculate prorated compensation based on time at each salary level
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        termination_date,
        employment_status,
        termination_reason,
        simulation_year,
        final_compensation AS full_year_equivalent_compensation,

        -- Calculate prorated annual compensation
        CASE
            -- No compensation events - use the starting compensation
            WHEN event_new_salary IS NULL THEN
                CASE
                    -- New hire during the year - prorate from hire date
                    WHEN hire_day_of_year > 1 THEN
                        starting_compensation * (EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE)) - hire_day_of_year + 1) / EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE))
                    -- Full year employee
                    ELSE starting_compensation
                END

            -- Has compensation event - calculate time-weighted average
            ELSE
                CASE
                    -- New hire with compensation event in same year
                    WHEN hire_day_of_year > 1 THEN
                        -- Time from hire to event at starting salary
                        (starting_compensation * GREATEST(event_day_of_year - hire_day_of_year, 0) / EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE))) +
                        -- Time from event to year end at new salary
                        (event_new_salary * (EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE)) - event_day_of_year + 1) / EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE)))

                    -- Existing employee with compensation event
                    ELSE
                        -- Time from year start to event at starting salary
                        (starting_compensation * GREATEST(event_day_of_year - 1, 0) / EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE))) +
                        -- Time from event to year end at new salary
                        (event_new_salary * (EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE)) - event_day_of_year + 1) / EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE)))
                END
        END AS prorated_annual_compensation

    FROM workforce_with_events
)

SELECT
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    employee_gross_compensation,
    current_age,
    current_tenure,
    level_id,
    termination_date,
    employment_status,
    termination_reason,
    simulation_year,
    ROUND(prorated_annual_compensation, 2) AS prorated_annual_compensation,
    full_year_equivalent_compensation,
    -- Add final_compensation to support correct mapping in downstream models
    full_year_equivalent_compensation AS final_compensation
FROM final_compensation
ORDER BY employee_id
