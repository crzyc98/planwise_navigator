"""Data inspection module for validating dbt model outputs.

Provides functions to connect to DuckDB and validate table contents
with detailed reports and data quality checks.
"""

import pandas as pd
from typing import Optional

from ..core.config import SCHEMA_NAME
from ..core.database_manager import get_connection


def inspect_stg_census_data() -> None:
    """Inspect and validate the stg_census_data table.

    Performs the following checks:
    - Table exists in the main schema
    - Table is not empty (row count > 0)
    - No NULL values in employee_id column
    - Displays summary statistics and sample data

    Raises:
        ValueError: If any validation fails
    """
    print("\n" + "="*60)
    print("INSPECTING: stg_census_data")
    print("="*60)

    conn = get_connection()

    try:
        # Check if table exists
        table_exists_query = f"""
        SELECT COUNT(*) as table_count
        FROM information_schema.tables
        WHERE table_schema = '{SCHEMA_NAME}'
        AND table_name = 'stg_census_data'
        """

        table_count = conn.execute(table_exists_query).fetchone()[0]

        if table_count == 0:
            raise ValueError(f"Table {SCHEMA_NAME}.stg_census_data does not exist!")

        print(f"✓ Table {SCHEMA_NAME}.stg_census_data exists")

        # Get row count
        row_count_query = f"SELECT COUNT(*) as row_count FROM {SCHEMA_NAME}.stg_census_data"
        row_count = conn.execute(row_count_query).fetchone()[0]

        if row_count == 0:
            raise ValueError("Table stg_census_data is empty!")

        print(f"✓ Table contains {row_count:,} rows")

        # Check for NULL employee_ids
        null_check_query = f"""
        SELECT COUNT(*) as null_count
        FROM {SCHEMA_NAME}.stg_census_data
        WHERE employee_id IS NULL
        """

        null_count = conn.execute(null_check_query).fetchone()[0]

        if null_count > 0:
            raise ValueError(f"Found {null_count} rows with NULL employee_id!")

        print(f"✓ No NULL values in employee_id column")

        # Get column information
        column_info_query = f"""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = '{SCHEMA_NAME}'
        AND table_name = 'stg_census_data'
        ORDER BY ordinal_position
        """

        columns_df = conn.execute(column_info_query).df()

        print(f"\nTable has {len(columns_df)} columns:")
        for _, row in columns_df.iterrows():
            print(f"  - {row['column_name']}: {row['data_type']}")

        # Get sample data
        sample_query = f"""
        SELECT *
        FROM {SCHEMA_NAME}.stg_census_data
        LIMIT 5
        """

        sample_df = conn.execute(sample_query).df()

        print("\nSample data (first 5 rows):")
        print(sample_df.to_markdown(index=False))

        # Get basic statistics based on actual schema
        stats_query = f"""
        SELECT
            COUNT(DISTINCT employee_id) as unique_employees,
            COUNT(*) as total_rows,
            COUNT(DISTINCT employee_ssn) as unique_ssns,
            MIN(employee_hire_date) as earliest_hire_date,
            MAX(employee_hire_date) as latest_hire_date,
            COUNT(CASE WHEN active = true THEN 1 END) as active_employees,
            COUNT(CASE WHEN employee_termination_date IS NOT NULL THEN 1 END) as terminated_employees,
            AVG(employee_gross_compensation) as avg_compensation,
            MIN(employee_gross_compensation) as min_compensation,
            MAX(employee_gross_compensation) as max_compensation
        FROM {SCHEMA_NAME}.stg_census_data
        """

        stats = conn.execute(stats_query).fetchone()

        print("\nBasic Statistics:")
        print(f"  - Unique employees: {stats[0]:,}")
        print(f"  - Total rows: {stats[1]:,}")
        print(f"  - Unique SSNs: {stats[2]:,}")
        print(f"  - Hire date range: {stats[3]} to {stats[4]}")
        print(f"  - Active employees: {stats[5]:,}")
        print(f"  - Terminated employees: {stats[6]:,}")
        print(f"  - Avg compensation: ${stats[7]:,.2f}")
        print(f"  - Compensation range: ${stats[8]:,.2f} to ${stats[9]:,.2f}")

        print("\n✅ All validations passed for stg_census_data!")

    except Exception as e:
        print(f"\n❌ ERROR during inspection: {str(e)}")
        raise

    finally:
        conn.close()
