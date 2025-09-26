{% snapshot scd_workforce_state %}

{{
  config(
    target_schema='main',
    unique_key="employee_id || '_' || simulation_year",
    strategy='timestamp',
    updated_at='snapshot_created_at'
  )
}}

-- Workforce State Snapshot - Eliminates Circular Dependency
-- Captures end-of-simulation-year workforce state for historical reference
-- This snapshot will be updated by the Dagster pipeline after each simulation year completes

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
    employment_status,
    simulation_year,
    snapshot_created_at
FROM {{ ref('fct_workforce_snapshot') }}
WHERE simulation_year = {{ var('simulation_year', 2025) }}
  AND (employment_status = 'active' OR employment_status = 'terminated')

{% endsnapshot %}
