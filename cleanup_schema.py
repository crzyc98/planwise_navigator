import duckdb
import os

# Path to the dbt database file
db_path = os.path.join(os.path.dirname(__file__), "simulation_dbt.duckdb")
print(f"Cleaning up database at: {db_path}")

# Check if database file exists
if not os.path.exists(db_path):
    print(f"Error: Database file not found at {db_path}")
    exit(1)

try:
    # Connect to the database
    con = duckdb.connect(database=db_path, read_only=False)
    print("\n=== Database Connection Successful ===")

    # Check if main_main schema exists
    schemas = con.execute(
        "SELECT schema_name FROM information_schema.schemata"
    ).fetchall()
    schemas = [s[0] for s in schemas]

    if "main_main" in schemas:
        print("\n=== Dropping main_main schema ===")
        # Drop all tables in main_main schema first
        tables = con.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main_main'
        """
        ).fetchall()

        for (table,) in tables:
            print(f"Dropping table: main_main.{table}")
            con.execute(f'DROP TABLE IF EXISTS "main_main"."{table}"')

        # Now drop the schema
        con.execute("DROP SCHEMA IF EXISTS main_main")
        print("Dropped main_main schema")
    else:
        print("\n=== main_main schema not found, nothing to drop ===")

    # Ensure main schema exists
    if "main" not in schemas:
        print("\n=== Creating main schema ===")
        con.execute("CREATE SCHEMA IF NOT EXISTS main")
        print("Created main schema")

    print("\n=== Current schemas ===")
    schemas = con.execute(
        "SELECT schema_name FROM information_schema.schemata"
    ).fetchall()
    for (schema,) in schemas:
        print(f"- {schema}")

except Exception as e:
    print(f"\nError: {e}")

finally:
    if "con" in locals():
        con.close()
        print("\nDatabase connection closed")
