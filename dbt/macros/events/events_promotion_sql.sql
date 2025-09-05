{% macro events_promotion_sql(cohort_table, simulation_year) %}
  {#-
    Generate promotion events for E068A fused event generation

    This macro extracts promotion event logic from int_promotion_events.sql
    and optimizes it for in-memory CTE processing within the fused
    fct_yearly_events model.

    Parameters:
    - cohort_table: CTE name containing cohort data with RNG values
    - simulation_year: Current simulation year

    Returns: SQL for promotion events CTE
  #}

  {% set previous_year = simulation_year - 1 %}

  -- Epic E059: Configurable promotion compensation variables
  {% set base_increase = var('promotion_base_increase_pct', 0.20) %}
  {% set distribution_range = var('promotion_distribution_range', 0.05) %}
  {% set max_cap_pct = var('promotion_max_cap_pct', 0.30) %}
  {% set max_cap_amount = var('promotion_max_cap_amount', 500000) %}
  {% set distribution_type = var('promotion_distribution_type', 'uniform') %}
  {% set level_overrides = var('promotion_level_overrides', {}) %}
  {% set normal_std_dev = var('promotion_normal_std_dev', 0.02) %}

  WITH current_workforce AS (
    SELECT
      employee_id,
      employee_ssn,
      employee_hire_date,
      employee_compensation AS employee_gross_compensation,
      current_age,
      current_tenure,
      level_id
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
      AND employment_status = 'active'
      -- Performance filter: Pre-filter promotion-eligible employees
      AND level_id < 5  -- Can't promote beyond max level
      AND current_tenure >= 1  -- Must have at least 1 year tenure to be promoted
      AND current_age < 65  -- Age limit for promotions
  ),

  -- Efficient band calculation with single-pass logic
  eligible_workforce AS (
    SELECT
      employee_id,
      employee_ssn,
      employee_hire_date,
      employee_gross_compensation,
      current_age,
      current_tenure,
      level_id,
      -- DuckDB optimization: Vectorized CASE expressions for band calculation
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
      -- Use hash_rng for deterministic random generation
      {{ hash_rng('employee_id', simulation_year, 'promotion') }} AS random_value
    FROM current_workforce
  ),

  -- Efficient hazard rate lookup with indexed join
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

  -- Vectorized salary calculation with business rules
  promoted_employees AS (
    SELECT
      employee_id,
      employee_ssn,
      'promotion' AS event_type,
      {{ simulation_year }} AS simulation_year,
      -- Calendar-driven: Promotions occur February 1st
      CAST('{{ simulation_year }}-02-01' AS DATE) AS effective_date,
      'Level ' || level_id || ' -> ' || (level_id + 1) AS event_details,
      level_id AS from_level,
      level_id + 1 AS to_level,
      employee_gross_compensation AS previous_salary,
      -- Configurable salary calculation: Epic E059 implementation
      ROUND(
        LEAST(
          -- Configurable percentage cap
          employee_gross_compensation * (1 + {{ max_cap_pct }}),
          -- Configurable absolute amount cap
          employee_gross_compensation + {{ max_cap_amount }},
          -- Configurable base increase with distribution, never reduce compensation
          GREATEST(
            employee_gross_compensation * (
              1 + COALESCE(
                -- Level-specific override if configured
                {% for level, rate in level_overrides.items() %}
                CASE WHEN level_id = {{ level }} THEN {{ rate }} END,
                {% endfor %}
                -- Default base rate with configurable distribution
                {{ base_increase }} +
                {% if distribution_type == 'uniform' %}
                  (((ABS(HASH(employee_id || 'promo_pct')) % 1000) / 1000.0 - 0.5) * 2 * {{ distribution_range }})
                {% elif distribution_type == 'normal' %}
                  -- Normal distribution approximation using hash-based Box-Muller
                  (SQRT(-2 * LN((ABS(HASH(employee_id || 'promo_pct1')) % 1000 + 1) / 1001.0))
                   * COS(2 * PI() * (ABS(HASH(employee_id || 'promo_pct2')) % 1000) / 1000.0)
                   * {{ normal_std_dev }})
                {% else %}
                  -- Deterministic: no distribution
                  0
                {% endif %}
              )
            ),
            employee_gross_compensation -- never reduce compensation on promotion
          )
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

  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    event_details,
    new_salary AS compensation_amount,
    previous_salary AS previous_compensation,
    NULL::decimal(5,4) AS employee_deferral_rate,
    NULL::decimal(5,4) AS prev_employee_deferral_rate,
    current_age AS employee_age,
    current_tenure AS employee_tenure,
    from_level + 1 AS level_id, -- Use promoted level_id
    age_band,
    tenure_band,
    promotion_rate AS event_probability,
    'promotion' AS event_category
  FROM promoted_employees
  ORDER BY employee_id

{% endmacro %}
