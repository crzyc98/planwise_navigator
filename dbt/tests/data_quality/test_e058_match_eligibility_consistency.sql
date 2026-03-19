{{
  config(
    severity='error',
    tags=['data_quality', 'e058', 'match_eligibility']
  )
}}

/*
  Data Quality Test: E058 Match Eligibility Reason Consistency

  Validates that match_eligibility_reason is consistent with eligible_for_match flag:
  - In backward compatibility mode, reason is always 'backward_compatibility_simple_rule'
  - In configured mode, 'eligible' means eligible_for_match=true
  - Other reasons (insufficient_hours, insufficient_tenure, inactive_eoy) mean eligible_for_match=false

  Returns rows where eligibility reason is inconsistent with the eligible_for_match flag.
*/

SELECT
  employee_id,
  simulation_year,
  match_eligibility_reason,
  eligible_for_match,
  match_apply_eligibility,
  'inconsistent_reason_and_flag' AS violation_type
FROM {{ ref('int_employer_eligibility') }}
WHERE NOT (
  -- In backward compatibility mode, reason is always 'backward_compatibility_simple_rule'
  (match_eligibility_reason = 'backward_compatibility_simple_rule') OR
  -- In configured mode, 'eligible' means eligible_for_match=true, others mean false
  (match_eligibility_reason = 'eligible' AND eligible_for_match = true) OR
  (match_eligibility_reason IN ('insufficient_hours', 'insufficient_tenure', 'inactive_eoy') AND eligible_for_match = false)
)
