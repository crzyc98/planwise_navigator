{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'simulation_year'],
    on_schema_change='sync_all_columns',
    indexes=[
        {'columns': ['simulation_year', 'employee_id'], 'type': 'btree', 'unique': true},
        {'columns': ['level_id', 'simulation_year'], 'type': 'btree'},
        {'columns': ['employment_status', 'simulation_year'], 'type': 'btree'}
    ]
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

-- **CORE FIX**: Unified event processing - handles all employee types in single pass
employee_events_consolidated AS (
    SELECT
        employee_id,
        -- Termination processing (unified for all employee types)
        MAX(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN effective_date END) AS termination_date,
        MAX(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN event_details END) AS termination_reason,
        COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN 1 END) > 0 AS has_termination,

        -- **CRITICAL FIX**: New hire termination identification
        COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' AND event_category = 'new_hire_termination' THEN 1 END) > 0 AS is_new_hire_termination,

        -- Hire events processing
        MAX(CASE WHEN event_type = 'hire' THEN effective_date END) AS hire_date,
        MAX(CASE WHEN event_type = 'hire' THEN compensation_amount END) AS hire_salary,
        MAX(CASE WHEN event_type = 'hire' THEN employee_age END) AS hire_age,
        MAX(CASE WHEN event_type = 'hire' THEN employee_ssn END) AS hire_ssn,
        MAX(CASE WHEN event_type = 'hire' THEN level_id END) AS hire_level_id,
        COUNT(CASE WHEN event_type = 'hire' THEN 1 END) > 0 AS is_new_hire,

        -- Promotion events processing
        MAX(CASE WHEN event_type = 'promotion' THEN compensation_amount END) AS promotion_salary,
        MAX(CASE WHEN event_type = 'promotion' THEN level_id END) AS promotion_level_id,
        COUNT(CASE WHEN event_type = 'promotion' THEN 1 END) > 0 AS has_promotion,

        -- Merit/raise events processing
        MAX(CASE WHEN event_type = 'raise' THEN compensation_amount END) AS merit_salary,
        COUNT(CASE WHEN event_type = 'raise' THEN 1 END) > 0 AS has_merit,

        -- Enrollment events processing
        MAX(CASE WHEN event_type = 'enrollment' THEN effective_date END) AS enrollment_date,
        MAX(CASE WHEN event_type = 'enrollment' THEN event_details END) AS enrollment_details,
        MAX(CASE WHEN event_type = 'enrollment' THEN employee_deferral_rate END) AS enrollment_deferral_rate,
        COUNT(CASE WHEN event_type = 'enrollment' THEN 1 END) > 0 AS has_enrollment,

        -- Enrollment change events (for deferral rate changes)
        MAX(CASE WHEN event_type = 'enrollment_change' THEN employee_deferral_rate END) AS changed_deferral_rate,
        COUNT(CASE WHEN event_type = 'enrollment_change' THEN 1 END) > 0 AS has_enrollment_change
    FROM current_year_events
    WHERE employee_id IS NOT NULL
    GROUP BY employee_id
),

-- Apply consolidated events to existing workforce
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
            WHEN ec.has_termination THEN CAST(ec.termination_date AS TIMESTAMP)
            ELSE CAST(b.termination_date AS TIMESTAMP)
        END AS termination_date,
        CASE
            WHEN ec.has_termination THEN 'terminated'
            ELSE b.employment_status
        END AS employment_status,
        ec.termination_reason
    FROM base_workforce b
    LEFT JOIN employee_events_consolidated ec ON b.employee_id = ec.employee_id
),

-- Apply promotion events (using consolidated event data)
workforce_after_promotions AS (
    SELECT
        w.employee_id,
        w.employee_ssn,
        w.employee_birth_date,
        w.employee_hire_date,
        CASE
            WHEN ec.has_promotion THEN ec.promotion_salary
            ELSE w.employee_gross_compensation
        END AS employee_gross_compensation,
        w.current_age,
        w.current_tenure,
        CASE
            WHEN ec.has_promotion THEN ec.promotion_level_id
            ELSE CAST(w.level_id AS INTEGER)
        END AS level_id,
        w.termination_date,
        w.employment_status,
        w.termination_reason
    FROM workforce_after_terminations w
    LEFT JOIN employee_events_consolidated ec ON w.employee_id = ec.employee_id
),

-- Apply merit increases (using consolidated event data)
workforce_after_merit AS (
    SELECT
        w.employee_id,
        w.employee_ssn,
        w.employee_birth_date,
        w.employee_hire_date,
        CASE
            WHEN ec.has_merit THEN ec.merit_salary
            ELSE w.employee_gross_compensation
        END AS employee_gross_compensation,
        w.current_age,
        w.current_tenure,
        w.level_id,
        w.termination_date,
        w.employment_status,
        w.termination_reason
    FROM workforce_after_promotions w
    LEFT JOIN employee_events_consolidated ec ON w.employee_id = ec.employee_id
),

-- **REVERTED & FIXED**: Add new hires from hiring events, applying termination status from consolidated processing
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
        -- **CRITICAL FIX**: Apply termination status from consolidated event processing
        -- **ENHANCED**: Prioritize new hire termination flag for accurate status determination
        CASE
            WHEN ec.is_new_hire_termination THEN CAST(ec.termination_date AS TIMESTAMP)
            WHEN ec.has_termination THEN CAST(ec.termination_date AS TIMESTAMP)
            ELSE NULL
        END AS termination_date,
        CASE
            WHEN ec.is_new_hire_termination THEN 'terminated'
            WHEN ec.has_termination THEN 'terminated'
            ELSE 'active'
        END AS employment_status,
        ec.termination_reason
    FROM {{ ref('fct_yearly_events') }} ye
    -- **KEY FIX**: Join with consolidated events to get termination status
    LEFT JOIN employee_events_consolidated ec ON ye.employee_id = ec.employee_id
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
        baseline.employee_id,
        baseline.employee_eligibility_date,
        baseline.waiting_period_days,
        baseline.current_eligibility_status,
        -- Use enrollment state accumulator for consistent enrollment tracking
        -- Priority: 1. Current year enrollment events, 2. Enrollment state accumulator, 3. Baseline
        COALESCE(
            CASE WHEN ec.has_enrollment THEN ec.enrollment_date END,
            accumulator.enrollment_date,
            baseline.employee_enrollment_date
        ) AS employee_enrollment_date,
        -- Calculate enrollment flag for year 1
        CASE
            WHEN COALESCE(
                CASE WHEN ec.has_enrollment THEN ec.enrollment_date END,
                accumulator.enrollment_date,
                baseline.employee_enrollment_date
            ) IS NOT NULL
            THEN true
            ELSE false
        END AS is_enrolled_flag
    FROM {{ ref('int_baseline_workforce') }} baseline
    LEFT JOIN (
        -- Get enrollment status from enrollment state accumulator
        SELECT
            employee_id,
            enrollment_date,
            enrollment_status AS is_enrolled
        FROM {{ ref('int_enrollment_state_accumulator') }}
        WHERE simulation_year = {{ simulation_year }}
    ) accumulator ON baseline.employee_id = accumulator.employee_id
    LEFT JOIN employee_events_consolidated ec ON baseline.employee_id = ec.employee_id
    WHERE baseline.employment_status = 'active'
    {% else %}
    -- Subsequent years: Get from eligibility events and baseline for those without events
    SELECT DISTINCT
        COALESCE(events.employee_id, baseline.employee_id) AS employee_id,
        COALESCE(events.employee_eligibility_date, baseline.employee_eligibility_date) AS employee_eligibility_date,
        COALESCE(events.waiting_period_days, baseline.waiting_period_days) AS waiting_period_days,
        COALESCE(events.current_eligibility_status, baseline.current_eligibility_status) AS current_eligibility_status,
        -- Use enrollment state accumulator for consistent enrollment tracking
        -- Priority: 1. Current year enrollment events, 2. Enrollment state accumulator, 3. Baseline
        COALESCE(
            CASE WHEN ec.has_enrollment THEN ec.enrollment_date END,
            accumulator.enrollment_date,
            baseline.employee_enrollment_date
        ) AS employee_enrollment_date,
        -- Calculate enrollment flag based on enrollment date
        CASE
            WHEN COALESCE(
                CASE WHEN ec.has_enrollment THEN ec.enrollment_date END,
                accumulator.enrollment_date,
                baseline.employee_enrollment_date
            ) IS NOT NULL
            THEN true
            ELSE false
        END AS is_enrolled_flag
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
    LEFT JOIN (
        -- Get enrollment status from enrollment state accumulator for current year
        SELECT
            employee_id,
            enrollment_date,
            enrollment_status AS is_enrolled
        FROM {{ ref('int_enrollment_state_accumulator') }}
        WHERE simulation_year = {{ simulation_year }}
    ) accumulator ON COALESCE(events.employee_id, baseline.employee_id) = accumulator.employee_id
    -- Add join to employee_events_consolidated to get current year enrollment events (for subsequent years)
    LEFT JOIN employee_events_consolidated ec ON COALESCE(events.employee_id, baseline.employee_id) = ec.employee_id
    {% endif %}
),

-- **UPDATED**: CTEs for prorated compensation calculation using consolidated events
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
        ee.is_enrolled_flag,
        -- Add deferral rate tracking
        COALESCE(
            ec.changed_deferral_rate,  -- Most recent change takes precedence
            ec.enrollment_deferral_rate,  -- Initial enrollment rate
            0.00  -- Default for non-enrolled
        ) AS current_deferral_rate,
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
    LEFT JOIN employee_events_consolidated ec ON fwc.employee_id = ec.employee_id
    -- **MERIT FIX**: Use consolidated event data for merit calculations
    LEFT JOIN (
        SELECT
            employee_id,
            merit_salary AS compensation_amount,
            -- Before merit period: previous salary × days before merit (approximated)
            0 AS before_contrib,  -- Simplified for now, can be enhanced later
            -- After merit period: new salary × days after merit (approximated)
            merit_salary * 0.5 AS after_contrib  -- Simplified assumption
        FROM employee_events_consolidated
        WHERE has_merit = true
    ) merit_calc ON fwc.employee_id = merit_calc.employee_id
    -- **PROMO FIX**: Use consolidated event data for promotion calculations
    LEFT JOIN (
        SELECT
            employee_id,
            promotion_salary AS compensation_amount
        FROM employee_events_consolidated
        WHERE has_promotion = true
    ) promo_calc ON fwc.employee_id = promo_calc.employee_id
    -- Add eligibility information
    LEFT JOIN employee_eligibility ee ON fwc.employee_id = ee.employee_id
    -- Epic E034: Add employee contribution calculations
    LEFT JOIN {{ ref('int_employee_contributions') }} contributions
        ON fwc.employee_id = contributions.employee_id
        AND contributions.simulation_year = sp.current_year
),

-- Final workforce with all joins including contributions
final_workforce_with_contributions AS (
    SELECT
        fw.*,
        contributions.annual_contribution_amount,
        contributions.effective_annual_deferral_rate,
        contributions.total_contribution_base_compensation,
        contributions.first_contribution_date,
        contributions.last_contribution_date,
        contributions.contribution_quality_flag
    FROM final_workforce fw
    LEFT JOIN {{ ref('int_employee_contributions') }} contributions
        ON fw.employee_id = contributions.employee_id
        AND contributions.simulation_year = fw.simulation_year
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
    is_enrolled_flag,
    -- Add deferral rate
    current_deferral_rate,
    -- Epic E034: Add contribution calculations
    COALESCE(annual_contribution_amount, 0.0) AS prorated_annual_contributions,
    -- Split contributions into pre-tax and Roth based on industry assumptions
    -- For now, assume 85% pre-tax, 15% Roth (typical split)
    COALESCE(annual_contribution_amount * 0.85, 0.0) AS pre_tax_contributions,
    COALESCE(annual_contribution_amount * 0.15, 0.0) AS roth_contributions,
    COALESCE(annual_contribution_amount, 0.0) AS ytd_contributions,
    -- IRS 402(g) limit check for 2025: $23,500 under 50, $31,000 for 50+
    CASE
        WHEN COALESCE(annual_contribution_amount, 0.0) >=
            CASE
                WHEN current_age >= 50 THEN 31000  -- Catch-up contribution limit
                ELSE 23500  -- Standard limit for under 50
            END
        THEN true
        ELSE false
    END AS irs_limit_reached,
    -- Additional contribution metadata
    effective_annual_deferral_rate,
    total_contribution_base_compensation,
    first_contribution_date,
    last_contribution_date,
    contribution_quality_flag,
    CURRENT_TIMESTAMP AS snapshot_created_at
FROM final_workforce_with_contributions

{% if is_incremental() %}
  -- Only process the current simulation year when running incrementally
  WHERE simulation_year = {{ simulation_year }}
{% endif %}

ORDER BY employee_id
