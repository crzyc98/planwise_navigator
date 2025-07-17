#!/usr/bin/env python3
"""MVP Orchestrator for debugging dbt models.

Interactive script to clear the database, run dbt models one by one,
and inspect results with detailed validation.
"""

import os
import sys

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import clear_database
from loaders import run_dbt_model
from inspectors import inspect_stg_census_data


def main() -> None:
    """Main orchestrator workflow."""
    print("\n" + "="*60)
    print("🚀 PLANWISE NAVIGATOR - MVP ORCHESTRATOR")
    print("="*60)
    print("\nThis tool will help you debug dbt models by running them")
    print("individually and inspecting the results at each step.")

    try:
        # Step 1: Clear database
        input("\n📋 Press Enter to clear the database...")
        clear_database()

        # Step 2: Run stg_census_data
        input("\n📋 Press Enter to run stg_census_data model...")
        run_dbt_model("stg_census_data")

        # Step 3: Inspect census data
        input("\n📋 Press Enter to inspect census data...")
        inspect_stg_census_data()

        print("\n✨ Foundational data looks good!")
        print("Now let's build on top of it...")

        # Step 4: Run int_baseline_workforce
        input("\n📋 Press Enter to run int_baseline_workforce model...")
        run_dbt_model("int_baseline_workforce")

        # Completion message
        print("\n" + "="*60)
        print("✅ MVP ORCHESTRATOR COMPLETED SUCCESSFULLY!")
        print("="*60)
        print("\nYou can now:")
        print("  1. Run additional models with run_dbt_model()")
        print("  2. Create new inspector functions for other tables")
        print("  3. Query the database directly with DuckDB")
        print("\nHappy debugging! 🎉")

    except KeyboardInterrupt:
        print("\n\n⚠️  Orchestrator interrupted by user.")
        sys.exit(1)

    except Exception as e:
        print(f"\n\n❌ FATAL ERROR: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
