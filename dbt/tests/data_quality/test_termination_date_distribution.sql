{{
  config(
    severity='error',
    tags=['data_quality', 'events', 'termination', 'distribution']
  )
}}

/*
  Data Quality Test: Termination Date Distribution

  Validates that termination dates are distributed across all months
  rather than clustering on a single date.

  Success Criteria (SC-001):
  - No single month should have >20% of terminations
  - Distribution should be roughly uniform across the year

  Bug Fix: Addresses the issue where all terminations were
  clustering on September 15 (day 258) due to hash collision.

  Returns rows for any month that has more than 20% of terminations.
*/

WITH monthly_counts AS (
    SELECT
        EXTRACT(MONTH FROM effective_date) AS term_month,
        COUNT(*) AS month_count,
        SUM(COUNT(*)) OVER() AS total_count
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'termination'
      AND simulation_year = {{ var('simulation_year') }}
    GROUP BY 1
),

distribution_check AS (
    SELECT
        term_month,
        month_count,
        total_count,
        ROUND(month_count * 100.0 / NULLIF(total_count, 0), 2) AS percentage
    FROM monthly_counts
)

SELECT
    term_month,
    month_count,
    total_count,
    percentage,
    CONCAT(
        'Month ', term_month, ' has ', percentage,
        '% of terminations (', month_count, ' of ', total_count,
        '), which exceeds the 20% threshold'
    ) as issue_description,
    'ERROR' as severity
FROM distribution_check
WHERE percentage > 20
ORDER BY term_month
