#!/usr/bin/env python3
"""
Compensation Growth Calibration Script

This script allows you to manually adjust compensation parameters
to achieve the 2% target growth rate based on S050 analysis findings.
"""

from typing import Dict, List, Optional

import duckdb
import pandas as pd


class CompensationCalibrator:
    def __init__(self, db_path: str = "simulation.duckdb"):
        self.db_path = db_path

    def get_connection(self):
        return duckdb.connect(self.db_path)

    def show_current_parameters(self, scenario_id: str = "default") -> pd.DataFrame:
        """Display current parameter values."""
        with self.get_connection() as conn:
            return conn.execute(
                """
                SELECT
                    job_level,
                    parameter_name,
                    parameter_value,
                    fiscal_year
                FROM stg_comp_levers
                WHERE scenario_id = ?
                ORDER BY fiscal_year, job_level, parameter_name
            """,
                [scenario_id],
            ).df()

    def show_current_targets(self, scenario_id: str = "default") -> pd.DataFrame:
        """Display current targets."""
        with self.get_connection() as conn:
            return conn.execute(
                """
                SELECT
                    metric_name,
                    target_value,
                    tolerance_pct,
                    priority,
                    description
                FROM stg_comp_targets
                WHERE scenario_id = ?
                ORDER BY priority, metric_name
            """,
                [scenario_id],
            ).df()

    def update_parameter(
        self,
        scenario_id: str,
        job_level: int,
        parameter_name: str,
        new_value: float,
        fiscal_year: int = 2025,
    ):
        """Update a specific parameter value."""
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE comp_levers
                SET parameter_value = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE scenario_id = ?
                  AND job_level = ?
                  AND parameter_name = ?
                  AND fiscal_year = ?
            """,
                [new_value, scenario_id, job_level, parameter_name, fiscal_year],
            )
            print(f"✅ Updated {parameter_name} for Level {job_level} to {new_value}")

    def create_calibration_scenario(
        self, new_scenario_id: str, base_scenario_id: str = "default"
    ) -> str:
        """Create a new scenario for calibration testing."""
        with self.get_connection() as conn:
            # Copy base scenario parameters
            conn.execute(
                """
                INSERT INTO comp_levers
                SELECT
                    ? as scenario_id,
                    fiscal_year,
                    job_level,
                    event_type,
                    parameter_name,
                    parameter_value,
                    is_locked,
                    CURRENT_TIMESTAMP as created_at,
                    'calibration_script' as created_by
                FROM comp_levers
                WHERE scenario_id = ?
            """,
                [new_scenario_id, base_scenario_id],
            )

            # Copy targets
            conn.execute(
                """
                INSERT INTO comp_targets
                SELECT
                    ? as scenario_id,
                    fiscal_year,
                    metric_name,
                    target_value,
                    tolerance_pct,
                    priority,
                    description,
                    CURRENT_TIMESTAMP as created_at,
                    'calibration_script' as created_by
                FROM comp_targets
                WHERE scenario_id = ?
            """,
                [new_scenario_id, base_scenario_id],
            )

            print(f"✅ Created calibration scenario: {new_scenario_id}")
            return new_scenario_id

    def apply_s050_recommendations(self, scenario_id: str):
        """Apply the specific recommendations from S050 analysis."""
        print(f"🎯 Applying S050 recommendations to scenario: {scenario_id}")

        # Based on S050 analysis, the primary levers are:
        # 1. Increase COLA rates to counteract new hire dilution
        # 2. Increase merit rates to boost existing employee compensation

        # Strategy 1: Increase COLA from 2.5% to 4.0% (+1.5% overall growth impact)
        print("\n📈 Phase 1: Increasing COLA rates to 4.0%")
        for job_level in range(1, 6):
            self.update_parameter(scenario_id, job_level, "cola_rate", 0.040, 2025)
            self.update_parameter(scenario_id, job_level, "cola_rate", 0.040, 2026)

        # Strategy 2: Increase merit rates by 1.0 percentage point (+1.0% overall growth impact)
        print("\n🎯 Phase 2: Increasing merit rates by 1.0 percentage point")
        merit_increases = {
            1: 0.045,  # 3.5% -> 4.5%
            2: 0.050,  # 4.0% -> 5.0%
            3: 0.055,  # 4.5% -> 5.5%
            4: 0.060,  # 5.0% -> 6.0%
            5: 0.065,  # 5.5% -> 6.5%
        }

        for job_level, new_merit_rate in merit_increases.items():
            self.update_parameter(
                scenario_id, job_level, "merit_base", new_merit_rate, 2025
            )
            self.update_parameter(
                scenario_id, job_level, "merit_base", new_merit_rate, 2026
            )

        print("\n✅ S050 recommendations applied!")
        print(
            "Combined impact: +4.0% COLA + Enhanced Merit = Expected +2.5% overall growth"
        )

    def run_simulation_with_scenario(self, scenario_id: str):
        """Run a simulation with the calibrated parameters."""
        print(f"\n🚀 To run simulation with scenario '{scenario_id}':")
        print(f"   1. Start Dagster: dagster dev")
        print(
            f"   2. Run simulation with scenario variable: --vars scenario_id:{scenario_id}"
        )
        print(
            f"   3. Check results in fct_workforce_snapshot WHERE parameter_scenario_id = '{scenario_id}'"
        )


def main():
    """Main calibration workflow."""
    calibrator = CompensationCalibrator()

    print("🎛️ COMPENSATION GROWTH CALIBRATION TOOL")
    print("=" * 50)

    # Show current state
    print("\n📊 Current Parameters:")
    current_params = calibrator.show_current_parameters()
    print(current_params.head(10).to_string(index=False))

    print("\n🎯 Current Targets:")
    targets = calibrator.show_current_targets()
    print(targets.to_string(index=False))

    # Create calibration scenario
    scenario_id = "calibration_v1"
    calibrator.create_calibration_scenario(scenario_id)

    # Apply S050 recommendations
    calibrator.apply_s050_recommendations(scenario_id)

    # Show updated parameters
    print("\n📊 Updated Parameters for Calibration:")
    updated_params = calibrator.show_current_parameters(scenario_id)
    print(updated_params.head(10).to_string(index=False))

    # Instructions for running simulation
    calibrator.run_simulation_with_scenario(scenario_id)


if __name__ == "__main__":
    main()
