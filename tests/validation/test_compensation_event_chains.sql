-- Test to validate that compensation event chains are properly sequenced
-- This ensures promotions happen before raises and raises use post-promotion salaries

-- Test 1: Promotion events should use correct previous_compensation (based on previous year/raises)
WITH promotion_compensation_validation AS (
    SELECT 
        employee_id,
        simulation_year,
        event_details,
        compensation_amount,
        previous_compensation,
        CASE 
            WHEN previous_compensation IS NULL THEN 'MISSING_PREVIOUS_COMPENSATION'
            WHEN previous_compensation < 50000 THEN 'UNREALISTICALLY_LOW_PREVIOUS'
            WHEN previous_compensation > 500000 THEN 'UNREALISTICALLY_HIGH_PREVIOUS'
            ELSE 'VALID'
        END as validation_status
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'promotion'
),

-- Test 2: Raise events in same year as promotion should use post-promotion compensation
raise_after_promotion_validation AS (
    SELECT 
        r.employee_id,
        r.simulation_year,
        r.previous_compensation as raise_previous_comp,
        p.compensation_amount as promotion_comp,
        CASE 
            WHEN p.compensation_amount IS NULL THEN 'NO_PROMOTION_IN_YEAR'
            WHEN ABS(r.previous_compensation - p.compensation_amount) < 0.01 THEN 'CORRECT_CHAIN'
            ELSE 'BROKEN_CHAIN'
        END as chain_validation
    FROM {{ ref('fct_yearly_events') }} r
    LEFT JOIN {{ ref('fct_yearly_events') }} p 
        ON r.employee_id = p.employee_id 
        AND r.simulation_year = p.simulation_year
        AND p.event_type = 'promotion'
    WHERE r.event_type = 'raise'
        AND p.employee_id IS NOT NULL  -- Only test employees who had promotions
),

-- Test 3: Event sequence within same day should follow priority (promotion before raise)
same_day_sequence_validation AS (
    SELECT 
        employee_id,
        simulation_year,
        effective_date,
        COUNT(*) as events_same_day,
        COUNT(CASE WHEN event_type = 'promotion' THEN 1 END) as promotions,
        COUNT(CASE WHEN event_type = 'raise' THEN 1 END) as raises,
        MIN(CASE WHEN event_type = 'promotion' THEN event_sequence END) as first_promotion_seq,
        MIN(CASE WHEN event_type = 'raise' THEN event_sequence END) as first_raise_seq,
        CASE 
            WHEN MIN(CASE WHEN event_type = 'promotion' THEN event_sequence END) < 
                 MIN(CASE WHEN event_type = 'raise' THEN event_sequence END) 
            THEN 'CORRECT_SEQUENCE'
            ELSE 'INCORRECT_SEQUENCE'
        END as sequence_validation
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type IN ('promotion', 'raise')
    GROUP BY employee_id, simulation_year, effective_date
    HAVING COUNT(*) > 1  -- Only check days with multiple events
)

-- Combine all validation results
SELECT 
    'promotion_compensation' as test_type,
    COUNT(*) as total_events,
    COUNT(CASE WHEN validation_status = 'VALID' THEN 1 END) as passed,
    COUNT(CASE WHEN validation_status != 'VALID' THEN 1 END) as failed,
    ROUND(100.0 * COUNT(CASE WHEN validation_status = 'VALID' THEN 1 END) / COUNT(*), 2) as pass_rate_pct
FROM promotion_compensation_validation

UNION ALL

SELECT 
    'raise_after_promotion' as test_type,
    COUNT(*) as total_events,
    COUNT(CASE WHEN chain_validation = 'CORRECT_CHAIN' THEN 1 END) as passed,
    COUNT(CASE WHEN chain_validation != 'CORRECT_CHAIN' THEN 1 END) as failed,
    ROUND(100.0 * COUNT(CASE WHEN chain_validation = 'CORRECT_CHAIN' THEN 1 END) / COUNT(*), 2) as pass_rate_pct
FROM raise_after_promotion_validation

UNION ALL

SELECT 
    'same_day_sequence' as test_type,
    COUNT(*) as total_events,
    COUNT(CASE WHEN sequence_validation = 'CORRECT_SEQUENCE' THEN 1 END) as passed,
    COUNT(CASE WHEN sequence_validation != 'CORRECT_SEQUENCE' THEN 1 END) as failed,
    ROUND(100.0 * COUNT(CASE WHEN sequence_validation = 'CORRECT_SEQUENCE' THEN 1 END) / COUNT(*), 2) as pass_rate_pct
FROM same_day_sequence_validation

-- Test should show 100% pass rate for all test types
HAVING MIN(pass_rate_pct) = 100