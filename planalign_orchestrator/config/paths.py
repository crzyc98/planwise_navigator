"""Path utilities for configuration management.

E073: Config Module Refactoring - paths module.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_project_root() -> Path:
    """Get project root directory (planalign_engine/).

    Returns:
        Path: Absolute path to project root
    """
    # This file lives at planalign_orchestrator/config/paths.py
    # Project root is parent of planalign_orchestrator
    return Path(__file__).resolve().parent.parent.parent


def get_database_path() -> Path:
    """Get standardized database path with environment variable support.

    This function implements Epic E050 database standardization by:
    - Using DATABASE_PATH environment variable if set
    - Defaulting to 'dbt/simulation.duckdb' (standardized location)
    - Creating parent directory if it doesn't exist
    - Returning resolved absolute path

    Returns:
        Path: Absolute path to the simulation database
    """
    db_path = os.getenv('DATABASE_PATH', 'dbt/simulation.duckdb')
    path = Path(db_path)

    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    return path.resolve()
