#!/usr/bin/env python3
"""
Simple database setup script for PlanWise Navigator

Quick wrapper around init_database.py for common use cases.
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from planalign_orchestrator.init_database import DatabaseInitializer


def setup_fresh_database():
    """Set up a fresh database with all tables and sample data."""
    logger.info("Setting up fresh PlanWise Navigator database...")

    initializer = DatabaseInitializer()
    success = initializer.initialize_database(fresh=True)

    if success:
        logger.info("Database setup completed successfully!")
        logger.info("Database location: %s", initializer.db_path)
        logger.info("Next steps:")
        logger.info("1. Run a simulation: python run_multi_year.py")
        logger.info("2. Check data: python -c \"import duckdb; print(duckdb.connect('dbt/simulation.duckdb').execute('SHOW TABLES').fetchall())\"")
    else:
        logger.error("Database setup failed. Check logs above.")
        sys.exit(1)


def validate_database():
    """Validate existing database structure."""
    logger.info("Validating database structure...")

    initializer = DatabaseInitializer()

    try:
        with initializer.get_connection() as conn:
            success = initializer.validate_database_structure(conn)

        if success:
            logger.info("Database validation passed!")
        else:
            logger.error("Database validation failed!")
            sys.exit(1)

    except Exception as e:
        logger.error("Validation error: %s", e, exc_info=True)
        sys.exit(1)


def main():
    """Interactive setup menu."""
    print("PlanWise Navigator Database Setup")
    print("=================================")
    print()
    print("1. Setup fresh database (drops existing tables)")
    print("2. Validate existing database")
    print("3. Exit")
    print()

    choice = input("Enter your choice (1-3): ").strip()

    if choice == "1":
        setup_fresh_database()
    elif choice == "2":
        validate_database()
    elif choice == "3":
        print("Goodbye!")
    else:
        print("Invalid choice. Please enter 1, 2, or 3.")
        sys.exit(1)


if __name__ == "__main__":
    main()
