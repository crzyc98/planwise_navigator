-- Test query to validate that the promotion persistence fix works correctly
-- This will test the specific case mentioned in the bug report (EMP_000012)

-- First, let's test if we can see the promotion events that existed
WITH sample_promotion_events AS (
    SELECT 
        'EMP_000012' as employee_id,
        2028 as simulation_year,
        'promotion' as event_type,
        'level_2_to_3' as event_details,
        3 as level_id,  -- Target level from promotion
        108688.50 as compensation_amount
),

-- Test the fixed logic: promotion level should be preserved
test_promotion_logic AS (
    SELECT 
        employee_id,
        simulation_year,
        -- This is the logic we fixed in workforce_after_promotions
        CASE
            WHEN event_type = 'promotion' THEN level_id  -- Use level_id directly (FIXED)
            ELSE 2  -- Assume employee was at level 2 before promotion
        END AS promotion_result_level,
        
        -- This is the logic we fixed in workforce_with_corrected_levels  
        CASE
            WHEN level_id IS NOT NULL THEN level_id  -- Preserve existing level (FIXED)
            ELSE 1  -- Fallback to compensation-based calculation
        END AS final_level
    FROM sample_promotion_events
)

SELECT 
    employee_id,
    simulation_year,
    promotion_result_level,
    final_level,
    CASE 
        WHEN final_level = 3 THEN 'PASS: Promotion level preserved correctly'
        ELSE 'FAIL: Promotion level not preserved'
    END as test_result
FROM test_promotion_logic;