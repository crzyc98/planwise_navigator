-- Test to validate that promotion events show proper level progression
-- Ensures no level skipping, no demotions, and proper level boundaries

WITH promotion_validation AS (
    SELECT
        pe.employee_id,
        pe.simulation_year,
        pe.from_level,
        pe.to_level,
        -- Check if promotion is exactly one level up
        CASE
            WHEN pe.to_level = pe.from_level + 1 THEN 'valid'
            WHEN pe.to_level <= pe.from_level THEN 'demotion_or_no_change'
            WHEN pe.to_level > pe.from_level + 1 THEN 'level_skipping'
            ELSE 'other'
        END as level_progression_type,
        -- Validate level boundaries
        CASE
            WHEN pe.from_level < 1 OR pe.from_level > 5 THEN 'invalid_from_level'
            WHEN pe.to_level < 1 OR pe.to_level > 5 THEN 'invalid_to_level'
            WHEN pe.from_level = 5 THEN 'promotion_from_max_level'
            ELSE 'valid_levels'
        END as level_boundary_validation,
        -- Check if from_level matches previous year's actual level
        ecy.level_id as actual_previous_level,
        CASE
            WHEN pe.from_level = ecy.level_id THEN 'matches_actual'
            WHEN pe.from_level != ecy.level_id THEN 'level_mismatch'
            ELSE 'no_previous_data'
        END as previous_level_validation
    FROM {{ ref('int_promotion_events') }} pe
    LEFT JOIN {{ ref('int_employee_compensation_by_year') }} ecy
        ON pe.employee_id = ecy.employee_id
        AND pe.simulation_year = ecy.simulation_year
        AND ecy.employment_status = 'active'
)

SELECT
    employee_id,
    simulation_year,
    from_level,
    to_level,
    actual_previous_level,
    level_progression_type,
    level_boundary_validation,
    previous_level_validation,
    CASE
        WHEN level_progression_type = 'demotion_or_no_change'
            THEN 'Employee ' || employee_id || ' has invalid promotion: from level ' || from_level || ' to ' || to_level || ' (demotion or no change)'
        WHEN level_progression_type = 'level_skipping'
            THEN 'Employee ' || employee_id || ' has invalid promotion: from level ' || from_level || ' to ' || to_level || ' (skipped levels)'
        WHEN level_boundary_validation = 'invalid_from_level'
            THEN 'Employee ' || employee_id || ' has invalid from_level: ' || from_level || ' (must be 1-5)'
        WHEN level_boundary_validation = 'invalid_to_level'
            THEN 'Employee ' || employee_id || ' has invalid to_level: ' || to_level || ' (must be 1-5)'
        WHEN level_boundary_validation = 'promotion_from_max_level'
            THEN 'Employee ' || employee_id || ' promoted from max level 5 (should not be possible)'
        WHEN previous_level_validation = 'level_mismatch'
            THEN 'Employee ' || employee_id || ' promotion from_level (' || from_level || ') does not match actual previous level (' || actual_previous_level || ')'
        ELSE 'Unknown validation error'
    END as error_message
FROM promotion_validation
WHERE
    level_progression_type != 'valid'
    OR level_boundary_validation != 'valid_levels'
    OR previous_level_validation != 'matches_actual'
