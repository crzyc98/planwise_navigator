#!/usr/bin/env python3
"""
Simple Compensation Calibration Script

Based on S050 analysis, this script applies the recommended parameter adjustments
to achieve 2% compensation growth target.
"""

import duckdb
import pandas as pd
from planalign_orchestrator.config import get_database_path


def main():
    print("🎯 SIMPLE COMPENSATION CALIBRATION")
    print("=" * 50)

    conn = duckdb.connect(str(get_database_path()))

    # Show current compensation growth issue
    print("\n📊 Current Problem (from S050 analysis):")
    print("   - Current Growth: -3.7% (vs target +2.0%)")
    print("   - Gap: -5.7 percentage points")
    print("   - Cause: New hire dilution effect")

    # Strategy: Increase COLA and Merit rates to counteract dilution
    print("\n🔧 Applying Calibration Strategy:")
    print("   - Increase COLA: 2.5% → 4.0% (+1.5% impact)")
    print("   - Increase Merit: +1.0pp across all levels (+1.0% impact)")
    print("   - Expected Result: +2.5% total growth (above 2% target)")

    # Update COLA rates
    print("\n📈 Step 1: Updating COLA rates to 4.0%...")
    conn.execute(
        """
        UPDATE comp_levers
        SET parameter_value = 0.040
        WHERE parameter_name = 'cola_rate'
          AND scenario_id = 'default'
    """
    )

    # Update Merit rates
    print("📈 Step 2: Increasing merit rates by 1.0 percentage point...")
    merit_updates = [
        (1, 0.045),  # 3.5% -> 4.5%
        (2, 0.050),  # 4.0% -> 5.0%
        (3, 0.055),  # 4.5% -> 5.5%
        (4, 0.060),  # 5.0% -> 6.0%
        (5, 0.065),  # 5.5% -> 6.5%
    ]

    for job_level, new_rate in merit_updates:
        conn.execute(
            """
            UPDATE comp_levers
            SET parameter_value = ?
            WHERE parameter_name = 'merit_base'
              AND job_level = ?
              AND scenario_id = 'default'
        """,
            [new_rate, job_level],
        )
        print(f"   - Level {job_level}: {new_rate:.1%}")

    # Update the compensation growth target
    print("\n🎯 Step 3: Updating compensation growth target to 2.0%...")
    conn.execute(
        """
        UPDATE comp_targets
        SET target_value = 0.02
        WHERE metric_name = 'compensation_growth_rate'
          AND scenario_id = 'default'
    """
    )

    # Show updated parameters
    print("\n✅ Calibration Complete! Updated Parameters:")
    updated_params = conn.execute(
        """
        SELECT
            job_level,
            parameter_name,
            parameter_value,
            CASE parameter_name
                WHEN 'cola_rate' THEN CONCAT(ROUND(parameter_value * 100, 1), '%')
                WHEN 'merit_base' THEN CONCAT(ROUND(parameter_value * 100, 1), '%')
                ELSE CAST(parameter_value AS VARCHAR)
            END as display_value
        FROM stg_comp_levers
        WHERE scenario_id = 'default'
          AND fiscal_year = 2025
          AND parameter_name IN ('cola_rate', 'merit_base')
        ORDER BY job_level, parameter_name
    """
    ).df()

    print(updated_params.to_string(index=False))

    # Show next steps
    print("\n🚀 Next Steps:")
    print("   1. Run simulation: 'dagster dev' then materialize simulation assets")
    print("   2. Check results in fct_workforce_snapshot for new growth rates")
    print("   3. If growth is still not 2%, run iterative adjustments")
    print("   4. Monitor new hire dilution impact in real-time")

    print("\n📋 Quick Simulation Commands:")
    print("   dagster asset materialize --select simulation_year_state")
    print("   dagster asset materialize --select multi_year_simulation")

    conn.close()


if __name__ == "__main__":
    main()
