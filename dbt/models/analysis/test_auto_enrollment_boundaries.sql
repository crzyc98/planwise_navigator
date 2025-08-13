{{ config(materialized='table') }}

/*
Auto-enrollment boundary condition and idempotency validation tests.

Tests key boundary conditions and validates that auto-enrollment logic
works correctly for edge cases and prevents duplicate enrollments.
*/

-- Test 1: Employees hired exactly on cutoff date (use compensation table for hire dates)
WITH boundary_test AS (
  SELECT
    'boundary_cutoff_date' as test_name,
    COUNT(*) as boundary_employees,
    COUNT(CASE WHEN {{ is_eligible_for_auto_enrollment('c.employee_hire_date', var('simulation_year')) }} THEN 1 END) as eligible_on_boundary,
    '{{ var("auto_enrollment_hire_date_cutoff", "2020-01-01") }}' as cutoff_date_tested
  FROM {{ ref('int_employee_compensation_by_year') }} c
  WHERE c.employee_hire_date = '{{ var("auto_enrollment_hire_date_cutoff", "2020-01-01") }}'::DATE
    AND c.simulation_year = {{ var('simulation_year') }}
    AND c.employment_status = 'active'
),

-- Test 2: No duplicate auto-enrollments per employee
duplicate_test AS (
  SELECT
    'duplicate_enrollments' as test_name,
    COUNT(*) as total_enrollment_events,
    COUNT(DISTINCT employee_id) as unique_employees,
    COUNT(*) - COUNT(DISTINCT employee_id) as duplicate_count
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'enrollment'
    AND simulation_year = {{ var('simulation_year') }}
),

-- Test 3: Scope coverage validation
scope_coverage_test AS (
  SELECT
    'scope_coverage' as test_name,
    COUNT(DISTINCT c.employee_id) as total_active_employees,
    COUNT(DISTINCT CASE WHEN {{ is_eligible_for_auto_enrollment('c.employee_hire_date', var('simulation_year')) }} THEN c.employee_id END) as eligible_for_auto_enrollment,
    COUNT(DISTINCT CASE WHEN c.employee_hire_date < '{{ var("auto_enrollment_hire_date_cutoff", "2020-01-01") }}'::DATE THEN c.employee_id END) as pre_cutoff_employees,
    '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' as current_scope
  FROM {{ ref('int_employee_compensation_by_year') }} c
  WHERE c.simulation_year = {{ var('simulation_year') }}
    AND c.employment_status = 'active'
),

-- Test 4: New hire vs existing employee logic
hire_cohort_test AS (
  SELECT
    'hire_cohort_logic' as test_name,
    COUNT(CASE WHEN EXTRACT(YEAR FROM c.employee_hire_date) = {{ var('simulation_year') }} THEN 1 END) as current_year_hires,
    COUNT(CASE WHEN EXTRACT(YEAR FROM c.employee_hire_date) < {{ var('simulation_year') }} THEN 1 END) as existing_employees,
    COUNT(CASE WHEN EXTRACT(YEAR FROM c.employee_hire_date) = {{ var('simulation_year') }} AND {{ is_eligible_for_auto_enrollment('c.employee_hire_date', var('simulation_year')) }} THEN 1 END) as eligible_new_hires,
    COUNT(CASE WHEN EXTRACT(YEAR FROM c.employee_hire_date) < {{ var('simulation_year') }} AND {{ is_eligible_for_auto_enrollment('c.employee_hire_date', var('simulation_year')) }} THEN 1 END) as eligible_existing
  FROM {{ ref('int_employee_compensation_by_year') }} c
  WHERE c.simulation_year = {{ var('simulation_year') }}
    AND c.employee_hire_date >= '{{ var("auto_enrollment_hire_date_cutoff", "2020-01-01") }}'::DATE
    AND c.employment_status = 'active'
),

-- Test 5: Idempotency check via enrollment registry
idempotency_test AS (
  SELECT
    'idempotency_check' as test_name,
    COUNT(*) as employees_in_registry,
    COUNT(CASE WHEN is_enrolled = true THEN 1 END) as previously_enrolled,
    COUNT(CASE WHEN first_enrollment_year < {{ var('simulation_year') }} THEN 1 END) as enrolled_prior_years
  FROM enrollment_registry
  WHERE employee_id IS NOT NULL
),

-- Combine all tests with validation logic
all_tests AS (
  SELECT
    test_name,
    boundary_employees,
    NULL::integer as total_events,
    NULL::integer as unique_employees,
    NULL::integer as duplicate_count,
    eligible_on_boundary,
    NULL::integer as total_active,
    NULL::text as current_scope,
    NULL::integer as current_year_hires,
    NULL::integer as existing_employees,
    NULL::integer as eligible_new_hires,
    NULL::integer as eligible_existing,
    NULL::integer as employees_in_registry,
    NULL::integer as previously_enrolled,
    cutoff_date_tested,
    CASE
      WHEN eligible_on_boundary = 0 AND boundary_employees > 0 THEN 'FAIL: Boundary date employees not eligible'
      WHEN boundary_employees = 0 THEN 'PASS: No employees on boundary date'
      ELSE 'PASS: Boundary employees properly eligible'
    END as test_result
  FROM boundary_test

  UNION ALL

  SELECT
    test_name,
    NULL, total_events, unique_employees, duplicate_count, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
    CASE
      WHEN duplicate_count > 0 THEN 'FAIL: ' || duplicate_count || ' duplicate enrollments found'
      ELSE 'PASS: No duplicate enrollments'
    END as test_result
  FROM duplicate_test

  UNION ALL

  SELECT
    test_name,
    NULL, NULL, NULL, NULL, eligible_for_auto_enrollment, total_active_employees, current_scope, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
    CASE
      WHEN current_scope = 'all_eligible_employees' AND eligible_for_auto_enrollment < (total_active_employees - pre_cutoff_employees) * 0.8
        THEN 'FAIL: Too few eligible (' || eligible_for_auto_enrollment || ' vs expected ~' || (total_active_employees - pre_cutoff_employees) || ')'
      WHEN current_scope = 'new_hires_only' AND eligible_for_auto_enrollment > total_active_employees * 0.3
        THEN 'FAIL: Too many eligible for new_hires_only scope'
      ELSE 'PASS: Scope coverage looks reasonable'
    END as test_result
  FROM scope_coverage_test

  UNION ALL

  SELECT
    test_name,
    NULL, NULL, NULL, NULL, NULL, NULL, NULL, current_year_hires, existing_employees, eligible_new_hires, eligible_existing, NULL, NULL, NULL,
    CASE
      WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'new_hires_only' AND eligible_existing > 0
        THEN 'FAIL: Existing employees eligible when scope is new_hires_only'
      WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'all_eligible_employees' AND eligible_existing = 0 AND existing_employees > 100
        THEN 'FAIL: No existing employees eligible when scope is all_eligible_employees'
      ELSE 'PASS: Hire cohort logic working correctly'
    END as test_result
  FROM hire_cohort_test

  UNION ALL

  SELECT
    test_name,
    NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, employees_in_registry, previously_enrolled, NULL,
    CASE
      WHEN previously_enrolled > employees_in_registry THEN 'FAIL: More enrolled than registry entries'
      ELSE 'PASS: Registry state consistent'
    END as test_result
  FROM idempotency_test
)

SELECT
  {{ var('simulation_year') }} as simulation_year,
  test_name,
  test_result,
  -- Include relevant test data
  boundary_employees,
  total_events,
  duplicate_count,
  eligible_on_boundary as eligible_on_boundary_date,
  total_active as total_active_employees,
  current_scope,
  current_year_hires,
  existing_employees,
  eligible_new_hires,
  eligible_existing,
  employees_in_registry,
  previously_enrolled,
  cutoff_date_tested,
  CASE
    WHEN test_result LIKE 'FAIL%' THEN 'CRITICAL'
    ELSE 'PASS'
  END as severity,
  CURRENT_TIMESTAMP as test_timestamp
FROM all_tests
ORDER BY
  CASE WHEN test_result LIKE 'FAIL%' THEN 1 ELSE 2 END,
  test_name
