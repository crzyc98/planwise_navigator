"""Staging data loading operations.

Handles running dbt staging models and related operations.
"""

import os
import subprocess
from pathlib import Path

from ..core.config import DBT_PROJECT_DIR


def run_dbt_model(model_name: str) -> None:
    """Run a specific dbt model using subprocess.

    Args:
        model_name: Name of the dbt model to run (e.g., 'stg_census_data')
    """
    print("\n" + "="*60)
    print(f"RUNNING DBT MODEL: {model_name}")
    print("="*60)

    # Save current directory
    original_dir = os.getcwd()

    try:
        # Change to dbt project directory
        os.chdir(DBT_PROJECT_DIR)

        # Construct dbt command
        cmd = ["dbt", "run", "--select", model_name]

        print(f"\nExecuting command: {' '.join(cmd)}")
        print(f"Working directory: {DBT_PROJECT_DIR}")
        print("-" * 40)

        # Run dbt command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )

        # Print output
        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)

        if result.returncode != 0:
            raise RuntimeError(f"dbt run failed with exit code {result.returncode}")

        print(f"\n✅ Successfully ran {model_name}")

    except Exception as e:
        print(f"\n❌ ERROR running dbt model: {str(e)}")
        raise

    finally:
        # Return to original directory
        os.chdir(original_dir)


def run_staging_models() -> None:
    """Run all staging models in sequence."""
    staging_models = [
        "stg_census_data",
        # Add other staging models here as needed
    ]

    print("\n" + "="*60)
    print("RUNNING ALL STAGING MODELS")
    print("="*60)

    for model in staging_models:
        try:
            run_dbt_model(model)
        except Exception as e:
            print(f"\n❌ Failed to run {model}: {str(e)}")
            raise


def run_dbt_command(command_args: list) -> None:
    """Run a custom dbt command with arbitrary arguments.

    Args:
        command_args: List of command arguments (e.g., ['test', '--select', 'stg_census_data'])
    """
    # Save current directory
    original_dir = os.getcwd()

    try:
        # Change to dbt project directory
        os.chdir(DBT_PROJECT_DIR)

        # Construct full command
        cmd = ["dbt"] + command_args

        print(f"\nExecuting command: {' '.join(cmd)}")
        print(f"Working directory: {DBT_PROJECT_DIR}")
        print("-" * 40)

        # Run command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )

        # Print output
        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)

        if result.returncode != 0:
            raise RuntimeError(f"dbt command failed with exit code {result.returncode}")

        print(f"\n✅ Successfully executed: {' '.join(cmd)}")

    except Exception as e:
        print(f"\n❌ ERROR running dbt command: {str(e)}")
        raise

    finally:
        # Return to original directory
        os.chdir(original_dir)
