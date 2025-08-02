#!/usr/bin/env python3
"""
Foundation Setup - Just Use What Works

Uses the existing run_staging.py that works perfectly.
Don't overthink it.
"""

import subprocess
import sys


def main():
    """Just call the working staging script."""
    print("🏗️  Foundation Setup - Using Working Staging")
    print("=" * 50)

    try:
        # Just call the script that works
        result = subprocess.run([
            sys.executable, "orchestrator_dbt/run_staging.py"
        ], check=True)

        print("✅ Staging complete - now running foundation models...")

        # First run the required foundation models
        foundation_models = [
            "int_effective_parameters",
            "int_baseline_workforce"
        ]

        for model in foundation_models:
            print(f"   Running {model}...")
            dbt_result = subprocess.run([
                "dbt", "run", "--select", model
            ], cwd="dbt", check=True, capture_output=True)
            print(f"   ✅ {model} completed")

        print("✅ Foundation models complete - now running hazard models...")

        # Then run the 3 hazard models with simple dbt commands
        hazard_models = [
            "int_hazard_termination",
            "int_hazard_promotion",
            "int_hazard_merit"
        ]

        for model in hazard_models:
            print(f"   Running {model}...")
            dbt_result = subprocess.run([
                "dbt", "run", "--select", model
            ], cwd="dbt", check=True, capture_output=True)
            print(f"   ✅ {model} completed")

        print("✅ Foundation ready - staging + hazard models loaded successfully")
        return 0

    except subprocess.CalledProcessError as e:
        print(f"❌ Foundation failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
