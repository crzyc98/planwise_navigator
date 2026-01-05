/*
  Test: Audit Trail for Core Contributions

  This test verifies that the `applied_years_of_service` field is populated
  for all employees who receive core contributions.

  Expected:
    - All employees with employer_core_amount > 0 have applied_years_of_service populated
    - applied_years_of_service matches the tenure from workforce snapshot

  This ensures compliance and audit requirements are met by tracking
  which service tier was used for each contribution calculation.
*/

WITH audit_check AS (
    SELECT
        ec.employee_id,
        ec.applied_years_of_service,
        ec.core_contribution_rate,
        ec.employer_core_amount,
        snap.years_of_service AS expected_years_of_service,
        CASE
            WHEN ec.applied_years_of_service IS NULL THEN 'MISSING_AUDIT_FIELD'
            WHEN ec.applied_years_of_service != snap.years_of_service THEN 'MISMATCH'
            ELSE 'OK'
        END AS audit_status
    FROM {{ ref('int_employer_core_contributions') }} ec
    INNER JOIN (
        SELECT
            employee_id,
            FLOOR(COALESCE(current_tenure, 0))::INT AS years_of_service
        FROM {{ ref('int_workforce_snapshot_optimized') }}
        WHERE simulation_year = {{ var('simulation_year', 2025) }}
    ) snap ON ec.employee_id = snap.employee_id
    WHERE ec.simulation_year = {{ var('simulation_year', 2025) }}
      AND ec.employer_core_amount > 0
)

-- Return rows where audit trail is missing or incorrect (test fails if any rows)
SELECT *
FROM audit_check
WHERE audit_status != 'OK'
