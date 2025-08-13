#!/usr/bin/env python3
"""Debug script to test navigator_orchestrator components"""

import subprocess
import sys
from pathlib import Path
import shutil

print("=== NAVIGATOR ORCHESTRATOR DEBUG ===\n")

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

db_file = Path("simulation.duckdb")
print(f"   simulation.duckdb exists: {db_file.exists()}")
print()

# 3. Test basic dbt command
print("3. TESTING DBT DIRECTLY:")
try:
    result = subprocess.run(
        ["dbt", "--version"],
        capture_output=True,
        text=True,
        cwd=dbt_dir if dbt_dir.exists() else None
    )
    print(f"   dbt --version return code: {result.returncode}")
    if result.stdout:
        print(f"   stdout: {result.stdout[:200]}")
    if result.stderr:
        print(f"   stderr: {result.stderr[:200]}")
except Exception as e:
    print(f"   ERROR: {e}")
print()

# 4. Test DbtRunner
print("4. TESTING DbtRunner:")
try:
    from navigator_orchestrator.dbt_runner import DbtRunner
    runner = DbtRunner(verbose=True)
    print(f"   DbtRunner working_dir: {runner.working_dir.absolute()}")
    print(f"   DbtRunner executable: {runner.executable}")

    # Try a simple dbt command
    print("\n   Attempting 'dbt --version' through DbtRunner...")
    result = runner.execute_command(
        ["--version"],
        description="Testing dbt version",
        stream_output=False,
        retry=False
    )
    print(f"   Success: {result.success}")
    print(f"   Return code: {result.return_code}")
    if not result.success:
        print(f"   stdout: {result.stdout[:400] if result.stdout else 'None'}")
        print(f"   stderr: {result.stderr[:400] if result.stderr else 'None'}")

except Exception as e:
    print(f"   ERROR importing/running DbtRunner: {e}")
    import traceback
    traceback.print_exc()
print()

# 5. Test with explicit paths
print("5. TESTING WITH EXPLICIT DBT PATH:")
try:
    dbt_path = shutil.which('dbt')
    if dbt_path:
        from navigator_orchestrator.dbt_runner import DbtRunner
        runner = DbtRunner(executable=dbt_path, verbose=True)
        print(f"   Using explicit dbt: {dbt_path}")
        result = runner.execute_command(
            ["--version"],
            description="Testing with explicit path",
            stream_output=False,
            retry=False
        )
        print(f"   Success: {result.success}")
        if not result.success:
            print(f"   Full stdout: {result.stdout}")
except Exception as e:
    print(f"   ERROR: {e}")

print("\n=== END DEBUG ===")
