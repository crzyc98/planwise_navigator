{{ config(materialized='table') }}

-- Temporary placeholder for int_deferral_rate_escalation_events
-- TODO: Fix missing in_auto_escalation_program column dependency

SELECT
    'PLACEHOLDER_EMP' as employee_id,
    {{ var('simulation_year') }} as simulation_year,
    'deferral_rate_escalation' as event_type,
    CAST('{{ var('simulation_year') }}-01-01' AS DATE) as effective_date,
    0.00 as old_deferral_rate,
    0.01 as new_deferral_rate,
    'auto_escalation' as escalation_trigger,
    CURRENT_TIMESTAMP as created_at,
    '{{ var('simulation_year') }}' as data_source
WHERE FALSE  -- Returns no rows, just creates the table structure
