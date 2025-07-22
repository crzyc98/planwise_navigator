"""Configuration for MVP orchestrator.

Contains paths to the dbt project directory and DuckDB database file.
"""

import os
from pathlib import Path

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()

# dbt project configuration
DBT_PROJECT_DIR = PROJECT_ROOT / "dbt"

# Database configuration
DUCKDB_PATH = PROJECT_ROOT / "simulation.duckdb"

# Ensure paths exist
if not DBT_PROJECT_DIR.exists():
    raise FileNotFoundError(f"dbt project directory not found at {DBT_PROJECT_DIR}")

# Schema configuration
SCHEMA_NAME = "main"
