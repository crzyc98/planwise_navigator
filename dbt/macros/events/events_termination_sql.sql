{% macro events_termination_sql(cohort_table, simulation_year) %}
  {#-
    Generate termination events for E068A fused event generation

    This macro extracts termination event logic from int_termination_events.sql
    and int_new_hire_termination_events.sql and optimizes it for in-memory
    CTE processing within the fused fct_yearly_events model.

    Parameters:
    - cohort_table: CTE name containing cohort data with RNG values
    - simulation_year: Current simulation year

    Returns: SQL for termination events CTE (both experienced and new hire)
  #}

  WITH workforce_needs AS (
    -- Get termination targets from centralized workforce planning
    SELECT
      workforce_needs_id,
      scenario_id,
      simulation_year,
      expected_experienced_terminations,
      experienced_termination_rate,
      starting_experienced_count,
      expected_new_hire_terminations,
      new_hire_termination_rate
    FROM {{ ref('int_workforce_needs') }}
    WHERE simulation_year = {{ simulation_year }}
      AND scenario_id = '{{ var('scenario_id', 'default') }}'
  ),

  active_workforce AS (
    -- Use consistent data source with other event models
    -- Exclude current-year new hires for experienced terminations
    SELECT
      employee_id,
      employee_ssn,
      employee_hire_date,
      employee_compensation AS employee_gross_compensation,
      current_age,
      current_tenure,
      level_id,
      CASE
        WHEN employee_hire_date < CAST('{{ simulation_year }}-01-01' AS DATE) THEN 'experienced'
        ELSE 'new_hire'
      END AS employee_type
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
      AND employment_status = 'active'
  ),

  workforce_with_bands AS (
    SELECT
      *,
      -- Age bands for hazard lookup
      {{ assign_age_band('current_age') }} AS age_band,
      -- Tenure bands for hazard lookup
      {{ assign_tenure_band('current_tenure') }} AS tenure_band,
      -- Use hash_rng for deterministic random generation
      {{ hash_rng('employee_id', simulation_year, 'termination') }} AS random_value
    FROM active_workforce
  ),

  -- Experienced employee terminations
  experienced_termination_candidates AS (
    SELECT
      w.*,
      wn.experienced_termination_rate AS termination_rate
    FROM workforce_with_bands w
    CROSS JOIN workforce_needs wn
    WHERE w.employee_type = 'experienced'
  ),

  final_experienced_terminations AS (
    SELECT
      w.employee_id,
      w.employee_ssn,
      'termination' AS event_type,
      {{ simulation_year }} AS simulation_year,
      (CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL ((ABS(HASH(w.employee_id)) % 365)) DAY) AS effective_date,
      CASE
        WHEN w.random_value < w.termination_rate THEN 'hazard_termination'
        ELSE 'gap_filling_termination'
      END AS termination_reason,
      w.employee_gross_compensation AS final_compensation,
      w.current_age,
      w.current_tenure,
      w.level_id,
      w.age_band,
      w.tenure_band,
      w.termination_rate AS event_probability,
      'experienced_termination' AS event_category
    FROM experienced_termination_candidates w
    QUALIFY ROW_NUMBER() OVER (
      ORDER BY
        -- Prioritize hazard-based terminations first
        CASE WHEN w.random_value < w.termination_rate THEN 0 ELSE 1 END,
        w.random_value
    ) <= (SELECT expected_experienced_terminations FROM workforce_needs)
  ),

  -- New hire terminations
  new_hire_termination_candidates AS (
    SELECT
      w.*,
      wn.new_hire_termination_rate AS termination_rate
    FROM workforce_with_bands w
    CROSS JOIN workforce_needs wn
    WHERE w.employee_type = 'new_hire'
  ),

  final_new_hire_terminations AS (
    SELECT
      w.employee_id,
      w.employee_ssn,
      'termination' AS event_type,
      {{ simulation_year }} AS simulation_year,
      (CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL ((ABS(HASH(w.employee_id || 'new_hire')) % 365)) DAY) AS effective_date,
      CASE
        WHEN w.random_value < w.termination_rate THEN 'new_hire_hazard_termination'
        ELSE 'new_hire_gap_filling_termination'
      END AS termination_reason,
      w.employee_gross_compensation AS final_compensation,
      w.current_age,
      w.current_tenure,
      w.level_id,
      w.age_band,
      w.tenure_band,
      w.termination_rate AS event_probability,
      'new_hire_termination' AS event_category
    FROM new_hire_termination_candidates w
    QUALIFY ROW_NUMBER() OVER (
      ORDER BY
        -- Prioritize hazard-based terminations first
        CASE WHEN w.random_value < w.termination_rate THEN 0 ELSE 1 END,
        w.random_value
    ) <= (SELECT expected_new_hire_terminations FROM workforce_needs)
  ),

  -- Apply deduplication to ensure one termination per employee
  all_terminations AS (
    SELECT
      employee_id,
      employee_ssn,
      event_type,
      simulation_year,
      effective_date,
      termination_reason AS event_details,
      final_compensation AS compensation_amount,
      NULL AS previous_compensation,
      NULL::decimal(5,4) AS employee_deferral_rate,
      NULL::decimal(5,4) AS prev_employee_deferral_rate,
      current_age AS employee_age,
      current_tenure AS employee_tenure,
      level_id,
      age_band,
      tenure_band,
      event_probability,
      event_category,
      1 AS priority -- Experienced terminations have priority
    FROM final_experienced_terminations

    UNION ALL

    SELECT
      employee_id,
      employee_ssn,
      event_type,
      simulation_year,
      effective_date,
      termination_reason AS event_details,
      final_compensation AS compensation_amount,
      NULL AS previous_compensation,
      NULL::decimal(5,4) AS employee_deferral_rate,
      NULL::decimal(5,4) AS prev_employee_deferral_rate,
      current_age AS employee_age,
      current_tenure AS employee_tenure,
      level_id,
      age_band,
      tenure_band,
      event_probability,
      event_category,
      2 AS priority -- New hire terminations are secondary
    FROM final_new_hire_terminations
  )

  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    event_details,
    compensation_amount,
    previous_compensation,
    employee_deferral_rate,
    prev_employee_deferral_rate,
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM all_terminations
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY employee_id, simulation_year
    ORDER BY priority, effective_date DESC
  ) = 1

{% endmacro %}
