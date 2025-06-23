#!/usr/bin/env python3
"""
Test script for Story S037 validation
Validates baseline workforce and expected growth patterns
"""

import duckdb
import sys


def test_baseline_workforce():
    """Test that baseline workforce has exactly 95 active employees"""
    conn = duckdb.connect("simulation.duckdb")
    try:
        baseline_count = conn.execute(
            "SELECT COUNT(*) FROM int_baseline_workforce WHERE employment_status = 'active'"
        ).fetchone()[0]

        print(f"Baseline active employees: {baseline_count}")

        if baseline_count != 95:
            print(f"❌ Expected baseline of 95, got {baseline_count}")
            return False
        else:
            print("✅ Baseline count matches expected value of 95")
            return True

    except Exception as e:
        print(f"Error checking baseline: {e}")
        return False
    finally:
        conn.close()


def test_simulation_growth():
    """Test simulation growth from 2025-2029 reaches approximately 107 employees"""
    conn = duckdb.connect("simulation.duckdb")
    try:
        # Check if simulation data exists
        years_data = conn.execute(
            """
            SELECT simulation_year, COUNT(*) as active_count
            FROM fct_workforce_snapshot
            WHERE employment_status = 'active'
            GROUP BY simulation_year
            ORDER BY simulation_year
        """
        ).fetchall()

        if not years_data:
            print("⚠️  No simulation data found. Run simulation first.")
            return False

        print("Simulation results:")
        for year, count in years_data:
            print(f"  {year}: {count} active employees")

        # Check 2029 result (last year)
        final_year_data = [row for row in years_data if row[0] == 2029]
        if final_year_data:
            final_count = final_year_data[0][1]
            target_range = (105, 110)  # Allow some tolerance around 107

            if target_range[0] <= final_count <= target_range[1]:
                print(
                    f"✅ Final workforce {final_count} is within target range {target_range}"
                )
                return True
            else:
                print(
                    f"❌ Final workforce {final_count} is outside target range {target_range}"
                )
                return False
        else:
            print("⚠️  No 2029 data found")
            return False

    except Exception as e:
        print(f"Error checking simulation: {e}")
        return False
    finally:
        conn.close()


def main():
    """Run all tests"""
    print("Running Story S037 validation tests...")
    print("=" * 50)

    baseline_ok = test_baseline_workforce()
    print()

    growth_ok = test_simulation_growth()
    print()

    if baseline_ok and growth_ok:
        print("🎉 All tests passed!")
        return 0
    else:
        print("💥 Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
