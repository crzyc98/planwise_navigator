-- Cleanup script for duplicate events in fct_yearly_events
-- Root cause: Non-deterministic ROW_NUMBER() event_id generation
-- This script deduplicates events by keeping only one copy per unique event

-- Step 1: Create a deduplicated temporary table
CREATE TEMPORARY TABLE fct_yearly_events_deduped AS
SELECT DISTINCT ON (
    scenario_id,
    plan_design_id,
    employee_id,
    simulation_year,
    event_type,
    effective_date,
    COALESCE(compensation_amount, -999)  -- Handle NULL compensation
)
    -- Use deterministic hash for new event_id
    'EVT_' || SUBSTR(MD5(
        scenario_id || '_' ||
        plan_design_id || '_' ||
        employee_id || '_' ||
        CAST(simulation_year AS VARCHAR) || '_' ||
        event_type || '_' ||
        CAST(effective_date AS VARCHAR) || '_' ||
        COALESCE(CAST(compensation_amount AS VARCHAR), 'NULL')
    ), 1, 24) AS event_id,
    scenario_id,
    plan_design_id,
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
    event_category,
    -- Recalculate event_sequence with proper ordering
    ROW_NUMBER() OVER (
        PARTITION BY scenario_id, plan_design_id, employee_id, simulation_year
        ORDER BY
            CASE event_type
                WHEN 'termination' THEN 1
                WHEN 'hire' THEN 2
                WHEN 'eligibility' THEN 3
                WHEN 'enrollment' THEN 4
                WHEN 'enrollment_change' THEN 5
                WHEN 'deferral_escalation' THEN 6
                WHEN 'promotion' THEN 7
                WHEN 'raise' THEN 8
                ELSE 9
            END,
            effective_date
    ) AS event_sequence,
    created_at,
    parameter_scenario_id,
    parameter_source,
    data_quality_flag
FROM fct_yearly_events
ORDER BY
    scenario_id,
    plan_design_id,
    employee_id,
    simulation_year,
    event_type,
    effective_date,
    COALESCE(compensation_amount, -999),
    created_at DESC;  -- Keep most recent if true duplicates exist

-- Step 2: Show statistics before cleanup
SELECT
    'Before Cleanup' as status,
    COUNT(*) as total_events,
    COUNT(DISTINCT event_id) as unique_event_ids,
    COUNT(*) - COUNT(DISTINCT event_id) as duplicate_event_ids
FROM fct_yearly_events;

SELECT
    'After Cleanup' as status,
    COUNT(*) as total_events,
    COUNT(DISTINCT event_id) as unique_event_ids,
    COUNT(*) - COUNT(DISTINCT event_id) as duplicate_event_ids
FROM fct_yearly_events_deduped;

-- Step 3: Show event count changes by type
SELECT
    'hire' as event_type,
    (SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'hire') as before_count,
    (SELECT COUNT(*) FROM fct_yearly_events_deduped WHERE event_type = 'hire') as after_count,
    (SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'hire') -
    (SELECT COUNT(*) FROM fct_yearly_events_deduped WHERE event_type = 'hire') as removed_count
UNION ALL
SELECT
    'termination' as event_type,
    (SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'termination') as before_count,
    (SELECT COUNT(*) FROM fct_yearly_events_deduped WHERE event_type = 'termination') as after_count,
    (SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'termination') -
    (SELECT COUNT(*) FROM fct_yearly_events_deduped WHERE event_type = 'termination') as removed_count
UNION ALL
SELECT
    'raise' as event_type,
    (SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'raise') as before_count,
    (SELECT COUNT(*) FROM fct_yearly_events_deduped WHERE event_type = 'raise') as after_count,
    (SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'raise') -
    (SELECT COUNT(*) FROM fct_yearly_events_deduped WHERE event_type = 'raise') as removed_count
UNION ALL
SELECT
    'enrollment' as event_type,
    (SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'enrollment') as before_count,
    (SELECT COUNT(*) FROM fct_yearly_events_deduped WHERE event_type = 'enrollment') as after_count,
    (SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'enrollment') -
    (SELECT COUNT(*) FROM fct_yearly_events_deduped WHERE event_type = 'enrollment') as removed_count;

-- Step 4: Replace original table (UNCOMMENT WHEN READY TO COMMIT)
-- WARNING: This will permanently modify your data. Create a backup first!
-- DROP TABLE fct_yearly_events;
-- ALTER TABLE fct_yearly_events_deduped RENAME TO fct_yearly_events;

PRAGMA database_list;
SELECT 'CLEANUP PREVIEW COMPLETE - Review results above before uncommenting Step 4' as message;
