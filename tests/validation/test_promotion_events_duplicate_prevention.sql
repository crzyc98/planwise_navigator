-- Test to ensure no employee receives multiple promotion events in the same year
-- This test validates the anti-join logic in int_promotion_events.sql

SELECT
    employee_id,
    simulation_year,
    COUNT(*) as promotion_count,
    'Employee ' || employee_id || ' has ' || COUNT(*) || ' promotion events in year ' || simulation_year || '. Expected: 1 per employee per year.' as error_message
FROM {{ ref('int_promotion_events') }}
GROUP BY employee_id, simulation_year
HAVING COUNT(*) > 1
