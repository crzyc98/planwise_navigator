{{ config(
  materialized='table',
  tags=['EVENT_GENERATION', 'E068A_EPHEMERAL']
) }}

{% set simulation_year = var('simulation_year') %}
{% set start_year = var('start_year', var('simulation_year')) | int %}

-- Generate termination events using hazard-based probability selection
-- Refactored to use int_workforce_needs for termination targets

WITH workforce_needs AS (
    -- Get termination targets from centralized workforce planning
    SELECT
        workforce_needs_id,
        scenario_id,
        simulation_year,
        expected_experienced_terminations,
        experienced_termination_rate,
        starting_experienced_count
    FROM {{ ref('int_workforce_needs') }}
    WHERE simulation_year = {{ simulation_year }}
      AND scenario_id = '{{ var('scenario_id', 'default') }}'
),

active_workforce AS (
    -- Use consistent data source with other event models
    -- IMPORTANT: Exclude current-year new hires so experienced terminations
    -- are selected only from prior-year active employees. This keeps
    -- experienced terminations aligned with workforce needs targets and avoids
    -- overlap with new-hire terminations.
    SELECT
        employee_id,
        employee_ssn,
        employee_hire_date,
        employee_compensation AS employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        'experienced' AS employee_type
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
      AND employment_status = 'active'
      AND employee_hire_date < CAST('{{ simulation_year }}-01-01' AS DATE)
),

workforce_with_bands AS (
    SELECT
        *,
        -- Age bands for hazard lookup
        CASE
            WHEN current_age < 25 THEN '< 25'
            WHEN current_age < 35 THEN '25-34'
            WHEN current_age < 45 THEN '35-44'
            WHEN current_age < 55 THEN '45-54'
            WHEN current_age < 65 THEN '55-64'
            ELSE '65+'
        END AS age_band,
        -- Tenure bands for hazard lookup
        CASE
            WHEN current_tenure < 2 THEN '< 2'
            WHEN current_tenure < 5 THEN '2-4'
            WHEN current_tenure < 10 THEN '5-9'
            WHEN current_tenure < 20 THEN '10-19'
            ELSE '20+'
        END AS tenure_band
    FROM active_workforce
),


-- E077: Per-Level Termination Quotas (ADR E077-B & E077-C)
level_termination_quotas AS (
    SELECT
        level_id,
        expected_terminations AS level_quota
    FROM {{ ref('int_workforce_needs_by_level') }}
    WHERE simulation_year = {{ simulation_year }}
      AND scenario_id = '{{ var('scenario_id', 'default') }}'
),

-- E077: Deterministic selection with hash-based ranking (ADR E077-C)
workforce_with_ranking AS (
    SELECT
        w.*,
        -- Deterministic hash (no floating point)
        HASH(w.employee_id || '|' || {{ simulation_year }} || '|TERMINATION|{{ var('random_seed', 42) }}') % 1000000 AS selection_hash
    FROM workforce_with_bands w
),

-- E077: Select exactly level_quota employees per level
final_experienced_terminations AS (
    SELECT
        w.employee_id,
        w.employee_ssn,
        'termination' AS event_type,
        {{ simulation_year }} AS simulation_year,
        (CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL ((ABS(HASH(w.employee_id)) % 365)) DAY) AS effective_date,
        'deterministic_termination' AS termination_reason,
        w.employee_gross_compensation AS final_compensation,
        w.current_age,
        w.current_tenure,
        w.level_id,
        w.age_band,
        w.tenure_band,
        w.employee_type,
        lq.level_quota,
        w.selection_hash
    FROM workforce_with_ranking w
    JOIN level_termination_quotas lq ON w.level_id = lq.level_id
    -- E077: Deterministic selection with employee_id tiebreaker
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY w.level_id
        ORDER BY
            w.selection_hash,    -- Primary: deterministic hash
            w.employee_id        -- Tiebreaker: unique ID for full determinism
    ) <= lq.level_quota
),

-- E077: Return deterministic terminations with workforce planning reference
final_result AS (
  SELECT
    fet.employee_id,
    fet.employee_ssn,
    fet.event_type,
    fet.simulation_year,
    fet.effective_date,
    'Termination - ' || fet.termination_reason || ' (level: ' || fet.level_id || ', hash: ' || fet.selection_hash || ', final compensation: $' || CAST(ROUND(fet.final_compensation, 0) AS VARCHAR) || ')' AS event_details,
    fet.final_compensation AS compensation_amount,
    fet.final_compensation AS previous_compensation,
    NULL::DECIMAL(5,4) AS employee_deferral_rate,
    NULL::DECIMAL(5,4) AS prev_employee_deferral_rate,
    fet.current_age AS employee_age,
    fet.current_tenure AS employee_tenure,
    fet.level_id,
    fet.age_band,
    fet.tenure_band,
    NULL AS event_probability,  -- E077: No probability, deterministic selection
    'termination' AS event_category
  FROM final_experienced_terminations fet
  CROSS JOIN workforce_needs wn
)

SELECT * FROM final_result
