#!/usr/bin/env python3
"""Enhanced debug script for navigator orchestrator"""

import shutil
import subprocess
import sys
from pathlib import Path
from navigator_orchestrator.config import get_database_path

print("=== NAVIGATOR ORCHESTRATOR ENHANCED DEBUG ===\n")

# 1. Check Python and paths
print("1. ENVIRONMENT CHECK:")
print(f"   Python: {sys.executable}")
print(f"   Current dir: {Path.cwd()}")
print(f"   dbt executable: {shutil.which('dbt')}")
print()

# 2. Check directory structure
print("2. DIRECTORY STRUCTURE:")
dbt_dir = Path("dbt")
print(f"   dbt/ exists: {dbt_dir.exists()}")
if dbt_dir.exists():
    print(f"   dbt/ absolute: {dbt_dir.absolute()}")
    print(f"   dbt_project.yml exists: {(dbt_dir / 'dbt_project.yml').exists()}")

db_file = get_database_path()
print(f"   simulation.duckdb exists: {db_file.exists()}")
print()

# 3. Test a simple dbt run directly
print("3. TESTING DBT RUN DIRECTLY:")
try:
    result = subprocess.run(
        [
            "dbt",
            "run",
            "--select",
            "stg_census_data",
            "--vars",
            '{"simulation_year": 2025}',
        ],
        capture_output=True,
        text=True,
        cwd=Path("dbt"),
    )
    print(f"   Direct dbt run return code: {result.returncode}")
    if result.returncode != 0:
        print(f"   ERROR output: {result.stderr[:500]}")
        print(f"   STDOUT: {result.stdout[:500]}")
    else:
        print(f"   SUCCESS: Direct dbt run worked")
except Exception as e:
    print(f"   ERROR: {e}")
print()

# 4. Test DbtRunner with --version (fixed)
print("4. TESTING DbtRunner --version:")
try:
    from navigator_orchestrator.dbt_runner import DbtRunner

    runner = DbtRunner(verbose=True)
    print(f"   DbtRunner working_dir: {runner.working_dir.absolute()}")
    print(f"   DbtRunner executable: {runner.executable}")

    # Test --version (should work now with the fix)
    result = runner.execute_command(
        ["--version"],
        description="Testing dbt version",
        stream_output=False,
        retry=False,
    )
    print(f"   Success: {result.success}")
    print(f"   Return code: {result.return_code}")
    if not result.success:
        print(f"   Command: {' '.join(result.command)}")
        print(f"   stdout: {result.stdout[:400] if result.stdout else 'None'}")
        print(f"   stderr: {result.stderr[:400] if result.stderr else 'None'}")
except Exception as e:
    print(f"   ERROR: {e}")
    import traceback

    traceback.print_exc()
print()

# 5. Test DbtRunner with a simple model
print("5. TESTING DbtRunner WITH SIMPLE MODEL:")
try:
    from navigator_orchestrator.dbt_runner import DbtRunner

    runner = DbtRunner(verbose=True)

    # Test run_model method
    result = runner.run_model(
        "stg_census_data",
        simulation_year=2025,
        description="Testing single model",
        stream_output=False,
        retry=False,
    )
    print(f"   run_model success: {result.success}")
    print(f"   Return code: {result.return_code}")
    if not result.success:
        print(f"   Command: {' '.join(result.command)}")
        print(f"   Error stdout: {result.stdout[:500]}")
        print(f"   Error stderr: {result.stderr[:500]}")
    else:
        print(f"   SUCCESS: Single model run worked")
except Exception as e:
    print(f"   ERROR: {e}")
    import traceback

    traceback.print_exc()
print()

# 6. Test the full pipeline initialization
print("6. TESTING PIPELINE INITIALIZATION:")
try:
    from navigator_orchestrator.config import load_simulation_config
    from navigator_orchestrator.pipeline import PipelineOrchestrator
    from navigator_orchestrator.registries import RegistryManager
    from navigator_orchestrator.utils import DatabaseConnectionManager
    from navigator_orchestrator.validation import DataValidator

    config = load_simulation_config(Path("config/simulation_config.yaml"))
    print(f"   Config loaded: start_year={config.simulation.start_year}")

    db = DatabaseConnectionManager(get_database_path())
    print(f"   Database connected: {db.db_path}")

    runner = DbtRunner(verbose=True)
    print(f"   DbtRunner created")

    registries = RegistryManager(db)
    print(f"   RegistryManager created")

    validator = DataValidator(db)
    print(f"   DataValidator created")

    orch = PipelineOrchestrator(config, db, runner, registries, validator, verbose=True)
    print(f"   PipelineOrchestrator created successfully")

except Exception as e:
    print(f"   ERROR during initialization: {e}")
    import traceback

    traceback.print_exc()
print()

# 7. Test running the first stage
print("7. TESTING FIRST STAGE EXECUTION:")
try:
    if "orch" in locals():
        # Get the first stage
        stages = orch._define_year_workflow(2025)
        first_stage = stages[0]
        print(f"   First stage: {first_stage.name.value}")
        print(f"   Models to run: {first_stage.models}")

        # Try to run just the first model
        if first_stage.models:
            model = first_stage.models[0]
            print(f"\n   Testing model: {model}")
            result = runner.run_model(
                model,
                simulation_year=2025,
                dbt_vars=orch._dbt_vars,
                stream_output=False,
                retry=False,
            )
            print(f"   Success: {result.success}")
            if not result.success:
                print(f"   Full command: {' '.join(result.command)}")
                print(f"   Full stdout:\n{result.stdout}")
                print(f"   Full stderr:\n{result.stderr}")
            else:
                print(f"   SUCCESS: First stage model worked")
    else:
        print("   Pipeline not initialized, skipping stage test")
except Exception as e:
    print(f"   ERROR: {e}")
    import traceback

    traceback.print_exc()

print("\n=== END ENHANCED DEBUG ===")
