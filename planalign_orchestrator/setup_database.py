#!/usr/bin/env python3
"""
Simple database setup script for PlanWise Navigator

Quick wrapper around init_database.py for common use cases.
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from planalign_orchestrator.init_database import DatabaseInitializer


def setup_fresh_database():
    """Set up a fresh database with all tables and sample data."""
    print("🚀 Setting up fresh PlanWise Navigator database...")

    initializer = DatabaseInitializer()
    success = initializer.initialize_database(fresh=True)

    if success:
        print("✅ Database setup completed successfully!")
        print(f"📍 Database location: {initializer.db_path}")
        print("\nNext steps:")
        print("1. Run a simulation: python run_multi_year.py")
        print("2. Check data: python -c \"import duckdb; print(duckdb.connect('dbt/simulation.duckdb').execute('SHOW TABLES').fetchall())\"")
    else:
        print("❌ Database setup failed. Check logs above.")
        sys.exit(1)


def validate_database():
    """Validate existing database structure."""
    print("🔍 Validating database structure...")

    initializer = DatabaseInitializer()

    try:
        with initializer.get_connection() as conn:
            success = initializer.validate_database_structure(conn)

        if success:
            print("✅ Database validation passed!")
        else:
            print("❌ Database validation failed!")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Validation error: {e}")
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
