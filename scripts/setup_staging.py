#!/usr/bin/env python3
"""
Simple Staging Setup Script

Does exactly what it says: sets up staging tables and nothing more.
No fancy orchestration, no multi-year nonsense, just basic staging setup.

Usage:
    python scripts/setup_staging.py
"""

import subprocess
import sys
import time
from pathlib import Path

def run_command(cmd, description):
    """Run a command and return success/failure."""
    print(f"🔧 {description}...")

    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed:")
        print(f"   stdout: {e.stdout}")
        print(f"   stderr: {e.stderr}")
        return False

def main():
    """Main function - just do staging setup."""
    print("🚀 Simple Staging Setup")
    print("=" * 50)

    start_time = time.time()

    # Change to dbt directory
    dbt_dir = Path(__file__).parent.parent / "dbt"
    if not dbt_dir.exists():
        print(f"❌ dbt directory not found: {dbt_dir}")
        return 1

    print(f"📁 Working in: {dbt_dir}")

    # Commands to run
    commands = [
        (f"cd {dbt_dir} && dbt seed", "Load seed files"),
        (f"cd {dbt_dir} && dbt run --models staging", "Run staging models"),
    ]

    # Run each command
    for cmd, desc in commands:
        if not run_command(cmd, desc):
            print(f"\n💥 Setup failed at: {desc}")
            return 1

    # Success
    total_time = time.time() - start_time
    print("\n" + "=" * 50)
    print(f"🎉 Staging setup completed successfully in {total_time:.1f}s")

    # Show what we created
    check_cmd = f"cd {dbt_dir} && duckdb ../simulation.duckdb -c \"SELECT COUNT(*) as tables FROM information_schema.tables WHERE table_name LIKE 'stg_%';\""
    try:
        result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"📊 Staging tables created: {result.stdout.strip()}")
    except:
        pass

    return 0

if __name__ == "__main__":
    sys.exit(main())
