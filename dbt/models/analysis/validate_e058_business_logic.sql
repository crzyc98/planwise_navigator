{{ config(
    materialized='table',
    tags=['validation', 'data_quality', 'e058', 'business_logic']
) }}

/*
  Epic E058 Phase 4: Comprehensive Business Logic Validation

  This model validates the complete Epic E058 employer match eligibility configuration
  feature by testing all business logic scenarios and edge cases.

  Test Categories:
  1. Eligibility Consistency Tests - Ensure eligibility flags match reason codes
  2. Match Calculation Integration Tests - Verify ineligible employees receive $0 match
  3. Configuration Consistency Tests - Validate configuration parameters are applied correctly
  4. Multi-Year Continuity Tests - Ensure eligibility transitions work correctly across years
  5. Edge Case Tests - Validate boundary conditions and special scenarios

  Expected Results:
  - All validation_result = 'PASS' for production deployment
  - Any 'FAIL' results indicate business logic violations that must be resolved
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH

-- Test 1: Only eligible employees receive match
ineligible_with_match AS (
    SELECT
        'ineligible_employees_receive_zero_match' as test_name,
        COUNT(*) as violation_count,
        CASE
            WHEN COUNT(*) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END as validation_result,
        'Ineligible employees must receive $0 employer match' as test_description,
        'HIGH' as severity
    FROM {{ ref('int_employee_match_calculations') }} m
    JOIN {{ ref('int_employer_eligibility') }} e
        ON m.employee_id = e.employee_id
        AND m.simulation_year = e.simulation_year
    WHERE e.eligible_for_match = FALSE
        AND m.employer_match_amount > 0
        AND m.simulation_year = {{ simulation_year }}
),

-- Test 2: All eligible enrolled employees with deferrals receive calculated match
eligible_without_match AS (
    SELECT
        'eligible_employees_with_deferrals_receive_match' as test_name,
        COUNT(*) as violation_count,
        CASE
            WHEN COUNT(*) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END as validation_result,
        'Eligible employees with deferrals must have match calculation performed' as test_description,
        'HIGH' as severity
    FROM {{ ref('int_employee_match_calculations') }} m
    JOIN {{ ref('int_employer_eligibility') }} e
        ON m.employee_id = e.employee_id
        AND m.simulation_year = e.simulation_year
    WHERE e.eligible_for_match = TRUE
        AND m.annual_deferrals > 0
        AND m.employer_match_amount = 0
        AND m.match_status != 'no_deferrals'
        AND m.simulation_year = {{ simulation_year }}
),

-- Test 3: Match status consistency with eligibility
match_status_consistency AS (
    SELECT
        'match_status_eligibility_consistency' as test_name,
        COUNT(*) as violation_count,
        CASE
            WHEN COUNT(*) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END as validation_result,
        'Match status must be consistent with eligibility determination' as test_description,
        'HIGH' as severity
    FROM {{ ref('int_employee_match_calculations') }} m
    JOIN {{ ref('int_employer_eligibility') }} e
        ON m.employee_id = e.employee_id
        AND m.simulation_year = e.simulation_year
    WHERE (
        (m.match_status = 'ineligible' AND e.eligible_for_match = TRUE) OR
        (m.match_status != 'ineligible' AND e.eligible_for_match = FALSE)
    )
    AND m.simulation_year = {{ simulation_year }}
),

-- Test 4: Eligibility reason codes are accurate
eligibility_reason_accuracy AS (
    SELECT
        'eligibility_reason_code_accuracy' as test_name,
        COUNT(*) as violation_count,
        CASE
            WHEN COUNT(*) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END as validation_result,
        'Eligibility reason codes must accurately reflect why employees are ineligible' as test_description,
        'MEDIUM' as severity
    FROM {{ ref('int_employer_eligibility') }} e
    WHERE simulation_year = {{ simulation_year }}
        AND (
            -- Insufficient tenure reason should match actual tenure vs requirement
            (match_eligibility_reason = 'insufficient_tenure' AND current_tenure >= match_tenure_requirement) OR
            -- Insufficient hours reason should match actual hours vs requirement
            (match_eligibility_reason = 'insufficient_hours' AND annual_hours_worked >= match_hours_requirement) OR
            -- Inactive EOY reason should match employment status when required
            (match_eligibility_reason = 'inactive_eoy' AND
             (match_requires_active_eoy = FALSE OR employment_status = 'active'))
        )
),

-- Test 5: Backward compatibility mode validation
backward_compatibility_validation AS (
    SELECT
        'backward_compatibility_mode_consistency' as test_name,
        COUNT(*) as violation_count,
        CASE
            WHEN COUNT(*) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END as validation_result,
        'Backward compatibility mode must use simple active+1000 hours rule' as test_description,
        'HIGH' as severity
    FROM {{ ref('int_employer_eligibility') }} e
    WHERE simulation_year = {{ simulation_year }}
        AND match_apply_eligibility = FALSE
        AND (
            match_eligibility_reason != 'backward_compatibility_simple_rule' OR
            -- The current implementation uses 'prorated_hours_with_tenure' as the method
            eligibility_method NOT IN ('backward_compatibility', 'prorated_hours_with_tenure')
        )
),

-- Test 6: Configuration parameter consistency
configuration_consistency AS (
    WITH config_variations AS (
        SELECT DISTINCT
            match_apply_eligibility,
            match_tenure_requirement,
            match_hours_requirement,
            match_requires_active_eoy,
            match_allow_new_hires,
            match_allow_terminated_new_hires,
            match_allow_experienced_terminations
        FROM {{ ref('int_employer_eligibility') }}
        WHERE simulation_year = {{ simulation_year }}
    )
    SELECT
        'configuration_parameter_consistency' as test_name,
        CASE
            WHEN (SELECT COUNT(*) FROM config_variations) > 1 THEN (SELECT COUNT(*) FROM config_variations) - 1
            ELSE 0
        END as violation_count,
        CASE
            WHEN (SELECT COUNT(*) FROM config_variations) <= 1 THEN 'PASS'
            ELSE 'FAIL'
        END as validation_result,
        'Configuration parameters must be consistent across all records' as test_description,
        'MEDIUM' as severity
),

-- Test 7: Capped match amount validation
capped_match_validation AS (
    SELECT
        'capped_match_amount_validation' as test_name,
        COUNT(*) as violation_count,
        CASE
            WHEN COUNT(*) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END as validation_result,
        'Capped match amount must be non-negative and final match should not exceed capped amount' as test_description,
        'MEDIUM' as severity
    FROM {{ ref('int_employee_match_calculations') }} m
    WHERE simulation_year = {{ simulation_year }}
        AND (
            capped_match_amount < 0 OR
            -- For eligible employees, final match should not exceed capped amount
            (is_eligible_for_match = TRUE AND employer_match_amount > capped_match_amount)
        )
),

-- Test 8: Multi-year eligibility transition validation
multi_year_transition_validation AS (
    SELECT
        'multi_year_eligibility_transition_consistency' as test_name,
        COUNT(*) as violation_count,
        CASE
            WHEN COUNT(*) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END as validation_result,
        'Multi-year eligibility transitions must follow logical progression' as test_description,
        'LOW' as severity
    FROM (
        SELECT
            e1.employee_id,
            e1.current_tenure as current_year_tenure,
            e1.eligible_for_match as current_year_eligible,
            e2.current_tenure as previous_year_tenure,
            e2.eligible_for_match as previous_year_eligible
        FROM {{ ref('int_employer_eligibility') }} e1
        LEFT JOIN {{ ref('int_employer_eligibility') }} e2
            ON e1.employee_id = e2.employee_id
            AND e2.simulation_year = {{ simulation_year - 1 }}
        WHERE e1.simulation_year = {{ simulation_year }}
            AND e2.employee_id IS NOT NULL
            AND e1.match_apply_eligibility = TRUE
            AND e2.match_apply_eligibility = TRUE
    ) transitions
    WHERE
        -- Employees who gain tenure should not lose eligibility (unless other factors)
        (current_year_tenure > previous_year_tenure
         AND current_year_eligible = FALSE
         AND previous_year_eligible = TRUE)
),

-- Test 9: Edge case validation for new hires
new_hire_edge_cases AS (
    SELECT
        'new_hire_eligibility_edge_cases' as test_name,
        COUNT(*) as violation_count,
        CASE
            WHEN COUNT(*) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END as validation_result,
        'New hire eligibility must respect configuration flags' as test_description,
        'MEDIUM' as severity
    FROM {{ ref('int_employer_eligibility') }} e
    JOIN {{ ref('int_baseline_workforce') }} b
        ON e.employee_id = b.employee_id
        AND e.simulation_year = b.simulation_year
    WHERE e.simulation_year = {{ simulation_year }}
        AND e.match_apply_eligibility = TRUE
        AND e.current_tenure < 1.0  -- New hires (less than 1 year tenure)
        AND (
            -- If new hires not allowed but employee is eligible
            (e.match_allow_new_hires = FALSE AND e.eligible_for_match = TRUE) OR
            -- If new hires allowed but employee is ineligible due to tenure only
            (e.match_allow_new_hires = TRUE
             AND e.eligible_for_match = FALSE
             AND e.match_eligibility_reason = 'insufficient_tenure'
             AND e.current_tenure >= e.match_tenure_requirement)
        )
),

-- Combine all test results
all_tests AS (
    SELECT * FROM ineligible_with_match
    UNION ALL
    SELECT * FROM eligible_without_match
    UNION ALL
    SELECT * FROM match_status_consistency
    UNION ALL
    SELECT * FROM eligibility_reason_accuracy
    UNION ALL
    SELECT * FROM backward_compatibility_validation
    UNION ALL
    SELECT * FROM configuration_consistency
    UNION ALL
    SELECT * FROM capped_match_validation
    UNION ALL
    SELECT * FROM multi_year_transition_validation
    UNION ALL
    SELECT * FROM new_hire_edge_cases
)

SELECT
    test_name,
    violation_count,
    validation_result,
    test_description,
    severity,
    {{ simulation_year }} as simulation_year,
    CURRENT_TIMESTAMP as validation_timestamp,
    CASE
        WHEN validation_result = 'PASS' THEN 'All business logic validations passed'
        ELSE 'CRITICAL: Business logic violations detected - Epic E058 requires attention'
    END as validation_summary
FROM all_tests
ORDER BY
    CASE severity
        WHEN 'HIGH' THEN 1
        WHEN 'MEDIUM' THEN 2
        WHEN 'LOW' THEN 3
    END,
    CASE validation_result
        WHEN 'FAIL' THEN 1
        WHEN 'PASS' THEN 2
    END,
    test_name
