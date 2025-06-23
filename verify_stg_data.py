import duckdb

database_path = "simulation.duckdb"

try:
    con = duckdb.connect(database=database_path, read_only=True)
    print(f"Connected to {database_path}")

    # List tables/views to confirm 'stg_census_data' exists
    tables = con.execute("SHOW TABLES").fetchdf()
    print("\nTables/Views in database:")
    print(tables)

    # Query the view to see the data
    df_stg = con.execute("SELECT * FROM stg_census_data LIMIT 10").fetchdf()
    print("\nSample data from stg_census_data:")
    print(df_stg)

    # You can also run a count to see the total number of records
    count = con.execute("SELECT COUNT(*) FROM stg_census_data").fetchone()[0]
    print(f"\nTotal records in stg_census_data: {count}")

except Exception as e:
    print(f"Error verifying stg_census_data: {e}")
finally:
    if "con" in locals():
        con.close()
    print("\nDuckDB connection closed.")
