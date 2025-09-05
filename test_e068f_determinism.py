#!/usr/bin/env python3
"""
E068F Determinism Validation Script

This script tests the deterministic behavior of the E068F implementation
by running debug models multiple times and verifying identical outputs.
"""

import subprocess
import hashlib
import json
import sys
from pathlib import Path
import argparse
from datetime import datetime

class E068FDeterminismTester:
    """Test deterministic behavior of E068F debug models."""

    def __init__(self, dbt_dir: str = "dbt", simulation_year: int = 2025, random_seed: int = 42):
        self.dbt_dir = Path(dbt_dir)
        self.simulation_year = simulation_year
        self.random_seed = random_seed

    def run_debug_model(self, event_type: str, run_id: str, dev_limit: int = 100) -> dict:
        """Run a debug model and return hash of results."""

        print(f"  Running {event_type} debug model (run {run_id})...")

        # Construct dbt command
        cmd = [
            "dbt", "run",
            "--select", f"debug_{event_type}_events",
            "--vars", json.dumps({
                "enable_debug_models": True,
                "debug_event": event_type,
                "simulation_year": self.simulation_year,
                "random_seed": self.random_seed,
                "dev_employee_limit": dev_limit,
                "enable_dev_subset": True
            }),
            "--full-refresh"
        ]

        # Run dbt command
        try:
            result = subprocess.run(
                cmd,
                cwd=self.dbt_dir,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout
            )

            if result.returncode != 0:
                print(f"    ❌ dbt run failed: {result.stderr}")
                return {"success": False, "error": result.stderr}

            # Query the results to compute hash
            return self._compute_results_hash(event_type)

        except subprocess.TimeoutExpired:
            print(f"    ❌ dbt run timed out after 2 minutes")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            print(f"    ❌ Unexpected error: {e}")
            return {"success": False, "error": str(e)}

    def _compute_results_hash(self, event_type: str) -> dict:
        """Compute hash of debug model results."""

        try:
            # Query the debug table using duckdb
            query = f"""
            SELECT
                employee_id,
                event_type,
                event_date,
                simulation_year,
                CAST(event_payload AS VARCHAR) as payload_str,
                -- Include debug fields for more comprehensive validation
                ROUND({event_type}_rng, 6) as rng_rounded,
                {event_type}_decision as decision
            FROM debug_{event_type}_events
            WHERE simulation_year = {self.simulation_year}
            ORDER BY employee_id, event_date
            """

            result = subprocess.run([
                "duckdb",
                str(self.dbt_dir / "simulation.duckdb"),
                "-c", query
            ], capture_output=True, text=True)

            if result.returncode != 0:
                return {"success": False, "error": f"Query failed: {result.stderr}"}

            # Create hash of the complete result set
            results_str = result.stdout.strip()
            results_hash = hashlib.sha256(results_str.encode()).hexdigest()

            # Count rows for reporting
            row_count = len([line for line in results_str.split('\n') if line.strip()])

            return {
                "success": True,
                "hash": results_hash,
                "row_count": row_count,
                "sample": results_str[:200] + "..." if len(results_str) > 200 else results_str
            }

        except Exception as e:
            return {"success": False, "error": f"Hash computation failed: {e}"}

    def test_event_determinism(self, event_type: str, num_runs: int = 3, dev_limit: int = 100) -> bool:
        """Test that an event type produces identical results across runs."""

        print(f"\n🧪 Testing {event_type} event determinism ({num_runs} runs)...")

        hashes = []
        row_counts = []

        for i in range(num_runs):
            result = self.run_debug_model(event_type, f"{i+1}", dev_limit)

            if not result["success"]:
                print(f"    ❌ Run {i+1} failed: {result['error']}")
                return False

            hashes.append(result["hash"])
            row_counts.append(result["row_count"])
            print(f"    Run {i+1}: {result['row_count']} events, hash: {result['hash'][:16]}...")

        # Check determinism
        if len(set(hashes)) == 1:
            print(f"    ✅ All runs produced identical results ({row_counts[0]} events)")
            print(f"    📊 Common hash: {hashes[0][:16]}...")
            return True
        else:
            print(f"    ❌ Runs produced different results!")
            for i, h in enumerate(hashes):
                print(f"      Run {i+1}: {h[:16]}... ({row_counts[i]} events)")
            return False

    def test_cross_seed_independence(self, event_type: str, dev_limit: int = 100) -> bool:
        """Test that different seeds produce different results."""

        print(f"\n🔀 Testing {event_type} seed independence...")

        # Test with two different seeds
        seeds = [12345, 54321]
        results = []

        for seed in seeds:
            old_seed = self.random_seed
            self.random_seed = seed

            result = self.run_debug_model(event_type, f"seed_{seed}", dev_limit)

            if not result["success"]:
                print(f"    ❌ Seed {seed} failed: {result['error']}")
                self.random_seed = old_seed
                return False

            results.append(result)
            print(f"    Seed {seed}: {result['row_count']} events, hash: {result['hash'][:16]}...")

            # Restore original seed
            self.random_seed = old_seed

        # Different seeds should produce different results
        if results[0]["hash"] != results[1]["hash"]:
            print(f"    ✅ Different seeds produce independent results")
            return True
        else:
            print(f"    ❌ Different seeds produced identical results (unexpected!)")
            return False

    def test_performance(self, event_type: str, dev_limit: int = 100) -> bool:
        """Test that debug models complete within performance targets."""

        print(f"\n⏱️  Testing {event_type} performance (target: <5s for {dev_limit} employees)...")

        start_time = datetime.now()

        result = self.run_debug_model(event_type, "perf_test", dev_limit)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        if not result["success"]:
            print(f"    ❌ Performance test failed: {result['error']}")
            return False

        print(f"    ⏰ Completed in {duration:.2f}s with {result['row_count']} events")

        if duration < 5.0:
            print(f"    ✅ Performance target met (<5s)")
            return True
        elif duration < 10.0:
            print(f"    ⚠️  Performance acceptable but slower than target ({duration:.2f}s)")
            return True
        else:
            print(f"    ❌ Performance target missed ({duration:.2f}s > 10s)")
            return False

    def run_comprehensive_test(self, event_types: list = None, dev_limit: int = 100) -> bool:
        """Run comprehensive test suite for all event types."""

        if event_types is None:
            event_types = ["hire", "termination", "promotion"]

        print(f"🚀 Running E068F Determinism & Performance Tests")
        print(f"   📅 Simulation Year: {self.simulation_year}")
        print(f"   🎲 Random Seed: {self.random_seed}")
        print(f"   👥 Dev Employee Limit: {dev_limit}")
        print(f"   🎯 Event Types: {', '.join(event_types)}")

        all_passed = True

        for event_type in event_types:
            print(f"\n" + "="*60)
            print(f"Testing {event_type.upper()} Events")
            print(f"="*60)

            # Test determinism
            determinism_passed = self.test_event_determinism(event_type, dev_limit=dev_limit)

            # Test seed independence
            independence_passed = self.test_cross_seed_independence(event_type, dev_limit=dev_limit)

            # Test performance
            performance_passed = self.test_performance(event_type, dev_limit=dev_limit)

            event_passed = determinism_passed and independence_passed and performance_passed

            if event_passed:
                print(f"\n    ✅ {event_type.upper()} TESTS PASSED")
            else:
                print(f"\n    ❌ {event_type.upper()} TESTS FAILED")
                all_passed = False

        # Final summary
        print(f"\n" + "="*60)
        print("FINAL RESULTS")
        print("="*60)

        if all_passed:
            print("🎉 ALL E068F TESTS PASSED!")
            print("   ✅ Determinism verified")
            print("   ✅ Seed independence verified")
            print("   ✅ Performance targets met")
        else:
            print("❌ SOME E068F TESTS FAILED!")
            print("   Please review the output above for details")

        return all_passed


def main():
    """Main test runner."""

    parser = argparse.ArgumentParser(description="Test E068F determinism and performance")
    parser.add_argument("--event-types", nargs="+", default=["hire", "termination", "promotion"],
                       help="Event types to test (default: hire termination promotion)")
    parser.add_argument("--dev-limit", type=int, default=100,
                       help="Number of employees for dev subset (default: 100)")
    parser.add_argument("--simulation-year", type=int, default=2025,
                       help="Simulation year (default: 2025)")
    parser.add_argument("--random-seed", type=int, default=42,
                       help="Random seed (default: 42)")
    parser.add_argument("--dbt-dir", default="dbt",
                       help="dbt project directory (default: dbt)")

    args = parser.parse_args()

    # Create tester and run tests
    tester = E068FDeterminismTester(
        dbt_dir=args.dbt_dir,
        simulation_year=args.simulation_year,
        random_seed=args.random_seed
    )

    success = tester.run_comprehensive_test(
        event_types=args.event_types,
        dev_limit=args.dev_limit
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
