{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key="employee_id || '_' || simulation_year",
    on_schema_change='sync_all_columns',
    tags=['STATE_ACCUMULATION']
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

-- **E079 PHASE 2A**: Flattened workforce snapshot (27 CTEs → 7 CTEs)
-- Performance optimization: eliminated redundant scans and sequential event processing
-- Key improvements:
--   1. Single-pass event application (consolidated events)
--   2. Materialized baseline comparison (not correlated subqueries)
--   3. Merged prorated compensation logic
--   4. Eliminated redundant pass-through CTEs

WITH
-- CTE 1: Base workforce + all events consolidated
base_workforce_and_events AS (
    SELECT
        -- Base workforce data
        {% if simulation_year == start_year %}
        bw.employee_id,
        bw.employee_ssn,
        bw.employee_birth_date,
        bw.employee_hire_date,
        bw.current_compensation AS employee_gross_compensation,
        bw.current_age,
        bw.current_tenure,
        bw.level_id,
        bw.termination_date,
        bw.employment_status,
        {% else %}
        prev.employee_id,
        prev.employee_ssn,
        prev.employee_birth_date,
        prev.employee_hire_date,
        prev.employee_gross_compensation,
        prev.current_age,
        prev.current_tenure,
        prev.level_id,
        prev.termination_date,
        prev.employment_status,
        {% endif %}

        -- Consolidated event data (from fct_yearly_events aggregation)
        ec.termination_date AS event_termination_date,
        ec.termination_reason,
        ec.has_termination,
        ec.is_new_hire_termination,
        ec.is_new_hire,
        ec.hire_date,
        ec.hire_salary,
        ec.hire_age,
        ec.hire_ssn,
        ec.hire_level_id,
        ec.has_promotion,
        ec.promotion_salary,
        ec.promotion_level_id,
        ec.has_merit,
        ec.merit_salary,
        ec.has_enrollment,
        ec.enrollment_date,
        ec.enrollment_details,
        ec.enrollment_deferral_rate,
        ec.has_enrollment_change,
        ec.changed_deferral_rate,

        -- Record source for union handling
        'existing' AS record_source,
        {{ simulation_year }} AS simulation_year
    FROM
        {% if simulation_year == start_year %}
        {{ ref('int_baseline_workforce') }} bw
        {% else %}
        {{ ref('int_active_employees_prev_year_snapshot') }} prev
        WHERE prev.simulation_year = {{ simulation_year }}
        {% endif %}
    LEFT JOIN (
        -- Consolidated events from fct_yearly_events
        SELECT
            employee_id,
            -- Termination processing
            MAX(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN effective_date END) AS termination_date,
            MAX(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN event_details END) AS termination_reason,
            COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN 1 END) > 0 AS has_termination,
            COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' AND event_category = 'new_hire_termination' THEN 1 END) > 0 AS is_new_hire_termination,

            -- Hire events
            MAX(CASE WHEN event_type = 'hire' THEN effective_date END) AS hire_date,
            MAX(CASE WHEN event_type = 'hire' THEN compensation_amount END) AS hire_salary,
            MAX(CASE WHEN event_type = 'hire' THEN employee_age END) AS hire_age,
            MAX(CASE WHEN event_type = 'hire' THEN employee_ssn END) AS hire_ssn,
            MAX(CASE WHEN event_type = 'hire' THEN level_id END) AS hire_level_id,
            COUNT(CASE WHEN event_type = 'hire' THEN 1 END) > 0 AS is_new_hire,

            -- Promotion events
            MAX(CASE WHEN event_type = 'promotion' THEN compensation_amount END) AS promotion_salary,
            MAX(CASE WHEN event_type = 'promotion' THEN level_id END) AS promotion_level_id,
            COUNT(CASE WHEN event_type = 'promotion' THEN 1 END) > 0 AS has_promotion,

            -- Merit/raise events
            MAX(CASE WHEN event_type = 'raise' THEN compensation_amount END) AS merit_salary,
            COUNT(CASE WHEN event_type = 'raise' THEN 1 END) > 0 AS has_merit,

            -- Enrollment events
            MAX(CASE WHEN event_type = 'enrollment' THEN effective_date END) AS enrollment_date,
            MAX(CASE WHEN event_type = 'enrollment' THEN event_details END) AS enrollment_details,
            MAX(CASE WHEN event_type = 'enrollment' THEN employee_deferral_rate END) AS enrollment_deferral_rate,
            COUNT(CASE WHEN event_type = 'enrollment' THEN 1 END) > 0 AS has_enrollment,

            -- Enrollment change events
            MAX(CASE WHEN event_type = 'enrollment_change' THEN employee_deferral_rate END) AS changed_deferral_rate,
            COUNT(CASE WHEN event_type = 'enrollment_change' THEN 1 END) > 0 AS has_enrollment_change
        FROM {{ ref('fct_yearly_events') }}
        WHERE simulation_year = {{ simulation_year }}
          AND employee_id IS NOT NULL
        GROUP BY employee_id
    ) ec ON
        {% if simulation_year == start_year %}
        bw.employee_id = ec.employee_id
        {% else %}
        prev.employee_id = ec.employee_id
        {% endif %}

    UNION ALL

    -- Add new hires with consolidated event data
    SELECT
        CAST(ye.employee_id AS VARCHAR) AS employee_id,
        ye.employee_ssn,
        CAST('{{ simulation_year }}-01-01' AS DATE) - INTERVAL (ye.employee_age * 365) DAY AS employee_birth_date,
        ye.effective_date AS employee_hire_date,
        ye.compensation_amount AS employee_gross_compensation,
        ye.employee_age AS current_age,
        0 AS current_tenure,
        ye.level_id,
        NULL AS termination_date,
        'active' AS employment_status,

        -- Event data for new hires
        ec.termination_date AS event_termination_date,
        ec.termination_reason,
        ec.has_termination,
        ec.is_new_hire_termination,
        true AS is_new_hire,
        ye.effective_date AS hire_date,
        ye.compensation_amount AS hire_salary,
        ye.employee_age AS hire_age,
        ye.employee_ssn AS hire_ssn,
        ye.level_id AS hire_level_id,
        ec.has_promotion,
        ec.promotion_salary,
        ec.promotion_level_id,
        ec.has_merit,
        ec.merit_salary,
        ec.has_enrollment,
        ec.enrollment_date,
        ec.enrollment_details,
        ec.enrollment_deferral_rate,
        ec.has_enrollment_change,
        ec.changed_deferral_rate,

        'new_hire' AS record_source,
        {{ simulation_year }} AS simulation_year
    FROM {{ ref('fct_yearly_events') }} ye
    LEFT JOIN (
        -- Consolidated events (same as above, but for new hires)
        SELECT
            employee_id,
            MAX(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN effective_date END) AS termination_date,
            MAX(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN event_details END) AS termination_reason,
            COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN 1 END) > 0 AS has_termination,
            COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' AND event_category = 'new_hire_termination' THEN 1 END) > 0 AS is_new_hire_termination,
            MAX(CASE WHEN event_type = 'promotion' THEN compensation_amount END) AS promotion_salary,
            MAX(CASE WHEN event_type = 'promotion' THEN level_id END) AS promotion_level_id,
            COUNT(CASE WHEN event_type = 'promotion' THEN 1 END) > 0 AS has_promotion,
            MAX(CASE WHEN event_type = 'raise' THEN compensation_amount END) AS merit_salary,
            COUNT(CASE WHEN event_type = 'raise' THEN 1 END) > 0 AS has_merit,
            MAX(CASE WHEN event_type = 'enrollment' THEN effective_date END) AS enrollment_date,
            MAX(CASE WHEN event_type = 'enrollment' THEN event_details END) AS enrollment_details,
            MAX(CASE WHEN event_type = 'enrollment' THEN employee_deferral_rate END) AS enrollment_deferral_rate,
            COUNT(CASE WHEN event_type = 'enrollment' THEN 1 END) > 0 AS has_enrollment,
            MAX(CASE WHEN event_type = 'enrollment_change' THEN employee_deferral_rate END) AS changed_deferral_rate,
            COUNT(CASE WHEN event_type = 'enrollment_change' THEN 1 END) > 0 AS has_enrollment_change
        FROM {{ ref('fct_yearly_events') }}
        WHERE simulation_year = {{ simulation_year }}
          AND employee_id IS NOT NULL
        GROUP BY employee_id
    ) ec ON ye.employee_id = ec.employee_id
    WHERE ye.event_type = 'hire'
      AND ye.simulation_year = {{ simulation_year }}
),

-- CTE 2: Apply ALL events in single pass + deduplicate + filter invalid hires
workforce_with_all_events AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,

        -- Apply compensation events in priority order (merit > promotion > hire > base)
        CASE
            WHEN has_merit THEN merit_salary
            WHEN has_promotion THEN promotion_salary
            WHEN is_new_hire THEN hire_salary
            ELSE employee_gross_compensation
        END AS employee_gross_compensation,

        current_age,
        current_tenure,

        -- Apply level changes (promotion > hire > base, then fallback to compensation-based)
        CASE
            WHEN has_promotion THEN promotion_level_id
            WHEN is_new_hire AND hire_level_id IS NOT NULL THEN hire_level_id
            WHEN level_id IS NOT NULL THEN level_id
            ELSE COALESCE(
                (SELECT MIN(level_id)
                 FROM {{ ref('stg_config_job_levels') }} levels
                 WHERE CASE
                        WHEN has_merit THEN merit_salary
                        WHEN has_promotion THEN promotion_salary
                        WHEN is_new_hire THEN hire_salary
                        ELSE employee_gross_compensation
                       END >= levels.min_compensation
                   AND (CASE
                        WHEN has_merit THEN merit_salary
                        WHEN has_promotion THEN promotion_salary
                        WHEN is_new_hire THEN hire_salary
                        ELSE employee_gross_compensation
                       END < levels.max_compensation OR levels.max_compensation IS NULL)
                ),
                1
            )
        END AS level_id,

        -- Apply termination status
        CASE
            WHEN is_new_hire_termination THEN CAST(event_termination_date AS TIMESTAMP)
            WHEN has_termination THEN CAST(event_termination_date AS TIMESTAMP)
            ELSE CAST(termination_date AS TIMESTAMP)
        END AS termination_date,

        CASE
            WHEN is_new_hire_termination THEN 'terminated'
            WHEN has_termination THEN 'terminated'
            ELSE employment_status
        END AS employment_status,

        termination_reason,
        is_new_hire,
        has_promotion,
        has_merit,
        promotion_salary,
        merit_salary,
        hire_salary,
        record_source,
        simulation_year,

        -- Deduplicate with correct priority
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY
                CASE
                    WHEN record_source = 'new_hire' AND EXTRACT(YEAR FROM employee_hire_date) = simulation_year THEN 1
                    WHEN record_source = 'existing' THEN 2
                    ELSE 3
                END,
                employee_gross_compensation DESC,
                termination_date ASC NULLS LAST
        ) AS rn
    FROM base_workforce_and_events
    WHERE NOT (
        -- Filter invalid NH_ employees without actual hire events
        employee_id LIKE 'NH_{{ simulation_year }}_%'
        AND NOT is_new_hire
    )
),

-- CTE 3: Prorated compensation calculation (merged 5 CTEs into 1)
workforce_with_prorated_comp AS (
    SELECT
        w.*,
        COALESCE(
            -- Calculate prorated compensation based on employment period
            CASE
                -- Employees with compensation events: use period-based calculation
                WHEN EXISTS (
                    SELECT 1 FROM {{ ref('fct_yearly_events') }} ye
                    WHERE ye.employee_id = w.employee_id
                      AND ye.simulation_year = {{ simulation_year }}
                      AND ye.event_type IN ('hire', 'promotion', 'raise', 'termination')
                ) THEN (
                    -- Sum compensation periods
                    SELECT SUM(period_salary * (DATE_DIFF('day', period_start, period_end) + 1) / 365.0)
                    FROM (
                        -- Generate compensation periods
                        SELECT
                            employee_id,
                            event_date AS period_start,
                            CASE
                                WHEN next_event_type = 'termination' THEN next_event_date
                                ELSE COALESCE(next_event_date - INTERVAL 1 DAY, '{{ simulation_year }}-12-31'::DATE)
                            END AS period_end,
                            new_compensation AS period_salary
                        FROM (
                            SELECT
                                employee_id,
                                effective_date AS event_date,
                                event_type,
                                compensation_amount AS new_compensation,
                                LEAD(effective_date) OVER (
                                    PARTITION BY employee_id
                                    ORDER BY effective_date,
                                    CASE event_type
                                        WHEN 'hire' THEN 1
                                        WHEN 'promotion' THEN 2
                                        WHEN 'raise' THEN 3
                                        WHEN 'termination' THEN 4
                                    END
                                ) AS next_event_date,
                                LEAD(event_type) OVER (
                                    PARTITION BY employee_id
                                    ORDER BY effective_date,
                                    CASE event_type
                                        WHEN 'hire' THEN 1
                                        WHEN 'promotion' THEN 2
                                        WHEN 'raise' THEN 3
                                        WHEN 'termination' THEN 4
                                    END
                                ) AS next_event_type
                            FROM {{ ref('fct_yearly_events') }}
                            WHERE employee_id = w.employee_id
                              AND simulation_year = {{ simulation_year }}
                              AND event_type IN ('hire', 'promotion', 'raise', 'termination')
                        ) timeline
                        WHERE event_type IN ('hire', 'promotion', 'raise')
                          AND new_compensation IS NOT NULL
                          AND new_compensation > 0
                    ) periods
                    WHERE period_start <= period_end
                      AND period_start >= '{{ simulation_year }}-01-01'::DATE
                      AND period_end <= '{{ simulation_year }}-12-31'::DATE
                )

                -- New hire (hired this year, no other comp events)
                WHEN EXTRACT(YEAR FROM w.employee_hire_date) = {{ simulation_year }}
                THEN w.employee_gross_compensation * (DATE_DIFF('day', w.employee_hire_date, COALESCE(w.termination_date, '{{ simulation_year }}-12-31'::DATE)) + 1) / 365.0

                -- Experienced employee terminated this year
                WHEN w.employment_status = 'terminated'
                  AND w.termination_date IS NOT NULL
                  AND EXTRACT(YEAR FROM w.termination_date) = {{ simulation_year }}
                THEN w.employee_gross_compensation * (DATE_DIFF('day', '{{ simulation_year }}-01-01'::DATE, w.termination_date) + 1) / 365.0

                -- Continuous active employee (full year)
                ELSE w.employee_gross_compensation
            END,
            w.employee_gross_compensation
        ) AS prorated_annual_compensation
    FROM workforce_with_all_events w
    WHERE w.rn = 1
),

-- CTE 4: Eligibility and enrollment data
workforce_with_eligibility AS (
    SELECT
        w.*,
        ee.employee_eligibility_date,
        ee.waiting_period_days,
        ee.current_eligibility_status,
        ee.employee_enrollment_date,
        ee.is_enrolled_flag
    FROM workforce_with_prorated_comp w
    LEFT JOIN (
        {% if simulation_year == start_year %}
        -- Year 1: Baseline + accumulator
        SELECT DISTINCT
            baseline.employee_id,
            baseline.employee_eligibility_date,
            baseline.waiting_period_days,
            baseline.current_eligibility_status,
            COALESCE(accumulator.enrollment_date, baseline.employee_enrollment_date) AS employee_enrollment_date,
            CASE WHEN COALESCE(accumulator.enrollment_date, baseline.employee_enrollment_date) IS NOT NULL THEN true ELSE false END AS is_enrolled_flag
        FROM {{ ref('int_baseline_workforce') }} baseline
        LEFT JOIN (
            SELECT employee_id, enrollment_date, enrollment_status AS is_enrolled
            FROM {{ ref('int_enrollment_state_accumulator') }}
            WHERE simulation_year = {{ simulation_year }}
        ) accumulator ON baseline.employee_id = accumulator.employee_id
        WHERE baseline.employment_status = 'active'

        UNION ALL

        -- Year 1 new hires
        SELECT DISTINCT
            accumulator.employee_id,
            COALESCE(he.effective_date::DATE, accumulator.enrollment_date::DATE) AS employee_eligibility_date,
            0 AS waiting_period_days,
            'eligible' AS current_eligibility_status,
            accumulator.enrollment_date AS employee_enrollment_date,
            CASE WHEN accumulator.enrollment_date IS NOT NULL THEN true ELSE false END AS is_enrolled_flag
        FROM (
            SELECT employee_id, enrollment_date, enrollment_status AS is_enrolled
            FROM {{ ref('int_enrollment_state_accumulator') }}
            WHERE simulation_year = {{ simulation_year }}
              AND employee_id LIKE 'NH_{{ simulation_year }}_%'
        ) accumulator
        LEFT JOIN (
            SELECT employee_id, effective_date
            FROM {{ ref('fct_yearly_events') }}
            WHERE simulation_year = {{ simulation_year }} AND event_type = 'hire'
        ) he ON accumulator.employee_id = he.employee_id
        WHERE accumulator.employee_id NOT IN (
            SELECT employee_id FROM {{ ref('int_baseline_workforce') }} WHERE employment_status = 'active'
        )
        {% else %}
        -- Subsequent years: events + baseline fallback + accumulator
        SELECT DISTINCT
            fwc.employee_id AS employee_id,
            COALESCE(events.employee_eligibility_date, baseline.employee_eligibility_date) AS employee_eligibility_date,
            COALESCE(events.waiting_period_days, baseline.waiting_period_days) AS waiting_period_days,
            COALESCE(events.current_eligibility_status, baseline.current_eligibility_status) AS current_eligibility_status,
            COALESCE(accumulator.enrollment_date, baseline.employee_enrollment_date) AS employee_enrollment_date,
            CASE WHEN COALESCE(accumulator.enrollment_date, baseline.employee_enrollment_date) IS NOT NULL THEN true ELSE false END AS is_enrolled_flag
        FROM workforce_with_prorated_comp fwc
        LEFT JOIN (
            SELECT DISTINCT
                employee_id,
                JSON_EXTRACT_STRING(event_details, '$.eligibility_date')::DATE AS employee_eligibility_date,
                JSON_EXTRACT(event_details, '$.waiting_period_days')::INT AS waiting_period_days,
                CASE
                    WHEN JSON_EXTRACT_STRING(event_details, '$.eligibility_date')::DATE <= '{{ simulation_year }}-12-31'::DATE THEN 'eligible'
                    ELSE 'pending'
                END AS current_eligibility_status
            FROM {{ ref('fct_yearly_events') }}
            WHERE event_type = 'eligibility'
              AND JSON_EXTRACT_STRING(event_details, '$.determination_type') = 'initial'
              AND simulation_year IN (
                  SELECT MAX(simulation_year)
                  FROM {{ ref('fct_yearly_events') }} ey
                  WHERE ey.event_type = 'eligibility'
                    AND ey.employee_id = fct_yearly_events.employee_id
                    AND ey.simulation_year <= {{ simulation_year }}
              )
        ) events ON fwc.employee_id = events.employee_id
        LEFT JOIN (
            SELECT employee_id, employee_eligibility_date, waiting_period_days, current_eligibility_status, employee_enrollment_date
            FROM {{ ref('int_baseline_workforce') }}
            WHERE employment_status = 'active'
        ) baseline ON fwc.employee_id = baseline.employee_id
        LEFT JOIN (
            SELECT employee_id, enrollment_date, enrollment_status AS is_enrolled
            FROM {{ ref('int_enrollment_state_accumulator') }}
            WHERE simulation_year = {{ simulation_year }}
        ) accumulator ON fwc.employee_id = accumulator.employee_id
        {% endif %}
    ) ee ON w.employee_id = ee.employee_id
),

-- CTE 5: Materialized baseline comparison (replace 5 correlated subqueries!)
baseline_comparison AS (
    SELECT
        employee_id,
        current_compensation AS baseline_compensation
    FROM {{ ref('int_baseline_workforce') }}
    WHERE simulation_year = {{ var('simulation_year') }}
),

-- CTE 6: Add contributions, accumulators, and all calculated fields
workforce_enriched AS (
    SELECT
        w.employee_id,
        w.employee_ssn,
        w.employee_birth_date,
        w.employee_hire_date,

        -- Compensation fields
        CASE WHEN w.employee_gross_compensation IS NULL OR w.employee_gross_compensation <= 0 THEN 50000 ELSE w.employee_gross_compensation END AS current_compensation,
        CASE WHEN w.prorated_annual_compensation IS NULL OR w.prorated_annual_compensation <= 0 THEN 50000 ELSE w.prorated_annual_compensation END AS prorated_annual_compensation,

        -- Full-year equivalent compensation
        CASE
            WHEN w.has_merit THEN CASE WHEN w.merit_salary <= 0 THEN w.employee_gross_compensation ELSE w.merit_salary END
            WHEN w.has_promotion THEN CASE WHEN w.promotion_salary <= 0 THEN w.employee_gross_compensation ELSE w.promotion_salary END
            WHEN EXTRACT(YEAR FROM w.employee_hire_date) = w.simulation_year THEN w.employee_gross_compensation
            ELSE w.employee_gross_compensation
        END AS full_year_equivalent_compensation,

        -- Demographics
        w.current_age,
        w.current_tenure,
        w.level_id,
        CASE
            WHEN w.current_age < 25 THEN '< 25'
            WHEN w.current_age < 35 THEN '25-34'
            WHEN w.current_age < 45 THEN '35-44'
            WHEN w.current_age < 55 THEN '45-54'
            WHEN w.current_age < 65 THEN '55-64'
            ELSE '65+'
        END AS age_band,
        CASE
            WHEN w.current_tenure < 2 THEN '< 2'
            WHEN w.current_tenure < 5 THEN '2-4'
            WHEN w.current_tenure < 10 THEN '5-9'
            WHEN w.current_tenure < 20 THEN '10-19'
            ELSE '20+'
        END AS tenure_band,

        -- Employment status
        w.employment_status,
        w.termination_date,
        w.termination_reason,
        CASE
            WHEN w.is_new_hire AND w.employment_status = 'active' THEN 'new_hire_active'
            WHEN w.is_new_hire AND w.employment_status = 'terminated' THEN 'new_hire_termination'
            WHEN w.employment_status = 'active' AND EXTRACT(YEAR FROM w.employee_hire_date) < w.simulation_year THEN 'continuous_active'
            WHEN w.employment_status = 'terminated' AND EXTRACT(YEAR FROM w.employee_hire_date) < w.simulation_year THEN 'experienced_termination'
            WHEN w.employment_status IS NULL THEN 'continuous_active'
            WHEN w.employee_hire_date IS NULL THEN 'continuous_active'
            ELSE 'continuous_active'
        END AS detailed_status_code,

        w.simulation_year,

        -- Eligibility
        w.employee_eligibility_date,
        w.waiting_period_days,
        w.current_eligibility_status,
        w.employee_enrollment_date,
        w.is_enrolled_flag,

        -- Deferral rates
        COALESCE(dsa.current_deferral_rate, 0.00) AS current_deferral_rate,
        CASE
            WHEN COALESCE(dsa.current_deferral_rate, 0.00) > 0 THEN 'participating'
            ELSE 'not_participating'
        END AS participation_status,
        CASE
            WHEN COALESCE(dsa.current_deferral_rate, 0.00) > 0 THEN
                CASE
                    WHEN esa.enrollment_method = 'auto' THEN 'participating - auto enrollment'
                    WHEN esa.enrollment_method = 'voluntary' THEN 'participating - voluntary enrollment'
                    WHEN esa.enrollment_method IS NULL THEN 'participating - census enrollment'
                    ELSE 'participating - voluntary enrollment'
                END
            ELSE
                CASE
                    WHEN COALESCE(esa.ever_opted_out, false) = true THEN 'not_participating - opted out of AE'
                    WHEN COALESCE(esa.ever_unenrolled, false) = true THEN 'not_participating - proactively unenrolled'
                    ELSE 'not_participating - not auto enrolled'
                END
        END AS participation_status_detail,

        -- Escalation tracking
        COALESCE(dsa.escalations_received, 0) AS total_deferral_escalations,
        dsa.last_escalation_date,
        COALESCE(dsa.has_escalations, false) AS has_deferral_escalations,
        COALESCE(dsa.original_deferral_rate, 0.00) AS original_deferral_rate,
        COALESCE(dsa.total_escalation_amount, 0.00) AS total_escalation_amount,

        -- Contributions
        COALESCE(contrib.annual_contribution_amount, 0.0) AS prorated_annual_contributions,
        COALESCE(contrib.annual_contribution_amount * 0.85, 0.0) AS pre_tax_contributions,
        COALESCE(contrib.annual_contribution_amount * 0.15, 0.0) AS roth_contributions,
        COALESCE(contrib.annual_contribution_amount, 0.0) AS ytd_contributions,
        CASE
            WHEN COALESCE(contrib.annual_contribution_amount, 0.0) >= CASE WHEN w.current_age >= 50 THEN 31000 ELSE 23500 END
            THEN true ELSE false
        END AS irs_limit_reached,
        contrib.effective_annual_deferral_rate,
        contrib.total_contribution_base_compensation,
        contrib.first_contribution_date,
        contrib.last_contribution_date,
        contrib.contribution_quality_flag,

        -- Employer contributions
        COALESCE(match_calc.employer_match_amount, 0.0) AS employer_match_amount,
        COALESCE(core_contrib.employer_core_amount, 0.0) AS employer_core_amount,
        COALESCE(match_calc.employer_match_amount, 0.0) + COALESCE(core_contrib.employer_core_amount, 0.0) AS total_employer_contributions,
        COALESCE(eligibility.annual_hours_worked, 0) AS annual_hours_worked,

        -- Quality flags (using materialized baseline comparison!)
        CASE
            WHEN w.employee_gross_compensation > 50000000 THEN 'CRITICAL_OVER_50M'
            WHEN w.employee_gross_compensation > 20000000 THEN 'CRITICAL_OVER_20M'
            WHEN w.employee_gross_compensation > 10000000 THEN 'CRITICAL_OVER_10M'
            WHEN w.employee_gross_compensation > 5000000 THEN 'SEVERE_OVER_5M'
            WHEN w.employee_gross_compensation > 2000000 THEN
                CASE
                    WHEN EXTRACT(YEAR FROM w.employee_hire_date) = w.simulation_year
                         AND w.employee_hire_date >= (w.simulation_year || '-11-01')::DATE
                    THEN 'WARNING_ANNUALIZED_LATE_HIRE'
                    ELSE 'WARNING_OVER_2M'
                END
            WHEN w.employee_gross_compensation < 10000 AND w.employment_status = 'active' THEN 'WARNING_UNDER_10K'
            WHEN bc.baseline_compensation > 0 AND (w.employee_gross_compensation / bc.baseline_compensation) > 100.0 THEN 'CRITICAL_INFLATION_100X'
            WHEN bc.baseline_compensation > 0 AND (w.employee_gross_compensation / bc.baseline_compensation) > 50.0 THEN 'CRITICAL_INFLATION_50X'
            WHEN bc.baseline_compensation > 0 AND (w.employee_gross_compensation / bc.baseline_compensation) > 10.0 THEN 'SEVERE_INFLATION_10X'
            WHEN bc.baseline_compensation > 0 AND (w.employee_gross_compensation / bc.baseline_compensation) > 5.0 THEN 'WARNING_INFLATION_5X'
            ELSE 'NORMAL'
        END AS compensation_quality_flag,

        CURRENT_TIMESTAMP AS snapshot_created_at
    FROM workforce_with_eligibility w
    LEFT JOIN baseline_comparison bc ON w.employee_id = bc.employee_id
    LEFT JOIN {{ ref('int_deferral_rate_state_accumulator_v2') }} dsa
        ON w.employee_id = dsa.employee_id AND dsa.simulation_year = w.simulation_year
    LEFT JOIN {{ ref('int_enrollment_state_accumulator') }} esa
        ON w.employee_id = esa.employee_id AND esa.simulation_year = w.simulation_year
    LEFT JOIN {{ ref('int_employee_contributions') }} contrib
        ON w.employee_id = contrib.employee_id AND contrib.simulation_year = w.simulation_year
    LEFT JOIN {{ ref('int_employee_match_calculations') }} match_calc
        ON w.employee_id = match_calc.employee_id AND match_calc.simulation_year = w.simulation_year
    LEFT JOIN {{ ref('int_employer_core_contributions') }} core_contrib
        ON w.employee_id = core_contrib.employee_id AND core_contrib.simulation_year = w.simulation_year
    LEFT JOIN {{ ref('int_employer_eligibility') }} eligibility
        ON w.employee_id = eligibility.employee_id AND eligibility.simulation_year = w.simulation_year
),

-- CTE 7: Final deduplication and output
final_deduped AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY employee_id, simulation_year ORDER BY employee_id) AS rn
    FROM workforce_enriched
    {% if is_incremental() %}
    WHERE simulation_year = {{ simulation_year }}
    {% endif %}
)

SELECT
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    current_compensation,
    prorated_annual_compensation,
    full_year_equivalent_compensation,
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
    employee_eligibility_date,
    waiting_period_days,
    current_eligibility_status,
    employee_enrollment_date,
    is_enrolled_flag,
    current_deferral_rate,
    participation_status,
    participation_status_detail,
    total_deferral_escalations,
    last_escalation_date,
    has_deferral_escalations,
    original_deferral_rate,
    total_escalation_amount,
    prorated_annual_contributions,
    pre_tax_contributions,
    roth_contributions,
    ytd_contributions,
    irs_limit_reached,
    effective_annual_deferral_rate,
    total_contribution_base_compensation,
    first_contribution_date,
    last_contribution_date,
    contribution_quality_flag,
    compensation_quality_flag,
    employer_match_amount,
    employer_core_amount,
    total_employer_contributions,
    annual_hours_worked,
    snapshot_created_at
FROM final_deduped
WHERE rn = 1
