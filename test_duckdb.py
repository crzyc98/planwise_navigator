#!/usr/bin/env python3
"""
DuckDB Connection Test Script

This script tests the basic functionality of DuckDB by:
1. Connecting to an in-memory database
2. Executing a simple query
3. Creating a table
4. Inserting and retrieving data
"""

import duckdb

try:
    # Connect to an in-memory DuckDB database
    # You can replace ':memory:' with a file path like 'my_database.duckdb'
    con = duckdb.connect(database=":memory:", read_only=False)
    print("✅ Successfully connected to DuckDB.")

    # Execute a simple query
    result = con.execute("SELECT 'Hello, DuckDB!' AS message").fetchdf()
    print("\n📊 Query Result:")
    print(result)

    # Test creating a table and inserting data
    con.execute("CREATE TABLE my_table (id INTEGER, name VARCHAR)")
    con.execute("INSERT INTO my_table VALUES (1, 'Alice'), (2, 'Bob')")
    print("\n✅ Table created and data inserted.")

    # Query the table
    table_data = con.execute("SELECT * FROM my_table").fetchdf()
    print("\n📋 Data from my_table:")
    print(table_data)

    print("\n🎉 DuckDB setup appears to be correct!")

except Exception as e:
    print(f"\n❌ An error occurred: {e}")
    print("DuckDB setup might have issues. Please check your installation.")
    raise

finally:
    # Close the connection
    if "con" in locals():
        con.close()
        print("\n🔌 DuckDB connection closed.")
