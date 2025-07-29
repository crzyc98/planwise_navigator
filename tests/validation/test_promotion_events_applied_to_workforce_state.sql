-- Test to validate that promotion events are properly applied to workforce snapshot
-- This ensures promotions "stick" and employee levels are correctly updated

-- Find promotions where the event level doesn't match the workforce snapshot level
SELECT
    p.employee_id,
    p.simulation_year,
    p.event_details,
    p.level_id as promotion_target_level,
    w.level_id as workforce_snapshot_level,
    p.compensation_amount as promotion_salary,
    w.employee_gross_compensation as snapshot_salary,
    'PROMOTION_NOT_APPLIED' as data_quality_issue
FROM {{ ref('fct_yearly_events') }} p
JOIN {{ ref('fct_workforce_snapshot') }} w 
    ON p.employee_id = w.employee_id 
    AND p.simulation_year = w.simulation_year
WHERE p.event_type = 'promotion'
    AND w.level_id != p.level_id  -- Promotion level should match workforce level
    AND w.employment_status = 'active'
    AND p.level_id IS NOT NULL
    AND w.level_id IS NOT NULL

-- Test should return 0 rows if promotion events are properly applied
HAVING COUNT(*) = 0