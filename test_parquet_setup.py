#!/usr/bin/env python3
"""Test script to verify Parquet extension setup works correctly."""

import pandas as pd
import tempfile
import os
from pathlib import Path

def test_duckdb_resource():
    """Test the DuckDBResource with Parquet functionality."""
    print("Testing DuckDBResource...")

    from orchestrator.resources.duckdb_resource import DuckDBResource

    # Test in-memory connection
    resource = DuckDBResource()
    conn = resource.get_connection()

    try:
        # Create test data
        conn.execute("CREATE TABLE test_data AS SELECT 1 as id, 'Alice' as name UNION SELECT 2, 'Bob'")

        # Export to parquet (in temp location)
        with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
            tmp_path = tmp.name

        try:
            conn.execute(f"COPY test_data TO '{tmp_path}' (FORMAT PARQUET)")
            print("✅ Created Parquet file successfully")

            # Read it back
            result = conn.execute(f"SELECT * FROM '{tmp_path}'").df()
            print("✅ Read Parquet file successfully")
            print(f"   Data: {result.to_dict('records')}")

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        print(f"❌ DuckDBResource test failed: {e}")
        return False
    finally:
        conn.close()

    print("✅ DuckDBResource test passed")
    return True

def test_pandas_parquet():
    """Test creating a Parquet file with pandas and reading with DuckDB."""
    print("\nTesting pandas → Parquet → DuckDB workflow...")

    from orchestrator.resources.duckdb_resource import DuckDBResource

    # Create test data with pandas
    df = pd.DataFrame({
        'employee_id': [1, 2, 3],
        'name': ['Alice', 'Bob', 'Charlie'],
        'salary': [50000, 60000, 55000]
    })

    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Write with pandas
        df.to_parquet(tmp_path, index=False)
        print("✅ Created Parquet file with pandas")

        # Read with DuckDB
        resource = DuckDBResource()
        conn = resource.get_connection()

        try:
            result = conn.execute(f"SELECT * FROM '{tmp_path}' ORDER BY employee_id").df()
            print("✅ Read Parquet file with DuckDB")
            print(f"   Data: {result.to_dict('records')}")

            # Test some analytics
            avg_salary = conn.execute(f"SELECT AVG(salary) as avg_salary FROM '{tmp_path}'").fetchone()[0]
            print(f"✅ Analytics work: Average salary = ${avg_salary:,.0f}")

        finally:
            conn.close()

    except Exception as e:
        print(f"❌ Pandas→DuckDB test failed: {e}")
        return False
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    print("✅ Pandas→DuckDB test passed")
    return True

if __name__ == "__main__":
    print("🧪 Testing PlanWise Navigator Parquet setup...\n")

    test1_passed = test_duckdb_resource()
    test2_passed = test_pandas_parquet()

    if test1_passed and test2_passed:
        print("\n🎉 All tests passed! Parquet extension is working correctly.")
        print("\nYou can now:")
        print("- Use DuckDBResource in your Dagster assets")
        print("- Read/write Parquet files in your pipelines")
        print("- Run dbt models that work with Parquet data")
    else:
        print("\n❌ Some tests failed. Check the output above for details.")
