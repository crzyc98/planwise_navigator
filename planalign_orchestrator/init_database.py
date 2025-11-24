#!/usr/bin/env python3
"""
Database Initialization Script for PlanWise Navigator

Creates all necessary tables and seeds required for the workforce simulation system.
This script can be run standalone or imported for programmatic database setup.

Features:
- Creates all core fact and dimension tables
- Loads configuration seed data
- Validates database structure
- Supports both fresh initialization and incremental updates
- Compatible with Epic E050 database standardization

Usage:
    python -m planalign_orchestrator.init_database
    python -m planalign_orchestrator.init_database --fresh  # Drop and recreate
    python -m planalign_orchestrator.init_database --validate-only  # Check structure
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
from .config import get_database_path


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseInitializer:
    """Manages database initialization and validation for PlanWise Navigator."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize with database path (uses standard path if not provided)."""
        self.db_path = db_path or get_database_path()
        self.project_root = Path(__file__).parent.parent
        self.dbt_dir = self.project_root / "dbt"
        self.seeds_dir = self.dbt_dir / "seeds"

        logger.info(f"Database path: {self.db_path}")
        logger.info(f"Seeds directory: {self.seeds_dir}")

    def create_database_directory(self) -> None:
        """Ensure database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created database directory: {self.db_path.parent}")

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        """Get database connection with standard configuration."""
        conn = duckdb.connect(str(self.db_path))

        # Configure DuckDB for analytical workloads
        conn.execute("SET memory_limit='4GB'")
        conn.execute("SET threads=4")
        conn.execute("SET enable_progress_bar=true")

        # Install required extensions
        extensions = ['parquet', 'httpfs', 'json']
        for ext in extensions:
            try:
                conn.execute(f"INSTALL {ext}")
                conn.execute(f"LOAD {ext}")
                logger.debug(f"Loaded extension: {ext}")
            except Exception as e:
                logger.warning(f"Failed to load extension {ext}: {e}")

        return conn

    def drop_all_tables(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Drop all existing tables for fresh initialization."""
        logger.info("Dropping all existing tables...")

        # Get list of all tables
        tables = conn.execute("SHOW TABLES").fetchall()

        for table in tables:
            table_name = table[0]
            try:
                conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                logger.debug(f"Dropped table: {table_name}")
            except Exception as e:
                logger.warning(f"Failed to drop table {table_name}: {e}")

        logger.info(f"Dropped {len(tables)} tables")

    def create_staging_tables(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create staging tables for seed data."""
        logger.info("Creating staging tables...")

        # stg_census_data - Core employee data
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stg_census_data (
                employee_id VARCHAR PRIMARY KEY,
                employee_ssn VARCHAR,
                employee_first_name VARCHAR,
                employee_last_name VARCHAR,
                employee_birth_date DATE,
                employee_hire_date DATE,
                employee_enrollment_date DATE,
                employee_gross_compensation DECIMAL(10,2),
                employee_deferral_rate DECIMAL(5,4),
                level_id INTEGER,
                active BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # stg_config_job_levels - Job level configuration
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stg_config_job_levels (
                level_id INTEGER PRIMARY KEY,
                name VARCHAR,
                description VARCHAR,
                job_families VARCHAR,
                min_compensation DECIMAL(10,2),
                max_compensation DECIMAL(10,2),
                comp_base_salary DECIMAL(10,2),
                comp_age_factor DECIMAL(5,4),
                comp_stochastic_std_dev DECIMAL(5,4),
                avg_annual_merit_increase DECIMAL(5,4),
                promotion_probability DECIMAL(5,4),
                target_bonus_percent DECIMAL(5,4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # stg_comp_levers - Compensation parameter configuration
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stg_comp_levers (
                scenario_id VARCHAR,
                fiscal_year INTEGER,
                event_type VARCHAR,
                parameter_name VARCHAR,
                job_level INTEGER,
                parameter_value DECIMAL(8,6),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (scenario_id, fiscal_year, event_type, parameter_name, COALESCE(job_level, -1))
            )
        """)

        # Hazard configuration tables
        hazard_tables = [
            'stg_config_promotion_hazard_base',
            'stg_config_promotion_hazard_age_multipliers',
            'stg_config_promotion_hazard_tenure_multipliers',
            'stg_config_termination_hazard_base',
            'stg_config_termination_hazard_age_multipliers',
            'stg_config_termination_hazard_tenure_multipliers',
            'stg_config_raises_hazard'
        ]

        for table in hazard_tables:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id INTEGER PRIMARY KEY,
                    level_id INTEGER,
                    band VARCHAR,
                    rate DECIMAL(8,6),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        # IRS contribution limits
        conn.execute("""
            CREATE TABLE IF NOT EXISTS irs_contribution_limits (
                tax_year INTEGER PRIMARY KEY,
                employee_deferral_limit DECIMAL(10,2),
                catch_up_limit DECIMAL(10,2),
                catch_up_age INTEGER,
                total_limit DECIMAL(10,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Default deferral rates
        conn.execute("""
            CREATE TABLE IF NOT EXISTS default_deferral_rates (
                demographic_segment VARCHAR PRIMARY KEY,
                base_rate DECIMAL(5,4),
                description VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        logger.info("Created staging tables")

    def create_intermediate_tables(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create intermediate processing tables."""
        logger.info("Creating intermediate tables...")

        # int_baseline_workforce - Starting workforce state
        conn.execute("""
            CREATE TABLE IF NOT EXISTS int_baseline_workforce (
                employee_id VARCHAR,
                employee_ssn VARCHAR,
                simulation_year INTEGER,
                employee_birth_date DATE,
                employee_hire_date DATE,
                employee_enrollment_date DATE,
                employee_deferral_rate DECIMAL(5,4),
                is_enrolled_at_census BOOLEAN,
                current_age INTEGER,
                current_tenure DECIMAL(6,2),
                level_id INTEGER,
                current_compensation DECIMAL(10,2),
                employment_status VARCHAR,
                age_band VARCHAR,
                tenure_band VARCHAR,
                compensation_band VARCHAR,
                is_from_census BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (employee_id, simulation_year)
            )
        """)

        # int_employee_compensation_by_year - Year-aware compensation
        conn.execute("""
            CREATE TABLE IF NOT EXISTS int_employee_compensation_by_year (
                employee_id VARCHAR,
                simulation_year INTEGER,
                base_compensation DECIMAL(10,2),
                adjusted_compensation DECIMAL(10,2),
                cola_adjustment DECIMAL(10,2),
                merit_adjustment DECIMAL(10,2),
                promotion_adjustment DECIMAL(10,2),
                total_adjustment DECIMAL(10,2),
                level_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (employee_id, simulation_year)
            )
        """)

        # int_workforce_needs - Workforce planning calculations
        conn.execute("""
            CREATE TABLE IF NOT EXISTS int_workforce_needs (
                simulation_year INTEGER PRIMARY KEY,
                starting_workforce_count INTEGER,
                target_workforce_count INTEGER,
                experienced_terminations INTEGER,
                expected_new_hire_terminations INTEGER,
                total_hires_needed INTEGER,
                target_growth_rate DECIMAL(5,4),
                new_hire_termination_rate DECIMAL(5,4),
                balance_status VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # int_deferral_rate_state_accumulator_v2 - Deferral rate state management
        conn.execute("""
            CREATE TABLE IF NOT EXISTS int_deferral_rate_state_accumulator_v2 (
                scenario_id VARCHAR,
                plan_design_id VARCHAR,
                employee_id VARCHAR,
                simulation_year INTEGER,
                as_of_month INTEGER,
                current_deferral_rate DECIMAL(5,4),
                rate_source VARCHAR,
                last_escalation_date DATE,
                escalation_eligible BOOLEAN,
                enrollment_date DATE,
                data_quality_flag VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (scenario_id, plan_design_id, employee_id, simulation_year, as_of_month)
            )
        """)

        # int_employee_contributions - Employee contribution calculations
        conn.execute("""
            CREATE TABLE IF NOT EXISTS int_employee_contributions (
                employee_id VARCHAR,
                simulation_year INTEGER,
                annual_compensation DECIMAL(10,2),
                final_deferral_rate DECIMAL(5,4),
                requested_contribution_amount DECIMAL(10,2),
                annual_contribution_amount DECIMAL(10,2),
                applicable_irs_limit DECIMAL(10,2),
                irs_limit_applied BOOLEAN,
                amount_capped_by_irs_limit DECIMAL(10,2),
                limit_type VARCHAR,
                current_age INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (employee_id, simulation_year)
            )
        """)

        logger.info("Created intermediate tables")

    def create_fact_tables(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create fact tables for final data marts."""
        logger.info("Creating fact tables...")

        # fct_yearly_events - Core event stream
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fct_yearly_events (
                employee_id VARCHAR,
                employee_ssn VARCHAR,
                event_type VARCHAR,
                simulation_year INTEGER,
                effective_date DATE,
                event_details VARCHAR,
                compensation_amount DECIMAL(10,2),
                previous_compensation DECIMAL(10,2),
                employee_deferral_rate DECIMAL(5,4),
                prev_employee_deferral_rate DECIMAL(5,4),
                employee_age INTEGER,
                employee_tenure DECIMAL(6,2),
                level_id INTEGER,
                age_band VARCHAR,
                tenure_band VARCHAR,
                compensation_band VARCHAR,
                event_sequence INTEGER,
                random_seed INTEGER,
                parameter_scenario_id VARCHAR,
                parameter_source VARCHAR,
                data_quality_flag VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # fct_workforce_snapshot - Point-in-time workforce state
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fct_workforce_snapshot (
                employee_id VARCHAR,
                employee_ssn VARCHAR,
                simulation_year INTEGER,
                employee_birth_date DATE,
                employee_hire_date DATE,
                enrollment_date DATE,
                current_age INTEGER,
                current_tenure DECIMAL(6,2),
                level_id INTEGER,
                current_compensation DECIMAL(10,2),
                employment_status VARCHAR,
                enrollment_status VARCHAR,
                current_deferral_rate DECIMAL(5,4),
                annual_deferral_contribution DECIMAL(10,2),
                annual_employer_match DECIMAL(10,2),
                annual_employer_core_contribution DECIMAL(10,2),
                age_band VARCHAR,
                tenure_band VARCHAR,
                compensation_band VARCHAR,
                data_quality_flag VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (employee_id, simulation_year)
            )
        """)

        # fct_compensation_growth - Compensation analytics
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fct_compensation_growth (
                simulation_year INTEGER,
                level_id INTEGER,
                avg_starting_compensation DECIMAL(10,2),
                avg_ending_compensation DECIMAL(10,2),
                total_cola_given DECIMAL(12,2),
                total_merit_given DECIMAL(12,2),
                total_promotion_adjustments DECIMAL(12,2),
                employee_count INTEGER,
                growth_rate DECIMAL(6,4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (simulation_year, level_id)
            )
        """)

        logger.info("Created fact tables")

    def create_dimension_tables(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create dimension tables for lookups."""
        logger.info("Creating dimension tables...")

        # dim_hazard_table - Risk probability lookup
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dim_hazard_table (
                event_type VARCHAR,
                level_id INTEGER,
                age_band VARCHAR,
                tenure_band VARCHAR,
                base_rate DECIMAL(8,6),
                age_multiplier DECIMAL(6,4),
                tenure_multiplier DECIMAL(6,4),
                final_rate DECIMAL(8,6),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (event_type, level_id, age_band, tenure_band)
            )
        """)

        logger.info("Created dimension tables")

    def load_seed_data(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Load seed data from CSV files."""
        logger.info("Loading seed data...")

        if not self.seeds_dir.exists():
            logger.warning(f"Seeds directory not found: {self.seeds_dir}")
            return

        # Mapping of CSV files to table names
        seed_mappings = {
            'config_job_levels.csv': 'stg_config_job_levels',
            'comp_levers.csv': 'stg_comp_levers',
            'irs_contribution_limits.csv': 'irs_contribution_limits',
            'default_deferral_rates.csv': 'default_deferral_rates',
            'config_promotion_hazard_base.csv': 'stg_config_promotion_hazard_base',
            'config_promotion_hazard_age_multipliers.csv': 'stg_config_promotion_hazard_age_multipliers',
            'config_promotion_hazard_tenure_multipliers.csv': 'stg_config_promotion_hazard_tenure_multipliers',
            'config_termination_hazard_base.csv': 'stg_config_termination_hazard_base',
            'config_termination_hazard_age_multipliers.csv': 'stg_config_termination_hazard_age_multipliers',
            'config_termination_hazard_tenure_multipliers.csv': 'stg_config_termination_hazard_tenure_multipliers',
            'config_raises_hazard.csv': 'stg_config_raises_hazard'
        }

        for csv_file, table_name in seed_mappings.items():
            csv_path = self.seeds_dir / csv_file

            if not csv_path.exists():
                logger.warning(f"Seed file not found: {csv_path}")
                continue

            try:
                # Use DuckDB's efficient CSV reading
                conn.execute(f"""
                    INSERT INTO {table_name}
                    SELECT * FROM read_csv_auto('{csv_path}')
                """)

                # Get row count for logging
                count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                logger.info(f"Loaded {count} rows into {table_name}")

            except Exception as e:
                logger.error(f"Failed to load {csv_file} into {table_name}: {e}")

    def create_sample_census_data(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create sample census data if none exists."""
        logger.info("Creating sample census data...")

        # Check if census data already exists
        count = conn.execute("SELECT COUNT(*) FROM stg_census_data").fetchone()[0]
        if count > 0:
            logger.info(f"Census data already exists ({count} employees)")
            return

        # Create sample employees
        conn.execute("""
            INSERT INTO stg_census_data (
                employee_id, employee_ssn, employee_first_name, employee_last_name,
                employee_birth_date, employee_hire_date, employee_enrollment_date,
                employee_gross_compensation, employee_deferral_rate, level_id, active
            )
            WITH sample_employees AS (
                SELECT
                    'EMP_' || LPAD(generate_series::VARCHAR, 6, '0') as employee_id,
                    '000-00-' || LPAD(generate_series::VARCHAR, 4, '0') as employee_ssn,
                    'Employee' as employee_first_name,
                    'Test_' || generate_series as employee_last_name,
                    DATE '1970-01-01' + INTERVAL (20 + (generate_series % 40)) YEAR as employee_birth_date,
                    DATE '2020-01-01' + INTERVAL (generate_series % 1460) DAY as employee_hire_date,
                    CASE WHEN generate_series % 3 = 0 THEN
                        DATE '2020-01-01' + INTERVAL (generate_series % 1460 + 30) DAY
                        ELSE NULL END as employee_enrollment_date,
                    50000 + (generate_series % 200000) as employee_gross_compensation,
                    CASE WHEN generate_series % 3 = 0 THEN
                        0.03 + (generate_series % 15) * 0.005
                        ELSE 0 END as employee_deferral_rate,
                    1 + (generate_series % 5) as level_id,
                    true as active
                FROM generate_series(1, 1000)
            )
            SELECT * FROM sample_employees
        """)

        count = conn.execute("SELECT COUNT(*) FROM stg_census_data").fetchone()[0]
        logger.info(f"Created {count} sample employees")

    def validate_database_structure(self, conn: duckdb.DuckDBPyConnection) -> bool:
        """Validate that all required tables exist and have data."""
        logger.info("Validating database structure...")

        required_tables = [
            'stg_census_data',
            'stg_config_job_levels',
            'stg_comp_levers',
            'int_baseline_workforce',
            'fct_yearly_events',
            'fct_workforce_snapshot'
        ]

        validation_passed = True

        for table in required_tables:
            try:
                # Check table exists
                result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                count = result[0] if result else 0

                if count > 0:
                    logger.info(f"✅ {table}: {count} rows")
                else:
                    logger.warning(f"⚠️  {table}: Empty table")

            except Exception as e:
                logger.error(f"❌ {table}: Table missing or invalid - {e}")
                validation_passed = False

        # Validate table schemas
        try:
            # Check fct_yearly_events has required columns
            columns = conn.execute("DESCRIBE fct_yearly_events").fetchall()
            required_columns = {'employee_id', 'event_type', 'simulation_year', 'effective_date'}
            existing_columns = {col[0] for col in columns}

            if required_columns.issubset(existing_columns):
                logger.info("✅ fct_yearly_events schema valid")
            else:
                missing = required_columns - existing_columns
                logger.error(f"❌ fct_yearly_events missing columns: {missing}")
                validation_passed = False

        except Exception as e:
            logger.error(f"❌ Schema validation failed: {e}")
            validation_passed = False

        if validation_passed:
            logger.info("✅ Database validation passed")
        else:
            logger.error("❌ Database validation failed")

        return validation_passed

    def initialize_database(self, fresh: bool = False) -> bool:
        """Initialize complete database structure."""
        logger.info("Starting database initialization...")

        try:
            # Create database directory
            self.create_database_directory()

            # Get connection
            with self.get_connection() as conn:
                if fresh:
                    self.drop_all_tables(conn)

                # Create all table structures
                self.create_staging_tables(conn)
                self.create_intermediate_tables(conn)
                self.create_fact_tables(conn)
                self.create_dimension_tables(conn)

                # Load seed data
                self.load_seed_data(conn)

                # Create sample data if needed
                self.create_sample_census_data(conn)

                # Validate structure
                success = self.validate_database_structure(conn)

                if success:
                    logger.info("✅ Database initialization completed successfully")
                else:
                    logger.error("❌ Database initialization completed with errors")

                return success

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False


def main():
    """Command-line interface for database initialization."""
    parser = argparse.ArgumentParser(
        description="Initialize PlanWise Navigator database"
    )
    parser.add_argument(
        '--fresh',
        action='store_true',
        help='Drop and recreate all tables'
    )
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only validate existing database structure'
    )
    parser.add_argument(
        '--db-path',
        type=Path,
        help='Override database path (default: uses standardized path)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Initialize database manager
    initializer = DatabaseInitializer(args.db_path)

    try:
        if args.validate_only:
            # Validation only mode
            with initializer.get_connection() as conn:
                success = initializer.validate_database_structure(conn)
        else:
            # Full initialization
            success = initializer.initialize_database(fresh=args.fresh)

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.info("Initialization cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
