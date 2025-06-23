#!/usr/bin/env python3
"""
Validate that termination quotas are being met across all simulation years
"""

import duckdb
import math


def main():
    conn = duckdb.connect("/Users/nicholasamaral/planwise_navigator/simulation.duckdb")

    try:
        # Get all simulation years
        years = conn.execute(
            """
            SELECT DISTINCT simulation_year
            FROM fct_yearly_events
            ORDER BY simulation_year
        """
        ).fetchall()

        print("=== Termination Quota Validation ===")
        print("Year | Exp Pop | Expected | Actual | Quota Met")
        print("-" * 50)

        all_quotas_met = True

        for (year,) in years:
            # Get experienced population for this year
            if year == 2025:
                # For 2025, experienced = all baseline employees
                exp_pop = conn.execute(
                    """
                    SELECT COUNT(*) FROM int_baseline_workforce
                """
                ).fetchone()[0]
            else:
                # For subsequent years, get from previous year's active workforce
                exp_pop = conn.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = {year-1}
                      AND employment_status = 'active'
                      AND EXTRACT(YEAR FROM employee_hire_date) < {year-1}
                """
                ).fetchone()[0]

            # Calculate expected terminations
            expected = math.ceil(exp_pop * 0.12)

            # Get actual terminations
            actual = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM fct_yearly_events
                WHERE simulation_year = {year}
                  AND event_type = 'termination'
            """
            ).fetchone()[0]

            quota_met = actual >= expected
            status = "✅" if quota_met else "❌"

            print(
                f"{year} |   {exp_pop:3}   |    {expected:2}    |   {actual:2}   | {status}"
            )

            if not quota_met:
                all_quotas_met = False

        print("-" * 50)
        if all_quotas_met:
            print("🎉 All termination quotas met!")
        else:
            print("❌ Some termination quotas not met")

        # Show growth rates
        print("\n=== Growth Rate Analysis ===")
        result = conn.execute(
            """
            WITH yr AS (
              SELECT simulation_year,
                     SUM(CASE WHEN event_type='termination' THEN 1 END) AS terms,
                     SUM(CASE WHEN event_type='hire' THEN 1 END) AS hires
              FROM fct_yearly_events
              GROUP BY 1
            ), hc AS (
              SELECT simulation_year,
                     COUNT(*) AS actives
              FROM fct_workforce_snapshot
              WHERE employment_status='active'
              GROUP BY 1
            )
            SELECT
                yr.simulation_year,
                LAG(actives) OVER (ORDER BY yr.simulation_year) AS start_hc,
                terms, hires, actives AS end_hc,
                ROUND((actives - LAG(actives) OVER (ORDER BY yr.simulation_year))
                      *100.0 / LAG(actives) OVER (ORDER BY yr.simulation_year),1) AS pct_growth
            FROM yr
            JOIN hc USING (simulation_year)
            ORDER BY simulation_year
        """
        ).fetchall()

        print("Year | Start | Terms | Hires | End | Growth%")
        print("-" * 45)
        for row in result:
            year, start, terms, hires, end, growth = row
            start_str = str(int(start)) if start is not None else "N/A"
            growth_str = f"{growth}%" if growth is not None else "N/A"
            growth_ok = growth is not None and 2.5 <= growth <= 3.5
            status = "✅" if growth_ok else "❌" if growth is not None else ""
            print(
                f"{year} | {start_str:5} | {terms:5} | {hires:5} | {end:3} | {growth_str:6} {status}"
            )

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
