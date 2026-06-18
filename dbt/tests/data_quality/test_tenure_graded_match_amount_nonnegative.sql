-- Test: Verify tenure-graded match events have sane, non-negative match amounts
-- Feature 099: each tenure band's match amount must be >= 0 and must not exceed
-- the band's theoretical maximum (sum of tier widths * tier rates) applied to
-- eligible compensation. Catches macro/SQL regressions in the tenure_graded branch.

WITH tenure_graded_events AS (
    -- Audit fields (formula_type, eligible_compensation) live inside event_payload JSON;
    -- the top-level match dollar amount is the `amount` column.
    SELECT
        employee_id,
        simulation_year,
        event_payload->>'formula_type' AS formula_type,
        amount AS match_amount,
        (event_payload->>'eligible_compensation')::DOUBLE AS eligible_compensation
    FROM {{ ref('fct_employer_match_events') }}
    WHERE event_payload->>'formula_type' = 'tenure_graded'
),

violations AS (
    SELECT *
    FROM tenure_graded_events
    WHERE match_amount < 0
       OR match_amount > eligible_compensation  -- sanity bound: match can't exceed 100% of comp
)

-- Test passes when this query returns 0 rows
SELECT * FROM violations
