{{ config(
  materialized='ephemeral',
  tags=['EVENT_GENERATION']
) }}

{#-
  Acquired-group members (#1226), unioned into int_hiring_events.

  Each acquisition joining this year adds `headcount` hire events dated on its
  effective date, on top of organic hiring. Members resample the sponsor's
  active staff at the start of the year (with replacement, seeded hash) and
  copy age, service, level, pay and scheduled hours. Prior service travels as
  employee_tenure, or starts at zero when the acquisition's service_credit is
  acquisition_date (#1227). acquisition_id marks them so new-hire-only logic
  can skip them.
-#}

{% set simulation_year = var('simulation_year') | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set joining = acquisitions_joining(simulation_year) %}

WITH donors AS (
  {% if simulation_year == start_year %}
  SELECT
    baseline.employee_id,
    baseline.current_age,
    baseline.current_tenure,
    baseline.level_id,
    baseline.current_compensation AS compensation,
    census.scheduled_hours_per_week
  FROM {{ ref('int_baseline_workforce') }} baseline
  LEFT JOIN {{ ref('stg_census_data') }} census
    ON baseline.employee_id = census.employee_id
  WHERE baseline.simulation_year = {{ simulation_year }}
    AND baseline.employment_status = 'active'
  {% else %}
  SELECT
    employee_id,
    current_age,
    current_tenure,
    level_id,
    employee_gross_compensation AS compensation,
    scheduled_hours_per_week
  FROM {{ ref('int_active_employees_prev_year_snapshot') }}
  {% endif %}
),

donor_pool AS (
  SELECT
    donors.*,
    ROW_NUMBER() OVER (ORDER BY employee_id) - 1 AS donor_index
  FROM donors
),

acquisitions AS (
  {% if joining %}
  SELECT acquisition_id, headcount, effective_date, ordinal, service_credit
  FROM (
    VALUES
    {% for item in joining %}
      ('{{ item.id }}', {{ item.headcount }}, DATE '{{ item.effective_date }}', {{ item.ordinal }}, '{{ item.service_credit }}'){% if not loop.last %},{% endif %}
    {% endfor %}
  ) AS a(acquisition_id, headcount, effective_date, ordinal, service_credit)
  {% else %}
  SELECT
    NULL::VARCHAR AS acquisition_id,
    0 AS headcount,
    NULL::DATE AS effective_date,
    0 AS ordinal,
    NULL::VARCHAR AS service_credit
  WHERE FALSE
  {% endif %}
),

member_slots AS (
  SELECT
    a.acquisition_id,
    a.effective_date,
    a.ordinal,
    a.service_credit,
    seq.i AS member_seq
  FROM acquisitions a
  CROSS JOIN UNNEST(range(1::BIGINT, CAST(a.headcount AS BIGINT) + 1)) AS seq(i)
),

-- Draw with replacement so headcount may exceed the sponsor's own staff.
draws AS (
  SELECT
    slots.*,
    -- NULL when there is nobody to draw from; the final select raises on it.
    CAST(PLANALIGN_HASH(
      slots.acquisition_id || '|' || CAST(slots.member_seq AS VARCHAR)
      || '|ACQUISITION|{{ subsystem_seed('hiring') }}'
    ) % NULLIF(pool.donor_count, 0) AS BIGINT) AS donor_index
  FROM member_slots slots
  CROSS JOIN (SELECT COUNT(*) AS donor_count FROM donors) pool
)

SELECT
  -- The guard sits in the output so no join order can skip it: an acquisition
  -- with no active staff to sample fails instead of adding nobody.
  CASE
    WHEN p.donor_index IS NULL
      THEN error('Acquisition ' || d.acquisition_id || ' has no active employees to sample members from')
    ELSE {{ acquisition_member_id('d.acquisition_id', 'd.member_seq') }}
  END AS employee_id,
  -- 910M + a 100k block per acquisition: above census SSNs (real, or the staging
  -- fallback below 900M) and above NH_ hires (900M + 100k per simulated year).
  'SSN-' || CAST(910000000 + d.ordinal * 100000 + d.member_seq AS VARCHAR) AS employee_ssn,
  'hire' AS event_type,
  {{ simulation_year }} AS simulation_year,
  d.effective_date,
  'Acquisition ' || d.acquisition_id || ' - Level ' || p.level_id || ' employee at $'
    || CAST(ROUND(p.compensation, 0) AS VARCHAR) || ' annual compensation' AS event_details,
  CAST(p.compensation AS DOUBLE) AS compensation_amount,
  NULL::DECIMAL(15,2) AS previous_compensation,
  NULL::DECIMAL(5,4) AS employee_deferral_rate,
  NULL::DECIMAL(5,4) AS prev_employee_deferral_rate,
  p.current_age AS employee_age,
  CAST(credited.tenure AS DECIMAL(12,2)) AS employee_tenure,
  p.level_id,
  {{ assign_age_band('p.current_age') }} AS age_band,
  {{ assign_tenure_band('credited.tenure') }} AS tenure_band,
  1.0 AS event_probability,
  'hire' AS event_category,
  CAST(p.scheduled_hours_per_week AS DECIMAL(5,2)) AS scheduled_hours_per_week,
  d.acquisition_id
FROM draws d
LEFT JOIN donor_pool p
  ON d.donor_index = p.donor_index
-- #1227: service the plan credits; everything reads it through current_tenure
CROSS JOIN LATERAL (
  SELECT CASE WHEN d.service_credit = 'acquisition_date' THEN 0
    ELSE p.current_tenure END AS tenure
) credited
