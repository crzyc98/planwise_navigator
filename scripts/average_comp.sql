WITH yearly_avg AS (
    SELECT
        simulation_year,
        AVG(current_compensation) as avg_comp
    FROM main.fct_workforce_snapshot
    GROUP BY simulation_year
)
SELECT
    simulation_year,
    avg_comp,
    (avg_comp - LAG(avg_comp) OVER (ORDER BY simulation_year))
        / LAG(avg_comp) OVER (ORDER BY simulation_year) * 100 as growth_pct
FROM yearly_avg
ORDER BY simulation_year
