{{
  config(
    materialized='incremental',
    unique_key=['participant_id', 'plan_id', 'snapshot_date'],
    on_schema_change='fail',
    contract={'enforced': true}
  )
}}

/*
Weekly Participant Balance Snapshots - S072-06

Pre-computed weekly snapshots for optimized query performance.
Reduces event reconstruction time from seconds to milliseconds.

Business Logic:
- Snapshots taken every Friday (or last business day of week)
- Includes all account balances, vesting status, and key metrics
- Optimized for dashboard queries and compliance reporting
- Falls back to event reconstruction for detailed audit trails

Performance Targets:
- Query time: <100ms for participant balance lookup
- Storage efficiency: <10MB per 1000 participants per year
- Reconstruction accuracy: 100% match with event history
*/

WITH weekly_periods AS (
  SELECT
    DATE_TRUNC('week', generate_series) + INTERVAL '4 days' AS snapshot_date  -- Fridays
  FROM GENERATE_SERIES(
    '2020-01-03'::DATE,  -- First Friday of 2020
    CURRENT_DATE + INTERVAL '4 weeks',
    INTERVAL '1 week'
  )
),

participant_universe AS (
  SELECT DISTINCT
    employee_id AS participant_id,
    scenario_id,
    plan_design_id,
    JSON_EXTRACT_STRING(payload_json, '$.plan_id') AS plan_id
  FROM {{ ref('fct_yearly_events') }}
  WHERE JSON_EXTRACT_STRING(payload_json, '$.event_type') IN (
    'eligibility', 'enrollment', 'contribution', 'vesting', 'forfeiture'
  )
  AND JSON_EXTRACT_STRING(payload_json, '$.plan_id') IS NOT NULL
),

-- Event-based balance calculations for each snapshot date
participant_balances AS (
  SELECT
    pu.participant_id,
    pu.plan_id,
    pu.scenario_id,
    pu.plan_design_id,
    wp.snapshot_date,

    -- Contribution aggregations up to snapshot date
    COALESCE(SUM(
      CASE
        WHEN e.event_type = 'contribution'
        AND e.effective_date <= wp.snapshot_date
        THEN CAST(JSON_EXTRACT_STRING(e.payload_json, '$.employee_contribution') AS DECIMAL(18,6))
        ELSE 0
      END
    ), 0) AS total_employee_contributions,

    COALESCE(SUM(
      CASE
        WHEN e.event_type = 'contribution'
        AND e.effective_date <= wp.snapshot_date
        THEN CAST(JSON_EXTRACT_STRING(e.payload_json, '$.employer_contribution') AS DECIMAL(18,6))
        ELSE 0
      END
    ), 0) AS total_employer_contributions,

    -- Latest vesting percentage as of snapshot date
    COALESCE(
      LAST(
        CAST(JSON_EXTRACT_STRING(e.payload_json, '$.vested_percentage') AS DECIMAL(8,4))
        ORDER BY e.effective_date ASC
      ) FILTER (
        WHERE e.event_type = 'vesting'
        AND e.effective_date <= wp.snapshot_date
      ),
      0.0000
    ) AS current_vested_percentage,

    -- Service years as of snapshot date
    COALESCE(
      LAST(
        CAST(JSON_EXTRACT_STRING(e.payload_json, '$.service_years') AS DECIMAL(8,2))
        ORDER BY e.effective_date ASC
      ) FILTER (
        WHERE e.event_type = 'vesting'
        AND e.effective_date <= wp.snapshot_date
      ),
      0.00
    ) AS service_years,

    -- Forfeiture adjustments up to snapshot date
    COALESCE(SUM(
      CASE
        WHEN e.event_type = 'forfeiture'
        AND e.effective_date <= wp.snapshot_date
        THEN CAST(JSON_EXTRACT_STRING(e.payload_json, '$.amount') AS DECIMAL(18,6))
        ELSE 0
      END
    ), 0) AS total_forfeitures,

    -- Enrollment status as of snapshot date
    CASE
      WHEN EXISTS (
        SELECT 1 FROM {{ ref('fct_yearly_events') }} enroll
        WHERE enroll.employee_id = pu.participant_id
        AND JSON_EXTRACT_STRING(enroll.payload_json, '$.plan_id') = pu.plan_id
        AND enroll.event_type = 'enrollment'
        AND enroll.effective_date <= wp.snapshot_date
      ) THEN TRUE
      ELSE FALSE
    END AS is_enrolled,

    -- Latest deferral percentage
    COALESCE(
      LAST(
        CAST(JSON_EXTRACT_STRING(e.payload_json, '$.deferral_percentage') AS DECIMAL(8,4))
        ORDER BY e.effective_date ASC
      ) FILTER (
        WHERE e.event_type = 'enrollment'
        AND e.effective_date <= wp.snapshot_date
        AND JSON_EXTRACT_STRING(e.payload_json, '$.plan_id') = pu.plan_id
      ),
      0.0000
    ) AS current_deferral_percentage,

    -- Count of contribution events (participation frequency)
    COUNT(
      CASE
        WHEN e.event_type = 'contribution'
        AND e.effective_date <= wp.snapshot_date
        THEN 1
      END
    ) AS contribution_event_count,

    -- Latest eligibility date
    MIN(
      CASE
        WHEN e.event_type = 'eligibility'
        AND e.effective_date <= wp.snapshot_date
        AND JSON_EXTRACT_STRING(e.payload_json, '$.plan_id') = pu.plan_id
        THEN CAST(JSON_EXTRACT_STRING(e.payload_json, '$.eligibility_date') AS DATE)
      END
    ) AS eligibility_date,

    -- Latest enrollment date
    MAX(
      CASE
        WHEN e.event_type = 'enrollment'
        AND e.effective_date <= wp.snapshot_date
        AND JSON_EXTRACT_STRING(e.payload_json, '$.plan_id') = pu.plan_id
        THEN CAST(JSON_EXTRACT_STRING(e.payload_json, '$.enrollment_date') AS DATE)
      END
    ) AS enrollment_date

  FROM participant_universe pu
  CROSS JOIN weekly_periods wp
  LEFT JOIN {{ ref('fct_yearly_events') }} e
    ON e.employee_id = pu.participant_id
    AND e.scenario_id = pu.scenario_id
    AND e.plan_design_id = pu.plan_design_id
    AND (
      JSON_EXTRACT_STRING(e.payload_json, '$.plan_id') = pu.plan_id
      OR e.event_type IN ('hire', 'termination', 'promotion', 'merit')  -- Workforce events
    )

  -- Only include snapshots where participant has activity
  WHERE EXISTS (
    SELECT 1 FROM {{ ref('fct_yearly_events') }} activity
    WHERE activity.employee_id = pu.participant_id
    AND activity.effective_date <= wp.snapshot_date
    AND (
      JSON_EXTRACT_STRING(activity.payload_json, '$.plan_id') = pu.plan_id
      OR activity.event_type IN ('hire', 'eligibility')
    )
  )

  GROUP BY
    pu.participant_id,
    pu.plan_id,
    pu.scenario_id,
    pu.plan_design_id,
    wp.snapshot_date
),

-- Calculate derived metrics and final balances
final_snapshots AS (
  SELECT
    participant_id,
    plan_id,
    scenario_id,
    plan_design_id,
    snapshot_date,

    -- Core balance components
    total_employee_contributions,
    total_employer_contributions,
    total_forfeitures,

    -- Calculated balances
    total_employee_contributions + total_employer_contributions AS gross_account_balance,

    -- Vested balance calculation
    total_employee_contributions +
    (total_employer_contributions * current_vested_percentage) -
    total_forfeitures AS vested_account_balance,

    -- Unvested balance
    total_employer_contributions * (1 - current_vested_percentage) AS unvested_balance,

    -- Net account balance (after forfeitures)
    total_employee_contributions + total_employer_contributions - total_forfeitures AS net_account_balance,

    -- Status and metadata
    current_vested_percentage,
    service_years,
    is_enrolled,
    current_deferral_percentage,
    contribution_event_count,
    eligibility_date,
    enrollment_date,

    -- Snapshot metadata
    CURRENT_TIMESTAMP AS snapshot_created_at,

    -- Data quality flags
    CASE
      WHEN total_employee_contributions < 0 THEN 'negative_employee_balance'
      WHEN total_employer_contributions < 0 THEN 'negative_employer_balance'
      WHEN current_vested_percentage > 1.0 THEN 'invalid_vesting_percentage'
      WHEN current_vested_percentage < 0.0 THEN 'invalid_vesting_percentage'
      WHEN is_enrolled AND contribution_event_count = 0 THEN 'enrolled_no_contributions'
      WHEN NOT is_enrolled AND contribution_event_count > 0 THEN 'contributions_not_enrolled'
      ELSE 'valid'
    END AS data_quality_flag,

    -- Performance metrics for monitoring
    CASE
      WHEN snapshot_date = CURRENT_DATE - INTERVAL '7 days' THEN TRUE
      ELSE FALSE
    END AS is_current_week,

    -- Participation metrics
    CASE
      WHEN is_enrolled AND current_deferral_percentage > 0 THEN 'active_participant'
      WHEN is_enrolled AND current_deferral_percentage = 0 THEN 'enrolled_zero_deferral'
      WHEN eligibility_date IS NOT NULL AND NOT is_enrolled THEN 'eligible_not_enrolled'
      WHEN eligibility_date IS NULL THEN 'not_eligible'
      ELSE 'unknown_status'
    END AS participation_status

  FROM participant_balances

  -- Data quality filters
  WHERE total_employee_contributions >= 0
  AND total_employer_contributions >= 0
  AND current_vested_percentage BETWEEN 0.0000 AND 1.0000
)

SELECT
  participant_id,
  plan_id,
  scenario_id,
  plan_design_id,
  snapshot_date,
  total_employee_contributions,
  total_employer_contributions,
  total_forfeitures,
  gross_account_balance,
  vested_account_balance,
  unvested_balance,
  net_account_balance,
  current_vested_percentage,
  service_years,
  is_enrolled,
  current_deferral_percentage,
  contribution_event_count,
  eligibility_date,
  enrollment_date,
  participation_status,
  data_quality_flag,
  is_current_week,
  snapshot_created_at

FROM final_snapshots

{% if is_incremental() %}
  -- Incremental logic: only process new weekly snapshots
  WHERE snapshot_date > (
    SELECT COALESCE(MAX(snapshot_date), '1900-01-01'::DATE)
    FROM {{ this }}
  )
{% endif %}

ORDER BY
  participant_id,
  plan_id,
  snapshot_date
