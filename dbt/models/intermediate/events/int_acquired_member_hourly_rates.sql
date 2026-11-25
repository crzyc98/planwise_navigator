{{ config(
  materialized='incremental',
  incremental_strategy='replace_simulation_year',
  on_schema_change='sync_all_columns',
  tags=['EVENT_GENERATION']
) }}

{% set simulation_year = var('simulation_year') | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set scenario_id = var('scenario_id', 'default') %}

-- Hourly rates for acquired members (#1253), one row per member whose donor
-- has a rate, written in the year the member joins.
--
-- A member copies the donor's pay and hours, so they share the donor's rate
-- per dollar of pay. The row keeps the donor's census rate and census pay; the
-- member's rate on any date is that rate x the member's pay / that pay, as
-- census_hourly_rate_now gives for census staff. A pay override scales the
-- member's pay, and the rate with it.
--
-- A donor can be an earlier acquired member, whose pair is read from the
-- years already written. A member whose donor has no rate (a simulated hire,
-- or census staff with none) has no row and is never raised.
--
-- Like an accumulator, later years read the rows earlier years wrote, so never
-- --full-refresh this model mid-simulation.

{% if acquisitions_joining(simulation_year) %}
WITH donor_rates AS (
  SELECT
    employee_id,
    census_hourly_rate,
    current_compensation AS census_annual_pay
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ start_year }}
    AND census_hourly_rate IS NOT NULL
    AND current_compensation > 0
  {% if is_incremental() %}
  UNION ALL
  SELECT
    employee_id,
    census_hourly_rate,
    census_annual_pay
  FROM {{ this }}
  WHERE simulation_year < {{ simulation_year }}
    AND scenario_id = '{{ scenario_id | replace("'", "''") }}'
  {% endif %}
)

SELECT
  '{{ scenario_id | replace("'", "''") }}'::VARCHAR AS scenario_id,
  {{ simulation_year }}::INTEGER AS simulation_year,
  CAST(hire.employee_id AS VARCHAR) AS employee_id,
  CAST(hire.acquisition_id AS VARCHAR) AS acquisition_id,
  CAST(hire.donor_employee_id AS VARCHAR) AS donor_employee_id,
  CAST(donor.census_hourly_rate AS DOUBLE) AS census_hourly_rate,
  CAST(donor.census_annual_pay AS DOUBLE) AS census_annual_pay
FROM {{ ref('int_hiring_events') }} hire
INNER JOIN donor_rates donor
  ON hire.donor_employee_id = donor.employee_id
WHERE hire.simulation_year = {{ simulation_year }}
  AND hire.acquisition_id IS NOT NULL
{% else %}
-- depends_on: {{ ref('int_hiring_events') }}
-- depends_on: {{ ref('int_baseline_workforce') }}
SELECT
  CAST(NULL AS VARCHAR) AS scenario_id,
  CAST(NULL AS INTEGER) AS simulation_year,
  CAST(NULL AS VARCHAR) AS employee_id,
  CAST(NULL AS VARCHAR) AS acquisition_id,
  CAST(NULL AS VARCHAR) AS donor_employee_id,
  CAST(NULL AS DOUBLE) AS census_hourly_rate,
  CAST(NULL AS DOUBLE) AS census_annual_pay
WHERE FALSE
{% endif %}
