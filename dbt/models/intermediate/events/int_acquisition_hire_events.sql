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

  Overrides (#1228) move a group away from mirroring staff while keeping its
  spread: one pay factor per group (relative_pay, or average_pay over the
  sampled group's mean pay), and one whole-year shift each for age and service
  that moves the sampled mean to the target. Age stays at least 18 and service
  between 0 and age minus 18. Without overrides none of this is rendered.
-#}

{% set simulation_year = var('simulation_year') | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set joining = acquisitions_joining(simulation_year) %}
{% set adjust_pay = (joining | selectattr('average_pay', 'number') | list
  or joining | selectattr('relative_pay', 'number') | list) | length > 0 %}
{% set adjust_age = joining | selectattr('average_age', 'number') | list | length > 0 %}
{% set adjust_service = adjust_age
  or joining | selectattr('average_service', 'number') | list | length > 0 %}
{% set override_keys = ['average_pay', 'relative_pay', 'average_age', 'average_service'] %}

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
  SELECT acquisition_id, headcount, effective_date, ordinal, service_credit,
    average_pay, relative_pay, average_age, average_service
  FROM (
    VALUES
    {% for item in joining %}
      ('{{ item.id }}', {{ item.headcount }}, DATE '{{ item.effective_date }}', {{ item.ordinal }}, '{{ item.service_credit }}'
        {%- for key in override_keys %}, {{ item.get(key) if item.get(key) is number else 'NULL' }}::DOUBLE{% endfor %}){% if not loop.last %},{% endif %}
    {% endfor %}
  ) AS a(acquisition_id, headcount, effective_date, ordinal, service_credit,
    average_pay, relative_pay, average_age, average_service)
  {% else %}
  SELECT
    NULL::VARCHAR AS acquisition_id,
    0 AS headcount,
    NULL::DATE AS effective_date,
    0 AS ordinal,
    NULL::VARCHAR AS service_credit,
    NULL::DOUBLE AS average_pay,
    NULL::DOUBLE AS relative_pay,
    NULL::DOUBLE AS average_age,
    NULL::DOUBLE AS average_service
  WHERE FALSE
  {% endif %}
),

member_slots AS (
  SELECT
    a.acquisition_id,
    a.effective_date,
    a.ordinal,
    a.service_credit,
    a.average_pay,
    a.relative_pay,
    a.average_age,
    a.average_service,
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
{% if adjust_pay or adjust_service %}
,

-- #1228: the sampled group's means, which overrides move to their targets
sampled_means AS (
  SELECT
    d.acquisition_id,
    AVG(p.compensation) AS mean_pay,
    AVG(p.current_age) AS mean_age,
    AVG(p.current_tenure) AS mean_tenure
  FROM draws d
  INNER JOIN donor_pool p
    ON d.donor_index = p.donor_index
  GROUP BY d.acquisition_id
)
{% endif %}

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
    || CAST(ROUND(member.compensation, 0) AS VARCHAR) || ' annual compensation' AS event_details,
  CAST(member.compensation AS DOUBLE) AS compensation_amount,
  NULL::DECIMAL(15,2) AS previous_compensation,
  NULL::DECIMAL(5,4) AS employee_deferral_rate,
  NULL::DECIMAL(5,4) AS prev_employee_deferral_rate,
  member.current_age AS employee_age,
  CAST(credited.tenure AS DECIMAL(12,2)) AS employee_tenure,
  p.level_id,
  {{ assign_age_band('member.current_age') }} AS age_band,
  {{ assign_tenure_band('credited.tenure') }} AS tenure_band,
  1.0 AS event_probability,
  'hire' AS event_category,
  CAST(p.scheduled_hours_per_week AS DECIMAL(5,2)) AS scheduled_hours_per_week,
  d.acquisition_id
FROM draws d
LEFT JOIN donor_pool p
  ON d.donor_index = p.donor_index
{% if adjust_pay or adjust_service %}
LEFT JOIN sampled_means means
  ON d.acquisition_id = means.acquisition_id
{% endif %}
-- #1228: who the member is after the group's overrides
CROSS JOIN LATERAL (
  SELECT
    {% if adjust_pay %}
    p.compensation * COALESCE(
      d.relative_pay, d.average_pay / NULLIF(means.mean_pay, 0), 1.0
    ) AS compensation,
    {% else %}
    p.compensation,
    {% endif %}
    {% if adjust_age %}
    CASE WHEN d.average_age IS NULL THEN p.current_age
      ELSE GREATEST(18, p.current_age + CAST(ROUND(d.average_age - means.mean_age) AS BIGINT))
    END AS current_age
    {% else %}
    p.current_age
    {% endif %}
) member
CROSS JOIN LATERAL (
  SELECT
    {% if adjust_service %}
    CASE WHEN d.average_service IS NULL AND d.average_age IS NULL THEN p.current_tenure
      ELSE GREATEST(0, LEAST(
        p.current_tenure + COALESCE(CAST(ROUND(d.average_service - means.mean_tenure) AS BIGINT), 0),
        member.current_age - 18
      ))
    END AS tenure
    {% else %}
    p.current_tenure AS tenure
    {% endif %}
) sampled
-- #1227: service the plan credits; everything reads it through current_tenure
CROSS JOIN LATERAL (
  SELECT CASE WHEN d.service_credit = 'acquisition_date' THEN 0
    ELSE sampled.tenure END AS tenure
) credited
