{% snapshot scd_workforce_state %}

{{
  config(
    target_schema='snapshots',
    unique_key='employee_id',
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
    {{ var('simulation_year', 2025) }} AS simulation_year,
    CURRENT_TIMESTAMP AS snapshot_created_at
FROM {{ ref('int_baseline_workforce') }}
WHERE employment_status = 'active'

{% endsnapshot %}
