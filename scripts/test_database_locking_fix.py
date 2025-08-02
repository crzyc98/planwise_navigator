#!/usr/bin/env python3
"""
Simple test script to validate S031-04 database locking fix.

This script tests that the updated threading approach in common_workflow.py
prevents database locking conflicts that previously occurred with parallel
process execution.

Usage:
    python scripts/test_database_locking_fix.py
    python scripts/test_database_locking_fix.py --force-sequential
    python scripts/test_database_locking_fix.py --threads 8
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from orchestrator_mvp.core.common_workflow import (
    clear_database_and_setup,
    load_seed_data,
    create_staging_tables
)


def test_database_locking_fix(force_sequential: bool = False, threads: int = 4) -> Dict[str, Any]:
    """
    Test the database locking fix by running the critical operations that
    previously caused conflicts.

    Args:
        force_sequential: Force sequential execution mode
        threads: Number of threads for dbt to use

    Returns:
        Dictionary with test results including success status and timing
    """
    print("🧪 S031-04 Database Locking Fix Test")
    print("=" * 50)
    print(f"Mode: {'Sequential' if force_sequential else f'Threaded ({threads} threads)'}")
    print()

    results = {
        "success": False,
        "mode": "sequential" if force_sequential else "threaded",
        "threads": threads if not force_sequential else 1,
        "timing": {},
        "errors": []
    }

    try:
        # Step 1: Clear database (should always work)
        print("Step 1: Clearing database...")
        start_time = time.perf_counter()
        clear_database_and_setup()
        results["timing"]["database_clear"] = time.perf_counter() - start_time
        print(f"✅ Database cleared ({results['timing']['database_clear']:.2f}s)")

        # Step 2: Load seed data (should always work)
        print("\nStep 2: Loading seed data...")
        start_time = time.perf_counter()
        load_seed_data()
        results["timing"]["seed_load"] = time.perf_counter() - start_time
        print(f"✅ Seeds loaded ({results['timing']['seed_load']:.2f}s)")

        # Step 3: Create staging tables (this is where locking used to occur)
        print(f"\nStep 3: Creating staging tables ({'sequential' if force_sequential else f'threaded with {threads} threads'})...")
        start_time = time.perf_counter()

        # This is the critical test - create_staging_tables with the new threading approach
        create_staging_tables(
            use_threading=not force_sequential,
            thread_count=threads,
            force_sequential=force_sequential
        )

        results["timing"]["staging_tables"] = time.perf_counter() - start_time
        print(f"✅ Staging tables created ({results['timing']['staging_tables']:.2f}s)")

        # If we got here without errors, the fix worked
        results["success"] = True
        results["timing"]["total"] = sum(results["timing"].values())

        print(f"\n🎉 SUCCESS: Database locking fix validated!")
        print(f"Total time: {results['timing']['total']:.2f}s")

    except Exception as e:
        error_msg = str(e)
        results["errors"].append(error_msg)
        print(f"\n❌ FAILED: {error_msg}")

        # Check if this is the old database locking error
        if "Conflicting lock is held" in error_msg or "database is locked" in error_msg:
            print("🚨 This appears to be a database locking error - fix not working!")
        else:
            print("ℹ️  This is a different error, not related to database locking")

    return results


def compare_sequential_vs_threaded() -> Dict[str, Any]:
    """
    Run basic performance comparison between sequential and threaded modes.
    This is a minimal comparison focused on proving the fix works, not
    extensive benchmarking.

    Returns:
        Dictionary with comparison results
    """
    print("\n📊 Basic Performance Comparison: Sequential vs Threaded")
    print("=" * 60)
    print("Note: This is a basic comparison to validate the fix works.")
    print("For extensive performance analysis, use the full benchmarking suite.")
    print()

    comparison_results = {
        "sequential": None,
        "threaded": None,
        "comparison": {}
    }

    # Test sequential mode
    print("🔄 Testing Sequential Mode...")
    sequential_results = test_database_locking_fix(force_sequential=True)
    comparison_results["sequential"] = sequential_results

    if sequential_results["success"]:
        print(f"Sequential completed in {sequential_results['timing']['total']:.2f}s")
    else:
        print("Sequential mode failed!")
        return comparison_results

    # Brief pause between tests
    time.sleep(2)

    # Test threaded mode
    print("\n🔄 Testing Threaded Mode (4 threads)...")
    threaded_results = test_database_locking_fix(force_sequential=False, threads=4)
    comparison_results["threaded"] = threaded_results

    if threaded_results["success"]:
        print(f"Threaded completed in {threaded_results['timing']['total']:.2f}s")

        # Calculate basic comparison metrics
        sequential_time = sequential_results["timing"]["total"]
        threaded_time = threaded_results["timing"]["total"]

        if sequential_time > 0:
            speedup = sequential_time / threaded_time
            time_saved = sequential_time - threaded_time
            improvement_pct = ((sequential_time - threaded_time) / sequential_time) * 100

            comparison_results["comparison"] = {
                "speedup": speedup,
                "time_saved_seconds": time_saved,
                "improvement_percentage": improvement_pct,
                "faster_mode": "threaded" if threaded_time < sequential_time else "sequential"
            }

            print(f"\n📈 Basic Performance Results:")
            print(f"   Sequential: {sequential_time:.2f}s")
            print(f"   Threaded:   {threaded_time:.2f}s")
            if speedup > 1:
                print(f"   Speedup:    {speedup:.2f}x faster ({improvement_pct:.1f}% improvement)")
            else:
                print(f"   Result:     Sequential was {1/speedup:.2f}x faster")
            print(f"   Time saved: {abs(time_saved):.2f}s")
    else:
        print("Threaded mode failed!")

    return comparison_results


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Test S031-04 database locking fix",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--force-sequential", action="store_true",
                       help="Test sequential mode only")
    parser.add_argument("--threads", type=int, default=4,
                       help="Number of threads for threaded test (default: 4)")
    parser.add_argument("--compare", action="store_true", default=True,
                       help="Run performance comparison (default: enabled)")
    parser.add_argument("--no-compare", action="store_true",
                       help="Skip performance comparison")

    args = parser.parse_args()

    try:
        if args.force_sequential:
            # Test sequential mode only
            results = test_database_locking_fix(force_sequential=True)
            exit_code = 0 if results["success"] else 1

        elif args.no_compare:
            # Test threaded mode only
            results = test_database_locking_fix(force_sequential=False, threads=args.threads)
            exit_code = 0 if results["success"] else 1

        else:
            # Run comparison (default behavior)
            comparison_results = compare_sequential_vs_threaded()

            sequential_success = comparison_results.get("sequential", {}).get("success", False)
            threaded_success = comparison_results.get("threaded", {}).get("success", False)

            if sequential_success and threaded_success:
                print(f"\n✅ BOTH MODES WORKING: Database locking fix validated!")
                exit_code = 0
            elif sequential_success:
                print(f"\n⚠️  PARTIAL SUCCESS: Sequential works, threaded has issues")
                exit_code = 1
            elif threaded_success:
                print(f"\n⚠️  PARTIAL SUCCESS: Threaded works, sequential has issues")
                exit_code = 1
            else:
                print(f"\n❌ BOTH MODES FAILED: Database locking fix needs work")
                exit_code = 2

        print(f"\n🏁 Test completed with exit code: {exit_code}")
        return exit_code

    except KeyboardInterrupt:
        print("\n\n⏹️  Test interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
