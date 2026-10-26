-- See specs/986-participant-deferral-behavior/design.md, section 2.
-- Zero-row wiring skeleton; real generation arrives in #983 (PR 3a).
{{ config(materialized='ephemeral', tags=['EVENT_GENERATION']) }}

SELECT
  CAST(NULL AS VARCHAR) AS employee_id,
  CAST(NULL AS VARCHAR) AS employee_ssn,
  CAST(NULL AS VARCHAR) AS event_type,
  CAST(NULL AS INTEGER) AS simulation_year,
  CAST(NULL AS DATE) AS effective_date,
  CAST(NULL AS VARCHAR) AS event_details,
  CAST(NULL AS DECIMAL(15,2)) AS compensation_amount,
  CAST(NULL AS DECIMAL(15,2)) AS previous_compensation,
  CAST(NULL AS DECIMAL(5,4)) AS employee_deferral_rate,
  CAST(NULL AS DECIMAL(5,4)) AS prev_employee_deferral_rate,
  CAST(NULL AS SMALLINT) AS employee_age,
  CAST(NULL AS DECIMAL(10,2)) AS employee_tenure,
  CAST(NULL AS SMALLINT) AS level_id,
  CAST(NULL AS VARCHAR) AS age_band,
  CAST(NULL AS VARCHAR) AS tenure_band,
  CAST(NULL AS DECIMAL(5,4)) AS event_probability,
  CAST(NULL AS VARCHAR) AS event_category
WHERE FALSE
