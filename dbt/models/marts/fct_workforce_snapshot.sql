{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key="employee_id || '_' || simulation_year",
    on_schema_change='sync_all_columns',
    tags=['STATE_ACCUMULATION']
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

-- **E079 PHASE 2A**: Flattened workforce snapshot (27 CTEs → 8 CTEs)
-- Performance optimization: eliminated redundant scans and sequential event processing
--
-- Key consolidations:
--   1. Merged base_workforce + employee_events_consolidated + all event applications into workforce_with_all_events (CTE 1-2)
--   2. Materialized prorated compensation periods separately to avoid correlated subqueries (CTE 3-4)
--   3. Materialized baseline comparison to replace 5 correlated subqueries in quality flags (CTE 5)
--   4. Single enrichment CTE with all joins (CTE 6-7)
--   5. Final deduplication (CTE 8)

WITH
-- CTE 1: Consolidated events from fct_yearly_events
consolidated_events AS (
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
),

-- CTE 2: Workforce with ALL events applied in single pass + new hires + deduplication
workforce_with_all_events AS (
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
        is_new_hire,
        has_promotion,
        has_merit,
        promotion_salary,
        merit_salary,
        hire_salary,
        simulation_year
    FROM (
        SELECT
            COALESCE(bw.employee_id, nh.employee_id) AS employee_id,
            COALESCE(bw.employee_ssn, nh.employee_ssn) AS employee_ssn,
            COALESCE(bw.employee_birth_date, nh.employee_birth_date) AS employee_birth_date,
            COALESCE(bw.employee_hire_date, nh.employee_hire_date) AS employee_hire_date,

            -- Apply compensation events in priority order
            CASE
                WHEN ec.has_merit THEN ec.merit_salary
                WHEN ec.has_promotion THEN ec.promotion_salary
                WHEN nh.employee_id IS NOT NULL THEN nh.hire_compensation
                ELSE bw.employee_gross_compensation
            END AS employee_gross_compensation,

            COALESCE(bw.current_age, nh.current_age) AS current_age,
            COALESCE(bw.current_tenure, 0) AS current_tenure,

            -- Apply level changes
            CASE
                WHEN ec.has_promotion THEN ec.promotion_level_id
                WHEN nh.employee_id IS NOT NULL AND nh.hire_level_id IS NOT NULL THEN nh.hire_level_id
                WHEN bw.level_id IS NOT NULL THEN bw.level_id
                ELSE 1
            END AS level_id,

            -- Apply termination status
            CASE
                WHEN ec.is_new_hire_termination THEN CAST(ec.termination_date AS TIMESTAMP)
                WHEN ec.has_termination THEN CAST(ec.termination_date AS TIMESTAMP)
                ELSE CAST(bw.termination_date AS TIMESTAMP)
            END AS termination_date,

            CASE
                WHEN ec.is_new_hire_termination THEN 'terminated'
                WHEN ec.has_termination THEN 'terminated'
                ELSE COALESCE(bw.employment_status, 'active')
            END AS employment_status,

            ec.termination_reason,
            COALESCE(ec.is_new_hire, false) AS is_new_hire,
            COALESCE(ec.has_promotion, false) AS has_promotion,
            COALESCE(ec.has_merit, false) AS has_merit,
            ec.promotion_salary,
            ec.merit_salary,
            nh.hire_compensation AS hire_salary,
            {{ simulation_year }} AS simulation_year,

            -- Deduplicate with correct priority
            ROW_NUMBER() OVER (
                PARTITION BY COALESCE(bw.employee_id, nh.employee_id)
                ORDER BY
                    CASE
                        WHEN nh.employee_id IS NOT NULL THEN 1
                        WHEN bw.employee_id IS NOT NULL THEN 2
                        ELSE 3
                    END,
                    COALESCE(bw.employee_gross_compensation, nh.hire_compensation, 0) DESC
            ) AS rn
        FROM (
            {% if simulation_year == start_year %}
            SELECT
                employee_id, employee_ssn, employee_birth_date, employee_hire_date,
                current_compensation AS employee_gross_compensation,
                current_age, current_tenure, level_id, termination_date, employment_status
            FROM {{ ref('int_baseline_workforce') }}
            {% else %}
            SELECT
                employee_id, employee_ssn, employee_birth_date, employee_hire_date,
                employee_gross_compensation, current_age, current_tenure, level_id,
                termination_date, employment_status
            FROM {{ ref('int_active_employees_prev_year_snapshot') }}
            WHERE simulation_year = {{ simulation_year }}
            {% endif %}
        ) bw
        FULL OUTER JOIN consolidated_events ec ON bw.employee_id = ec.employee_id
        FULL OUTER JOIN (
            SELECT
                CAST(employee_id AS VARCHAR) AS employee_id,
                employee_ssn,
                CAST('{{ simulation_year }}-01-01' AS DATE) - INTERVAL (employee_age * 365) DAY AS employee_birth_date,
                effective_date AS employee_hire_date,
                compensation_amount AS hire_compensation,
                employee_age AS current_age,
                level_id AS hire_level_id
            FROM {{ ref('fct_yearly_events') }}
            WHERE event_type = 'hire' AND simulation_year = {{ simulation_year }}
        ) nh ON bw.employee_id = nh.employee_id OR (bw.employee_id IS NULL AND ec.employee_id = nh.employee_id)
        WHERE NOT (
            COALESCE(bw.employee_id, nh.employee_id) LIKE 'NH_{{ simulation_year }}_%'
            AND ec.is_new_hire IS NOT TRUE
        )
    ) unioned
    WHERE rn = 1
),

-- CTE 3: Prorated compensation periods (materialized to avoid correlated subqueries)
prorated_comp_periods AS (
    SELECT
        ye.employee_id,
        SUM(
            ye.compensation_amount * (DATE_DIFF('day', ye.period_start, ye.period_end) + 1) / 365.0
        ) AS prorated_annual_compensation
    FROM (
        SELECT
            employee_id,
            event_date AS period_start,
            CASE
                WHEN next_event_type = 'termination' THEN next_event_date
                ELSE COALESCE(next_event_date - INTERVAL 1 DAY, '{{ simulation_year }}-12-31'::DATE)
            END AS period_end,
            new_compensation AS compensation_amount
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
            WHERE simulation_year = {{ simulation_year }}
              AND event_type IN ('hire', 'promotion', 'raise', 'termination')
        ) timeline
        WHERE event_type IN ('hire', 'promotion', 'raise')
          AND new_compensation IS NOT NULL
          AND new_compensation > 0
    ) ye
    WHERE period_start <= period_end
      AND period_start >= '{{ simulation_year }}-01-01'::DATE
      AND period_end <= '{{ simulation_year }}-12-31'::DATE
      AND DATE_DIFF('day', period_start, period_end) >= 0
    GROUP BY ye.employee_id
),

-- CTE 4: Workforce with prorated compensation
workforce_with_prorated_comp AS (
    SELECT
        w.*,
        COALESCE(
            pcp.prorated_annual_compensation,
            -- Simple fallback calculation for employees without events
            CASE
                WHEN EXTRACT(YEAR FROM w.employee_hire_date) = {{ simulation_year }}
                THEN w.employee_gross_compensation * (DATE_DIFF('day', w.employee_hire_date, COALESCE(w.termination_date, '{{ simulation_year }}-12-31'::DATE)) + 1) / 365.0
                WHEN w.employment_status = 'terminated' AND w.termination_date IS NOT NULL AND EXTRACT(YEAR FROM w.termination_date) = {{ simulation_year }}
                THEN w.employee_gross_compensation * (DATE_DIFF('day', '{{ simulation_year }}-01-01'::DATE, w.termination_date) + 1) / 365.0
                ELSE w.employee_gross_compensation
            END
        ) AS prorated_annual_compensation
    FROM workforce_with_all_events w
    LEFT JOIN prorated_comp_periods pcp ON w.employee_id = pcp.employee_id
),

-- CTE 5: Eligibility data
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
        SELECT DISTINCT
            baseline.employee_id,
            baseline.employee_eligibility_date,
            baseline.waiting_period_days,
            baseline.current_eligibility_status,
            COALESCE(accumulator.enrollment_date, baseline.employee_enrollment_date) AS employee_enrollment_date,
            CASE WHEN COALESCE(accumulator.enrollment_date, baseline.employee_enrollment_date) IS NOT NULL THEN true ELSE false END AS is_enrolled_flag
        FROM {{ ref('int_baseline_workforce') }} baseline
        LEFT JOIN (
            SELECT employee_id, enrollment_date
            FROM {{ ref('int_enrollment_state_accumulator') }}
            WHERE simulation_year = {{ simulation_year }}
        ) accumulator ON baseline.employee_id = accumulator.employee_id
        WHERE baseline.employment_status = 'active'
        {% else %}
        SELECT DISTINCT
            w.employee_id,
            COALESCE(events.employee_eligibility_date, baseline.employee_eligibility_date) AS employee_eligibility_date,
            COALESCE(events.waiting_period_days, baseline.waiting_period_days) AS waiting_period_days,
            COALESCE(events.current_eligibility_status, baseline.current_eligibility_status) AS current_eligibility_status,
            COALESCE(accumulator.enrollment_date, baseline.employee_enrollment_date) AS employee_enrollment_date,
            CASE WHEN COALESCE(accumulator.enrollment_date, baseline.employee_enrollment_date) IS NOT NULL THEN true ELSE false END AS is_enrolled_flag
        FROM workforce_with_prorated_comp w
        LEFT JOIN (
            SELECT DISTINCT employee_id, JSON_EXTRACT_STRING(event_details, '$.eligibility_date')::DATE AS employee_eligibility_date,
                   JSON_EXTRACT(event_details, '$.waiting_period_days')::INT AS waiting_period_days,
                   'eligible' AS current_eligibility_status
            FROM {{ ref('fct_yearly_events') }}
            WHERE event_type = 'eligibility' AND simulation_year <= {{ simulation_year }}
        ) events ON w.employee_id = events.employee_id
        LEFT JOIN {{ ref('int_baseline_workforce') }} baseline ON w.employee_id = baseline.employee_id
        LEFT JOIN (
            SELECT employee_id, enrollment_date
            FROM {{ ref('int_enrollment_state_accumulator') }}
            WHERE simulation_year = {{ simulation_year }}
        ) accumulator ON w.employee_id = accumulator.employee_id
        {% endif %}
    ) ee ON w.employee_id = ee.employee_id
),

-- CTE 6: Materialized baseline comparison (replaces 5 correlated subqueries in quality flags!)
baseline_comparison AS (
    SELECT employee_id, current_compensation AS baseline_compensation
    FROM {{ ref('int_baseline_workforce') }}
    WHERE simulation_year = {{ var('simulation_year') }}
),

-- CTE 7: Enriched workforce with all joins and calculated fields
workforce_enriched AS (
    SELECT
        w.employee_id,
        w.employee_ssn,
        w.employee_birth_date,
        w.employee_hire_date,
        CASE WHEN w.employee_gross_compensation IS NULL OR w.employee_gross_compensation <= 0 THEN 50000 ELSE w.employee_gross_compensation END AS current_compensation,
        CASE WHEN w.prorated_annual_compensation IS NULL OR w.prorated_annual_compensation <= 0 THEN 50000 ELSE w.prorated_annual_compensation END AS prorated_annual_compensation,
        CASE
            WHEN w.has_merit THEN CASE WHEN w.merit_salary <= 0 THEN w.employee_gross_compensation ELSE w.merit_salary END
            WHEN w.has_promotion THEN CASE WHEN w.promotion_salary <= 0 THEN w.employee_gross_compensation ELSE w.promotion_salary END
            WHEN EXTRACT(YEAR FROM w.employee_hire_date) = w.simulation_year THEN w.employee_gross_compensation
            ELSE w.employee_gross_compensation
        END AS full_year_equivalent_compensation,
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
        w.employment_status,
        w.termination_date,
        w.termination_reason,
        CASE
            WHEN w.is_new_hire AND w.employment_status = 'active' THEN 'new_hire_active'
            WHEN w.is_new_hire AND w.employment_status = 'terminated' THEN 'new_hire_termination'
            WHEN w.employment_status = 'active' AND EXTRACT(YEAR FROM w.employee_hire_date) < w.simulation_year THEN 'continuous_active'
            WHEN w.employment_status = 'terminated' AND EXTRACT(YEAR FROM w.employee_hire_date) < w.simulation_year THEN 'experienced_termination'
            ELSE 'continuous_active'
        END AS detailed_status_code,
        w.simulation_year,
        w.employee_eligibility_date,
        w.waiting_period_days,
        w.current_eligibility_status,
        w.employee_enrollment_date,
        w.is_enrolled_flag,
        COALESCE(dsa.current_deferral_rate, 0.00) AS current_deferral_rate,
        CASE WHEN COALESCE(dsa.current_deferral_rate, 0.00) > 0 THEN 'participating' ELSE 'not_participating' END AS participation_status,
        CASE
            WHEN COALESCE(dsa.current_deferral_rate, 0.00) > 0 THEN
                CASE
                    WHEN esa.enrollment_method = 'auto' THEN 'participating - auto enrollment'
                    WHEN esa.enrollment_method = 'voluntary' THEN 'participating - voluntary enrollment'
                    ELSE 'participating - census enrollment'
                END
            ELSE
                CASE
                    WHEN COALESCE(esa.ever_opted_out, false) = true THEN 'not_participating - opted out of AE'
                    WHEN COALESCE(esa.ever_unenrolled, false) = true THEN 'not_participating - proactively unenrolled'
                    ELSE 'not_participating - not auto enrolled'
                END
        END AS participation_status_detail,
        COALESCE(dsa.escalations_received, 0) AS total_deferral_escalations,
        dsa.last_escalation_date,
        COALESCE(dsa.has_escalations, false) AS has_deferral_escalations,
        COALESCE(dsa.original_deferral_rate, 0.00) AS original_deferral_rate,
        COALESCE(dsa.total_escalation_amount, 0.00) AS total_escalation_amount,
        COALESCE(contrib.annual_contribution_amount, 0.0) AS prorated_annual_contributions,
        COALESCE(contrib.annual_contribution_amount * 0.85, 0.0) AS pre_tax_contributions,
        COALESCE(contrib.annual_contribution_amount * 0.15, 0.0) AS roth_contributions,
        COALESCE(contrib.annual_contribution_amount, 0.0) AS ytd_contributions,
        CASE WHEN COALESCE(contrib.annual_contribution_amount, 0.0) >= CASE WHEN w.current_age >= 50 THEN 31000 ELSE 23500 END THEN true ELSE false END AS irs_limit_reached,
        contrib.effective_annual_deferral_rate,
        contrib.total_contribution_base_compensation,
        contrib.first_contribution_date,
        contrib.last_contribution_date,
        contrib.contribution_quality_flag,
        COALESCE(match_calc.employer_match_amount, 0.0) AS employer_match_amount,
        COALESCE(core_contrib.employer_core_amount, 0.0) AS employer_core_amount,
        COALESCE(match_calc.employer_match_amount, 0.0) + COALESCE(core_contrib.employer_core_amount, 0.0) AS total_employer_contributions,
        COALESCE(eligibility.annual_hours_worked, 0) AS annual_hours_worked,
        CASE
            WHEN w.employee_gross_compensation > 50000000 THEN 'CRITICAL_OVER_50M'
            WHEN w.employee_gross_compensation > 20000000 THEN 'CRITICAL_OVER_20M'
            WHEN w.employee_gross_compensation > 10000000 THEN 'CRITICAL_OVER_10M'
            WHEN w.employee_gross_compensation > 5000000 THEN 'SEVERE_OVER_5M'
            WHEN w.employee_gross_compensation > 2000000 THEN
                CASE
                    WHEN EXTRACT(YEAR FROM w.employee_hire_date) = w.simulation_year AND w.employee_hire_date >= (w.simulation_year || '-11-01')::DATE
                    THEN 'WARNING_ANNUALIZED_LATE_HIRE' ELSE 'WARNING_OVER_2M'
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

-- CTE 8: Final deduplication
final_deduped AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY employee_id, simulation_year ORDER BY employee_id) AS rn
    FROM workforce_enriched
    {% if is_incremental() %}
    WHERE simulation_year = {{ simulation_year }}
    {% endif %}
)

SELECT
    employee_id, employee_ssn, employee_birth_date, employee_hire_date, current_compensation,
    prorated_annual_compensation, full_year_equivalent_compensation, current_age, current_tenure,
    level_id, age_band, tenure_band, employment_status, termination_date, termination_reason,
    detailed_status_code, simulation_year, employee_eligibility_date, waiting_period_days,
    current_eligibility_status, employee_enrollment_date, is_enrolled_flag, current_deferral_rate,
    participation_status, participation_status_detail, total_deferral_escalations, last_escalation_date,
    has_deferral_escalations, original_deferral_rate, total_escalation_amount, prorated_annual_contributions,
    pre_tax_contributions, roth_contributions, ytd_contributions, irs_limit_reached,
    effective_annual_deferral_rate, total_contribution_base_compensation, first_contribution_date,
    last_contribution_date, contribution_quality_flag, compensation_quality_flag, employer_match_amount,
    employer_core_amount, total_employer_contributions, annual_hours_worked, snapshot_created_at
FROM final_deduped
WHERE rn = 1
