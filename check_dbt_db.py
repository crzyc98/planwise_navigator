import duckdb
import os

# Path to the dbt database file
db_path = os.path.join(os.path.dirname(__file__), "simulation_dbt.duckdb")
print(f"Checking dbt database at: {db_path}")

# Check if database file exists
if not os.path.exists(db_path):
    print(f"Error: Database file not found at {db_path}")
    exit(1)

try:
    # Connect to the database
    con = duckdb.connect(database=db_path, read_only=True)
    print("\n=== Database Connection Successful ===")

    # List all schemas and tables
    print("\n=== All Schemas and Tables ===")
    tables = con.execute(
        """
        SELECT
            table_schema,
            table_name,
            table_type
        FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name
    """
    ).fetchall()

    if not tables:
        print("No tables found in any schema!")
    else:
        for schema, table, table_type in tables:
            print(f"Schema: {schema}, Table: {table} ({table_type})")

            # Get row count
            try:
                count = con.execute(
                    f'SELECT COUNT(*) FROM "{schema}"."{table}"'
                ).fetchone()[0]
                print(f"  Rows: {count}")

                # Show columns
                print("  Columns:")
                columns = con.execute(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = ? AND table_name = ?
                    ORDER BY ordinal_position
                """,
                    [schema, table],
                ).fetchall()

                for col_name, col_type in columns:
                    print(f"    {col_name}: {col_type}")

                # Show sample data if table is not empty
                if count > 0:
                    print("  Sample data (first 3 rows):")
                    data = con.execute(
                        f'SELECT * FROM "{schema}"."{table}" LIMIT 3'
                    ).fetchall()
                    for row in data:
                        print(f"    {row}")

            except Exception as e:
                print(f"  Error querying table: {e}")

    # List all schemas (including system schemas)
    print("\n=== All Schemas ===")
    schemas = con.execute(
        "SELECT schema_name FROM information_schema.schemata"
    ).fetchall()
    for (schema,) in schemas:
        print(f"- {schema}")

    # Check if there are any tables in the main schema
    print("\n=== Checking main schema ===")
    tables_in_main = con.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main'
    """
    ).fetchall()

    if not tables_in_main:
        print("No tables found in 'main' schema")
    else:
        print("Tables in 'main' schema:")
        for (table,) in tables_in_main:
            print(f"- {table}")

except Exception as e:
    print(f"\nError: {e}")

finally:
    if "con" in locals():
        con.close()
        print("\nDatabase connection closed")
