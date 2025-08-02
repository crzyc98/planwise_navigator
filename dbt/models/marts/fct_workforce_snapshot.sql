{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'simulation_year'],
    on_schema_change='fail',
    indexes=[
        {'columns': ['simulation_year', 'employee_id'], 'type': 'btree', 'unique': true},
        {'columns': ['level_id', 'simulation_year'], 'type': 'btree'},
        {'columns': ['employment_status', 'simulation_year'], 'type': 'btree'}
    ],
    contract={
        "enforced": true
    }
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

-- Year-end workforce snapshot that applies events to generate current workforce state
-- **FIX**: Added comprehensive fixes for test failures: status codes, level_id nulls, and duplicates
-- **VARIANCE FIX**: Enhanced new hire termination logic to eliminate workforce variance issues

-- Debug: simulation_year = {{ simulation_year }}
WITH simulation_parameters AS (
    SELECT {{ simulation_year }} AS current_year
),

-- Base workforce: use baseline for year 1, previous year's active workforce for subsequent years
base_workforce AS (
    {% if simulation_year == start_year %}
    -- Year 1: Use baseline workforce (2024 census)
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        current_compensation AS employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        termination_date,
        employment_status
    FROM {{ ref('int_baseline_workforce') }}
    {% else %}
    -- Subsequent years: Use helper model to break circular dependency
    -- This creates a temporal dependency (year N depends on year N-1) instead of circular
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
        employment_status
    FROM {{ ref('int_active_employees_prev_year_snapshot') }}
    {% endif %}
),

-- Get all events for current simulation year
current_year_events AS (
    SELECT *
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
),

-- Apply termination events (FIXED: Case-insensitive matching and proper filtering)
workforce_after_terminations AS (
    SELECT
        b.employee_id,
        b.employee_ssn,
        b.employee_birth_date,
        b.employee_hire_date,
        b.employee_gross_compensation,
        b.current_age,
        b.current_tenure,
        b.level_id,
        CASE
            WHEN t.employee_id IS NOT NULL THEN CAST(t.effective_date AS TIMESTAMP)
            ELSE CAST(b.termination_date AS TIMESTAMP)
        END AS termination_date,
        CASE
            WHEN t.employee_id IS NOT NULL THEN 'terminated'
            ELSE b.employment_status
        END AS employment_status,
        t.event_details AS termination_reason
    FROM base_workforce b
    LEFT JOIN (
        -- FIXED: Pre-filter termination events with case-insensitive matching
        SELECT DISTINCT
            employee_id,
            effective_date,
            event_details
        FROM current_year_events
        WHERE UPPER(event_type) = 'TERMINATION'
            AND employee_id IS NOT NULL
            AND simulation_year = (SELECT current_year FROM simulation_parameters)
    ) t ON b.employee_id = t.employee_id
        AND b.employee_id IS NOT NULL
),

-- Apply promotion events
workforce_after_promotions AS (
    SELECT
        w.employee_id,
        w.employee_ssn,
        w.employee_birth_date,
        w.employee_hire_date,
        CASE
            WHEN p.employee_id IS NOT NULL THEN p.compensation_amount
            ELSE w.employee_gross_compensation
        END AS employee_gross_compensation,
        w.current_age,
        w.current_tenure,
        CASE
            WHEN p.employee_id IS NOT NULL THEN p.to_level
            ELSE w.level_id
        END AS level_id,
        w.termination_date,
        w.employment_status,
        w.termination_reason
    FROM workforce_after_terminations w
    LEFT JOIN (
        SELECT
            employee_id,
            level_id AS to_level,  -- FIXED: Use level_id directly instead of parsing event_details
            compensation_amount
        FROM current_year_events
        WHERE event_type = 'promotion'
    ) p ON w.employee_id = p.employee_id
),

-- Apply merit increases (RAISE events) to update current compensation
workforce_after_merit AS (
    SELECT
        w.employee_id,
        w.employee_ssn,
        w.employee_birth_date,
        w.employee_hire_date,
        CASE
            WHEN r.employee_id IS NOT NULL THEN r.compensation_amount
            ELSE w.employee_gross_compensation
        END AS employee_gross_compensation,
        w.current_age,
        w.current_tenure,
        w.level_id,
        w.termination_date,
        w.employment_status,
        w.termination_reason
    FROM workforce_after_promotions w
    LEFT JOIN current_year_events r
        ON w.employee_id = r.employee_id
        AND r.event_type = 'raise'
),

-- Add new hires from hiring events (use fct_yearly_events for persistence across years)
-- FIX: Enhanced termination logic to properly filter and join termination events
new_hires AS (
    SELECT
        CAST(ye.employee_id AS VARCHAR) AS employee_id,
        ye.employee_ssn,
        -- Calculate birth date from age (approximate)
        CAST('{{ simulation_year }}-01-01' AS DATE) - INTERVAL (ye.employee_age * 365) DAY AS employee_birth_date,
        ye.effective_date AS employee_hire_date,
        ye.compensation_amount AS employee_gross_compensation,
        ye.employee_age AS current_age,
        0 AS current_tenure, -- New hires start with 0 tenure
        ye.level_id,
        -- Check if this new hire has a termination event in the same year (FIXED: Case-insensitive)
        CAST(term.effective_date AS TIMESTAMP) AS termination_date,
        CASE WHEN term.employee_id IS NOT NULL THEN 'terminated' ELSE 'active' END AS employment_status,
        term.event_details AS termination_reason
    FROM {{ ref('fct_yearly_events') }} ye
    LEFT JOIN (
        -- FIXED: Pre-filter termination events with case-insensitive matching
        SELECT DISTINCT
            employee_id,
            effective_date,
            event_details,
            simulation_year
        FROM {{ ref('fct_yearly_events') }}
        WHERE UPPER(event_type) = 'TERMINATION'
            AND employee_id IS NOT NULL
            AND simulation_year = {{ simulation_year }}
            AND EXTRACT(YEAR FROM effective_date) = {{ simulation_year }}
    ) term ON ye.employee_id = term.employee_id
        AND ye.employee_id IS NOT NULL
    WHERE ye.event_type = 'hire'
      AND ye.simulation_year = {{ simulation_year }}
),

-- **FIX 3**: Combine existing workforce with new hires and handle duplicates
unioned_workforce_raw AS (
    SELECT
        *,
        'existing' AS record_source
    FROM workforce_after_merit
    UNION ALL
    SELECT
        *,
        'new_hire' AS record_source
    FROM new_hires
),

-- **OPTIMIZED FIX**: Deduplicate with correct priority for new hires to preserve hire dates
unioned_workforce AS (
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
        termination_reason
    FROM (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY employee_id
                ORDER BY
                    -- OPTIMIZATION: Prioritize new_hire records for employees hired this year
                    -- This ensures correct hire dates are preserved for status classification
                    CASE
                        WHEN record_source = 'new_hire' AND
                             EXTRACT(YEAR FROM employee_hire_date) = {{ simulation_year }}
                        THEN 1
                        WHEN record_source = 'existing' THEN 2
                        ELSE 3
                    END,
                    employee_gross_compensation DESC,
                    termination_date ASC NULLS LAST
            ) AS rn
        FROM unioned_workforce_raw
    ) ranked
    WHERE rn = 1
),

-- **FIX 2**: Apply level_id correction for compensation outside defined ranges
workforce_with_corrected_levels AS (
    SELECT
        uw.employee_id,
        uw.employee_ssn,
        uw.employee_birth_date,
        uw.employee_hire_date,
        uw.employee_gross_compensation,
        uw.current_age,
        uw.current_tenure,
        -- **CRITICAL FIX**: Preserve promotion levels instead of recalculating based on compensation
        -- Priority order: 1. Existing level (from promotions), 2. Compensation-based calculation as fallback
        CASE
            WHEN uw.level_id IS NOT NULL THEN uw.level_id  -- Preserve existing level (includes promotions)
            ELSE COALESCE(
                (SELECT MIN(level_id)
                 FROM {{ ref('stg_config_job_levels') }} levels
                 WHERE uw.employee_gross_compensation >= levels.min_compensation
                   AND (uw.employee_gross_compensation < levels.max_compensation OR levels.max_compensation IS NULL)
                ),
                1  -- Default to level 1 for compensation below minimum range
            )
        END AS level_id,
        uw.termination_date,
        uw.employment_status,
        uw.termination_reason
    FROM unioned_workforce uw
),

-- Pass through the workforce data (terminations already handled correctly)
-- VARIANCE FIX: This CTE is intentionally a pass-through - no additional termination logic
final_workforce_corrected AS (
    SELECT
        uw.employee_id,
        uw.employee_ssn,
        uw.employee_birth_date,
        uw.employee_hire_date,
        uw.employee_gross_compensation,
        uw.current_age,
        uw.current_tenure,
        uw.level_id,
        uw.termination_date,
        uw.employment_status,
        uw.termination_reason
    FROM workforce_with_corrected_levels uw
),

-- Extract eligibility information from baseline (year 1) or events (subsequent years)
employee_eligibility AS (
    {% if simulation_year == start_year %}
    -- Year 1: Get eligibility data from baseline workforce (census data)
    SELECT DISTINCT
        employee_id,
        employee_eligibility_date,
        waiting_period_days,
        current_eligibility_status,
        employee_enrollment_date
    FROM {{ ref('int_baseline_workforce') }}
    WHERE employment_status = 'active'
    {% else %}
    -- Subsequent years: Get from eligibility events and baseline for those without events
    SELECT DISTINCT
        COALESCE(events.employee_id, baseline.employee_id) AS employee_id,
        COALESCE(events.employee_eligibility_date, baseline.employee_eligibility_date) AS employee_eligibility_date,
        COALESCE(events.waiting_period_days, baseline.waiting_period_days) AS waiting_period_days,
        COALESCE(events.current_eligibility_status, baseline.current_eligibility_status) AS current_eligibility_status,
        baseline.employee_enrollment_date  -- Keep enrollment date from baseline if available
    FROM (
        -- Get eligibility from events
        SELECT DISTINCT
            employee_id,
            JSON_EXTRACT_STRING(event_details, '$.eligibility_date')::DATE AS employee_eligibility_date,
            JSON_EXTRACT(event_details, '$.waiting_period_days')::INT AS waiting_period_days,
            -- Derive current eligibility status based on eligibility date and current date
            CASE
                WHEN JSON_EXTRACT_STRING(event_details, '$.eligibility_date')::DATE <= '{{ simulation_year }}-12-31'::DATE
                THEN 'eligible'
                ELSE 'pending'
            END AS current_eligibility_status
        FROM {{ ref('fct_yearly_events') }}
        WHERE event_type = 'eligibility'
          AND JSON_EXTRACT_STRING(event_details, '$.determination_type') = 'initial'
          -- Get the most recent eligibility determination for each employee
          AND simulation_year IN (
              SELECT MAX(simulation_year)
              FROM {{ ref('fct_yearly_events') }} ey
              WHERE ey.event_type = 'eligibility'
                AND ey.employee_id = fct_yearly_events.employee_id
                AND ey.simulation_year <= {{ simulation_year }}
          )
    ) events
    FULL OUTER JOIN (
        -- Get baseline eligibility for employees without events
        SELECT 
            employee_id,
            employee_eligibility_date,
            waiting_period_days,
            current_eligibility_status,
            employee_enrollment_date
        FROM {{ ref('int_baseline_workforce') }}
        WHERE employment_status = 'active'
    ) baseline ON events.employee_id = baseline.employee_id
    {% endif %}
),

-- CTEs for prorated compensation calculation
comp_events_for_periods AS (
    SELECT
        employee_id,
        event_type,
        effective_date,
        compensation_amount,
        previous_compensation,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date, event_type
        ) AS event_sequence_in_year
    FROM current_year_events
    WHERE event_type IN ('hire', 'promotion', 'raise', 'termination')
),

-- **EPIC E030 FIX**: Sequential event-based periods to eliminate overlapping compensation
-- Step 1: Get all compensation events in chronological order for each employee
employee_compensation_timeline AS (
    SELECT
        employee_id,
        effective_date AS event_date,
        event_type,
        compensation_amount AS new_compensation,
        previous_compensation,
        -- Add row number to handle events on same date with proper priority
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date,
            CASE event_type
                WHEN 'hire' THEN 1
                WHEN 'promotion' THEN 2
                WHEN 'raise' THEN 3
                WHEN 'termination' THEN 4
            END
        ) AS event_sequence
    FROM comp_events_for_periods
    WHERE event_type IN ('hire', 'promotion', 'raise', 'termination')
),

-- Step 2: Create timeline with period boundaries using LEAD for next event
employee_timeline_with_boundaries AS (
    SELECT
        employee_id,
        event_date,
        event_type,
        new_compensation,
        previous_compensation,
        event_sequence,
        -- Get the next event date to define period end
        LEAD(event_date) OVER (
            PARTITION BY employee_id
            ORDER BY event_sequence
        ) AS next_event_date
    FROM employee_compensation_timeline
),

-- Step 3: Generate sequential non-overlapping periods
all_compensation_periods AS (
    -- Baseline period: Start of year to first event (for non-hires)
    SELECT
        t.employee_id,
        0 AS period_sequence,
        'baseline' AS period_type,
        '{{ simulation_year }}-01-01'::DATE AS period_start,
        t.event_date - INTERVAL 1 DAY AS period_end,
        -- Get baseline compensation from previous_compensation (start of year value)
        COALESCE(t.previous_compensation, w.employee_gross_compensation, 0) AS period_salary
    FROM employee_timeline_with_boundaries t
    LEFT JOIN final_workforce_corrected w ON t.employee_id = w.employee_id
    WHERE t.event_sequence = 1  -- First event for this employee
      AND t.event_date > '{{ simulation_year }}-01-01'::DATE  -- Not at start of year
      AND t.event_type != 'hire'  -- Hires don't have baseline periods

    UNION ALL

    -- Event periods: Each event creates a period from its date to next event
    SELECT
        employee_id,
        event_sequence AS period_sequence,
        event_type || '_period' AS period_type,
        event_date AS period_start,
        COALESCE(
            next_event_date - INTERVAL 1 DAY,
            '{{ simulation_year }}-12-31'::DATE
        ) AS period_end,
        new_compensation AS period_salary
    FROM employee_timeline_with_boundaries
    WHERE event_type IN ('hire', 'promotion', 'raise')  -- Only compensation-affecting events
      AND new_compensation IS NOT NULL
      AND new_compensation > 0
),

-- Validate and clean periods
compensation_periods AS (
    SELECT
        employee_id,
        period_sequence,
        period_type,
        period_start,
        period_end,
        period_salary
    FROM all_compensation_periods
    WHERE period_start IS NOT NULL
      AND period_end IS NOT NULL
      AND period_salary IS NOT NULL
      AND period_salary > 0
      AND period_start <= period_end
      AND period_start >= '{{ simulation_year }}-01-01'::DATE
      AND period_end <= '{{ simulation_year }}-12-31'::DATE
),

-- Calculate prorated compensation for employees with events
employees_with_events_prorated AS (
    SELECT
        employee_id,
        SUM(
            period_salary * (DATE_DIFF('day', period_start, period_end) + 1) / 365.0
        ) AS prorated_annual_compensation
    FROM compensation_periods
    WHERE period_start IS NOT NULL
      AND period_end IS NOT NULL
      AND period_salary IS NOT NULL
      AND period_start <= period_end
      AND period_salary > 0
      AND DATE_DIFF('day', period_start, period_end) >= 0
    GROUP BY employee_id
),

-- Handle employees with no compensation events (continuous employment)
employees_without_events_prorated AS (
    SELECT
        fwc.employee_id,
        -- Calculate based on employment period
        CASE
            -- New hire (hired this year)
            WHEN EXTRACT(YEAR FROM fwc.employee_hire_date) = {{ simulation_year }}
                THEN fwc.employee_gross_compensation * (DATE_DIFF('day', fwc.employee_hire_date, COALESCE(fwc.termination_date, '{{ simulation_year }}-12-31'::DATE)) + 1) / 365.0

            -- Experienced employee terminated this year
            WHEN fwc.employment_status = 'terminated' AND fwc.termination_date IS NOT NULL AND EXTRACT(YEAR FROM fwc.termination_date) = {{ simulation_year }}
                THEN fwc.employee_gross_compensation * (DATE_DIFF('day', '{{ simulation_year }}-01-01'::DATE, fwc.termination_date) + 1) / 365.0

            -- Continuous active employee (full year)
            ELSE fwc.employee_gross_compensation
        END AS prorated_annual_compensation
    FROM final_workforce_corrected fwc
    WHERE fwc.employee_id NOT IN (SELECT employee_id FROM comp_events_for_periods)
      AND fwc.employment_status = 'active' -- Only calculate for active employees without events
),

-- Combine prorated compensation for all employees
employee_prorated_compensation AS (
    SELECT employee_id, prorated_annual_compensation FROM employees_with_events_prorated
    UNION ALL
    SELECT employee_id, prorated_annual_compensation FROM employees_without_events_prorated
),

-- Add age and tenure bands
final_workforce AS (
    SELECT
        fwc.employee_id,
        fwc.employee_ssn,
        fwc.employee_birth_date,
        fwc.employee_hire_date,
        fwc.employee_gross_compensation AS current_compensation,
        -- Use the standard prorated compensation from the periods calculation
        COALESCE(
            epc.prorated_annual_compensation,
            fwc.employee_gross_compensation
        ) AS prorated_annual_compensation,
        fwc.current_age,
        fwc.current_tenure,
        fwc.level_id,
        fwc.employment_status,
        fwc.termination_date,
        fwc.termination_reason,
        sp.current_year AS simulation_year,
        -- **NEW**: Add data needed for full_year_equivalent calculation
        merit_calc.compensation_amount AS merit_new_salary,
        promo_calc.compensation_amount AS promo_new_salary,
        -- Add eligibility fields
        ee.employee_eligibility_date,
        ee.waiting_period_days,
        ee.current_eligibility_status,
        ee.employee_enrollment_date,
        -- Recalculate bands with updated age/tenure (these are indeed static for a given year here)
        CASE
            WHEN fwc.current_age < 25 THEN '< 25'
            WHEN fwc.current_age < 35 THEN '25-34'
            WHEN fwc.current_age < 45 THEN '35-44'
            WHEN fwc.current_age < 55 THEN '45-54'
            WHEN fwc.current_age < 65 THEN '55-64'
            ELSE '65+'
        END AS age_band,
        CASE
            WHEN fwc.current_tenure < 2 THEN '< 2'
            WHEN fwc.current_tenure < 5 THEN '2-4'
            WHEN fwc.current_tenure < 10 THEN '5-9'
            WHEN fwc.current_tenure < 20 THEN '10-19'
            ELSE '20+'
        END AS tenure_band,
        -- **FIX 1**: Enhanced detailed_status_code logic to handle all edge cases
        CASE
            -- Active new hires (hired in current year, still active)
            WHEN fwc.employment_status = 'active' AND
                 EXTRACT(YEAR FROM fwc.employee_hire_date) = sp.current_year
            THEN 'new_hire_active'

            -- Terminated new hires (hired and terminated in current year)
            WHEN fwc.employment_status = 'terminated' AND
                 EXTRACT(YEAR FROM fwc.employee_hire_date) = sp.current_year
            THEN 'new_hire_termination'

            -- Active existing employees (hired before current year, still active)
            WHEN fwc.employment_status = 'active' AND
                 EXTRACT(YEAR FROM fwc.employee_hire_date) < sp.current_year
            THEN 'continuous_active'

            -- Terminated existing employees (hired before current year, terminated this year)
            WHEN fwc.employment_status = 'terminated' AND
                 EXTRACT(YEAR FROM fwc.employee_hire_date) < sp.current_year
            THEN 'experienced_termination'

            -- Handle edge cases with NULL values or invalid states
            WHEN fwc.employment_status IS NULL
            THEN 'continuous_active'  -- Default for NULL employment status

            WHEN fwc.employee_hire_date IS NULL
            THEN 'continuous_active'  -- Default for NULL hire date

            -- This should now be unreachable, but kept as safeguard
            ELSE 'continuous_active'
        END AS detailed_status_code
    FROM final_workforce_corrected fwc
    CROSS JOIN simulation_parameters sp
    LEFT JOIN employee_prorated_compensation epc ON fwc.employee_id = epc.employee_id
    -- **MERIT FIX**: Direct merit calculation via LEFT JOIN
    LEFT JOIN (
        SELECT
            employee_id,
            compensation_amount,
            -- Before merit period: previous salary × days before merit
            COALESCE(previous_compensation, 0) * (DATE_DIFF('day', '{{ simulation_year }}-01-01'::DATE, effective_date - INTERVAL 1 DAY) + 1) / 365.0 AS before_contrib,
            -- After merit period: new salary × days after merit
            compensation_amount * (DATE_DIFF('day', effective_date, '{{ simulation_year }}-12-31'::DATE) + 1) / 365.0 AS after_contrib
        FROM current_year_events
        WHERE event_type = 'raise'
    ) merit_calc ON fwc.employee_id = merit_calc.employee_id
    -- **PROMO FIX**: Add promotion calculation for full_year_equivalent
    LEFT JOIN (
        SELECT
            employee_id,
            compensation_amount
        FROM current_year_events
        WHERE event_type = 'promotion'
    ) promo_calc ON fwc.employee_id = promo_calc.employee_id
    -- Add eligibility information
    LEFT JOIN employee_eligibility ee ON fwc.employee_id = ee.employee_id
)

SELECT
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    current_compensation,
    prorated_annual_compensation,
    -- **NEW**: Full-year equivalent compensation - annualizes all compensation periods
    -- This eliminates proration-based dilution by calculating what each employee
    -- would earn if they worked the full year at their effective rates
    CASE
        -- For employees with merit increases: use the post-merit salary as full-year equivalent
        WHEN merit_new_salary IS NOT NULL THEN merit_new_salary

        -- For promoted employees: use post-promotion salary as full-year equivalent
        WHEN promo_new_salary IS NOT NULL THEN promo_new_salary

        -- For new hires: use their hired salary as full-year equivalent
        WHEN EXTRACT(YEAR FROM employee_hire_date) = simulation_year THEN current_compensation

        -- For continuous employees: use current salary as full-year equivalent
        ELSE current_compensation
    END AS full_year_equivalent_compensation,
    current_age,
    current_tenure,
    level_id,
    age_band,
    tenure_band,
    employment_status,
    termination_date,
    termination_reason,
    detailed_status_code,
    simulation_year,
    -- Add eligibility fields
    employee_eligibility_date,
    waiting_period_days,
    current_eligibility_status,
    employee_enrollment_date,
    CURRENT_TIMESTAMP AS snapshot_created_at
FROM final_workforce

{% if is_incremental() %}
  -- Only process the current simulation year when running incrementally
  WHERE simulation_year = {{ simulation_year }}
{% endif %}

ORDER BY employee_id
