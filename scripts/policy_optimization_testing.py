#!/usr/bin/env python3
"""
S052 Policy Parameter Optimization Testing Script
Systematic testing of all 35 COLA/Merit combinations for Epic E012 Phase 2B

This script:
1. Loads all 35 test scenarios from config/policy_test_scenarios.yaml
2. Dynamically modifies the dbt SQL model to test each scenario
3. Runs both Methodology A and C for each scenario
4. Collects comprehensive results for analysis
5. Identifies scenarios achieving 2% ± 0.5% growth target
6. Ranks by efficiency (minimal policy adjustment)

Usage:
    python scripts/policy_optimization_testing.py

Output:
    - results/policy_optimization_results_YYYYMMDD_HHMMSS.csv
    - Prints summary statistics and top recommendations
"""

from __future__ import annotations

import sys
import subprocess
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import pandas as pd
import duckdb


class PolicyOptimizationTester:
    """Systematic policy optimization testing framework"""

    def __init__(self, project_root: str = "/Users/nicholasamaral/planwise_navigator"):
        self.project_root = Path(project_root)
        self.scenarios_file = (
            self.project_root / "config" / "policy_test_scenarios.yaml"
        )
        self.dbt_project_dir = self.project_root / "dbt"
        self.model_file = (
            self.dbt_project_dir / "models" / "marts" / "fct_policy_optimization.sql"
        )
        self.db_file = self.project_root / "simulation.duckdb"
        self.results_dir = self.project_root / "results"

        # Ensure results directory exists
        self.results_dir.mkdir(exist_ok=True)

        # Load scenarios
        self.scenarios = self._load_scenarios()
        print(f"✓ Loaded {len(self.scenarios)} test scenarios")

    def _load_scenarios(self) -> Dict[str, Dict[str, Any]]:
        """Load test scenarios from YAML configuration"""
        try:
            with open(self.scenarios_file, "r") as f:
                config = yaml.safe_load(f)
            return config["scenarios"]
        except Exception as e:
            raise RuntimeError(
                f"Failed to load scenarios from {self.scenarios_file}: {e}"
            )

    def _create_dynamic_model(
        self, scenario_name: str, cola_rate: float, merit_budget: float
    ) -> str:
        """Create SQL model with dynamic scenario parameters"""

        # Read the base model template
        with open(self.model_file, "r") as f:
            base_sql = f.read()

        # Create dynamic SQL by replacing the hard-coded scenario logic
        # We'll inject the specific scenario parameters
        dynamic_sql = base_sql.replace(
            "CASE '{{ test_scenario }}'", f"CASE '{scenario_name}'"
        )

        # Replace the specific test values for this scenario
        dynamic_sql = dynamic_sql.replace(
            f"WHEN '{scenario_name}' THEN 0.025  -- Baseline",
            f"WHEN '{scenario_name}' THEN {cola_rate}",
        ).replace(
            f"WHEN '{scenario_name}' THEN 0.040  -- Baseline",
            f"WHEN '{scenario_name}' THEN {merit_budget}",
        )

        return dynamic_sql

    def _run_scenario_test(
        self, scenario_name: str, cola_rate: float, merit_budget: float
    ) -> pd.DataFrame:
        """Run a single scenario test and return results"""

        print(
            f"  Testing {scenario_name}: COLA {cola_rate*100:.1f}%, Merit {merit_budget*100:.1f}%"
        )

        try:
            # Run dbt model with scenario parameters using the new variable approach
            cmd = [
                "dbt",
                "run",
                "--models",
                "fct_policy_optimization",
                "--vars",
                f'{{"simulation_year": 2026, "test_scenario": "{scenario_name}", "test_cola_rate": {cola_rate}, "test_merit_budget": {merit_budget}}}',
            ]

            # Run dbt command without capturing output
            subprocess.run(cmd, cwd=self.dbt_project_dir, check=True)

            # Extract results from DuckDB
            with duckdb.connect(str(self.db_file)) as conn:
                df = conn.execute("SELECT * FROM fct_policy_optimization").df()

            # Add scenario metadata
            df["scenario_id"] = scenario_name
            df["test_cola_rate"] = cola_rate
            df["test_merit_budget"] = merit_budget

            return df

        except subprocess.CalledProcessError as e:
            print(f"    ❌ Failed to run scenario {scenario_name}: {e.stderr}")
            return pd.DataFrame()
        except Exception as e:
            print(f"    ❌ Error processing scenario {scenario_name}: {e}")
            return pd.DataFrame()

    def run_all_scenarios(self) -> pd.DataFrame:
        """Run all 35 test scenarios and collect results"""

        print("\n🚀 Starting systematic policy optimization testing...")
        print(f"   Testing {len(self.scenarios)} scenarios across both methodologies")

        all_results = []
        failed_scenarios = []

        # Track progress
        scenario_count = 0
        total_scenarios = len(self.scenarios)

        for scenario_id, scenario_config in self.scenarios.items():
            scenario_count += 1
            print(f"\n[{scenario_count}/{total_scenarios}] Processing {scenario_id}")

            cola_rate = scenario_config["cola_rate"]
            merit_budget = scenario_config["merit_budget"]

            # Run the scenario test
            scenario_results = self._run_scenario_test(
                scenario_id, cola_rate, merit_budget
            )

            if not scenario_results.empty:
                # Add additional metadata
                scenario_results["scenario_category"] = scenario_config.get(
                    "category", "unknown"
                )
                scenario_results["scenario_description"] = scenario_config.get(
                    "name", scenario_id
                )
                all_results.append(scenario_results)
                print(f"    ✓ Completed {scenario_id}")
            else:
                failed_scenarios.append(scenario_id)
                print(f"    ❌ Failed {scenario_id}")

        if failed_scenarios:
            print(
                f"\n⚠️  {len(failed_scenarios)} scenarios failed: {', '.join(failed_scenarios)}"
            )

        # Combine all results
        if all_results:
            combined_results = pd.concat(all_results, ignore_index=True)
            print(
                f"\n✅ Successfully collected results from {len(all_results)} scenarios"
            )
            return combined_results
        else:
            raise RuntimeError("No scenarios completed successfully")

    def analyze_results(self, results_df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze results to identify optimal scenarios"""

        print("\n📊 Analyzing results...")

        # Filter for target-achieving scenarios (2% ± 0.5%)
        target_scenarios = results_df[
            (results_df["simulated_growth_pct"] >= 1.5)
            & (results_df["simulated_growth_pct"] <= 2.5)
        ].copy()

        print(f"   Target-achieving scenarios: {len(target_scenarios)}")

        # Calculate efficiency metrics
        target_scenarios["efficiency_rank"] = target_scenarios.groupby(
            "calculation_method"
        )["deviation_from_target"].rank()
        target_scenarios["policy_adjustment_rank"] = target_scenarios.groupby(
            "calculation_method"
        )["total_policy_adjustment_pct"].rank()
        target_scenarios["combined_efficiency_score"] = (
            target_scenarios["efficiency_rank"]
            + target_scenarios["policy_adjustment_rank"]
        )

        # Get top recommendations by methodology
        methodology_a_top = target_scenarios[
            target_scenarios["calculation_method"] == "methodology_a_current"
        ].nsmallest(5, "combined_efficiency_score")

        methodology_c_top = target_scenarios[
            target_scenarios["calculation_method"] == "methodology_c_full_year"
        ].nsmallest(5, "combined_efficiency_score")

        analysis = {
            "total_scenarios_tested": len(results_df["scenario_id"].unique()),
            "target_achieving_scenarios": len(target_scenarios),
            "methodology_a_target_count": len(
                target_scenarios[
                    target_scenarios["calculation_method"] == "methodology_a_current"
                ]
            ),
            "methodology_c_target_count": len(
                target_scenarios[
                    target_scenarios["calculation_method"] == "methodology_c_full_year"
                ]
            ),
            "methodology_a_top_recommendations": methodology_a_top,
            "methodology_c_top_recommendations": methodology_c_top,
            "all_target_scenarios": target_scenarios,
        }

        return analysis

    def save_results(self, results_df: pd.DataFrame, analysis: Dict[str, Any]) -> str:
        """Save results to CSV files"""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save complete results
        results_file = self.results_dir / f"policy_optimization_results_{timestamp}.csv"
        results_df.to_csv(results_file, index=False)

        # Save target-achieving scenarios summary
        summary_file = self.results_dir / f"policy_optimization_summary_{timestamp}.csv"
        analysis["all_target_scenarios"].to_csv(summary_file, index=False)

        # Save top recommendations
        recommendations_file = (
            self.results_dir / f"policy_optimization_recommendations_{timestamp}.csv"
        )

        # Combine top recommendations from both methodologies
        top_recommendations = pd.concat(
            [
                analysis["methodology_a_top_recommendations"],
                analysis["methodology_c_top_recommendations"],
            ],
            ignore_index=True,
        )

        top_recommendations.to_csv(recommendations_file, index=False)

        print("\n💾 Results saved:")
        print(f"   Complete results: {results_file}")
        print(f"   Target scenarios: {summary_file}")
        print(f"   Top recommendations: {recommendations_file}")

        return str(results_file)

    def print_summary(self, analysis: Dict[str, Any]):
        """Print analysis summary to console"""

        print("\n" + "=" * 80)
        print("🎯 POLICY OPTIMIZATION TESTING SUMMARY")
        print("=" * 80)

        print(f"Total scenarios tested: {analysis['total_scenarios_tested']}")
        print(
            f"Target-achieving scenarios (2% ± 0.5%): {analysis['target_achieving_scenarios']}"
        )
        print(f"  - Methodology A (Current): {analysis['methodology_a_target_count']}")
        print(
            f"  - Methodology C (Full-year): {analysis['methodology_c_target_count']}"
        )

        print("\n🏆 TOP RECOMMENDATIONS - METHODOLOGY A (Current):")
        if not analysis["methodology_a_top_recommendations"].empty:
            for idx, row in (
                analysis["methodology_a_top_recommendations"].head(3).iterrows()
            ):
                print(
                    f"   {row['scenario_id']}: COLA {row['cola_rate_pct']}%, Merit {row['merit_budget_pct']}% "
                    f"→ {row['simulated_growth_pct']:.2f}% growth (deviation: {row['deviation_from_target']:.2f})"
                )
        else:
            print("   No scenarios achieved target for Methodology A")

        print("\n🏆 TOP RECOMMENDATIONS - METHODOLOGY C (Full-year):")
        if not analysis["methodology_c_top_recommendations"].empty:
            for idx, row in (
                analysis["methodology_c_top_recommendations"].head(3).iterrows()
            ):
                print(
                    f"   {row['scenario_id']}: COLA {row['cola_rate_pct']}%, Merit {row['merit_budget_pct']}% "
                    f"→ {row['simulated_growth_pct']:.2f}% growth (deviation: {row['deviation_from_target']:.2f})"
                )
        else:
            print("   No scenarios achieved target for Methodology C")

        print("\n" + "=" * 80)


def main():
    """Main execution function"""

    try:
        # Initialize tester
        tester = PolicyOptimizationTester()

        # Run all scenarios
        results = tester.run_all_scenarios()

        # Analyze results
        analysis = tester.analyze_results(results)

        # Save results
        results_file = tester.save_results(results, analysis)

        # Print summary
        tester.print_summary(analysis)

        print("\n✅ Policy optimization testing completed successfully!")
        print(f"📁 Results available at: {results_file}")

    except Exception as e:
        print(f"\n❌ Policy optimization testing failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
