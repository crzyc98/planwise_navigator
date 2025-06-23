import duckdb
import os

# Path to the local database file
db_path = os.path.join(os.path.dirname(__file__), "simulation.duckdb")
print(f"Checking local database at: {db_path}")

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
    query = """
    SELECT
        table_schema,
        table_name,
        table_type
    FROM information_schema.tables
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY table_schema, table_name
    """

    tables = con.execute(query).fetchall()

    if not tables:
        print("No tables found in any schema!")
    else:
        for schema, table, table_type in tables:
            print(f"Schema: {schema}, Table: {table} ({table_type})")

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
