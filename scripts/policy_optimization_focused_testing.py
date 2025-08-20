#!/usr/bin/env python3
"""
S052 Focused Policy Parameter Optimization Testing
Testing realistic policy adjustments based on initial findings

Initial findings showed that all original scenarios (2.5%-4.5% COLA, 4%-10% Merit)
produced growth rates far above the 2% target. This focused test uses much smaller
policy adjustments to find scenarios that actually achieve the target.

Usage:
    python scripts/policy_optimization_focused_testing.py
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import duckdb
import pandas as pd
import yaml


class FocusedPolicyTester:
    """Focused policy optimization testing with realistic parameters"""

    def __init__(self, project_root: str = "/Users/nicholasamaral/planwise_navigator"):
        self.project_root = Path(project_root)
        self.scenarios_file = (
            self.project_root / "config" / "policy_test_scenarios_revised.yaml"
        )
        self.dbt_project_dir = self.project_root / "dbt"
        self.db_file = self.project_root / "simulation.duckdb"
        self.results_dir = self.project_root / "results"

        # Ensure results directory exists
        self.results_dir.mkdir(exist_ok=True)

        # Load scenarios
        self.scenarios = self._load_scenarios()
        print(f"✓ Loaded {len(self.scenarios)} focused test scenarios")

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

    def _run_scenario_test(
        self, scenario_name: str, cola_rate: float, merit_budget: float
    ) -> pd.DataFrame:
        """Run a single scenario test and return results"""

        print(
            f"  Testing {scenario_name}: COLA {cola_rate*100:.1f}%, Merit {merit_budget*100:.1f}%"
        )

        try:
            # Run dbt model with scenario parameters
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

    def run_focused_testing(self) -> pd.DataFrame:
        """Run focused policy optimization testing"""

        print("\n🎯 Starting focused policy optimization testing...")
        print(f"   Testing {len(self.scenarios)} realistic scenarios")

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

                # Print immediate results for analysis
                for _, row in scenario_results.iterrows():
                    method = (
                        "Method A"
                        if row["calculation_method"] == "methodology_a_current"
                        else "Method C"
                    )
                    growth = row["simulated_growth_pct"]
                    status = "🎯 TARGET" if 1.5 <= growth <= 2.5 else "❌ Off-target"
                    print(f"    {method}: {growth:.2f}% growth {status}")

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

    def analyze_focused_results(self, results_df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze focused testing results"""

        print("\n📊 Analyzing focused testing results...")

        # Filter for target-achieving scenarios (2% ± 0.5%)
        target_scenarios = results_df[
            (results_df["simulated_growth_pct"] >= 1.5)
            & (results_df["simulated_growth_pct"] <= 2.5)
        ].copy()

        print(f"   🎯 Target-achieving scenarios: {len(target_scenarios)}")

        if len(target_scenarios) > 0:
            # Calculate efficiency metrics for target scenarios
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
            methodology_a_targets = target_scenarios[
                target_scenarios["calculation_method"] == "methodology_a_current"
            ]
            methodology_c_targets = target_scenarios[
                target_scenarios["calculation_method"] == "methodology_c_full_year"
            ]

            methodology_a_top = (
                methodology_a_targets.nsmallest(5, "combined_efficiency_score")
                if len(methodology_a_targets) > 0
                else pd.DataFrame()
            )
            methodology_c_top = (
                methodology_c_targets.nsmallest(5, "combined_efficiency_score")
                if len(methodology_c_targets) > 0
                else pd.DataFrame()
            )
        else:
            methodology_a_top = pd.DataFrame()
            methodology_c_top = pd.DataFrame()
            target_scenarios = pd.DataFrame()

        # Also find closest scenarios even if not in target range
        methodology_a_all = results_df[
            results_df["calculation_method"] == "methodology_a_current"
        ].copy()
        methodology_c_all = results_df[
            results_df["calculation_method"] == "methodology_c_full_year"
        ].copy()

        methodology_a_all["deviation_abs"] = abs(
            methodology_a_all["simulated_growth_pct"] - 2.0
        )
        methodology_c_all["deviation_abs"] = abs(
            methodology_c_all["simulated_growth_pct"] - 2.0
        )

        methodology_a_closest = methodology_a_all.nsmallest(5, "deviation_abs")
        methodology_c_closest = methodology_c_all.nsmallest(5, "deviation_abs")

        analysis = {
            "total_scenarios_tested": len(results_df["scenario_id"].unique()),
            "target_achieving_scenarios": len(target_scenarios),
            "methodology_a_target_count": len(methodology_a_targets)
            if len(target_scenarios) > 0
            else 0,
            "methodology_c_target_count": len(methodology_c_targets)
            if len(target_scenarios) > 0
            else 0,
            "methodology_a_top_recommendations": methodology_a_top,
            "methodology_c_top_recommendations": methodology_c_top,
            "methodology_a_closest": methodology_a_closest,
            "methodology_c_closest": methodology_c_closest,
            "all_target_scenarios": target_scenarios,
            "all_results": results_df,
        }

        return analysis

    def save_focused_results(
        self, results_df: pd.DataFrame, analysis: Dict[str, Any]
    ) -> str:
        """Save focused testing results"""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save complete results
        results_file = (
            self.results_dir / f"policy_optimization_focused_results_{timestamp}.csv"
        )
        results_df.to_csv(results_file, index=False)

        # Save analysis summary
        summary_file = (
            self.results_dir / f"policy_optimization_focused_analysis_{timestamp}.csv"
        )

        # Combine target scenarios and closest scenarios for comprehensive analysis
        if not analysis["all_target_scenarios"].empty:
            analysis["all_target_scenarios"].to_csv(summary_file, index=False)
        else:
            # If no target scenarios, save the closest ones
            closest_combined = pd.concat(
                [
                    analysis["methodology_a_closest"].head(3),
                    analysis["methodology_c_closest"].head(3),
                ],
                ignore_index=True,
            )
            closest_combined.to_csv(summary_file, index=False)

        print("\n💾 Focused testing results saved:")
        print(f"   Complete results: {results_file}")
        print(f"   Analysis summary: {summary_file}")

        return str(results_file)

    def print_focused_summary(self, analysis: Dict[str, Any]):
        """Print focused analysis summary"""

        print("\n" + "=" * 80)
        print("🎯 FOCUSED POLICY OPTIMIZATION RESULTS")
        print("=" * 80)

        print(f"Total scenarios tested: {analysis['total_scenarios_tested']}")
        print(
            f"Target-achieving scenarios (2% ± 0.5%): {analysis['target_achieving_scenarios']}"
        )

        if analysis["target_achieving_scenarios"] > 0:
            print(
                f"  - Methodology A (Current): {analysis['methodology_a_target_count']}"
            )
            print(
                f"  - Methodology C (Full-year): {analysis['methodology_c_target_count']}"
            )

            print("\n🏆 TOP TARGET-ACHIEVING SCENARIOS:")

            if not analysis["methodology_a_top_recommendations"].empty:
                print("\nMethodology A (Current):")
                for idx, row in (
                    analysis["methodology_a_top_recommendations"].head(3).iterrows()
                ):
                    print(
                        f"   {row['scenario_id']}: COLA {row['cola_rate_pct']}%, Merit {row['merit_budget_pct']}% "
                        f"→ {row['simulated_growth_pct']:.2f}% (deviation: {row['deviation_from_target']:.2f})"
                    )

            if not analysis["methodology_c_top_recommendations"].empty:
                print("\nMethodology C (Full-year):")
                for idx, row in (
                    analysis["methodology_c_top_recommendations"].head(3).iterrows()
                ):
                    print(
                        f"   {row['scenario_id']}: COLA {row['cola_rate_pct']}%, Merit {row['merit_budget_pct']}% "
                        f"→ {row['simulated_growth_pct']:.2f}% (deviation: {row['deviation_from_target']:.2f})"
                    )
        else:
            print("\n⚠️  No scenarios achieved the target range")
            print("\n🔍 CLOSEST SCENARIOS TO TARGET (2.0%):")

            print("\nMethodology A (Current) - Closest:")
            for idx, row in analysis["methodology_a_closest"].head(3).iterrows():
                print(
                    f"   {row['scenario_id']}: COLA {row['cola_rate_pct']}%, Merit {row['merit_budget_pct']}% "
                    f"→ {row['simulated_growth_pct']:.2f}% (deviation: {row['deviation_abs']:.2f})"
                )

            print("\nMethodology C (Full-year) - Closest:")
            for idx, row in analysis["methodology_c_closest"].head(3).iterrows():
                print(
                    f"   {row['scenario_id']}: COLA {row['cola_rate_pct']}%, Merit {row['merit_budget_pct']}% "
                    f"→ {row['simulated_growth_pct']:.2f}% (deviation: {row['deviation_abs']:.2f})"
                )

        # Growth rate distribution
        results_df = analysis["all_results"]
        methodology_a = results_df[
            results_df["calculation_method"] == "methodology_a_current"
        ]
        methodology_c = results_df[
            results_df["calculation_method"] == "methodology_c_full_year"
        ]

        print("\n📈 GROWTH RATE DISTRIBUTION:")
        print(
            f"Methodology A: {methodology_a['simulated_growth_pct'].min():.2f}% - {methodology_a['simulated_growth_pct'].max():.2f}% (avg: {methodology_a['simulated_growth_pct'].mean():.2f}%)"
        )
        print(
            f"Methodology C: {methodology_c['simulated_growth_pct'].min():.2f}% - {methodology_c['simulated_growth_pct'].max():.2f}% (avg: {methodology_c['simulated_growth_pct'].mean():.2f}%)"
        )

        print("\n" + "=" * 80)


def main():
    """Main execution function"""

    try:
        # Initialize focused tester
        tester = FocusedPolicyTester()

        # Run focused testing
        results = tester.run_focused_testing()

        # Analyze results
        analysis = tester.analyze_focused_results(results)

        # Save results
        results_file = tester.save_focused_results(results, analysis)

        # Print summary
        tester.print_focused_summary(analysis)

        print("\n✅ Focused policy optimization testing completed!")
        print(f"📁 Results available at: {results_file}")

    except Exception as e:
        print(f"\n❌ Focused policy optimization testing failed: {e}")
        raise


if __name__ == "__main__":
    main()
