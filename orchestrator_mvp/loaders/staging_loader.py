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


def run_dbt_seed(seed_name: str) -> None:
    """Run a specific dbt seed using subprocess.

    Args:
        seed_name: Name of the dbt seed to run (e.g., 'config_job_levels')
    """
    print("\n" + "="*60)
    print(f"LOADING DBT SEED: {seed_name}")
    print("="*60)

    # Save current directory
    original_dir = os.getcwd()

    try:
        # Change to dbt project directory
        os.chdir(DBT_PROJECT_DIR)

        # Construct dbt command
        cmd = ["dbt", "seed", "--select", seed_name]

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
            raise RuntimeError(f"dbt seed failed with exit code {result.returncode}")

        print(f"\n✅ Successfully loaded seed {seed_name}")

    except Exception as e:
        print(f"\n❌ ERROR loading dbt seed: {str(e)}")
        raise

    finally:
        # Return to original directory
        os.chdir(original_dir)


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


def run_dbt_model_with_vars(model_name: str, vars_dict: dict) -> dict:
    """Run a specific dbt model with variable parameters.

    Args:
        model_name: Name of the dbt model to run (e.g., 'fct_workforce_snapshot')
        vars_dict: Dictionary of variables to pass to dbt (e.g., {'simulation_year': 2025})

    Returns:
        Dictionary with success status and any error messages
    """
    print("\n" + "="*60)
    print(f"RUNNING DBT MODEL WITH VARS: {model_name}")
    print(f"Variables: {vars_dict}")
    print("="*60)

    # Save current directory
    original_dir = os.getcwd()

    try:
        # Change to dbt project directory
        os.chdir(DBT_PROJECT_DIR)

        # Construct dbt command with variables
        cmd = ["dbt", "run", "--select", model_name]

        # Add variables if provided
        if vars_dict:
            vars_string = ",".join([f"{k}={v}" for k, v in vars_dict.items()])
            cmd.extend(["--vars", f"{{{vars_string}}}"])

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
            error_msg = f"dbt run failed with exit code {result.returncode}"
            print(f"\n❌ ERROR: {error_msg}")
            return {"success": False, "error": error_msg}

        print(f"\n✅ Successfully ran {model_name} with variables")
        return {"success": True}

    except Exception as e:
        error_msg = f"ERROR running dbt model with vars: {str(e)}"
        print(f"\n❌ {error_msg}")
        return {"success": False, "error": error_msg}

    finally:
        # Return to original directory
        os.chdir(original_dir)
