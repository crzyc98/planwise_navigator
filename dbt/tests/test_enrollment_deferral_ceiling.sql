-- Test: 10% ceiling enforced in both enrollment models (FR-009)
-- Returns rows only when a deferral rate exceeds 10%.
SELECT employee_id, 'voluntary' AS model, selected_deferral_rate AS deferral_rate
FROM {{ ref('int_voluntary_enrollment_decision') }}
WHERE selected_deferral_rate > 0.10
UNION ALL
SELECT employee_id, 'proactive' AS model, proactive_deferral_rate AS deferral_rate
FROM {{ ref('int_proactive_voluntary_enrollment') }}
WHERE proactive_deferral_rate > 0.10
